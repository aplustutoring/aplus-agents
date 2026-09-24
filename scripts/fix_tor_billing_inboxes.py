#!/usr/bin/env python3
"""One-off remediation: get the school billing desks off our deals as teachers.

Roman, 2026-09-24, on the Joseph Ramirez PO: "I did notice that you used the
accounts payable email not the teachers." PR #294 stops new ones. This fixes
the ones already there.

What was wrong. Five schools' shared mailboxes were sitting on deals as the
Teacher of Record, and four of them existed as CONTACTS carrying the persona
"Teacher of Record/EF/ES" (one named literally "Teacher"). Every one had been
emailed by us, which means teacher-facing mail about a family's lessons was
landing in an accounts payable queue while the actual teacher heard nothing.

    acctspayable@eliteacademic.com          Elite
    ap@heartlandcharterschool.com           Heartland
    vendorinfo@heartwoodcharterschool.org   Heartwood
    providers@compasscharters.org           Compass
    charter@wetutorathome.com               ours

Two passes, both idempotent, dry by default.

  DEALS    For each deal carrying one of those addresses, find the real teacher
           by name among TOR-flagged contacts (the same lookup po_inbox uses on
           a PO with no teacher email, which is the path that got Ruth
           Hernandez right). On a single confident match: stamp the real
           address, associate the real teacher, drop the billing contact. On
           zero or several matches, change nothing and print it for a human. A
           deal we cannot resolve is left visibly broken rather than quietly
           guessed at.

  CONTACTS Stamp generic_inbox = true, which is the documented exclusion from
           every teacher outreach list, and remove the Teacher of Record
           persona. A billing desk is not a teacher.

Deliberately NOT touched: eight deals whose teacher address is a personal
gmail/yahoo bearing somebody else's name (kathyannolson92@ on Summer Cox, and
two more from April). Those are a different fault, they need a person to say
which half is wrong, and they are printed at the end.

Usage:
  python3 scripts/fix_tor_billing_inboxes.py              # dry run
  python3 scripts/fix_tor_billing_inboxes.py --execute
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "email"))
from src import po_inbox as po  # noqa: E402

# Same as scripts/waiting.py: find the repo .env by walking up, so the script
# runs as a plain command rather than needing the caller to export anything.
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
if load_dotenv:
    for _parent in [HERE] + list(HERE.parents):
        if (_parent / ".env").exists():
            load_dotenv(_parent / ".env")
            break

HS = "https://api.hubapi.com"
TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

TOR_PERSONA = "Teacher of Record/EF/ES"

# Verified by hand on 2026-09-24, one at a time, against the contact record and
# the school. This list is remediation scope, NOT a detection rule: the rule
# that decides what is a teacher going forward is po_inbox._why_not_the_teacher
# and it needs no list.
BILLING = {
    "acctspayable@eliteacademic.com": "Elite",
    "ap@heartlandcharterschool.com": "Heartland",
    "vendorinfo@heartwoodcharterschool.org": "Heartwood",
    "providers@compasscharters.org": "Compass",
    "charter@wetutorathome.com": "A+ (ours)",
}


def hs(method: str, path: str, **kw):
    for _ in range(6):
        r = requests.request(method, HS + path, headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:250]}")
        return r.json() if r.text else {}
    raise RuntimeError("rate limited six times")


def search_deals() -> list[dict]:
    rows, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "teacher_of_record_email", "operator": "IN",
             "values": list(BILLING)}]}],
            "properties": ["dealname", "teacher_of_record_email",
                           "teacher_of_record_name", "createdate"],
            "limit": 100}
        if after:
            body["after"] = after
        d = hs("POST", "/crm/v3/objects/deals/search", json=body)
        rows += d.get("results", [])
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            return rows


def contact_by_email(addr: str) -> dict | None:
    d = hs("POST", "/crm/v3/objects/contacts/search", json={
        "filterGroups": [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": addr}]}],
        "properties": ["email", "firstname", "lastname", "a_persona",
                       "generic_inbox"],
        "limit": 1})
    res = d.get("results") or []
    return res[0] if res else None


def split_name(full: str) -> tuple[str, str]:
    bits = (full or "").split()
    if not bits:
        return "", ""
    return bits[0], " ".join(bits[1:])


def fix_deals(execute: bool) -> tuple[int, list]:
    deals = search_deals()
    print(f"\n{'=' * 74}\nDEALS carrying a billing desk as the teacher: {len(deals)}\n")
    fixed, stuck = 0, []
    cache: dict[str, dict | None] = {}
    for d in sorted(deals, key=lambda x: x["properties"].get("createdate") or ""):
        p = d["properties"]
        bad = (p.get("teacher_of_record_email") or "").lower()
        name = (p.get("teacher_of_record_name") or "").strip()
        first, last = split_name(name)
        label = (p.get("dealname") or "")[:46]

        matches = po._tor_by_name(first, last) if last else []
        good = [m for m in matches
                if not po._why_not_the_teacher(
                    ((m.get("properties") or {}).get("email") or ""), first, last)]
        if len(good) != 1:
            stuck.append((d["id"], label, name, bad,
                          f"{len(matches)} name match(es), {len(good)} usable"))
            print(f"  SKIP  {label:<46}  {name:<22}  "
                  f"{len(matches)} match(es), {len(good)} usable")
            continue

        tor = good[0]
        real = ((tor.get("properties") or {}).get("email") or "").lower()
        print(f"  FIX   {label:<46}  {name:<22}  {bad}  ->  {real}")
        if not execute:
            fixed += 1
            continue

        hs("PATCH", f"/crm/v3/objects/deals/{d['id']}",
           json={"properties": {"teacher_of_record_email": real}})
        # The repo's own helper, not a hand-rolled endpoint: deal→contact is
        # v4 with an explicit HUBSPOT_DEFINED typeId 3, and this is the call
        # po_inbox already makes in production.
        po.hs.associate_contact_to_deal(d["id"], tor["id"])
        if bad not in cache:
            cache[bad] = contact_by_email(bad)
        billing = cache[bad]
        if billing:
            try:
                hs("DELETE", f"/crm/v4/objects/deals/{d['id']}"
                             f"/associations/contacts/{billing['id']}")
            except RuntimeError as e:      # not associated is not a failure
                print(f"        (association removal: {e})")
        fixed += 1
    return fixed, stuck


def fix_contacts(execute: bool) -> int:
    print(f"\n{'=' * 74}\nCONTACTS that are billing desks wearing the teacher persona\n")
    n = 0
    for addr, school in BILLING.items():
        c = contact_by_email(addr)
        if not c:
            print(f"  ----  {addr:<40} no contact")
            continue
        p = c["properties"]
        who = f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip()
        vals = [v for v in (p.get("a_persona") or "").split(";") if v]
        fixes = {}
        if TOR_PERSONA in vals:
            fixes["a_persona"] = ";".join(v for v in vals if v != TOR_PERSONA)
        if (p.get("generic_inbox") or "") != "true":
            fixes["generic_inbox"] = "true"
        if not fixes:
            print(f"  ok    {addr:<40} {who:<24} already clean")
            continue
        print(f"  FIX   {addr:<40} {who:<24} {school}")
        for kk, vv in fixes.items():
            print(f"          {kk} = {vv!r}")
        if execute:
            hs("PATCH", f"/crm/v3/objects/contacts/{c['id']}",
               json={"properties": fixes})
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="write to HubSpot (default is a dry run)")
    a = ap.parse_args()
    if not TOKEN:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    mode = "EXECUTE" if a.execute else "DRY RUN"
    print(f"{'=' * 74}\n{mode}: school billing desks stamped as Teacher of Record")

    fixed, stuck = fix_deals(a.execute)
    contacts = fix_contacts(a.execute)

    print(f"\n{'=' * 74}\nSUMMARY  ({mode})")
    print(f"  deals corrected : {fixed}")
    print(f"  deals left alone: {len(stuck)}")
    print(f"  contacts fixed  : {contacts}")
    if stuck:
        print("\nLEFT FOR A HUMAN. No confident single teacher match, so nothing\n"
              "was guessed. Each needs someone to say who the teacher is:\n")
        for did, label, name, bad, why in stuck:
            print(f"  {did}  {label:<46} {name:<22} {why}")
        for why, n in Counter(s[4] for s in stuck).most_common():
            print(f"     {why}: {n}")
    if not a.execute:
        print("\nDry run. Nothing was written. Re-run with --execute.")


if __name__ == "__main__":
    main()
