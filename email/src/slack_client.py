"""Slack bot client (DMs to owners + channel posts).

Uses the Slack Web API with a bot token (chat:write, im:write, users:read).
Modeled on aplus-marketing-skills' _slack_call(). DMs go to a member id (Uxxxx);
chat.postMessage accepts a user id as `channel` to open/post the IM.
"""
from __future__ import annotations

import requests

from .config import DRY_RUN, SLACK_BOT_TOKEN, SLACK_USER_TOKEN_VISIONARY

API = "https://slack.com/api"


# Seats that can speak in their own voice. Only the visionary today; a seat
# without a user token falls back to the bot so a missing secret never silences
# a pester, it only changes who it appears to come from.
USER_TOKENS = {"visionary": lambda: SLACK_USER_TOKEN_VISIONARY}


def user_token_for(role: str | None) -> str:
    return (USER_TOKENS.get(role or "") or (lambda: ""))()


def _call(endpoint: str, payload: dict, token: str | None = None) -> dict:
    r = requests.post(
        f"{API}/{endpoint}",
        headers={"Authorization": f"Bearer {token or SLACK_BOT_TOKEN}"},
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


def dm(user_id: str, text: str, as_role: str | None = None) -> dict:
    """Direct-message a Slack user by member id. With `as_role` set to a seat
    that has a user token (see USER_TOKENS), the message is posted BY that
    person, so it lands in their DM with the recipient as if they typed it.
    No token for the seat → bot DM, with a warning so the gap is visible."""
    if not user_id:
        print(f"    ⚠️  no slack_user_id; skipping DM: {text}")
        return {"ok": False, "error": "no_user_id"}
    if as_role:
        tok = user_token_for(as_role)
        if tok:
            if DRY_RUN:
                print(f"[DRY_RUN] slack (as {as_role}) → {user_id}: {text}")
                return {"ok": True, "dry_run": True, "as_role": as_role}
            return _call("chat.postMessage",
                         {"channel": user_id, "text": text, "unfurl_links": False}, token=tok)
        print(f"    ⚠️  no user token for seat '{as_role}'; DM goes out as the bot")
    return post_message(user_id, text)
