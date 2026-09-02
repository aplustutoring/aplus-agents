#!/usr/bin/env python3
"""Stamp a canonical school onto teacher (TOR/EF/ES) contacts.

Roman 2026-09-02: teacher contacts had no usable school field (student_school
filled on 15/159 of the charter-gap TOR list; company on 26/159), so every
teacher segmentation was a guess parsed from the email domain. Charter DEALS
already know both the teacher (teacher_of_record_email, 98% filled) and the
school (student_school, 96% filled) — so the school is derived from the deals
the teacher is named on, canonicalised through ops/hubspot-schema/
school-aliases.yml (iLEAD = one bucket), and written to the [Agent] contact
property `school_canonical`.

Resolution order per teacher:
  1. deals where teacher_of_record_email == contact email → most common
     canonical student_school (ties broken by most recent deal)
  2. email-domain fallback from the alias file (`domains:`)
  3. unresolved → reported, NOT written

A deal spelling missing from the alias file is reported loudly (and the deal
is skipped) so the file stays complete. Nothing is guessed.

Read-only by default. --execute writes (backs up current values first).

  python3 scripts/teacher_school_stamp.py                 # Pile 1 (list 3110), dry run
  python3 scripts/teacher_school_stamp.py --all-tor       # every TOR-persona contact
  python3 scripts/teacher_school_stamp.py --execute       # write
"""

import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    # worktrees have no .env — fall back to the main checkout's
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

ALIAS_FILE = Path(__file__).resolve().parent.parent / "ops" / "hubspot-schema" / "school-aliases.yml"
TARGET_PROP = "school_canonical"
TOR_LIST_ID = 3110                       # Charter 26/27 Gap - TORs - Worked With Us
TOR_PERSONA = "Teacher of Record/EF/ES"  # a_persona LABEL (== value for this option)
CHARTER_PIPELINES = ["907748", "72281989", "88841552", "5119061", "1066195"]
SINCE = "2025-08-01"


# ── HubSpot ────────────────────────────────────────────────────────────────
def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        r.raise_for_status()
        return r.json() if r.text else {}
    r.raise_for_status()


def search_all(object_type, filters, props, sorts=None):
    out, after = {}, None
    while True:
        body = {"filterGroups": [{"filters": filters}], "properties": props, "limit": 100}
        if sorts:
            body["sorts"] = sorts
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


def batch_read(object_type, ids, props):
    out = {}
    for i in range(0, len(ids), 100):
        j = hs("POST", f"/crm/v3/objects/{object_type}/batch/read",
               json={"inputs": [{"id": c} for c in ids[i:i + 100]], "properties": props})
        for row in j.get("results", []):
            out[str(row["id"])] = row.get("properties", {})
    return out


# ── alias map ──────────────────────────────────────────────────────────────
def _key(s):
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def load_school_aliases(path=ALIAS_FILE):
    """Returns (alias_key -> canonical, domain -> canonical, canonical -> network)."""
    import yaml
    spec = yaml.safe_load(path.read_text())
    aliases, networks = {}, {}
    for s in spec.get("schools", []):
        canon = s["canonical"]
        networks[canon] = s.get("network")
        for a in s.get("aliases", []) + [canon]:
            k = _key(a)
            if k in aliases and aliases[k] != canon:
                sys.exit(f"alias file conflict: {a!r} → {aliases[k]!r} and {canon!r}")
            aliases[k] = canon
    domains = {d.lower(): c for d, c in (spec.get("domains") or {}).items()}
    return aliases, domains, networks


# ── resolution ─────────────────────────────────────────────────────────────
def teacher_schools_from_deals(aliases, since=SINCE):
    """tor_email -> Counter(canonical) over charter deals since `since`.
    Returns (by_tor, unknown_spellings Counter)."""
    since_ms = int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000)
    deals = search_all("deals", [
        {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES},
        {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)},
    ], ["teacher_of_record_email", "student_school", "createdate"],
        sorts=[{"propertyName": "createdate", "direction": "DESCENDING"}])
    by_tor, unknown = collections.defaultdict(collections.Counter), collections.Counter()
    latest = {}   # (tor, canon) -> first-seen (== most recent) index for tie-breaks
    for i, d in enumerate(deals.values()):
        tor = _key(d.get("teacher_of_record_email"))
        raw = (d.get("student_school") or "").strip()
        if not tor or not raw:
            continue
        canon = aliases.get(_key(raw))
        if not canon:
            unknown[raw] += 1
            continue
        by_tor[tor][canon] += 1
        latest.setdefault((tor, canon), i)
    resolved = {}
    for tor, c in by_tor.items():
        top = max(c.values())
        resolved[tor] = min((k for k, v in c.items() if v == top), key=lambda k: latest[(tor, k)])
    return resolved, dict(by_tor), unknown, len(deals)


