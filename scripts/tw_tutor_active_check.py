#!/usr/bin/env python3
"""READ-ONLY on Teachworks; one write on HubSpot (opt-in --write-props):
verify every tutor named in [Agent] Last Tutor Name is still an ACTIVE
Teachworks employee, and stamp the result.

Roman 2026-08-17: "before recommending a tutor cross reference if they are
still active in Teachworks" (Ruth was named but no longer tutors with us).

Steps:
  1. Pull all employees from both TW accounts → {first-name-lower: [statuses]}.
     Tutors are matched on FIRST NAME (that's all we stamped) — if the same
     first name maps to both an active and an inactive tutor, we treat it as
     active (benefit of the doubt) but flag it as AMBIGUOUS in the report.
  2. Pull every contact on the gap master list (3104) with last_tutor_name.
  3. Classify: active / inactive / not_found / ambiguous.
  4. --write-props: stamp last_tutor_active (true/false) via UPDATE-only
     import so segments/emails can branch on it. Read-only otherwise.
Prints the full report to the run log.
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import defaultdict
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
    TW_TOKENS["in_person"] = os.getenv("TEACHWORKS_TOKEN_INPERSON", "")
HS_BASE = "https://api.hubapi.com"
TW_BASE = "https://api.teachworks.com/v1"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
GAP_LIST_ID = 3104


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


def hs(method, path, **kw):
    r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=30, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def list_members(list_id):
    ids, after = [], None
    while True:
        j = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250" + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-props", action="store_true")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN or not TW_TOKENS:
        sys.exit("missing tokens")

    # 1) employees
    by_first = defaultdict(list)  # first-lower -> [(acct, full name, status)]
    for acct, tok in TW_TOKENS.items():
        emps = tw_get("employees", token=tok)
        print(f"[{acct}] {len(emps)} employees")
        for e in emps:
            first = (e.get("first_name") or "").strip()
            if not first:
                continue
            by_first[first.lower()].append((acct, f"{first} {e.get('last_name') or ''}".strip(),
                                            (e.get("status") or "").strip()))
    statuses = defaultdict(int)
    for lst in by_first.values():
        for _, _, s in lst:
            statuses[s] += 1
    print("employee status values:", dict(statuses))

    def is_active(s):
        return s.lower().startswith("activ")

    # 2) gap contacts
    ids = list_members(GAP_LIST_ID)
    contacts = {}
    for i in range(0, len(ids), 100):
        j = hs("POST", "/crm/v3/objects/contacts/batch/read",
               json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                     "properties": ["firstname", "lastname", "email", "last_tutor_name", "student_first_name"]})
        for row in j.get("results", []):
            contacts[str(row["id"])] = row.get("properties", {})

    # 3) classify
    buckets = defaultdict(list)
    tutor_verdict = {}
    for cid, p in contacts.items():
        t = (p.get("last_tutor_name") or "").strip()
        if not t:
            continue
        recs = by_first.get(t.lower(), [])
        if not recs:
            v = "not_found"
        else:
            act = [r for r in recs if is_active(r[2])]
            inact = [r for r in recs if not is_active(r[2])]
            v = "active" if act and not inact else "inactive" if inact and not act else "ambiguous"
        tutor_verdict[t] = (v, recs)
        buckets[v].append((cid, p, t))

    print("\n══ TUTOR VERDICTS (by tutor first name) ══")
    for t, (v, recs) in sorted(tutor_verdict.items(), key=lambda x: (x[1][0], x[0])):
        n = sum(1 for b in buckets[v] if b[2] == t)
        detail = "; ".join(f"{a}:{name} [{s or '?'}]" for a, name, s in recs) or "no employee with this first name"
        print(f"  {v.upper():<10} {t:<14} families {n:>3} | {detail}")
    print("\n══ FAMILY COUNTS ══")
    for v in ("active", "inactive", "not_found", "ambiguous"):
        print(f"  {v:<10} {len(buckets[v])}")
    print(f"  no tutor  {sum(1 for p in contacts.values() if not (p.get('last_tutor_name') or '').strip())}")

    if not args.write_props:
        print("\nread-only run (no --write-props)")
        return

    # 4) stamp last_tutor_active
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Email", "Last Tutor Active"])
    n = 0
    for v, rows in buckets.items():
        flag = "true" if v in ("active", "ambiguous") else "false"
        for cid, p, t in rows:
            if (p.get("email") or "").strip():
                w.writerow([p["email"].strip(), flag])
                n += 1
    req = {"name": f"Charter gap tutor-active check ({date.today().isoformat()})",
           "importOperations": {"0-1": "UPDATE"},
           "files": [{"fileName": "tutor_active.csv", "fileFormat": "CSV",
                      "fileImportPage": {"hasHeader": True, "columnMappings": [
                          {"columnObjectTypeId": "0-1", "columnName": "Email", "propertyName": "email",
                           "columnType": "HUBSPOT_ALTERNATE_ID"},
                          {"columnObjectTypeId": "0-1", "columnName": "Last Tutor Active",
                           "propertyName": "last_tutor_active"}]}}]}
    r = requests.post(f"{HS_BASE}/crm/v3/imports", headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"},
                      files={"files": ("tutor_active.csv", io.BytesIO(buf.getvalue().encode()), "text/csv")},
                      data={"importRequest": json.dumps(req)}, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"import failed {r.status_code}: {r.text[:300]}")
    imp = r.json().get("importId") or r.json().get("id")
    state = ""
    for _ in range(30):
        time.sleep(10)
        state = hs("GET", f"/crm/v3/imports/{imp}").get("state", "")
        if state in ("DONE", "FAILED", "CANCELED", "DEFERRED"):
            break
    print(f"\nstamped last_tutor_active on {n} contacts — import {imp}: {state}")


if __name__ == "__main__":
    main()
