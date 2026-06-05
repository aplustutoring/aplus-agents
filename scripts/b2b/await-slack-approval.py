#!/usr/bin/env python3
"""Poll the current Slack topic approval thread and update topic queue state."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "b2b"))

from state import append_history_run, read_topic_queue, topic_queue_transaction
from lens_runs import Topic, generate_slot_candidates, lens_for_slot
from skills_runner import SkillsRunner

SLACK_BASE = "https://slack.com/api"
APPROVE_EMOJIS = {"white_check_mark", "white_check_mark_v1", "white_check_mark_v2", "heavy_check_mark"}
TARGET_SCHOOLS_PATH = REPO_ROOT / "skills" / "aplus-research" / "target-schools.md"
CANDIDATE_LABELS = ["A", "B", "C"]

EDIT_PATTERN = re.compile(r"^EDIT\s*([1-3])\s*:\s*(.+)$", re.IGNORECASE)
SKIP_PATTERN = re.compile(r"^SKIP\s*([1-3])\s*$", re.IGNORECASE)
APPROVE_PATTERN = re.compile(r"^APPROVE\s*$", re.IGNORECASE)
DENY_PATTERN = re.compile(r"^DENY\s*$", re.IGNORECASE)
REDO_PATTERN = re.compile(r"^REDO\s*([1-3])\s*$", re.IGNORECASE)
PICK_PATTERN = re.compile(r"^PICK\s*([1-3])\s*:\s*([ABC])\s*$", re.IGNORECASE)


def _load_context() -> str:
    if TARGET_SCHOOLS_PATH.is_file():
        return TARGET_SCHOOLS_PATH.read_text(encoding="utf-8")
    return "(No target-schools.md present; HOT 13 list unavailable for this run.)"


def _slack_token() -> str:
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    return tok


def _slack(method: str, endpoint: str, **kwargs: Any) -> dict:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_slack_token()}"
    r = requests.request(method, f"{SLACK_BASE}/{endpoint}", headers=headers, timeout=30, **kwargs)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack API error on {endpoint}: {body.get('error', body)}")
    return body


def fetch_reactions(channel: str, ts: str) -> dict[str, list[str]]:
    body = _slack("GET", "reactions.get", params={"channel": channel, "timestamp": ts})
    message = body.get("message") or {}
    reactions = message.get("reactions") or []
    return {r["name"]: list(r.get("users", [])) for r in reactions}


def fetch_thread_replies(channel: str, ts: str) -> list[dict]:
    body = _slack(
        "GET",
        "conversations.replies",
        params={"channel": channel, "ts": ts, "limit": 200},
    )
    messages = body.get("messages") or []
    return [m for m in messages if m.get("ts") != ts]


def post_thread_reply(channel: str, parent_ts: str, text: str) -> None:
    _slack(
        "POST",
        "chat.postMessage",
        json={"channel": channel, "text": text, "thread_ts": parent_ts, "mrkdwn": True},
    )


def parse_reply_commands(text: str) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        if DENY_PATTERN.match(raw):
            commands.append({"type": "deny"})
            continue
        if APPROVE_PATTERN.match(raw):
            commands.append({"type": "approve"})
            continue
        skip_match = SKIP_PATTERN.match(raw)
        if skip_match:
            commands.append({"type": "skip", "slot": int(skip_match.group(1))})
            continue
        redo_match = REDO_PATTERN.match(raw)
        if redo_match:
            commands.append({"type": "redo", "slot": int(redo_match.group(1))})
            continue
        pick_match = PICK_PATTERN.match(raw)
        if pick_match:
            commands.append(
                {"type": "pick", "slot": int(pick_match.group(1)), "label": pick_match.group(2).upper()}
            )
            continue
        edit_match = EDIT_PATTERN.match(raw)
        if edit_match:
            commands.append(
                {
                    "type": "edit",
                    "slot": int(edit_match.group(1)),
                    "headline": edit_match.group(2).strip(),
                }
            )
    return commands


def collect_new_commands(replies: list[dict], processed_reply_ts: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    commands: list[dict[str, Any]] = []
    new_ts: list[str] = []
    for msg in sorted(replies, key=lambda m: m.get("ts", "")):
        ts = msg.get("ts")
        if not ts or ts in processed_reply_ts:
            continue
        if msg.get("bot_id"):
            continue
        text = msg.get("text", "")
        user = msg.get("user") or msg.get("username") or "unknown"
        parsed = parse_reply_commands(text)
        if parsed:
            for command in parsed:
                command["ts"] = ts
                command["user"] = user
                commands.append(command)
            new_ts.append(ts)
    return commands, new_ts


def find_reaction_approver(reactions: dict[str, list[str]]) -> str | None:
    for name in APPROVE_EMOJIS:
        users = reactions.get(name, [])
        if users:
            return users[0]
    return None


def summarize_changes(changes: dict[str, Any]) -> str:
    lines: list[str] = []
    for slot, edit in changes.get("edits", {}).items():
        lines.append(
            f":pencil2: Slot {slot} headline updated by {edit['user']}. Type `APPROVE` to confirm the slate."
        )
    for skip in changes.get("skips", []):
        lines.append(
            f":no_entry_sign: Slot {skip['slot']} skipped by {skip['user']}. No blog will publish that day. Type `APPROVE` to confirm the slate."
        )
    for pick in changes.get("picks", []):
        lines.append(
            f":point_right: Slot {pick['slot']} set to option {pick['label']} by {pick['user']}: {pick['headline']}. Type `APPROVE` to confirm the slate."
        )
    for err in changes.get("pick_errors", []):
        lines.append(
            f":warning: No candidates to pick for slot {err['slot']} — run `REDO {err['slot']}` first, then `PICK {err['slot']}: A`."
        )
    if changes.get("denied"):
        lines.append(
            f":x: Slate denied by {changes['denied_by']}. No blogs publish this week. Topic-gen will retry next Thursday."
        )
    elif changes.get("approved"):
        by = changes.get("approved_by")
        who = f"<@{by}>" if by and by != "auto" else "the slate"
        lines.append(
            f":white_check_mark: *Got it, {who} — approval received and locked.* "
            f"All 3 topics are confirmed. I'll build the blogs into HubSpot drafts this weekend and "
            f"post a summary with the draft links right here on Monday. Nothing else needed from you. :rocket:"
        )
    return "\n".join(lines)


def ensure_topic_slots(topics: list[dict], slot: int) -> None:
    while len(topics) < slot:
        topics.append(
            {
                "slot": len(topics) + 1,
                "lens": "unknown",
                "lens_status": "failed",
                "headline": "",
                "category": "",
                "sources": [],
                "why_matters": "",
                "angle": "",
                "roman_take": "",
                "danielle_take": "",
                "skipped": False,
            }
        )


def format_candidates_reply(slot: int, candidates: list[dict]) -> str:
    lines = [f":arrows_counterclockwise: *Slot {slot} regenerated — pick one:*"]
    for c in candidates:
        cat = f"  _({c['category']})_" if c.get("category") else ""
        lines.append(f"*{c['label']})* {c['headline']}{cat}")
    lines.append(f"Reply `PICK {slot}: A` (or B/C) to choose — or `EDIT {slot}: your own headline`.")
    return "\n".join(lines)


def _topic_to_candidate(label: str, t: Topic) -> dict:
    return {
        "label": label,
        "headline": t.headline,
        "category": t.category,
        "sources": list(t.sources),
        "why_matters": t.why_matters,
        "angle": t.angle,
        "roman_take": t.roman_take,
        "danielle_take": t.danielle_take,
    }


def process_redos(queue: Any, redo_cmds: list[dict[str, Any]], channel: str, parent_ts: str, *, dry_run: bool) -> list[dict]:
    """Regenerate 3 candidates for each REDO'd slot, store them on the slot, and
    post the choices to the thread. Needs ANTHROPIC_API_KEY (the lens uses web search)."""
    if not redo_cmds:
        return []
    if queue.topics is None:
        queue.topics = []

    redone: list[dict] = []
    runner: Optional[SkillsRunner] = None
    context: Optional[str] = None

    for cmd in redo_cmds:
        slot = cmd["slot"]
        user = cmd.get("user", "unknown")
        ensure_topic_slots(queue.topics, slot)
        existing_lens = (queue.topics[slot - 1] or {}).get("lens")
        lens = lens_for_slot(slot, existing_lens)

        if dry_run:
            redone.append({"slot": slot, "user": user, "count": 0, "dry_run": True})
            continue

        if runner is None:
            runner = SkillsRunner()
            context = _load_context()
        topics = generate_slot_candidates(lens, runner, context, n=len(CANDIDATE_LABELS))
        if not topics:
            post_thread_reply(
                channel, parent_ts,
                f":warning: Slot {slot} regeneration produced no candidates — try `REDO {slot}` again "
                f"or `EDIT {slot}: your own headline`.",
            )
            redone.append({"slot": slot, "user": user, "count": 0})
            continue

        candidates = [_topic_to_candidate(CANDIDATE_LABELS[i], t) for i, t in enumerate(topics[: len(CANDIDATE_LABELS)])]
        topic = dict(queue.topics[slot - 1])
        topic["lens"] = lens.name
        topic["candidates"] = candidates
        topic["lens_status"] = "awaiting_pick"
        topic["redo_by"] = user
        queue.topics[slot - 1] = topic
        post_thread_reply(channel, parent_ts, format_candidates_reply(slot, candidates))
        redone.append({"slot": slot, "user": user, "count": len(candidates)})

    return redone


def apply_commands_to_queue(queue: Any, commands: list[dict[str, Any]], reaction_approver: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "approved": False,
        "approved_by": None,
        "denied": False,
        "denied_by": None,
        "edits": {},
        "skips": [],
        "picks": [],
        "pick_errors": [],
    }

    if queue.topics is None:
        queue.topics = []

    for command in commands:
        if command["type"] == "deny":
            result["denied"] = True
            result["denied_by"] = command["user"]
            result["approved"] = False
            result["approved_by"] = None
        elif command["type"] == "approve" and not result["denied"]:
            result["approved"] = True
            result["approved_by"] = command["user"]
        elif command["type"] == "edit":
            slot = command["slot"]
            headline = command["headline"]
            ensure_topic_slots(queue.topics, slot)
            topic = dict(queue.topics[slot - 1])
            topic["headline"] = headline
            topic["edited_by"] = command["user"]
            topic["edited_note"] = headline
            topic["lens_status"] = "ok"
            queue.topics[slot - 1] = topic
            result["edits"][slot] = {"user": command["user"], "headline": headline}
        elif command["type"] == "skip":
            slot = command["slot"]
            ensure_topic_slots(queue.topics, slot)
            topic = dict(queue.topics[slot - 1])
            topic["skipped"] = True
            queue.topics[slot - 1] = topic
            result["skips"].append({"slot": slot, "user": command["user"]})
        elif command["type"] == "pick":
            slot = command["slot"]
            label = command["label"]
            ensure_topic_slots(queue.topics, slot)
            topic = dict(queue.topics[slot - 1])
            chosen = next((c for c in (topic.get("candidates") or []) if (c.get("label") or "").upper() == label), None)
            if chosen is None:
                result["pick_errors"].append({"slot": slot, "label": label, "user": command["user"]})
            else:
                for k in ("headline", "category", "sources", "why_matters", "angle", "roman_take", "danielle_take"):
                    if k in chosen:
                        topic[k] = chosen[k]
                topic["lens_status"] = "ok"
                topic["skipped"] = False
                topic["picked_label"] = label
                topic["picked_by"] = command["user"]
                topic.pop("candidates", None)
                topic.pop("redo_by", None)
                queue.topics[slot - 1] = topic
                result["picks"].append({"slot": slot, "label": label, "headline": chosen.get("headline", ""), "user": command["user"]})

    if reaction_approver and not result["denied"]:
        result["approved"] = True
        result["approved_by"] = reaction_approver

    if result["approved"] and not result["denied"]:
        queue.approval = {
            "status": "approved",
            "approved_by": result["approved_by"],
            "approved_at": datetime.now().astimezone().isoformat(),
            "denied_by": None,
            "denied_at": None,
            "edit_note": None,
        }
    elif result["denied"]:
        queue.approval = {
            "status": "denied",
            "approved_by": None,
            "approved_at": None,
            "denied_by": result["denied_by"],
            "denied_at": datetime.now().astimezone().isoformat(),
            "edit_note": "DENY",
        }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll Slack approval thread and update topic queue state")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing state or posting confirmations")
    args = parser.parse_args()

    if not os.environ.get("SLACK_BOT_TOKEN"):
        print("ERROR: SLACK_BOT_TOKEN not set", file=sys.stderr)
        return 3

    queue = read_topic_queue()
    if not queue.slack or not queue.approval:
        print("no pending topic approval state found", file=sys.stderr)
        return 0

    if queue.approval.get("status") != "pending":
        print(f"approval status is terminal ({queue.approval.get('status')}); nothing to do", file=sys.stderr)
        return 0

    channel = queue.slack.get("channel_id")
    parent_ts = queue.slack.get("message_ts")
    if not channel or not parent_ts:
        print("missing slack channel/message ts in state", file=sys.stderr)
        return 3

    processed_reply_ts = set(queue.slack.get("processed_reply_ts") or [])
    reactions = fetch_reactions(channel, parent_ts)
    replies = fetch_thread_replies(channel, parent_ts)
    commands, new_reply_ts = collect_new_commands(replies, processed_reply_ts)
    reaction_approver = find_reaction_approver(reactions)

    if not commands and not reaction_approver:
        print("no new approval commands or reactions found", file=sys.stderr)
        return 0

    redo_cmds = [c for c in commands if c["type"] == "redo"]
    other_cmds = [c for c in commands if c["type"] != "redo"]

    # REDO regenerates candidates (web-searched lens call) + posts choices; must run
    # before any same-cycle PICK so the candidates exist on the slot.
    redone = process_redos(queue, redo_cmds, channel, parent_ts, dry_run=args.dry_run)
    changes = apply_commands_to_queue(queue, other_cmds, reaction_approver)
    changes["redos"] = redone

    if not (changes["edits"] or changes["skips"] or changes["picks"] or changes["pick_errors"]
            or changes["approved"] or changes["denied"] or redone):
        print("no actionable changes found in new replies", file=sys.stderr)
        return 0

    summary = summarize_changes(changes)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "commands": commands, "summary": summary, "redos": redone}, indent=2))
        return 0

    with topic_queue_transaction() as transaction_queue:
        transaction_queue.topics = queue.topics
        transaction_queue.slack = dict(queue.slack)
        transaction_queue.slack["processed_reply_ts"] = sorted(set(processed_reply_ts).union(new_reply_ts))
        transaction_queue.approval = queue.approval

    append_history_run({
        "ts": datetime.now().astimezone().isoformat(),
        "kind": "await_slack_approval",
        "week": queue.current_week,
        "changes": {
            "approved": changes["approved"],
            "approved_by": changes.get("approved_by"),
            "denied": changes["denied"],
            "denied_by": changes.get("denied_by"),
            "edits": changes["edits"],
            "skips": [s["slot"] for s in changes["skips"]],
            "picks": [{"slot": p["slot"], "label": p["label"]} for p in changes["picks"]],
            "redos": [{"slot": r["slot"], "count": r["count"]} for r in redone],
        },
    })

    if summary:
        post_thread_reply(channel, parent_ts, summary)
    print(json.dumps({"status": "updated", "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
