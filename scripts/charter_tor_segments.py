#!/usr/bin/env python3
"""Charter TOR (teacher) segmentation for the 26/27 outreach from Danielle.

The teacher-side counterpart to scripts/charter_gap_segments.py. Where the
family segmenter splits on recency x student-count x personalization, the
teacher relationship has different axes: whether the teacher has already sent
us business in 26/27, and how much business came through them in 25/26.

Builds the TOR universe from four independent signals (union, not intersection
— no single one is complete):
  a_persona contains "Teacher of Record/EF/ES"      (1065)
  hs_lead_status = "Charter School Teacher TOR/EF"  (1086)
  charter_school_teacher is known                   (1172)
  educational_facillitator_teacher_of_record = true ( 548)

Then attributes charter deals to teachers. NOTE: deals carry
`teacher_of_record_name` but NOT an email (checked 2026-08-21 — 2244 of 2284
deals since 2025-08-01 have the name, 0 have an email), so attribution is a
normalized full-name match against the TOR contacts. Unmatched names are
reported, never guessed at.

Segments (one static list per cell):
  A   Restarted        >=1 charter deal created since 2026-07-01
  B1  Anchor           no 26/27 deal, 5+ families in 25/26
  B2  Multi            no 26/27 deal, 2-4 families in 25/26
  B3  Single           no 26/27 deal, 1 family in 25/26
  C1  Intro - iLEAD    no deal history, school = iLEAD (case-study variant)
  C2  Intro - other    no deal history, any other partner school

--write-props stamps tor_family_count / tor_student_count /
tor_families_lapsed / tor_segment onto the contacts (batch update, UPDATE-only
by definition). --build-lists creates/refreshes the six static lists.
Read-only otherwise.
"""

import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    # worktrees have no .env — fall back to the main checkout's
    if "/.claude/worktrees/" in str(_here) or "/scratchpad/" in str(_here):
        base = str(_here).split("/.claude/worktrees/")[0]
        load_dotenv(Path("/Users/romanslavinsky/code/aplus-agents/.env"), override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

GAP_LIST_ID = 3104                 # lapsed 25/26 families (charter_gap_analysis)
SINCE = "2025-08-01"               # start of the 25/26 attribution window
YEAR_2627 = "2026-07-01"           # a deal created on/after this is 26/27 business
CHARTER_PIPELINES = {"907748", "72281989", "88841552", "5119061", "1066195"}
LIST_PREFIX = "Charter TOR 26/27 - "
INTERNAL_DOMAIN = "@wetutorathome.com"
NOT_STUDENT_TOKENS = {"a", "summer", "level", "ilead", "charter"}

SEGMENTS = [
    ("A",  "Restarted",           "A - Restarted 26/27"),
    ("B1", "Anchor (5+)",         "B1 - Anchor (5+ families)"),
    ("B2", "Multi (2-4)",         "B2 - Multi (2-4 families)"),
    ("B3", "Single (1)",          "B3 - Single (1 family)"),
    ("C1", "Intro - iLEAD",       "C1 - Intro (iLEAD)"),
    ("C2", "Intro - other",       "C2 - Intro (other schools)"),
]


def hs(method, path, **kw):
    for _ in range(5):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=40, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10) or 10))
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def search_all(obj, filter_groups, props):
    out, after = {}, None
    while True:
        body = {"filterGroups": filter_groups, "properties": props, "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", f"/crm/v3/objects/{obj}/search", json=body)
        for r in j.get("results", []):
            out[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return out
        time.sleep(0.12)


def list_members(list_id):
    ids, after = [], None
    while True:
        j = hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250"
               + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


TOR_PROPS = ["email", "firstname", "lastname", "charter_school_teacher", "hs_lead_status",
             "a_persona", "hs_marketable_status", "hs_email_optout",
             "hs_email_hard_bounce_reason", "hubspot_owner_id", "createdate",
             "tor_family_count", "tor_student_count", "tor_families_lapsed", "tor_segment"]


def load_tors():
    """Union of the four TOR signals. No single signal is complete."""
    signals = [
        ("a_persona", [{"filters": [{"propertyName": "a_persona", "operator": "CONTAINS_TOKEN",
                                     "value": "Teacher of Record/EF/ES"}]}]),
        ("lead_status", [{"filters": [{"propertyName": "hs_lead_status", "operator": "EQ",
                                       "value": "Charter School Teacher TOR/EF"}]}]),
        ("school_prop", [{"filters": [{"propertyName": "charter_school_teacher",
                                       "operator": "HAS_PROPERTY"}]}]),
        ("ef_flag", [{"filters": [{"propertyName": "educational_facillitator_teacher_of_record",
                                   "operator": "EQ", "value": "true"}]}]),
    ]
    tors = {}
    for label, groups in signals:
        got = search_all("contacts", groups, TOR_PROPS)
        new = len(set(got) - set(tors))
        for k, v in got.items():
            tors.setdefault(k, v)
        print(f"  {label:<12} {len(got):>5}  (+{new} new)  union={len(tors)}")
    return tors


def load_charter_deals():
    """Every charter-pipeline deal created since SINCE."""
    since_ms = int(datetime.fromisoformat(SINCE).replace(tzinfo=timezone.utc).timestamp() * 1000)
    deals, after = {}, None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": sorted(CHARTER_PIPELINES)},
            {"propertyName": "createdate", "operator": "GTE", "value": since_ms}]}],
            "properties": ["dealname", "amount", "dealstage", "pipeline", "createdate",
                           "teacher_of_record_name"],
            "limit": 100}
        if after:
            body["after"] = after
        j = hs("POST", "/crm/v3/objects/deals/search", json=body)
        for r in j.get("results", []):
            deals[r["id"]] = r["properties"]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return deals
        time.sleep(0.12)


