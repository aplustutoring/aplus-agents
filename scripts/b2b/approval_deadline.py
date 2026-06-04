"""Monday 7 AM PT approval-deadline check (decision #5).

Reads state/topic-queue.json for the pending approval, polls the Slack message
for reactions and thread replies, and resolves the slate-level approval. The
slate is all 3 topics together (Mon=slot 1, Wed=slot 2, Fri=slot 3 per #7).

Approval signals:
  :white_check_mark: reaction  → slate approved by that user (decision #4:
                                  whoever sees it first wins)
  Thread reply `EDIT N: ...`   → swap slot N headline with the replacement
  Thread reply `SKIP N`        → mark slot N skipped (no publish that day)

If no :white_check_mark: by deadline, auto-approve the slate and DM Roman
(decision #5). Edits and skips collected from the thread are always applied,
whether the slate was approved early or auto-approved at deadline.

Idempotent: re-running after a terminal status (approved / auto_approved) is
a noop.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "shared"))
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "b2b"))

import requests
from dotenv import load_dotenv

from state import (
    append_history_run,
    read_topic_queue,
    write_topic_queue,
)

load_dotenv(override=True)

logger = logging.getLogger(__name__)

SLACK_BASE = "https://slack.com/api"
APPROVE_EMOJI = "white_check_mark"
TERMINAL_STATUSES = {"approved", "auto_approved"}

import re
EDIT_PATTERN = re.compile(r"^EDIT\s*(\d):\s*(.+)$", re.IGNORECASE | re.DOTALL)
SKIP_PATTERN = re.compile(r"^SKIP\s*(\d)\s*$", re.IGNORECASE | re.MULTILINE)


def _slack_token() -> str:
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    return tok


def _slack(method: str, endpoint: str, **kwargs) -> dict:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_slack_token()}"
    r = requests.request(
        method, f"{SLACK_BASE}/{endpoint}", headers=headers, timeout=30, **kwargs
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack API error on {endpoint}: {body.get('error', body)}")
    return body


# ---------- approval signal detection ----------

def fetch_reactions(channel: str, ts: str) -> dict[str, list[str]]:
    """Return {emoji_name: [user_ids]} for the message."""
    body = _slack("GET", "reactions.get", params={"channel": channel, "timestamp": ts})
    message = (body.get("message") or {})
    reactions = message.get("reactions", []) or []
    return {r["name"]: list(r.get("users", [])) for r in reactions}


def fetch_thread_replies(channel: str, ts: str) -> list[dict]:
    body = _slack(
        "GET", "conversations.replies",
        params={"channel": channel, "ts": ts, "limit": 100},
    )
    messages = body.get("messages", []) or []
    # Slack returns the parent message as messages[0]; drop it.
    return [m for m in messages if m.get("ts") != ts]


def detect_approver(reactions: dict[str, list[str]]) -> Optional[str]:
    """Return the first user who reacted :white_check_mark:, or None."""
    users = reactions.get(APPROVE_EMOJI, [])
    return users[0] if users else None


def collect_edits_and_skips(replies: list[dict]) -> tuple[dict[int, str], set[int]]:
    """Walk thread replies and pull out per-slot edits and skip directives.

    Last EDIT N wins (so Danielle can correct a typo by re-replying).
    Any SKIP N anywhere in any reply marks that slot as skipped.
    """
    edits: dict[int, str] = {}
    skips: set[int] = set()
    for msg in replies:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        for skip_match in SKIP_PATTERN.finditer(text):
            slot = int(skip_match.group(1))
            if 1 <= slot <= 3:
                skips.add(slot)
        edit_match = EDIT_PATTERN.match(text)
        if edit_match:
            slot = int(edit_match.group(1))
            replacement = edit_match.group(2).strip()
            if 1 <= slot <= 3 and replacement:
                edits[slot] = replacement
    return edits, skips


# ---------- DM Roman ----------

def dm_roman_if_configured(message: str) -> bool:
    """Open a DM with Roman and post the message. Returns True if sent."""
    roman_id = os.environ.get("ROMAN_SLACK_USER_ID")
    if not roman_id:
        logger.warning("ROMAN_SLACK_USER_ID not set; skipping auto-approve DM")
        return False
    try:
        open_resp = _slack("POST", "conversations.open", json={"users": roman_id})
        dm_channel = open_resp.get("channel", {}).get("id")
        if not dm_channel:
            logger.warning("conversations.open returned no channel id")
            return False
        _slack("POST", "chat.postMessage", json={"channel": dm_channel, "text": message})
        return True
    except Exception as e:
        logger.exception("DM to Roman failed: %s", e)
        return False


# ---------- main resolution ----------

def resolve_approval(dry_run: bool = False) -> dict:
    queue = read_topic_queue()
    if not queue.slack or not queue.approval:
        return {"status": "skipped", "reason": "no slack/approval block in queue"}

    current_status = queue.approval.get("status")
    if current_status in TERMINAL_STATUSES:
        logger.info("approval already terminal: %s — nothing to do", current_status)
        return {"status": "noop", "current": current_status}

    channel = queue.slack["channel_id"]
    ts = queue.slack["message_ts"]
    logger.info("checking approval for channel=%s ts=%s", channel, ts)

    reactions = fetch_reactions(channel, ts)
    replies = fetch_thread_replies(channel, ts)
    logger.info(
        "approval_signals reactions=%s thread_replies=%d",
        list(reactions.keys()), len(replies),
    )

    approver = detect_approver(reactions)
    edits, skips = collect_edits_and_skips(replies)
    now_iso = datetime.now().astimezone().isoformat()

    if approver is not None:
        status = "approved"
        approved_by = approver
        resolution = "reaction"
    else:
        status = "auto_approved"
        approved_by = "auto"
        resolution = "auto_at_deadline"

    # Apply edits to the queue.topics list (mutates the slot's headline; keep the
    # original headline in an `original_headline` field for traceability).
    topics = list(queue.topics or [])
    for slot, new_headline in edits.items():
        idx = slot - 1
        if 0 <= idx < len(topics):
            t = dict(topics[idx])
            t.setdefault("original_headline", t.get("headline"))
            t["headline"] = new_headline
            t["edited"] = True
            topics[idx] = t

    # Mark skips
    for slot in skips:
        idx = slot - 1
        if 0 <= idx < len(topics):
            t = dict(topics[idx])
            t["skipped"] = True
            topics[idx] = t

    result = {
        "status": status,
        "approved_by": approved_by,
        "approved_at": now_iso,
        "edits": {str(k): v for k, v in edits.items()},
        "skips": sorted(list(skips)),
        "resolution": resolution,
    }

    if status == "auto_approved" and not dry_run:
        slate = "\n".join(
            f"  • Slot {i + 1} ({'SKIP' if topics[i].get('skipped') else 'publish'}): "
            f"{topics[i].get('headline', '(missing)')[:80]}"
            for i in range(min(3, len(topics)))
        )
        dm_roman_if_configured(
            f":robot_face: Monday 7 AM auto-approve fired — slate going to publish.\n"
            f"{slate}\n"
            f"Reply in the original thread to override before Mon 8 AM publish."
        )

    if dry_run:
        return {"dry_run": True, "topics_after_edits": topics, **result}

    queue.topics = topics
    queue.approval = {k: v for k, v in result.items() if k != "resolution"}
    write_topic_queue(queue)

    append_history_run({
        "ts": now_iso,
        "kind": "approval_deadline",
        "week": queue.current_week,
        **result,
    })

    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Monday 7 AM approval-deadline check")
    p.add_argument("--dry-run", action="store_true", help="don't write state or DM Roman")
    args = p.parse_args()
    try:
        result = resolve_approval(dry_run=args.dry_run)
    except Exception as e:
        logger.exception("approval_deadline_failed: %s", e)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _self_test() -> None:
    """Pure-function tests for the parsers (no API calls)."""
    # detect_approver
    assert detect_approver({}) is None
    assert detect_approver({"thumbsup": ["U1"]}) is None
    assert detect_approver({"white_check_mark": []}) is None
    assert detect_approver({"white_check_mark": ["U1", "U2"]}) == "U1"

    # collect_edits_and_skips
    replies = [
        {"text": "EDIT 2: New corrected headline for slot two"},
        {"text": "SKIP 3"},
        {"text": "Just a random reply, no command here"},
        {"text": "edit 1: lowercase prefix should still match"},
    ]
    edits, skips = collect_edits_and_skips(replies)
    assert edits == {1: "lowercase prefix should still match", 2: "New corrected headline for slot two"}, edits
    assert skips == {3}, skips

    # Re-edit replaces (last wins)
    replies2 = [
        {"text": "EDIT 1: first attempt"},
        {"text": "EDIT 1: corrected version"},
    ]
    edits2, _ = collect_edits_and_skips(replies2)
    assert edits2 == {1: "corrected version"}, edits2

    # Out-of-range slot rejected
    replies3 = [{"text": "EDIT 9: too high"}, {"text": "SKIP 0"}]
    edits3, skips3 = collect_edits_and_skips(replies3)
    assert edits3 == {} and skips3 == set()

    print("approval_deadline parser tests PASSED")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
        sys.exit(0)
    sys.exit(main())
