#!/usr/bin/env python3
"""Stamp a canonical school onto teacher (TOR/EF/ES) contacts, and flag
generic (shared/role) inboxes so teacher lists can exclude them.

Roman 2026-09-02: teacher contacts had no usable school field, so every
teacher segmentation was a guess parsed from the email domain. Three sources
in HubSpot already know the school, and this script uses them in order of
specificity, never guessing:

  1. DEALS   charter deals where teacher_of_record_email == contact email →
             student_school (96% filled), canonicalised through
             ops/hubspot-schema/school-aliases.yml. Unanimous wins outright.
  2. INTAKE  contact enumeration `charter_school_teacher` (LABEL, per the
             enumeration rule), filled on 1,075/1,086 teachers and agreeing
             with deals 217/218 times. Wins over a SPLIT deal vote.
  3. DOMAIN  email-domain fallback from the alias file — every domain there
             was verified against intake and the school's own website.
  4. unresolved → reported, NOT written.

A deal ↔ intake disagreement is reported. A network-level intake label (IEM,
Pacific Charter Institute, iLEAD) is not a disagreement with one of its own
schools; the deal's specific school wins.

Generic inboxes (purchasing@, invoices@, studentservices@, info@, noreply@ …)
are detected from the email local-part and stamped `generic_inbox = Yes`
("keep generic inboxes separate"). They still get a school. Internal test
contacts (@wetutorathome.com) and contacts with no email are skipped.

Unknown deal spellings / intake labels are reported loudly so the alias file
stays complete. iLEAD is ONE bucket (Roman 2026-09-02).

Read-only by default. --execute writes (backs up current values first).

  python3 scripts/teacher_school_stamp.py                 # list 3110, dry run
  python3 scripts/teacher_school_stamp.py --all-tor       # every TOR-persona contact
  python3 scripts/teacher_school_stamp.py --all-tor --execute
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
SCHOOL_PROP = "school_canonical"
GENERIC_PROP = "generic_inbox"
INTAKE_PROP = "charter_school_teacher"   # intake enumeration; read the LABEL
TOR_LIST_ID = 3110                       # Charter 26/27 Gap - TORs - Worked With Us
TOR_PERSONA = "Teacher of Record/EF/ES"  # a_persona LABEL (== value for this option)
CHARTER_PIPELINES = ["907748", "72281989", "88841552", "5119061", "1066195"]
SINCE = "2025-08-01"
INTERNAL_DOMAINS = {"wetutorathome.com"}

# Shared/role mailboxes. Anchored words on the whole local-part, plus a few
# substrings that only ever appear in role addresses.
_ROLE_WORDS = (r"no-?reply|info|office|admin|support|help|contact|hello|purchasing|accounts?|accounting|"
               r"ap|ar|billing|invoices?|vendors?|po|pos|purchaseorders?|orders?|frontdesk|reception|"
               r"school|team|staff|hr|payroll|finance|programs?|enrollment|registrar|scheduling")
GENERIC_LOCALPART = re.compile(
    rf"^(?:{_ROLE_WORDS})$|^(?:[a-z]+[._-])?(?:{_ROLE_WORDS})$|relations|purchasing|inquir|invoice|"
    r"purchaseorder|studentservices|businessservices|business\.services|contractprogram|noreply|no-reply",
    re.I)


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


def enum_labels(object_type, prop):
    """value -> LABEL for an enumeration property (agents read labels)."""
    return {o["value"]: o["label"] for o in hs("GET", f"/crm/v3/properties/{object_type}/{prop}").get("options", [])}


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


def is_generic(email):
    return bool(GENERIC_LOCALPART.search(_key(email).split("@")[0]))


# ── resolution ─────────────────────────────────────────────────────────────
def teacher_schools_from_deals(aliases, since=SINCE):
    """tor_email -> canonical (unanimous or most common, most recent breaks ties).
    Returns (resolved, by_tor Counter map, unknown spellings, deal count)."""
    since_ms = int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000)
    deals = search_all("deals", [
        {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES},
        {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)},
    ], ["teacher_of_record_email", "student_school", "createdate"],
        sorts=[{"propertyName": "createdate", "direction": "DESCENDING"}])
    by_tor, unknown = collections.defaultdict(collections.Counter), collections.Counter()
    latest = {}
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


def _compatible(specific, bucket, networks):
    """A network-level label (IEM, PCI, iLEAD) agrees with any of its own schools."""
    return specific == bucket or networks.get(specific) == bucket


def resolve_contacts(contacts, resolved, by_tor, domains, aliases, networks, intake_labels):
    rows, unknown_intake = [], collections.Counter()
    for cid, p in contacts.items():
        email = _key(p.get("email"))
        row = {"id": cid, "email": p.get("email") or "", "name": f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip(),
               "current": (p.get(SCHOOL_PROP) or "").strip(), "current_generic": (p.get(GENERIC_PROP) or "") == "true",
               "school": None, "how": None, "note": None, "generic": False, "skip": None}
        if not email:
            row["skip"] = "no email"
        elif email.split("@")[-1] in INTERNAL_DOMAINS:
            row["skip"] = "internal/test"
        if row["skip"]:
            rows.append(row)
            continue
        row["generic"] = is_generic(email)

        deal_c = resolved.get(email)
        split = len(by_tor.get(email, {})) > 1
        label = intake_labels.get(p.get(INTAKE_PROP) or "", p.get(INTAKE_PROP) or "")
        intake_c = aliases.get(_key(label)) if label else None
        if label and not intake_c:
            unknown_intake[label] += 1
        dom_c = domains.get(email.split("@")[-1])

        if deal_c and intake_c and not _compatible(deal_c, intake_c, networks):
            if split:
                row["school"], row["how"] = intake_c, "intake"
                row["note"] = f"deal split {dict(by_tor[email])} → intake wins"
            else:
                row["school"], row["how"] = deal_c, "deal"
                row["note"] = f"intake says {intake_c!r}, deals unanimous"
        elif deal_c:
            row["school"], row["how"] = deal_c, "deal"
        elif intake_c:
            row["school"], row["how"] = intake_c, "intake"
            if dom_c and not _compatible(intake_c, dom_c, networks) and not _compatible(dom_c, intake_c, networks):
                row["note"] = f"domain says {dom_c!r}"
        elif dom_c:
            row["school"], row["how"] = dom_c, "domain"
        rows.append(row)
    return rows, unknown_intake


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

    aliases, domains, networks = load_school_aliases()
    print(f"alias file: {len(set(aliases.values()))} canonical schools, {len(aliases)} spellings, {len(domains)} domains")
    intake_labels = enum_labels("contacts", INTAKE_PROP)

    resolved, by_tor, unknown, ndeals = teacher_schools_from_deals(aliases, args.since)
    print(f"charter deals since {args.since}: {ndeals} → {len(resolved)} distinct TOR emails with a school")
    if unknown:
        print(f"\n!! {sum(unknown.values())} deals carry {len(unknown)} student_school spellings NOT in {ALIAS_FILE.name} — add them:")
        for raw, n in unknown.most_common():
            print(f"     {n:5}  {raw!r}")

    props = ["email", "firstname", "lastname", INTAKE_PROP, SCHOOL_PROP, GENERIC_PROP]
    if args.all_tor:
        contacts = search_all("contacts", [{"propertyName": "a_persona", "operator": "CONTAINS_TOKEN", "value": TOR_PERSONA}], props)
        src = f"a_persona = {TOR_PERSONA!r}"
    else:
        contacts = batch_read("contacts", list_members(args.list), props)
        src = f"list {args.list}"
    rows, unknown_intake = resolve_contacts(contacts, resolved, by_tor, domains, aliases, networks, intake_labels)
    print(f"\ncontacts from {src}: {len(rows)}")
    if unknown_intake:
        print(f"!! {INTAKE_PROP} labels NOT in the alias file: {dict(unknown_intake)}")

    live = [r for r in rows if not r["skip"]]
    print("resolution:", dict(collections.Counter(r["how"] or "UNRESOLVED" for r in live)))
    skipped = [r for r in rows if r["skip"]]
    if skipped:
        print(f"skipped {len(skipped)}: " + "; ".join(f"{r['id']} {r['email'] or r['name']!r} ({r['skip']})" for r in skipped))
    noted = [r for r in live if r["note"]]
    if noted:
        print(f"\n{len(noted)} source disagreements (resolved as shown, worth a human look):")
        for r in noted:
            print(f"     {r['email'][:44]:44} → {r['school']!r:36} {r['note']}")
    generic = [r for r in live if r["generic"]]
    print(f"\n{len(generic)} generic inboxes (stamped {GENERIC_PROP}=Yes, still get a school):")
    for r in generic:
        print(f"     {r['email'][:44]:44} {r['name'][:32]:32} → {r['school']}")
    unresolved = [r for r in live if not r["school"]]
    if unresolved:
        print(f"\n{len(unresolved)} UNRESOLVED (no deal, no intake, no known domain) — not written:")
        for r in unresolved:
            print(f"     {r['id']:>13}  {r['email']:44} {r['name']}")
    print("\nschool distribution (to be written):")
    for s, n in collections.Counter(r["school"] for r in live if r["school"]).most_common():
        print(f"     {n:4}  {s}")

    todo = []
    for r in live:
        upd = {}
        if r["school"] and r["school"] != r["current"]:
            upd[SCHOOL_PROP] = r["school"]
        if r["generic"] and not r["current_generic"]:
            upd[GENERIC_PROP] = "true"
        if upd:
            todo.append((r, upd))
    n_school = sum(1 for _, u in todo if SCHOOL_PROP in u)
    n_generic = sum(1 for _, u in todo if GENERIC_PROP in u)
    print(f"\nwrites needed: {len(todo)} contacts ({n_school} school, {n_generic} generic flag); "
          f"already correct: {len(live) - len(unresolved) - n_school}; unresolved: {len(unresolved)}")
    if not args.execute:
        print("DRY RUN — nothing written. Re-run with --execute.")
        return
    if not todo:
        return

    backup = Path(args.backup_dir) / f"teacher_school_backup_{date.today().isoformat()}.json"
    backup.write_text(json.dumps({r["id"]: {SCHOOL_PROP: r["current"], GENERIC_PROP: r["current_generic"]} for r, _ in todo}, indent=1))
    print(f"backup of current values for {len(todo)} contacts → {backup}")
    ok = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        hs("POST", "/crm/v3/objects/contacts/batch/update",
           json={"inputs": [{"id": r["id"], "properties": u} for r, u in chunk]})
        ok += len(chunk)
        print(f"  {ok}/{len(todo)}", end="\r")
        time.sleep(0.2)
    print(f"\nwrote {ok} contacts")


if __name__ == "__main__":
    main()