def norm_name(s):
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def attribute(tors, deals):
    """Deal -> TOR contact by normalized full name. Returns (hits, unmatched)."""
    idx = collections.defaultdict(list)
    for cid, p in tors.items():
        n = norm_name(f"{p.get('firstname', '')} {p.get('lastname', '')}")
        if n and " " in n:            # single-token names are too ambiguous to match on
            idx[n].append(cid)
    hits, unmatched, ambiguous = collections.defaultdict(list), collections.Counter(), set()
    for did, d in deals.items():
        n = norm_name(d.get("teacher_of_record_name"))
        if not n:
            continue
        ids = idx.get(n)
        if not ids:
            unmatched[n] += 1
            continue
        if len(ids) > 1:
            ambiguous.add(n)
        hits[ids[0]].append(did)
    return hits, unmatched, ambiguous


def profile(tors, deals, hits, gap):
    """Per-teacher rollup: 25/26 families+students, 26/27 families, lapsed families."""
    cutoff = datetime.fromisoformat(YEAR_2627).replace(tzinfo=timezone.utc)
    rows = {}
    for cid, p in tors.items():
        fam25, fam2627, students, amount25 = set(), set(), {}, 0.0
        for did in hits.get(cid, []):
            d = deals[did]
            parts = [x.strip() for x in (d.get("dealname") or "").split(" - ")]
            parent = parts[0].lower() if parts else ""
            created = parse_dt(d.get("createdate"))
            if created and created >= cutoff:
                fam2627.add(parent)
            else:
                fam25.add(parent)
                try:
                    amount25 += float(d.get("amount") or 0)
                except (TypeError, ValueError):
                    pass
            if len(parts) >= 3:
                cand = parts[1].split(" ")[0].strip(" .,")
                if (cand and cand.lower() not in NOT_STUDENT_TOKENS
                        and re.match(r"^[A-Za-zÀ-ÿ'\-]+$", cand)):
                    students.setdefault(cand.lower(), cand)
        rows[cid] = {
            "email": (p.get("email") or "").strip(),
            "name": f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "school": p.get("charter_school_teacher") or "",
            "fam25": len(fam25), "fam2627": len(fam2627),
            "students": len(students), "amount25": round(amount25),
            "lapsed": 0,          # filled by caller from associations
            "optout": p.get("hs_email_optout") == "true",
            "marketable": p.get("hs_marketable_status") == "true",
            "bounced": bool(p.get("hs_email_hard_bounce_reason")),
        }
    return rows


def segment_of(r):
    if r["fam2627"] > 0:
        return "A"
    if r["fam25"] >= 5:
        return "B1"
    if r["fam25"] >= 2:
        return "B2"
    if r["fam25"] == 1:
        return "B3"
    return "C1" if r["school"] == "iLEAD" else "C2"


def mailable(r):
    """Exclusions the campaign applies on top of HubSpot's own suppression."""
    if not r["email"]:
        return "no email"
    if r["email"].lower().endswith(INTERNAL_DOMAIN):
        return "internal"
    if r["optout"]:
        return "opted out"
    if r["bounced"]:
        return "hard bounced"
    if not r["marketable"]:
        return "non-marketable"
    return ""


# ---------------------------------------------------------------- writes

def write_props(rows):
    payload = [{"id": cid, "properties": {
        "tor_family_count": str(r["fam2627"] or r["fam25"]),
        "tor_student_count": str(r["students"]),
        "tor_families_lapsed": str(r["lapsed"]),
        "tor_segment": segment_of(r),
    }} for cid, r in rows.items()]
    done = 0
    for i in range(0, len(payload), 100):
        hs("POST", "/crm/v3/objects/contacts/batch/update", json={"inputs": payload[i:i + 100]})
        done += len(payload[i:i + 100])
        print(f"  stamped {done}/{len(payload)}")
        time.sleep(0.2)


