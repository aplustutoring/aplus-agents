#!/usr/bin/env python3
"""Cross-reference every contact on a school domain against the teacher contract.

Roman, 2026-09-25: "so do a full run of all of the domains that we have for
teacher emails and cross reference so that they have the right personas?"

Why domains and not names. Name lookups are fragile in a way that keeps costing
us real teachers. Dianna Gregorie is contact 247427104125
<dgregorie@eliteacademic.com>, and `lastname EQ 'Gregorie'` returns NOTHING
because her record carries dirty whitespace, so two live Joseph Cruz deals
pointed at accounts payable while she sat in the portal. Holly Oregel is the
same shape: on Sarah Sheridan's record in plain sight, with no persona, so the
TOR-only lookup could not see her. A domain is exact and survives dirty names.

What "the right persona" means (po_inbox.TOR_CREATE):
    a_persona       Teacher of Record/EF/ES     append-only, never exclusive
    hs_lead_status  Charter School Teacher TOR/EF
    owner           the sales seat (Danielle, #AP046)

Who EARNS it. Not everyone with a school address is a teacher of record: a
principal, an office manager or somebody we met at a conference is not. So the
persona is granted only on evidence that we already treat them as one:

    a. they are the teacher_of_record_email on at least one DEAL, or
    b. they are the teacher_of_record_email_address on at least one CONTACT
       (the family's own record, the field Kath reads by eye), or
    c. they already carry the TOR lead status.

Role mailboxes go the other way: `generic_inbox = true`, which is the
documented exclusion from every teacher outreach list, and no TOR persona. A
billing desk is not a teacher. Whether an address is a person is decided by
po_inbox._why_not_the_teacher against the contact's own name, not by a word
list, because five schools have already outrun the word lists.

Usage:
  python3 scripts/teacher_persona_sweep.py            # dry run
  python3 scripts/teacher_persona_sweep.py --execute
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "email"))
from src import po_inbox as po  # noqa: E402
from src.config import staff  # noqa: E402

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
if load_dotenv:
    for _p in [HERE] + list(HERE.parents):
        if (_p / ".env").exists():
            load_dotenv(_p / ".env")
            break

HS = "https://api.hubapi.com"
TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

ALIASES = HERE.parent / "ops" / "hubspot-schema" / "school-aliases.yml"
PERSONA = "Teacher of Record/EF/ES"
LEAD = "Charter School Teacher TOR/EF"
PROPS = ["email", "firstname", "lastname", "a_persona", "hs_lead_status",
         "hubspot_owner_id", "generic_inbox", "school_canonical",
         "teacher_of_record_email_address"]


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


def page(path: str, body: dict) -> list[dict]:
    out, after = [], None
    while True:
        b = dict(body)
        if after:
            b["after"] = after
        d = hs("POST", path, json=b)
        out += d.get("results", [])
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            return out


def school_domains() -> dict:
    with open(ALIASES) as f:
        return (yaml.safe_load(f) or {}).get("domains") or {}


# Local parts that are a job, not a person. Used ONLY when the contact carries
# no name at all, so there is nothing to compare the address against. Where a
# name exists, _why_not_the_teacher decides and this list is not consulted.
_ROLE_SHAPE = re.compile(
    r"^(?:[a-z]*[._-])?(?:no-?reply|info|office|admin|administration|support|help|"
    r"contact|hello|purchas\w*|account\w*|acct\w*|ap|ar|payable\w*|billing|"
    r"invoic\w*|vendor\w*|po|pos|purchaseorder\w*|order\w*|frontdesk|reception|"
    r"school|team|staff|hr|payroll|finance|business\w*|program\w*|enroll\w*|"
    r"registrar|scheduling|provider\w*|charter|marketing|portal|studentservices)"
    r"(?:[._-][a-z]*)?$", re.I)


# Name fields holding something that is not a person's name. Real examples
# from the portal: firstname 'Teacher', firstname 'Compass' / lastname
# 'Charter Schools', firstname 'Excel Academy Charter School'.
_JUNK_NAME = re.compile(r"\b(charter|academy|school|schools|learning cent|"
                        r"teacher|vendor|office|admin|info|support|district|"
                        r"education|unknown|n/?a)\b", re.I)


def junk_name(first: str, last: str) -> bool:
    whole = f"{first or ''} {last or ''}".strip()
    return bool(whole) and bool(_JUNK_NAME.search(whole))


def classify(email: str, first: str, last: str) -> str:
    """person | role mailbox | unknown.

    Only a role-SHAPED address is a role mailbox. A mismatch between the name
    and the address is NOT evidence of one, because it has three very
    different causes and this sweep cannot tell them apart:

        acctspayable@eliteacademic.com   the address is a billing desk
        sgtrivino@compasscharters.org    firstname is literally 'Teacher'
        jf11525@bestacademycs.com        Jorge Flores, at a school that issues
                                         initials-and-number addresses

    The first draft treated all three as role mailboxes and would have stamped
    generic_inbox on the last two, excluding real teachers from every outreach
    list. That is the harm this sweep exists to undo, so a mismatch now means
    "cannot tell" and nothing is written.
    """
    local = (email or "").split("@")[0].strip().lower()
    if not local:
        return "unknown"
    if _ROLE_SHAPE.match(local):
        return "role mailbox"
    if (first or last) and not junk_name(first, last) \
            and not po._why_not_the_teacher(email, first, last):
        return "person"
    return "unknown"


def contacts_on(domain: str) -> list[dict]:
    """Everyone at this school. hs_email_domain is exact, so dirty names and
    odd capitalisation cannot hide anybody."""
    return page("/crm/v3/objects/contacts/search", {
        "filterGroups": [{"filters": [
            {"propertyName": "hs_email_domain", "operator": "EQ", "value": domain}]}],
        "properties": PROPS, "limit": 100})


def teachers_named_on_deals() -> set:
    """Every address we have ever treated as a teacher of record on a DEAL."""
    rows = page("/crm/v3/objects/deals/search", {
        "filterGroups": [{"filters": [
            {"propertyName": "teacher_of_record_email", "operator": "HAS_PROPERTY"}]}],
        "properties": ["teacher_of_record_email"], "limit": 100})
    return {(r["properties"].get("teacher_of_record_email") or "").strip().lower()
            for r in rows} - {""}


def teachers_named_on_families() -> set:
    """And every address a FAMILY named as their child's teacher."""
    rows = page("/crm/v3/objects/contacts/search", {
        "filterGroups": [{"filters": [
            {"propertyName": "teacher_of_record_email_address",
             "operator": "HAS_PROPERTY"}]}],
        "properties": ["teacher_of_record_email_address"], "limit": 100})
    return {(r["properties"].get("teacher_of_record_email_address") or "").strip().lower()
            for r in rows} - {""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--limit-domains", type=int, default=0,
                    help="only the first N domains (for a quick look)")
    a = ap.parse_args()
    if not TOKEN:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    mode = "EXECUTE" if a.execute else "DRY RUN"
    sales = staff("sales") or {}
    print(f"{'=' * 78}\n{mode}: teacher personas across every school domain")
    print(f"sales seat: {sales.get('name')} ({sales.get('hubspot_owner_id')})")

    domains = school_domains()
    if a.limit_domains:
        domains = dict(list(domains.items())[:a.limit_domains])
    print(f"domains: {len(domains)}")

    print("building the evidence set (who we already treat as a teacher)...")
    evidence = teachers_named_on_deals() | teachers_named_on_families()
    print(f"  addresses named as a teacher of record somewhere: {len(evidence)}\n")

    tally = Counter()
    grant, flag, unknown, junk, already = [], [], [], [], 0
    by_school = defaultdict(Counter)

    for domain, school in sorted(domains.items()):
        people = contacts_on(domain)
        if not people:
            continue
        for c in people:
            p = c["properties"]
            em = (p.get("email") or "").strip().lower()
            first = (p.get("firstname") or "").strip()
            last = (p.get("lastname") or "").strip()
            vals = [v for v in (p.get("a_persona") or "").split(";") if v]
            has_persona = PERSONA in vals
            verdict = classify(em, first, last)
            tally[verdict] += 1
            if junk_name(first, last):
                junk.append((c["id"], em, school, f"{first} {last}".strip()))
            if verdict == "unknown":
                # No name on the contact and nothing role-shaped in the address.
                # The first draft of this sweep called that a role mailbox, and
                # it wanted to stamp generic_inbox on hugo.ramos@springscs.org,
                # janet.ilko@springscs.org and michelle.varju@theblueridge...
                # — real people whose contacts simply have no first/last name.
                # That would have excluded them from every teacher outreach
                # list, which is the exact harm this sweep exists to undo.
                # An absence of evidence is not evidence.
                unknown.append((c["id"], em, school))
                continue

            if verdict == "role mailbox":
                fixes = {}
                if (p.get("generic_inbox") or "") != "true":
                    fixes["generic_inbox"] = "true"
                if has_persona:
                    fixes["a_persona"] = ";".join(v for v in vals if v != PERSONA)
                if fixes:
                    flag.append((c["id"], em, school, fixes))
                continue

            earns = em in evidence or (p.get("hs_lead_status") or "") == LEAD
            if not earns:
                tally["person, no teacher evidence — left alone"] += 1
                by_school[school]["no evidence"] += 1
                continue
            fixes = {}
            if not has_persona:
                fixes["a_persona"] = ";".join(vals + [PERSONA])
            if (p.get("hs_lead_status") or "") != LEAD and "Family" not in vals:
                fixes["hs_lead_status"] = LEAD
            if str(p.get("hubspot_owner_id") or "") != str(sales.get("hubspot_owner_id")):
                fixes["hubspot_owner_id"] = str(sales.get("hubspot_owner_id"))
            if not (p.get("school_canonical") or "").strip():
                fixes["school_canonical"] = school
            if fixes:
                grant.append((c["id"], em, school, first, last, fixes))
                by_school[school]["to fix"] += 1
            else:
                already += 1
                by_school[school]["already right"] += 1

    print(f"{'=' * 78}\nTEACHERS TO CORRECT: {len(grant)}\n")
    for cid, em, school, first, last, fixes in grant[:60]:
        who = f"{first} {last}".strip() or "(no name)"
        print(f"  {cid:<14} {who[:24]:<24} {em[:38]:<38} {school[:18]}")
        print(f"       {', '.join(sorted(fixes))}")
    if len(grant) > 60:
        print(f"  ... and {len(grant) - 60} more")

    print(f"\n{'=' * 78}\nROLE MAILBOXES TO FLAG: {len(flag)}\n")
    for cid, em, school, fixes in flag:
        print(f"  {cid:<14} {em[:44]:<44} {school[:18]}  {', '.join(sorted(fixes))}")

    print(f"\n{'=' * 78}\nNO NAME, NOT ROLE-SHAPED — LEFT ALONE: {len(unknown)}\n")
    for cid, em, school in unknown[:40]:
        print(f"  {cid:<14} {em[:44]:<44} {school[:18]}")
    if len(unknown) > 40:
        print(f"  ... and {len(unknown) - 40} more")
    print("  These need a first/last name on the contact before anything can be"
          "\n  decided about them. Naming them is a separate, safe pass.")

    print(f"\n{'=' * 78}\nNAME FIELDS HOLDING JUNK: {len(junk)}\n")
    print("  The address is fine; the NAME is not a person's name. Nothing here is\n"
          "  written by this sweep, but these are real teachers we cannot address\n"
          "  properly in any email, and outreach copy would greet them by it.\n")
    for cid, em, school, nm in junk[:40]:
        print(f"  {cid:<14} {em[:40]:<40} name={nm[:30]!r}")
    if len(junk) > 40:
        print(f"  ... and {len(junk) - 40} more")

    print(f"\n{'=' * 78}\nBY SCHOOL")
    for school, c in sorted(by_school.items(), key=lambda x: -sum(x[1].values())):
        print(f"  {school[:30]:<30} fix {c['to fix']:>3}   ok {c['already right']:>3}"
              f"   no evidence {c['no evidence']:>3}")

    print(f"\n{'=' * 78}\nSUMMARY ({mode})")
    for kk, vv in tally.most_common():
        print(f"  {kk:<44} {vv}")
    print(f"  {'already correct':<44} {already}")
    print(f"  {'teachers to correct':<44} {len(grant)}")
    print(f"  {'role mailboxes to flag':<44} {len(flag)}")
    print(f"  {'left alone, cannot tell':<44} {len(unknown)}")
    print(f"  {'name fields holding junk':<44} {len(junk)}")

    if not a.execute:
        print("\nDry run. Nothing was written. Re-run with --execute.")
        return
    n = 0
    for cid, _em, _school, _f, _l, fixes in grant:
        hs("PATCH", f"/crm/v3/objects/contacts/{cid}", json={"properties": fixes})
        n += 1
    for cid, _em, _school, fixes in flag:
        hs("PATCH", f"/crm/v3/objects/contacts/{cid}", json={"properties": fixes})
        n += 1
    print(f"\nwrote {n} contact(s)")


if __name__ == "__main__":
    main()