def resolve_contacts(contacts, resolved, domains):
    """contacts: id -> props (email, school_canonical). Returns plan rows."""
    rows = []
    for cid, p in contacts.items():
        email = _key(p.get("email"))
        school, how = None, None
        if email in resolved:
            school, how = resolved[email], "deal"
        elif email.split("@")[-1] in domains:
            school, how = domains[email.split("@")[-1]], "domain"
        rows.append({"id": cid, "email": p.get("email") or "", "current": (p.get(TARGET_PROP) or "").strip(),
                     "school": school, "how": how})
    return rows


# ── main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", type=int, default=TOR_LIST_ID, help=f"static list of teacher contacts (default {TOR_LIST_ID})")
    ap.add_argument("--all-tor", action="store_true", help=f"every contact with a_persona '{TOR_PERSONA}' instead of --list")
    ap.add_argument("--since", default=SINCE, help="deal createdate floor (default %(default)s)")
    ap.add_argument("--execute", action="store_true", help="write; default is a dry run")
    ap.add_argument("--backup-dir", default=".", help="where the pre-write backup JSON goes")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")

    aliases, domains, _ = load_school_aliases()
    print(f"alias file: {len(set(aliases.values()))} canonical schools, {len(aliases)} spellings, {len(domains)} domains")

    resolved, by_tor, unknown, ndeals = teacher_schools_from_deals(aliases, args.since)
    print(f"charter deals since {args.since}: {ndeals} → {len(resolved)} distinct TOR emails with a school")
    if unknown:
        print(f"\n!! {sum(unknown.values())} deals carry {len(unknown)} student_school spellings NOT in {ALIAS_FILE.name} — add them:")
        for raw, n in unknown.most_common():
            print(f"     {n:5}  {raw!r}")

    if args.all_tor:
        contacts = search_all("contacts", [{"propertyName": "a_persona", "operator": "CONTAINS_TOKEN", "value": TOR_PERSONA}],
                              ["email", TARGET_PROP])
        src = f"a_persona = {TOR_PERSONA!r}"
    else:
        contacts = batch_read("contacts", list_members(args.list), ["email", TARGET_PROP])
        src = f"list {args.list}"
    rows = resolve_contacts(contacts, resolved, domains)
    print(f"\ncontacts from {src}: {len(rows)}")

    by_how = collections.Counter(r["how"] or "UNRESOLVED" for r in rows)
    print("resolution:", dict(by_how))
    multi = [r for r in rows if r["how"] == "deal" and len(by_tor[_key(r["email"])]) > 1]
    if multi:
        print(f"{len(multi)} teachers named on deals for >1 canonical school (most common wins):")
        for r in multi[:15]:
            print(f"     {r['email'][:42]:42} {dict(by_tor[_key(r['email'])])}")
    unresolved = [r for r in rows if not r["school"]]
    if unresolved:
        print(f"\n{len(unresolved)} UNRESOLVED (no deal, no known domain) — not written:")
        for r in unresolved:
            print(f"     {r['id']:>13}  {r['email']}")
    print("\nschool distribution (to be written):")
    for s, n in collections.Counter(r["school"] for r in rows if r["school"]).most_common():
        print(f"     {n:4}  {s}")

    todo = [r for r in rows if r["school"] and r["school"] != r["current"]]
    same = sum(1 for r in rows if r["school"] and r["school"] == r["current"])
    print(f"\nwrites needed: {len(todo)}  (already correct: {same}, unresolved: {len(unresolved)})")
    if not args.execute:
        print("DRY RUN — nothing written. Re-run with --execute.")
        return

    backup = Path(args.backup_dir) / f"school_canonical_backup_{date.today().isoformat()}.json"
    backup.write_text(json.dumps({r["id"]: r["current"] for r in todo}, indent=1))
    print(f"backup of current {TARGET_PROP} for {len(todo)} contacts → {backup}")
    ok = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        hs("POST", "/crm/v3/objects/contacts/batch/update",
           json={"inputs": [{"id": r["id"], "properties": {TARGET_PROP: r["school"]}} for r in chunk]})
        ok += len(chunk)
        print(f"  {ok}/{len(todo)}", end="\r")
        time.sleep(0.2)
    print(f"\nwrote {TARGET_PROP} on {ok} contacts")


if __name__ == "__main__":
    main()
