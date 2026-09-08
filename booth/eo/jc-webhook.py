#!/usr/bin/env python3
"""Register the booth's inbound-SMS webhook on JustCall.

Additive only: the account's existing call.completed (Zapier) and call.missed
(HubSpot) webhooks are never read back, modified, or deleted.

The webhook fires for inbound SMS on EVERY number on the account, not just
the booth line — JustCall scopes by event type, not by number. The Worker's
/sms handler guards on the destination number and no-ops for anything that
did not land on the booth line, so main-line traffic is unaffected.

    JUSTCALL_API_KEY=... JUSTCALL_API_SECRET=... python3 booth/eo/jc-webhook.py [--create]
"""
import json
import os
import sys
import urllib.error
import urllib.request

KEY = os.environ.get("JUSTCALL_API_KEY")
SEC = os.environ.get("JUSTCALL_API_SECRET")
if not (KEY and SEC):
    sys.exit("set JUSTCALL_API_KEY and JUSTCALL_API_SECRET")

TARGET = "https://eo-booth.nameless-mountain-bafa.workers.dev/sms"

H = {
    "Authorization": f"{KEY}:{SEC}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# JustCall names events "<object>.<action>" (call.completed, call.missed).
# The inbound-SMS name is not documented in what we can reach, so try the
# plausible spellings and keep the one the API accepts.
CANDIDATE_TYPES = [
    "sms.received",
    "sms.inbound",
    "text.received",
    "sms.incoming",
    "message.received",
]


def call(method, path, body=None):
    url = f"https://api.justcall.io/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:
        return 0, str(e)[:200]


def show_current():
    status, body = call("GET", "v2.1/webhooks")
    if status != 200:
        print(f"could not list webhooks: {status} {body[:200]}")
        return
    for w in json.loads(body).get("data", []):
        for u in w.get("webhook_urls", []):
            print(f"  {w['type']:18} {u['status']:8} {u['webhook_url'][:70]}")


print("current webhooks:")
show_current()

if "--create" not in sys.argv:
    print("\nRe-run with --create to add the inbound-SMS webhook.")
    sys.exit(0)

print(f"\nregistering {TARGET}")
for t in CANDIDATE_TYPES:
    status, body = call("POST", "v2.1/webhooks", {"type": t, "webhook_url": TARGET})
    print(f"  type={t:18} -> {status} {body[:160]}")
    if status in (200, 201):
        print(f"\nregistered as '{t}'.")
        break
else:
    print("\nNone of the candidate event names were accepted — needs the dashboard.")

print("\nwebhooks now:")
show_current()
