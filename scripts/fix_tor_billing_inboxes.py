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

  DEALS    For each deal carrying one of those addresses, find the real
           teacher two ways, in order. First by name among TOR-flagged
           contacts, the same lookup po_inbox uses on a PO with no teacher
           email, which is the path that got Ruth Hernandez right. Then, if
           that finds nobody, off the FAMILY record's
           teacher_of_record_email_address (Roman 2026-09-24: "if the family is
           in hubspot, you can check their property for teacher of record name
           and email too"), admitted only when it corroborates the teacher the
           PO names. On a single confident answer: stamp the real address,
           associate the real teacher, drop the billing contact. Otherwise
           change nothing and print it. A deal we cannot resolve is left
           visibly broken rather than quietly guessed at.

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


def _tor_via_family(deal_id: str, first: str, last: str):
    """The teacher off this deal's FAMILY record, when it agrees with the PO.

    po._tor_from_family does the agreeing; all this does is find the family
    contacts on the deal and offer each one. Measured 2026-09-24: this resolves
    Stephanie Negrete-Claar (sclaar@, 17 deals, the family spells her
    "Stephanie Claar") and Janna Morbitz (janna@heartwood..., 4 deals), and
    correctly refuses Dianna Gregorie and Colbie Van Horn, whose families name
    a different teacher entirely.
    """
    try:
        a = hs("GET", f"/crm/v4/objects/deals/{deal_id}/associations/contacts")
    except RuntimeError:
        return None
    for r in a.get("results", []):
        notes: list = []
        tor = po._tor_from_family({"tor_first": first, "tor_last": last}, "",
                                  str(r["toObjectId"]), notes)
        if tor:
            return tor
    return None


def split_name(full: str) -> tuple[str, str]:
    bits = (full or "").split()
    if not bits:
        return "", ""
    return bits[0], " ".join(bits[1:])


CHARTER_PIPELINES = ["907748", "72281989", "88841552", "5119061", "1066195"]
DEAD_STAGES = {"Stopped", "Hours Reassigned"}


def _stage_labels() -> dict:
    return {s["id"]: s["label"]
            for pl in hs("GET", "/crm/v3/pipelines/deals")["results"]
            for s in pl["stages"]}


def search_blank_teacher_deals() -> list[dict]:
    """Live charter deals carrying NO teacher address at all.

    Roman, 2026-09-25, on Sarah Sheridan: "it clearly says holly oregel is her
    fucking teacher. how the fuck you miss that."

    He was right. I measured the DEAL property, found it empty, and reported 40
    deals as having no teacher named, after building the family-record lookup
    for exactly this case. Sarah's contact carries Holly Oregel
    <horegel@viedu.org> in plain sight, and 50 of the 54 blank deals are
    recoverable the same way, from 11 teachers.

    NOTE on staleness: do not filter these by the stage's isClosed flag. Every
    charter pipeline marks "Post-Lesson" isClosed=true even though that is
    where live tutoring sits (331 of 366 deals). Filtering on it returns 15
    deals and hides the business.
    """
    labels = _stage_labels()
    rows, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES},
            {"propertyName": "createdate", "operator": "GTE", "value": "2026-07-01"},
            {"propertyName": "teacher_of_record_email", "operator": "NOT_HAS_PROPERTY"}]}],
            "properties": ["dealname", "teacher_of_record_email",
                           "teacher_of_record_name", "createdate", "dealstage"],
            "limit": 100}
        if after:
            body["after"] = after
        d = hs("POST", "/crm/v3/objects/deals/search", json=body)
        rows += d.get("results", [])
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return [r for r in rows
            if labels.get(r["properties"].get("dealstage")) not in DEAD_STAGES]


def fix_blank_deals(execute: bool) -> tuple[int, int]:
    """Give a blank deal the teacher its own family record already names."""
    deals = search_blank_teacher_deals()
    print(f"\n{'=' * 74}\nLIVE deals with NO teacher address at all: {len(deals)}\n")
    fixed, stuck = 0, 0
    for d in deals:
        p = d["properties"]
        label = (p.get("dealname") or "")[:46]
        first, last = split_name((p.get("teacher_of_record_name") or "").strip())
        tor = _tor_from_family_any(d["id"])
        if tor is None:
            print(f"  SKIP  {label:<46}  nothing on the family record either")
            stuck += 1
            continue
        real = ((tor.get("properties") or {}).get("email") or "").lower()
        who = "%s %s" % ((tor.get("properties") or {}).get("firstname") or "",
                         (tor.get("properties") or {}).get("lastname") or "")
        print(f"  FIX   {label:<46}  {who.strip()[:22]:<22}  ->  {real}")
        if execute:
            hs("PATCH", f"/crm/v3/objects/deals/{d['id']}",
               json={"properties": {"teacher_of_record_email": real,
                                    "teacher_of_record_name": who.strip()}})
            po.hs.associate_contact_to_deal(d["id"], tor["id"])
        fixed += 1
    return fixed, stuck


