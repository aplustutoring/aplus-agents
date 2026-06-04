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
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "b2b"))

from state import append_history_run, read_topic_queue, topic_queue_transaction

SLACK_BASE = "https://slack.com/api"
APPROVE_EMOJIS = {"white_check_mark", "white_check_mark_v1", "white_check_mark_v2", "heavy_check_mark"}

EDIT_PATTERN = re.compile(r"^EDIT\s*([1-3])\s*:\s*(.+)$", re.IGNORECASE)
SKIP_PATTERN = re.compile(r"^SKIP\s*([1-3])\s*$", re.IGNORECASE)
APPROVE_PATTERN = re.compile(r"^APPROVE\s*$", re.IGNORECASE)
DENY_PATTERN = re.compile(r"^DENY\s*$", re.IGNORECASE)


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
    if changes.get("denied"):
        lines.append(
            f":x: Slate denied by {changes['denied_by']}. No blogs publish this week. Topic-gen will retry next Thursday."
        )
    elif changes.get("approved"):
        lines.append(
            f":white_check_mark: Slate approved by {changes['approved_by']}. Blogs publish Mon/Wed/Fri at 8am."
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


def apply_commands_to_queue(queue: Any, commands: list[dict[str, Any]], reaction_approver: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "approved": False,
        "approved_by": None,
        "denied": False,
        "denied_by": None,
        "edits": {},
        "skips": [],
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

    changes = apply_commands_to_queue(queue, commands, reaction_approver)
    if not changes["edits"] and not changes["skips"] and not changes["approved"] and not changes["denied"]:
        print("no actionable changes found in new replies", file=sys.stderr)
        return 0

    summary = summarize_changes(changes)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "commands": commands, "summary": summary}, indent=2))
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
        },
    })

    if summary:
        post_thread_reply(channel, parent_ts, summary)
    print(json.dumps({"status": "updated", "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
