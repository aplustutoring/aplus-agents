#!/usr/bin/env python3
"""Tutor roster check: stamp [Agent] Tutor Roster Status on Tutors-persona
contacts from the Teachworks EMPLOYEE roster (both accounts, email match).

Roman 2026-08-25: "To correlate if a tutor is active you have to check if
they are active in Teachworks on active roster" + two-account reminder.
Active in EITHER account = Active; value records which. Read-only against
Teachworks; the only HubSpot write is the UPDATE-only import (--write-props).

Auth (env / CI secrets): HUBSPOT_PRIVATE_APP_TOKEN,
TEACHWORKS_TOKEN (online), TEACHWORKS_TOKEN_INPERSON.
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
TW_TOKENS = {}
if os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", ""):
    TW_TOKENS["online"] = os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", "")
if os.getenv("TEACHWORKS_TOKEN_INPERSON", ""):
    TW_TOKENS["in person"] = os.getenv("TEACHWORKS_TOKEN_INPERSON", "")
HS_BASE = "https://api.hubapi.com"
TW_BASE = "https://api.teachworks.com/v1"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}


def tw_get(endpoint, params=None, token=None):
    headers = {"Authorization": f"Token token={token}", "Content-Type": "application/json"}
    params = dict(params or {})
    params["per_page"] = 80
    params["page"] = 1
    out = []
    while True:
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers, params=params, timeout=30)
            if r.status_code == 403:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        data = r.json()
        if not data:
            break
        out.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-props", action="store_true")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN or not TW_TOKENS:
        sys.exit("missing tokens")

    # roster: email -> {account: active_bool}
    roster = {}
    for acct, tok in TW_TOKENS.items():
        emps = tw_get("employees", token=tok)
        act = sum(1 for e in emps if (e.get("status") or "").lower().startswith("activ"))
        print(f"[{acct}] employees {len(emps)} ({act} active)")
        for e in emps:
            em = (e.get("email") or "").strip().lower()
            if em:
                cur = roster.setdefault(em, {})
                cur[acct] = (e.get("status") or "").lower().startswith("activ") or cur.get(acct, False)

    # Tutors-persona contacts
    out, after = [], None
    while True:
        b = {"filterGroups": [{"filters": [
            {"propertyName": "a_persona", "operator": "CONTAINS_TOKEN", "value": "Tutors"}]}],
            "properties": ["firstname", "lastname", "email"], "limit": 200}
        if after:
            b["after"] = after
        j = requests.post(f"{HS_BASE}/crm/v3/objects/contacts/search", headers=H, json=b, timeout=30).json()
        out += j.get("results", [])
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            break
    print(f"Tutors-persona contacts: {len(out)}")

    def verdict(em):
        r = roster.get(em)
        if not r:
            return "Not found"
        on, ip = r.get("online", False), r.get("in person", False)
        if on and ip:
            return "Active (both)"
        if on:
            return "Active (online)"
        if ip:
            return "Active (in person)"
        return "Inactive (both)"

    results = []
    for c in out:
        em = (c["properties"].get("email") or "").strip().lower()
        results.append((em, verdict(em) if em else "Not found",
                        c["properties"].get("firstname"), c["properties"].get("lastname")))
    counts = Counter(v for _, v, _, _ in results)
    print("verdicts:", dict(counts))
    active_total = sum(n for v, n in counts.items() if v.startswith("Active"))
    print(f"HubSpot says Tutors: {len(results)} | TW roster confirms active: {active_total} "
          f"(staleness: {len(results) - active_total})")

    if not args.write_props:
        print("read-only run (no --write-props)")
        return

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Email", "Tutor Roster Status"])
    n = 0
    for em, v, _, _ in results:
        if em:
            w.writerow([em, v])
            n += 1
    req = {"name": f"Tutor roster check {date.today().isoformat()}",
           "importOperations": {"0-1": "UPDATE"},
           "files": [{"fileName": "roster.csv", "fileFormat": "CSV",
                      "fileImportPage": {"hasHeader": True, "columnMappings": [
                          {"columnObjectTypeId": "0-1", "columnName": "Email", "propertyName": "email",
                           "columnType": "HUBSPOT_ALTERNATE_ID"},
                          {"columnObjectTypeId": "0-1", "columnName": "Tutor Roster Status",
                           "propertyName": "tutor_roster_status"}]}}]}
    r = requests.post(f"{HS_BASE}/crm/v3/imports", headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"},
                      files={"files": ("roster.csv", io.BytesIO(buf.getvalue().encode()), "text/csv")},
                      data={"importRequest": json.dumps(req)}, timeout=120)
    if r.status_code >= 400:
        sys.exit(f"import failed {r.status_code}: {r.text[:300]}")
    imp = r.json().get("importId") or r.json().get("id")
    state = ""
    for _ in range(30):
        time.sleep(10)
        state = requests.get(f"{HS_BASE}/crm/v3/imports/{imp}", headers=H, timeout=30).json().get("state", "")
        if state in ("DONE", "FAILED", "CANCELED", "DEFERRED"):
            break
    print(f"stamped {n} contacts — import {imp}: {state}")


if __name__ == "__main__":
    main()
