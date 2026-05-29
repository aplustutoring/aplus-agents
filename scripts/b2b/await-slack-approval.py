#!/usr/bin/env python3
"""
Post an approval question to a Slack channel, poll the thread for the first
human reply, and return the decision via stdout + exit code.

Used as a gate inside the weekly content pipeline. Replaces a "stop and wait
for chat input" stop gate with a "stop and wait for Slack thread reply" gate.

Recognized reply patterns (case-insensitive, first reply wins):
  - "approve" / "yes" / "✅" / "go" / single letter "a" — use the default/
    recommended option
  - single letter "b" through "z" — pick that lettered option
  - "kill" / "stop" / "no" — abort the run
  - anything else — keep polling

Exit codes:
  0 — approved (decision printed on stdout)
  1 — killed by reviewer (decision printed: "KILL")
  2 — timeout
  3 — error

Usage:
    python3 scripts/b2b/await-slack-approval.py \\
        --channel C0B4K9K0162 \\
        --title "Topic approval needed - May 18 weekly bundle" \\
        --options-file aplus-content/2026-05-18-weekly/approval-options.txt \\
        --default A \\
        --timeout-min 30
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ.get("SLACK_BOT_TOKEN")


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def post_message(channel, text):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={**auth_headers(), "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": text, "mrkdwn": True},
        timeout=30,
    )
    d = r.json()
    return d


def get_replies(channel, parent_ts):
    r = requests.get(
        "https://slack.com/api/conversations.replies",
        headers=auth_headers(),
        params={"channel": channel, "ts": parent_ts, "limit": 50},
        timeout=30,
    )
    return r.json()


def post_thread_reply(channel, parent_ts, text):
    requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={**auth_headers(), "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": text, "thread_ts": parent_ts, "mrkdwn": True},
        timeout=30,
    )


def parse_decision(text, default_letter):
    """Map a free-form reply to a decision.

    Returns one of:
      ("approve", letter)  — use this letter for downstream
      ("kill", None)
      None — unrecognized; keep waiting
    """
    t = text.strip().lower()
    # Strip surrounding markdown/punctuation
    t = t.strip(".,!?:;'\"`*_ ")

    if t in ("approve", "yes", "y", "go", "ship", "ok", "okay", ":white_check_mark:", "✅"):
        return ("approve", default_letter)
    if t in ("kill", "stop", "no", "abort", ":x:", "❌"):
        return ("kill", None)
    # Single-letter answer (any letter from a-z)
    if len(t) == 1 and "a" <= t <= "z":
        return ("approve", t.upper())
    # Pattern like "topic b" or "go with b"
    for token in t.split():
        if len(token) == 1 and "a" <= token <= "z":
            return ("approve", token.upper())
    return None


def main():
    parser = argparse.ArgumentParser(description="Post a Slack approval question and await reply")
    parser.add_argument("--channel", required=True, help="Slack channel ID or name")
    parser.add_argument("--title", required=True, help="Headline of the approval message")
    parser.add_argument("--options-file", help="File containing the options block (markdown)")
    parser.add_argument("--default", default="A", help="Default letter if reply is 'approve'")
    parser.add_argument("--timeout-min", type=int, default=30, help="Poll timeout in minutes")
    parser.add_argument("--poll-seconds", type=int, default=15, help="Poll interval")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set in .env", file=sys.stderr)
        return 3

    # Build the message body
    options_block = ""
    if args.options_file:
        p = Path(args.options_file)
        if not p.exists():
            print(f"ERROR: options file not found: {p}", file=sys.stderr)
            return 3
        options_block = p.read_text().strip()

    instruction = (
        f"\n*To approve:* reply in this thread.\n"
        f"  • `approve` (or `{args.default.lower()}`) -> use recommended option *{args.default}*\n"
        f"  • single letter (e.g., `b`) -> pick that option\n"
        f"  • `kill` -> abort the run"
    )

    body = f"*{args.title}*\n\n{options_block}\n{instruction}"
    print(f"Posting approval message to {args.channel}...", file=sys.stderr)

    resp = post_message(args.channel, body)
    if not resp.get("ok"):
        print(f"ERROR posting: {resp}", file=sys.stderr)
        return 3
    parent_ts = resp["ts"]
    channel_id_resolved = resp.get("channel", args.channel)
    print(f"  parent_ts: {parent_ts}", file=sys.stderr)
    print(f"  channel_id: {channel_id_resolved}", file=sys.stderr)

    deadline = time.time() + (args.timeout_min * 60)
    last_count = 0
    print(f"Polling for thread reply (timeout {args.timeout_min} min, every {args.poll_seconds}s)...", file=sys.stderr)

    while time.time() < deadline:
        d = get_replies(channel_id_resolved, parent_ts)
        if not d.get("ok"):
            print(f"WARN replies fetch failed: {d.get('error')}", file=sys.stderr)
        else:
            msgs = [m for m in d.get("messages", []) if m.get("ts") != parent_ts]
            # Skip bot's own messages (replies posted by us as confirmation)
            human_msgs = [m for m in msgs if not m.get("bot_id")]
            if len(human_msgs) > last_count:
                last_count = len(human_msgs)
                # Look at the most recent human reply
                latest = human_msgs[-1]
                text = latest.get("text", "")
                user = latest.get("user", "?")
                print(f"  reply from {user}: {text!r}", file=sys.stderr)
                decision = parse_decision(text, args.default)
                if decision is None:
                    # Confirm we didn't understand; keep polling
                    post_thread_reply(
                        channel_id_resolved, parent_ts,
                        f":thinking_face: Didn't understand `{text}`. Reply `approve`, a letter, or `kill`."
                    )
                    continue
                action, letter = decision
                if action == "kill":
                    post_thread_reply(channel_id_resolved, parent_ts, ":octagonal_sign: Run aborted by reviewer.")
                    print("KILL", flush=True)
                    return 1
                if action == "approve":
                    post_thread_reply(
                        channel_id_resolved, parent_ts,
                        f":white_check_mark: Approved. Continuing with topic *{letter}*."
                    )
                    print(letter, flush=True)  # this is the decision returned to caller
                    return 0
        time.sleep(args.poll_seconds)

    post_thread_reply(
        channel_id_resolved, parent_ts,
        f":clock1: Timed out after {args.timeout_min} minutes with no approval. Run not started."
    )
    print("TIMEOUT", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
