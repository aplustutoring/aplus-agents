#!/usr/bin/env python3
"""Create or update the agent doorbell workflow that rings deal-sync-relay.

The HubSpot private-app webhook (README step 4) can only be configured in the
HubSpot UI with a secret only Roman holds, and on 2026-09-09 it turned out it
had never been done: `wrangler tail` showed zero requests on deal creation and
every new deal waited for the (GitHub-throttled) cron. This workflow is the
doorbell instead: deal created or dealstage changed -> POST to the relay. It is
a DOORBELL per #AP016 (trigger -> webhook, zero judgment) and lives here so it
is versioned and re-creatable, unlike every hand-built workflow before it.

Usage (needs HUBSPOT_PRIVATE_APP_TOKEN with the `automation` scope, and the
relay's WEBHOOK_TOKEN, which is a wrangler secret on deal-sync-relay):

    RELAY_WEBHOOK_TOKEN=... python3 apply_doorbell.py            # create/update
    RELAY_WEBHOOK_TOKEN=... python3 apply_doorbell.py --dry-run  # print payload
    python3 apply_doorbell.py --show                              # print live flow

Idempotent: matched by exact name. Rotating the relay token = re-run this.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
RELAY_URL = "https://deal-sync-relay.nameless-mountain-bafa.workers.dev/call-completed"
API = "https://api.hubapi.com/automation/v4/flows"


def _headers() -> dict:
    tok = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
    if not tok:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN is not set")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def payload(relay_token: str, delay: int = 1) -> dict:
    p = json.loads((HERE / "workflow.json").read_text())
    url = f"{RELAY_URL}?token={relay_token}&delay={delay}"
    for a in p["actions"]:
        if a.get("type") == "WEBHOOK":
            a["webhookUrl"] = url
    return p


def find_existing(name: str) -> dict | None:
    after = None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        r = requests.get(API, headers=_headers(), params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        for f in d.get("results", []):
            if f.get("name") == name:
                return f
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--delay", type=int, default=1, help="relay coalescing delay, minutes")
    args = ap.parse_args()

    name = json.loads((HERE / "workflow.json").read_text())["name"]
    if args.show:
        f = find_existing(name)
        if not f:
            print("no doorbell workflow in portal")
            return
        full = requests.get(f"{API}/{f['id']}", headers=_headers(), timeout=30).json()
        full_s = json.dumps(full, indent=1)
        for a in full.get("actions", []):  # never print the token
            if a.get("type") == "WEBHOOK":
                full_s = full_s.replace(a["webhookUrl"], RELAY_URL + "?token=***")
        print(full_s)
        return

    relay_token = os.environ.get("RELAY_WEBHOOK_TOKEN", "")
    if not relay_token:
        sys.exit("RELAY_WEBHOOK_TOKEN is not set (wrangler secret on deal-sync-relay)")
    body = payload(relay_token, args.delay)
    if args.dry_run:
        print(json.dumps(body, indent=1).replace(relay_token, "***"))
        return
    existing = find_existing(name)
    if existing:
        fid = existing["id"]
        live = requests.get(f"{API}/{fid}", headers=_headers(), timeout=30).json()
        body["revisionId"] = live.get("revisionId")
        r = requests.put(f"{API}/{fid}", headers=_headers(), json=body, timeout=30)
        verb = "updated"
    else:
        r = requests.post(API, headers=_headers(), json=body, timeout=30)
        verb = "created"
    if r.status_code >= 300:
        sys.exit(f"HubSpot {r.status_code}: {r.text[:800]}")
    d = r.json()
    print(f"doorbell {verb}: flow {d.get('id')} enabled={d.get('isEnabled')} "
          f"https://app.hubspot.com/workflows/6312752/platform/flow/{d.get('id')}/edit")


if __name__ == "__main__":
    main()
