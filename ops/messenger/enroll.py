#!/usr/bin/env python3
"""Enroll HubSpot list members into HubSpot workflows — the Monday-launch
runner for campaign.yml.

Reads campaign.yml: refuses to run unless `armed: true` AND today (PT) ==
`launch_date` (both checks skipped with --force, for manual runs). For each
{list_id, workflow_id} pair: fetch list members' emails, enroll each via the
automation v2 endpoint, log per-contact results. Already-enrolled contacts
error harmlessly (logged, not fatal). Dry-run default; live needs
--confirm LAUNCH.
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}


def list_emails(list_id):
    ids, after = [], None
    while True:
        url = f"{HS_BASE}/crm/v3/lists/{list_id}/memberships?limit=250"
        if after:
            url += f"&after={after}"
        r = requests.get(url, headers=H, timeout=30)
        r.raise_for_status()
        j = r.json()
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            break
    out = []
    for i in range(0, len(ids), 100):
        r = requests.post(f"{HS_BASE}/crm/v3/objects/contacts/batch/read", headers=H,
                          json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                                "properties": ["email"]}, timeout=30)
        r.raise_for_status()
        out += [(str(row["id"]), (row["properties"].get("email") or "").strip())
                for row in r.json().get("results", [])]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", default="", help="must be LAUNCH for a live run")
    ap.add_argument("--force", action="store_true",
                    help="skip the armed/launch-date gates (manual runs)")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(HERE / "campaign.yml"))
    tz = ZoneInfo(cfg.get("timezone", "America/Los_Angeles"))
    today = datetime.now(tz).date().isoformat()

    if not args.force:
        if not cfg.get("armed"):
            print("campaign.yml armed: false — nothing to do.")
            return
        if today != str(cfg.get("launch_date")):
            print(f"today {today} != launch_date {cfg.get('launch_date')} — nothing to do.")
            return

    live = args.confirm == "LAUNCH"
    pairs = [p for p in cfg.get("enrollments", []) if p.get("workflow_id")]
    pilot = cfg.get("pilot") or {}
    if pilot.get("workflow_id"):
        pairs = [{"list_id": pilot["list_id"], "workflow_id": pilot["workflow_id"],
                  "email_ids": pilot.get("email_ids", []), "segment": "pilot"}] + pairs
    if not pairs:
        sys.exit("campaign.yml has no enrollments with workflow_id set.")

    # pre-flight: publish AUTOMATED_DRAFT emails + enable the workflow (live only)
    for p in pairs:
        for eid in p.get("email_ids", []):
            st = requests.get(f"{HS_BASE}/marketing/v3/emails/{eid}", headers=H, timeout=30).json().get("state")
            print(f"email {eid}: {st}")
            if live and st == "AUTOMATED_DRAFT":
                r = requests.post(f"{HS_BASE}/marketing/v3/emails/{eid}/publish", headers=H, timeout=30)
                print(f"  publish -> {r.status_code}")
        wf = requests.get(f"{HS_BASE}/automation/v4/flows/{p['workflow_id']}", headers=H, timeout=30).json()
        print(f"workflow {p['workflow_id']} '{wf.get('name')}': enabled={wf.get('isEnabled')}")
        if live and not wf.get("isEnabled"):
            wf["isEnabled"] = True
            r = requests.put(f"{HS_BASE}/automation/v4/flows/{p['workflow_id']}", headers=H, json=wf, timeout=30)
            print(f"  enable -> {r.status_code}")

    for p in pairs:
        contacts = list_emails(p["list_id"])
        with_email = [(cid, em) for cid, em in contacts if em]
        print(f"list {p['list_id']} -> workflow {p['workflow_id']}: "
              f"{len(with_email)} contacts ({len(contacts) - len(with_email)} no-email skipped)")
        if not live:
            print("  DRY RUN — not enrolling. (--confirm LAUNCH to enroll)")
            continue
        ok = failed = 0
        for cid, em in with_email:
            r = requests.post(
                f"{HS_BASE}/automation/v2/workflows/{p['workflow_id']}/enrollments/contacts/{em}",
                headers=H, timeout=30)
            if r.status_code < 400:
                ok += 1
            else:
                failed += 1
                print(f"  ❌ {em}: {r.status_code} {r.text[:150]}")
            time.sleep(0.15)
        print(f"  enrolled {ok}, failed {failed}")
    print("done.")


if __name__ == "__main__":
    main()
