#!/usr/bin/env python3
"""Warn when a credential in knowledge/credentials.yml is nearing expiry (#AP044).

NEVER REMEDIATES. It warns and exits; it does not edit copy, flip public_ready,
or touch any file. A credential going stale is a decision for a human (renew,
retire the claim, or update the term), and an agent silently rewriting customer
language is exactly the failure mode the fleet's never-remediates rule exists
to prevent.

Exit codes follow the fleet's exit-code rule: 0 = ran fine (with or without a
warning), 1 = could not do its job.

    python3 scripts/credential_expiry_check.py                 # report only
    python3 scripts/credential_expiry_check.py --slack         # + Slack warning
    python3 scripts/credential_expiry_check.py --window-days 180
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import credentials as C  # noqa: E402

DEFAULT_WINDOW = 180
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("CREDENTIAL_ALERT_CHANNEL", "")


def post_slack(text: str) -> bool:
    if not (SLACK_BOT_TOKEN and SLACK_CHANNEL):
        print("  (no SLACK_BOT_TOKEN / CREDENTIAL_ALERT_CHANNEL — not posting)")
        return False
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                               "Content-Type": "application/json"},
                      json={"channel": SLACK_CHANNEL, "text": text}, timeout=20)
    ok = r.ok and r.json().get("ok")
    print(f"  slack -> {'posted' if ok else r.text[:200]}")
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW)
    ap.add_argument("--slack", action="store_true")
    ap.add_argument("--today", default="", help="override today (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    try:
        creds = (C._load().get("credentials") or {})
    except FileNotFoundError:
        print(f"ERROR: {C.CREDENTIALS_PATH} not found", file=sys.stderr)
        return 1
    if not creds:
        print(f"ERROR: no credentials declared in {C.CREDENTIALS_PATH}", file=sys.stderr)
        return 1

    warnings = []
    for cid, c in creds.items():
        left = C.days_until_expiry(cid, today)
        name = c.get("name", cid)
        if left is None:
            print(f"  {cid}: no expires_on set — cannot check")
            continue
        state = "EXPIRED" if left < 0 else ("WARN" if left <= args.window_days else "ok")
        confirmed = "" if c.get("expires_on_confirmed") else "  [expiry date UNCONFIRMED]"
        print(f"  {cid}: {left} days ({c.get('expires_on')}) [{state}]{confirmed}")
        if state == "ok":
            continue
        if left < 0:
            warnings.append(
                f":rotating_light: *{name}* EXPIRED {abs(left)} days ago "
                f"({c.get('expires_on')}).\n"
                f"The claim `{c.get('claim_string')}` is no longer true and is still "
                f"declared in `knowledge/credentials.yml`.\n"
                f"Renew it, or set `public_ready: false` and remove the claim from live surfaces. "
                f"Nothing has been changed automatically.")
        else:
            warnings.append(
                f":hourglass_flowing_sand: *{name}* expires in *{left} days* "
                f"({c.get('expires_on')}).\n"
                f"Claim in use: `{c.get('claim_string')}`\n"
                f"Start the renewal, or plan to retire the claim. "
                f"Nothing has been changed automatically.")

    if not warnings:
        print("no credentials within the warning window.")
        return 0

    body = "*Credential expiry warning* (`#AP044`, read-only check)\n\n" + "\n\n".join(warnings)
    print("\n" + body)
    if args.slack:
        post_slack(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
