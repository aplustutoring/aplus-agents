#!/usr/bin/env python3
"""Verify each gap family's LAST TUTOR is still an ACTIVE Teachworks employee —
exact, by employee id (never by first name alone).

Roman 2026-08-17: "before recommending a tutor cross reference if they are
still active in Teachworks" (Ruth was named but no longer tutors with us).
The first pass matched on first name and left 168 families ambiguous
(3 Jonathans, 11 Hannahs...). This pass re-walks each family's most recent
completed lesson, takes the lesson's employee_id, and checks THAT employee.

Per gap contact (list 3104) with a Teachworks match:
  customers (email) -> students -> lessons since SINCE -> most recent
  completed lesson -> employee_id -> employee record -> status.
Falls back to exact full-name match against the employee list when a lesson
has no employee_id. Tutor last names stay internal (report only).

--write-props stamps (UPDATE-only import, crm.import):
  last_tutor_active  true/false
  last_tutor_name    re-stamped from the SAME lesson (first name only) so the
                     name and the active flag always describe the same person
Read-only otherwise. Both TW tokens required (CI).
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
SINCE = "2025-08-01"


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


def first_name(raw):
    raw = (raw or "").strip()
    if "," in raw:
        return raw.split(",", 1)[1].strip()
    return raw.split(" ")[0] if raw else ""


def norm(s):
    return " ".join((s or "").lower().split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-props", action="store_true")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN or not TW_TOKENS:
        sys.exit("missing tokens")

    # employees per account: by id + by normalized full name (both orders)
    emp_by_id, emp_by_name = {}, {}
    for acct, tok in TW_TOKENS.items():
        emps = tw_get("employees", token=tok)
        print(f"[{acct}] {len(emps)} employees")
        for e in emps:
            f, l = (e.get("first_name") or "").strip(), (e.get("last_name") or "").strip()
            rec = {"acct": acct, "id": e.get("id"), "first": f, "last": l, "status": (e.get("status") or "").strip()}
            emp_by_id[(acct, str(e.get("id")))] = rec
            emp_by_name.setdefault((acct, norm(f"{f} {l}")), []).append(rec)
            emp_by_name.setdefault((acct, norm(f"{l}, {f}")), []).append(rec)

    def is_active(rec):
        return rec["status"].lower().startswith("activ")

    ids = list_members(GAP_LIST_ID)
    contacts = {}
    for i in range(0, len(ids), 100):
        j = hs("POST", "/crm/v3/objects/contacts/batch/read",
               json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                     "properties": ["firstname", "lastname", "email", "last_tutor_name"]})
        for row in j.get("results", []):
            contacts[str(row["id"])] = row.get("properties", {})

    results = {}  # cid -> dict(verdict, tutor_first, tutor_full, acct, lesson_date, how)
    counts = defaultdict(int)
    for n, (cid, p) in enumerate(contacts.items(), 1):
        email = (p.get("email") or "").strip().lower()
        if not email:
            counts["no_email"] += 1
            continue
        best = None
        for acct, tok in TW_TOKENS.items():
            for cust in tw_get("customers", {"email": email}, token=tok):
                for s in tw_get("students", {"customer_id": cust["id"]}, token=tok):
                    for l in tw_get("lessons", {"student_id": s["id"], "from_date[gte]": SINCE}, token=tok):
                        st = str(l.get("status") or "").lower()
                        if "attend" not in st and "complete" not in st:
                            continue
                        d = str(l.get("from_date") or "")[:10]
                        if not best or d > best["date"]:
                            best = {"date": d, "acct": acct, "emp_id": l.get("employee_id"),
                                    "emp_name": l.get("employee_name") or ""}
        if not best:
            counts["no_lesson"] += 1
            continue
        rec, how = None, ""
        if best["emp_id"] is not None and (best["acct"], str(best["emp_id"])) in emp_by_id:
            rec, how = emp_by_id[(best["acct"], str(best["emp_id"]))], "id"
        else:
            cands = emp_by_name.get((best["acct"], norm(best["emp_name"])), [])
            if len(cands) == 1:
                rec, how = cands[0], "name"
            elif len(cands) > 1:
                act = [c for c in cands if is_active(c)]
                rec, how = (act[0] if len(act) == 1 else cands[0]), "name-multi"
        if not rec:
            verdict = "unresolved"
        else:
            verdict = "active" if is_active(rec) else "inactive"
        counts[verdict] += 1
        results[cid] = {"verdict": verdict, "how": how, "lesson_date": best["date"], "acct": best["acct"],
                        "tutor_first": rec["first"] if rec else first_name(best["emp_name"]),
                        "tutor_full": f"{rec['first']} {rec['last']}" if rec else best["emp_name"],
                        "status": rec["status"] if rec else "?"}
        if n % 50 == 0:
            print(f"  ...{n}/{len(contacts)}")

    print("\n══ FAMILY COUNTS ══")
    for k in ("active", "inactive", "unresolved", "no_lesson", "no_email"):
        print(f"  {k:<11} {counts[k]}")
    print("\n══ INACTIVE TUTORS (families affected) ══")
    agg = defaultdict(list)
    for cid, r in results.items():
        if r["verdict"] != "active":
            agg[(r["tutor_full"], r["status"], r["acct"])].append(contacts[cid])
    for (t, st, acct), fams in sorted(agg.items(), key=lambda x: -len(x[1])):
        print(f"  {t} [{st}, {acct}] — {len(fams)} families: "
              + ", ".join(f"{f.get('firstname')} {f.get('lastname')}" for f in fams[:6])
              + (" ..." if len(fams) > 6 else ""))
    print("\n══ ACTIVE TUTORS ══")
    aagg = defaultdict(int)
    for r in results.values():
        if r["verdict"] == "active":
            aagg[r["tutor_full"]] += 1
    print("  " + "; ".join(f"{t} ({n})" for t, n in sorted(aagg.items(), key=lambda x: -x[1])))
    changed = sum(1 for cid, r in results.items()
                  if (contacts[cid].get("last_tutor_name") or "").strip() != r["tutor_first"])
    print(f"\nlast_tutor_name would change for {changed} contacts (id-exact vs earlier stamp)")

    if not args.write_props:
        print("read-only run (no --write-props)")
        return

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Email", "Last Tutor Active", "Last Tutor Name"])
    n = 0
    for cid, r in results.items():
        em = (contacts[cid].get("email") or "").strip()
        if em:
            w.writerow([em, "true" if r["verdict"] == "active" else "false", r["tutor_first"]])
            n += 1
    req = {"name": f"Charter gap tutor-active (id-exact) {date.today().isoformat()}",
           "importOperations": {"0-1": "UPDATE"},
           "files": [{"fileName": "tutor_active.csv", "fileFormat": "CSV",
                      "fileImportPage": {"hasHeader": True, "columnMappings": [
                          {"columnObjectTypeId": "0-1", "columnName": "Email", "propertyName": "email",
                           "columnType": "HUBSPOT_ALTERNATE_ID"},
                          {"columnObjectTypeId": "0-1", "columnName": "Last Tutor Active",
                           "propertyName": "last_tutor_active"},
                          {"columnObjectTypeId": "0-1", "columnName": "Last Tutor Name",
                           "propertyName": "last_tutor_name"}]}}]}
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
    print(f"\nstamped last_tutor_active + last_tutor_name on {n} contacts — import {imp}: {state}")


if __name__ == "__main__":
    main()
