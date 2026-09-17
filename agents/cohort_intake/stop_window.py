"""The 15-minute stop window (spec §5.2, DRAFT): post the plan to the agent
channel, mention the approvers, wait, and continue unless someone replied
`stop` in the thread. Fails CLOSED: if the replies cannot be read (missing
scope, API error) the run does not proceed, because a stop window that
cannot hear "stop" is not a stop window. --wait-minutes 0 skips it (the
human already reviewed the dry run).
"""
from __future__ import annotations

import time

import requests

from ._bootstrap import DRY_RUN, agent_cfg, slack_client, staff
from src.config import SLACK_BOT_TOKEN  # noqa: E402

STOP_WORDS = ("stop", "halt", "cancel", "wait")


def _mentions() -> str:
    ids = [(staff(seat) or {}).get("slack_user_id") for seat in agent_cfg()["slack"]["summary_to"]]
    return " ".join(f"<@{u}>" for u in ids if u)


def _replies(channel: str, ts: str) -> list[dict] | None:
    r = requests.get("https://slack.com/api/conversations.replies",
                     headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                     params={"channel": channel, "ts": ts, "limit": 100}, timeout=20)
    data = r.json()
    if not data.get("ok"):
        print(f"  ⚠️  conversations.replies: {data.get('error')}")
        return None
    return [m for m in data.get("messages", []) if m.get("ts") != ts]


def said_stop(messages: list[dict]) -> str | None:
    for m in messages:
        text = (m.get("text") or "").strip().lower()
        if any(text == w or text.startswith(w + " ") or text.startswith(w + "!") for w in STOP_WORDS):
            return m.get("user") or "someone"
    return None


def hold(summary: str, minutes: float, poll_seconds: int = 30) -> tuple[bool, str]:
    """(proceed, why). Posts the summary and waits `minutes` for a stop."""
    sc = agent_cfg()["slack"]
    text = (f"{_mentions()} {summary}\n\n⏱ Executing in {minutes:g} min unless someone replies "
            f"*stop* in this thread.")
    if DRY_RUN:
        print(f"[DRY_RUN] stop window skipped ({minutes:g} min): would post to {sc['channel']}")
        return True, "dry run"
    if minutes <= 0:
        slack_client.post_message(sc["channel"], f"{_mentions()} {summary}\n\n▶️ Executing now (no wait).")
        return True, "no wait requested"
    res = slack_client.post_message(sc["channel"], text)
    ts, channel = res.get("ts"), res.get("channel") or sc["channel"]
    if not res.get("ok") or not ts:
        return False, f"could not post the stop-window message ({res.get('error')})"
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(min(poll_seconds, max(1, deadline - time.time())))
        msgs = _replies(channel, ts)
        if msgs is None:
            return False, "cannot read thread replies (scope?); not proceeding blind"
        who = said_stop(msgs)
        if who:
            slack_client.post_message(sc["channel"], f"🛑 Stopped by <@{who}>. Nothing written.")
            return False, f"stopped by {who}"
    slack_client.post_message(sc["channel"], "▶️ No stop in the window; executing.")
    return True, "window elapsed"
