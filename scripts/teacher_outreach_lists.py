#!/usr/bin/env python3
"""Charter teacher outreach 26/27: build the audience lists (Roman "Go" 2026-09-04).

Every teacher gets both messages (Stanford Badge + Teacher Scholarship); the
list decides the order and the rail. Council: docs/councils/2026-09-02-charter-
teacher-outreach.md. Copy: ops/messenger/templates/teacher-outreach-2026-09/.

  List 1  Worked with us      list 3110 + list 3111            → sequence (Danielle's inbox)
  List 2  Known-school cold   iLEAD / Sage Oak / Blue Ridge    → sequence (Danielle's inbox)
  List 3  Stranger-school cold  every other named school       → marketing campaign, one school per wave
  List 4  IEM Education Specialists  school_canonical = IEM    → marketing campaign, own wave
  Top 30  List 1 ranked by charter deal $ since Aug 2025       → hand-written day-10 note

Excluded from every list: generic_inbox = Yes, opted out, hard-bounced, no
email, internal (@wetutorathome.com), enrolled in the Sage Oak Summit sequence
(310056606), and school_canonical blank.

Rails (Roman 2026-09-03/04): email only, no call tasks, no meeting links.
Sequence vs campaign rule: if the teacher would recognise Danielle's name she
writes them; otherwise the company does.

Read-only by default; --build-lists creates/refreshes the static lists (names
below, upsert by exact name). Prints the top-30 either way.
"""

import argparse
import collections
import json
import os
import sys
import time
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
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

TOR_PERSONA = "Teacher of Record/EF/ES"
WORKED_LISTS = [3110, 3111]
SUMMIT_SEQUENCE_ID = "310056606"
KNOWN_SCHOOLS = {"iLEAD", "Sage Oak Charter Schools", "Blue Ridge Academy"}
IEM_BUCKET = "IEM"
INTERNAL_DOMAINS = {"wetutorathome.com"}
CHARTER_PIPELINES = ["907748", "72281989", "88841552", "5119061", "1066195"]
SINCE = "2025-08-01"
PREFIX = "Teacher Outreach 26/27 - "
LIST_NAMES = {
    1: PREFIX + "1 Worked With Us (sequence)",
    2: PREFIX + "2 Known Schools Cold (sequence)",
    3: PREFIX + "3 Stranger Schools Cold (campaign)",
    4: PREFIX + "4 IEM Education Specialists (campaign)",
    "top30": PREFIX + "Top 30 by deal $ (hand-written note)",
}


def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def search_all(object_type, filters, props):
    out, after = {}, None
    while True:
        body = {"filterGroups": [{"filters": filters}], "properties": props, "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", f"/crm/v3/objects/{object_type}/search", json=body)
        for x in j.get("results", []):
            out[str(x["id"])] = x.get("properties", {})
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return out
        time.sleep(0.15)


def list_members(list_id):
    ids, after = [], None
    while True:
        j = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250" + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


def upsert_list(name, ids):
    """Static list by exact name: create if missing, else replace membership."""
    j = hs("POST", "/crm/v3/lists/search", json={"query": name, "count": 20})
    hit = next((l for l in j.get("lists", []) if l.get("name") == name), None)
    if hit:
        lid = hit["listId"]
        cur = set(list_members(lid))
        rm = sorted(cur - set(ids))
        for i in range(0, len(rm), 250):
            hs("PUT", f"/crm/v3/lists/{lid}/memberships/remove", json=rm[i:i + 250])
    else:
        lid = hs("POST", "/crm/v3/lists", json={"name": name, "objectTypeId": "0-1",
                                                "processingType": "MANUAL"})["list"]["listId"]
    for i in range(0, len(ids), 250):
        hs("PUT", f"/crm/v3/lists/{lid}/memberships/add", json=ids[i:i + 250])
    return lid


