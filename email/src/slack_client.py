"""Slack bot client (DMs to owners + channel posts).

Uses the Slack Web API with a bot token (chat:write, im:write, users:read).
Modeled on aplus-marketing-skills' _slack_call(). DMs go to a member id (Uxxxx);
chat.postMessage accepts a user id as `channel` to open/post the IM.
"""
from __future__ import annotations

import requests

from .config import DRY_RUN, SLACK_BOT_TOKEN

API = "https://slack.com/api"


def _call(endpoint: str, payload: dict) -> dict:
    r = requests.post(
        f"{API}/{endpoint}",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        json=payload,
        timeout=20,
    )
    data = r.json()
    if not data.get("ok"):
        print(f"    ⚠️  Slack {endpoint} error: {data.get('error')}")
    return data


def post_message(channel: str, text: str) -> dict:
    """Post to a channel (#name or Cxxxx) or DM a user id (Uxxxx)."""
    if DRY_RUN:
        print(f"[DRY_RUN] slack → {channel}: {text}")
        return {"ok": True, "dry_run": True}
    if not SLACK_BOT_TOKEN:
        print(f"    ⚠️  SLACK_BOT_TOKEN unset; skipping post to {channel}")
        return {"ok": False, "error": "no_token"}
    return _call("chat.postMessage", {"channel": channel, "text": text, "unfurl_links": False})


def dm(user_id: str, text: str) -> dict:
    """Direct-message a Slack user by member id."""
    if not user_id:
        print(f"    ⚠️  no slack_user_id; skipping DM: {text}")
        return {"ok": False, "error": "no_user_id"}
    return post_message(user_id, text)
