#!/usr/bin/env python3
"""
Archive (soft-delete) HubSpot CRM objects by id — the fleet's cleanup tool.

Born 2026-09-10: a stale-checkout bug made queued workflow runs re-do work,
leaving duplicate tickets, tasks and notes that no agent could remove (the
HubSpot connector can create and update, not archive; no token exists
outside Actions). Runs via .github/workflows/hubspot-archive.yml.

Every object is fetched and printed BEFORE it is archived so the Actions log
is the audit trail. Archived objects are recoverable from HubSpot's recycle
bin for 90 days.

Usage: archive_objects.py --object-type tickets --ids 1,2,3 [--dry-run]
Env:   HUBSPOT_PRIVATE_APP_TOKEN or HUBSPOT_API_KEY
"""

import argparse
import os
import sys

import requests

API = "https://api.hubapi.com/crm/v3/objects"
LABEL = {"tickets": "subject", "tasks": "hs_task_subject", "notes": "hs_body_preview",
         "deals": "dealname", "contacts": "email"}


def token():
    t = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN") or os.getenv("HUBSPOT_API_KEY")
    if not t:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN / HUBSPOT_API_KEY not set")
    return t


def fetch(object_type, oid, tok):
    r = requests.get(f"{API}/{object_type}/{oid}",
                     params={"properties": LABEL.get(object_type, "hs_object_id")},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def archive(object_type, oid, tok):
    r = requests.delete(f"{API}/{object_type}/{oid}",
                        headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--object-type", required=True, choices=sorted(LABEL))
    ap.add_argument("--ids", required=True, help="comma-separated object ids")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ids = [i.strip() for i in a.ids.split(",") if i.strip()]
    if not all(i.isdigit() for i in ids):
        sys.exit(f"ids must be numeric: {ids}")
    tok = token()
    done = missing = 0
    for oid in ids:
        obj = fetch(a.object_type, oid, tok)
        if obj is None:
            print(f"  {a.object_type}/{oid}: not found (already archived?) — skipped")
            missing += 1
            continue
        label = (obj.get("properties") or {}).get(LABEL.get(a.object_type, ""), "")
        label = (label or "")[:90].replace("\n", " ")
        if a.dry_run:
            print(f"  [dry-run] would archive {a.object_type}/{oid}: {label}")
            continue
        archive(a.object_type, oid, tok)
        print(f"  archived {a.object_type}/{oid}: {label}")
        done += 1
    print(f"{'dry run — ' if a.dry_run else ''}{done} archived, {missing} missing, {len(ids)} requested")


if __name__ == "__main__":
    main()