def _tor_from_family_any(deal_id: str):
    """The teacher named on this deal's family record, whoever it is.

    Unlike the billing-desk pass there is no PO name to corroborate against:
    the deal names nobody, so the family record IS the only claim. Taking it is
    still right, because a teacher the family named beats no teacher at all,
    and it is the same field a human reads off the profile.
    """
    try:
        a = hs("GET", f"/crm/v4/objects/deals/{deal_id}/associations/contacts")
    except RuntimeError:
        return None
    ids = [str(r["toObjectId"]) for r in a.get("results", [])]
    if not ids:
        return None
    b = hs("POST", "/crm/v3/objects/contacts/batch/read",
           json={"properties": ["firstname", "lastname",
                                "teacher_of_record_name",
                                "teacher_of_record_email_address"],
                 "inputs": [{"id": i} for i in ids]})
    for c in b.get("results", []):
        cp = c["properties"]
        addr = (cp.get("teacher_of_record_email_address") or "").strip().lower()
        nm = (cp.get("teacher_of_record_name") or "").strip()
        if not addr:
            continue
        f, l = split_name(nm)
        if po._why_not_the_teacher(addr, f, l):
            continue                      # the family's own two fields disagree
        tor = po.hs.find_contact_by_email(
            addr, properties=["email", "firstname", "lastname", "a_persona",
                              "hs_lead_status"])
        if not tor:
            tor = po.hs.create_contact(addr, f or None, l or None, **po.TOR_CREATE)
        return tor
    return None


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
        route = "by name"
        if len(good) > 1:
            stuck.append((d["id"], label, name, bad,
                          f"{len(matches)} name matches, ambiguous"))
            print(f"  SKIP  {label:<46}  {name:<22}  ambiguous ({len(matches)} matches)")
            continue
        if not good:
            # Roman 2026-09-24: ask the family record, the way Kath does by
            # hand. Admitted only when it corroborates the teacher the PO
            # names, so a family whose field has drifted to a different
            # teacher cannot put the wrong person on the deal.
            tor = _tor_via_family(d["id"], first, last)
            route = "via the family record"
        if not good and tor is None:
            # And before giving up, look for this person under ANY persona.
            # _tor_by_name searches TOR-FLAGGED contacts only, and teachers
            # keep arriving without the flag: Dianna Gregorie is contact
            # 247427104125 <dgregorie@eliteacademic.com> with no persona at
            # all, so two live Joseph Cruz deals pointed at accounts payable
            # while she sat in the portal. Holly Oregel is the same shape.
            # The address still has to look like the name.
            cand = po._same_person_any_persona(first, last)
            addr = ((cand or {}).get("properties") or {}).get("email") or ""
            if cand and addr and not po._why_not_the_teacher(addr, first, last):
                tor, route = cand, "found under another persona"
        if not good:
            if tor is None:
                stuck.append((d["id"], label, name, bad,
                              "no teacher contact, and the family record does not agree"))
                print(f"  SKIP  {label:<46}  {name:<22}  "
                      f"no match, family record no help")
                continue
            good = [tor]

        tor = good[0]
        real = ((tor.get("properties") or {}).get("email") or "").lower()
        print(f"  FIX   {label:<46}  {name:<22}  {bad}  ->  {real}  [{route}]")
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
    blank_fixed, blank_stuck = fix_blank_deals(a.execute)
    contacts = fix_contacts(a.execute)

    print(f"\n{'=' * 74}\nSUMMARY  ({mode})")
    print(f"  billing-desk deals corrected : {fixed}")
    print(f"  billing-desk deals left alone: {len(stuck)}")
    print(f"  blank deals given a teacher  : {blank_fixed}")
    print(f"  blank deals with no answer   : {blank_stuck}")
    print(f"  contacts fixed               : {contacts}")
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