def build_lists(rows):
    existing = {}
    j = hs("POST", "/crm/v3/lists/search", json={"query": LIST_PREFIX, "count": 250, "offset": 0})
    for L in j.get("lists", []):
        existing[L.get("name")] = L.get("listId")
    for code, _short, suffix in SEGMENTS:
        name = LIST_PREFIX + suffix
        members = [cid for cid, r in rows.items()
                   if segment_of(r) == code and not mailable(r)]
        lid = existing.get(name)
        if not lid:
            created = hs("POST", "/crm/v3/lists", json={
                "name": name, "objectTypeId": "0-1", "processingType": "MANUAL"})
            lid = created["list"]["listId"]
            print(f"  created list {lid}  {name}")
        else:
            cur = list_members(lid)
            if cur:
                hs("PUT", f"/crm/v3/lists/{lid}/memberships/remove", json=cur)
            print(f"  refreshed list {lid}  {name} (cleared {len(cur)})")
        for i in range(0, len(members), 100):
            hs("PUT", f"/crm/v3/lists/{lid}/memberships/add", json=members[i:i + 100])
        print(f"    -> {len(members)} members")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-props", action="store_true",
                    help="stamp tor_* properties onto the TOR contacts")
    ap.add_argument("--build-lists", action="store_true",
                    help="create/refresh the six static segment lists")
    ap.add_argument("--json", default="", help="dump the per-teacher rollup to this path")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN not set")

    print("TOR universe (union of four signals):")
    tors = load_tors()

    print(f"\ncharter deals created since {SINCE}:")
    deals = load_charter_deals()
    named = sum(1 for d in deals.values() if d.get("teacher_of_record_name"))
    print(f"  {len(deals)} deals, {named} carry teacher_of_record_name")

    hits, unmatched, ambiguous = attribute(tors, deals)
    print(f"  attributed to {len(hits)} teachers; "
          f"{sum(unmatched.values())} deals name a teacher with no matching contact "
          f"({len(unmatched)} distinct names)")
    if ambiguous:
        print(f"  ⚠ {len(ambiguous)} names match >1 contact (first wins): "
              f"{', '.join(sorted(ambiguous)[:5])}")

    gap = set(list_members(GAP_LIST_ID))
    rows = profile(tors, deals, hits, gap)

    # lapsed-family count comes from the contact-to-contact Family association
    tor_ids = list(tors)
    for i in range(0, len(tor_ids), 100):
        j = hs("POST", "/crm/v4/associations/contact/contact/batch/read",
               json={"inputs": [{"id": c} for c in tor_ids[i:i + 100]]})
        for row in j.get("results", []):
            cid = str(row["from"]["id"])
            fams = [str(t["toObjectId"]) for t in row.get("to", [])
                    if any("Family" in (l.get("label") or "") for l in t.get("associationTypes", []))]
            rows[cid]["lapsed"] = len([f for f in fams if f in gap])
        time.sleep(0.1)

    print("\n=== SEGMENTS ===")
    print(f"  {'code':<4} {'segment':<22} {'total':>6} {'mailable':>9} {'excluded':>9}")
    for code, short, _suffix in SEGMENTS:
        cell = [r for r in rows.values() if segment_of(r) == code]
        ok = [r for r in cell if not mailable(r)]
        print(f"  {code:<4} {short:<22} {len(cell):>6} {len(ok):>9} {len(cell) - len(ok):>9}")
    print(f"  {'':<4} {'TOTAL':<22} {len(rows):>6} "
          f"{sum(1 for r in rows.values() if not mailable(r)):>9} "
          f"{sum(1 for r in rows.values() if mailable(r)):>9}")

    print("\n  exclusions by reason:")
    for reason, n in collections.Counter(mailable(r) for r in rows.values()).most_common():
        if reason:
            print(f"    {n:>5}  {reason}")

    print("\n  teachers with lapsed (gap-list) families: "
          f"{sum(1 for r in rows.values() if r['lapsed'])} "
          f"({sum(r['lapsed'] for r in rows.values())} families)")

    if unmatched:
        print("\n  ⚠ top deal teacher names with NO contact record (hygiene queue):")
        for n, c in unmatched.most_common(10):
            print(f"    {c:>3} deals  {n}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {cid: dict(r, segment=segment_of(r), excluded=mailable(r))
             for cid, r in rows.items()}, indent=2))
        print(f"\n  wrote {args.json}")

    if args.write_props:
        print("\nstamping tor_* properties:")
        write_props(rows)
    if args.build_lists:
        print("\nbuilding segment lists:")
        build_lists(rows)
    if not (args.write_props or args.build_lists):
        print("\n(read-only — pass --write-props / --build-lists to write)")


if __name__ == "__main__":
    main()