def excluded_reason(p):
    email = (p.get("email") or "").strip().lower()
    if not email:
        return "no email"
    if email.split("@")[-1] in INTERNAL_DOMAINS:
        return "internal"
    if (p.get("hs_email_optout") or "").lower() == "true":
        return "opted out"
    if (p.get("hs_email_bounce") or "0") not in ("0", ""):
        return "bounced"
    if (p.get("generic_inbox") or "") == "true":
        return "generic inbox"
    if p.get("hs_latest_sequence_enrolled") == SUMMIT_SEQUENCE_ID:
        return "in Summit sequence"
    if not (p.get("school_canonical") or "").strip():
        return "no school"
    return None


def deal_dollars_by_tor():
    since_ms = int(time.mktime(time.strptime(SINCE, "%Y-%m-%d")) * 1000)
    deals = search_all("deals", [
        {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES},
        {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)},
    ], ["teacher_of_record_email", "amount"])
    amt = collections.Counter()
    for d in deals.values():
        e = (d.get("teacher_of_record_email") or "").strip().lower()
        if e:
            amt[e] += float(d.get("amount") or 0)
    return amt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-lists", action="store_true", help="create/refresh the static lists (default: read-only)")
    ap.add_argument("--out", default="teacher_outreach_lists.json", help="where to save the membership snapshot")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")

    props = ["email", "firstname", "lastname", "school_canonical", "generic_inbox", "hs_email_optout",
             "hs_email_bounce", "hs_latest_sequence_enrolled"]
    tor = search_all("contacts", [{"propertyName": "a_persona", "operator": "CONTAINS_TOKEN", "value": TOR_PERSONA}], props)
    worked = set()
    for lid in WORKED_LISTS:
        worked |= set(list_members(lid))
    print(f"teacher contacts: {len(tor)} | worked-with-us (lists {WORKED_LISTS}): {len(worked & set(tor))}")

    lists = {1: [], 2: [], 3: [], 4: []}
    excl = collections.Counter()
    by_school_3 = collections.Counter()
    for cid, p in tor.items():
        why = excluded_reason(p)
        if why:
            excl[why] += 1
            continue
        school = p["school_canonical"].strip()
        if cid in worked:
            lists[1].append(cid)
        elif school in KNOWN_SCHOOLS:
            lists[2].append(cid)
        elif school == IEM_BUCKET:
            lists[4].append(cid)
        else:
            lists[3].append(cid)
            by_school_3[school] += 1

    print("excluded:", dict(excl))
    for n in (1, 2, 3, 4):
        print(f"  list {n}: {len(lists[n]):4}  {LIST_NAMES[n]}")
    print("  list 2 by school:", dict(collections.Counter(tor[c]["school_canonical"] for c in lists[2])))
    print("  list 3 by school (wave order = size):")
    for s, n in by_school_3.most_common():
        print(f"      {n:4}  {s}")

    amt = deal_dollars_by_tor()
    ranked = sorted(lists[1], key=lambda c: -amt.get((tor[c].get("email") or "").lower(), 0))
    top30 = ranked[:30]
    print("\ntop 30 of list 1 by charter deal $ since Aug 2025 (hand-written day-10 note):")
    for c in top30:
        p = tor[c]
        print(f"   ${amt.get((p.get('email') or '').lower(), 0):>9,.0f}  {p.get('firstname','')} {p.get('lastname','')}  <{p.get('email','')}>  {p.get('school_canonical')}")

    snap = {"built": date.today().isoformat(), "lists": {str(k): v for k, v in lists.items()}, "top30": top30,
            "list_ids": {}, "excluded": dict(excl)}
    if args.build_lists:
        for n in (1, 2, 3, 4):
            lid = upsert_list(LIST_NAMES[n], lists[n])
            snap["list_ids"][str(n)] = lid
            print(f"  ✔ list {n} → HubSpot list {lid} ({len(lists[n])} members)")
        lid = upsert_list(LIST_NAMES["top30"], top30)
        snap["list_ids"]["top30"] = lid
        print(f"  ✔ top 30 → HubSpot list {lid}")
    else:
        print("\nDRY RUN — no lists written. Re-run with --build-lists.")
    Path(args.out).write_text(json.dumps(snap, indent=1))
    print(f"snapshot → {args.out}")


if __name__ == "__main__":
    main()
