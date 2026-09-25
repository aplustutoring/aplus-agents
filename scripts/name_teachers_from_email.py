#!/usr/bin/env python3
"""Name the unnamed teachers from the emails they sent us.

Roman, 2026-09-25: "i am confident we can figure out rules so that all of
possible teachers are linked."

He was right and I was wrong, for the third time in a day. I had checked two
structured fields — the deal's teacher_of_record_name and the family's
teacher_of_record_name — found nothing, and reported that no record names
these contacts. I had not checked the emails ON the contact. When a teacher
writes to us, the From header carries their real name:

    awatters@eliteacademic.com       (blank)        ->  Allison Watters
    kmason@eliteacademic.com         (blank)        ->  Kristine Mason
    kconstanza@compasscharters.org   "Compass..."   ->  Kimberly Constanza

Two gates, because a From header is not automatically true:

  1. The name must be a person's name, not a job. Many role mailboxes sign
     themselves "Accounts Payable" or "Vendor Relations", and one of them,
     jhlebo@compasscharters.org, signs itself literally "Teacher".
  2. The name must match the ADDRESS, by the same rule everything else here
     uses. "Allison Watters" fits awatters@; "Mike Sarti" does not fit
     coordinator@brightonhallschool.org, which is a shared mailbox a person
     happens to use, and naming that contact Mike would have outreach greet
     a coordinator inbox as Mike.

Only the INCOMING direction counts: a From header on a message we sent is us.

Usage:
  python3 scripts/name_teachers_from_email.py            # dry run
  python3 scripts/name_teachers_from_email.py --execute
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "email"))
from src import po_inbox as po  # noqa: E402

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


def hs(method: str, path: str, **kw):
    for _ in range(6):
        r = requests.request(method, HS + path, headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
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


def unnamed_on_school_domains() -> list[tuple]:
    with open(ALIASES) as f:
        domains = (yaml.safe_load(f) or {}).get("domains") or {}
    out = []
    for domain in domains:
        for c in page("/crm/v3/objects/contacts/search", {
                "filterGroups": [{"filters": [
                    {"propertyName": "hs_email_domain", "operator": "EQ",
                     "value": domain}]}],
                "properties": ["email", "firstname", "lastname"], "limit": 100}):
            p = c["properties"]
            first = (p.get("firstname") or "").strip()
            last = (p.get("lastname") or "").strip()
            whole = f"{first} {last}".strip()
            if whole and not po.junk_person_name(first, last):
                continue
            out.append((c["id"], (p.get("email") or "").strip().lower(), whole))
    return out


def signatures(contact_id: str, addr: str) -> Counter:
    """Every name this address has signed its INCOMING mail with, counted.

    One address signs itself several ways. kconstanza@compasscharters.org
    used "Kimberly Constanza" eight times and "Compass Charter Schools" five,
    and the first draft of this script took whichever the API happened to
    return first, so a real teacher came back as a school. Collect them all
    and let the gates choose.
    """
    try:
        a = hs("GET", f"/crm/v4/objects/contacts/{contact_id}/associations/emails")
    except RuntimeError:
        return Counter()
    ids = [str(x["toObjectId"]) for x in a.get("results", [])][:50]
    if not ids:
        return Counter()
    seen = Counter()
    for i in range(0, len(ids), 100):
        b = hs("POST", "/crm/v3/objects/emails/batch/read",
               json={"properties": ["hs_email_from_email", "hs_email_from_firstname",
                                    "hs_email_from_lastname", "hs_email_direction"],
                     "inputs": [{"id": x} for x in ids[i:i + 100]]})
        for e in b.get("results", []):
            p = e["properties"]
            if (p.get("hs_email_from_email") or "").strip().lower() != addr:
                continue
            if "INCOMING" not in (p.get("hs_email_direction") or "").upper():
                continue      # a From header on OUR message is us, not them
            first = (p.get("hs_email_from_firstname") or "").strip()
            last = (p.get("hs_email_from_lastname") or "").strip()
            if first or last:
                seen[(first, last)] += 1
    return seen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if not TOKEN:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    mode = "EXECUTE" if a.execute else "DRY RUN"
    print(f"{'=' * 78}\n{mode}: name the unnamed from the emails they sent us")

    targets = unnamed_on_school_domains()
    print(f"contacts with no usable name on a school domain: {len(targets)}\n")

    take, refused = [], Counter()
    for cid, addr, was in targets:
        sigs = signatures(cid, addr)
        if not sigs:
            refused["never emailed us, or no name in the header"] += 1
            continue
        # every signature that is a person's name AND fits the address,
        # most-used first
        ok = [(n, (f, l)) for (f, l), n in sigs.most_common()
              if not po.junk_person_name(f, l)
              and not po._why_not_the_teacher(addr, f, l)]
        if not ok:
            worst = sigs.most_common(1)[0][0]
            refused["signs itself with a job or a school" if
                    po.junk_person_name(*worst)
                    else "the signature does not fit the address"] += 1
            continue
        first, last = ok[0][1]
        take.append((cid, addr, was, first, last, sigs))

    print(f"{'=' * 78}\nNAMEABLE: {len(take)}\n")
    for cid, addr, was, first, last, sigs in take:
        other = [f"{f} {l}".strip() for (f, l), _n in sigs.most_common()
                 if (f, l) != (first, last)]
        print(f"  {cid:<14} {addr[:42]:<42} {was or '(blank)':<24} -> {first} {last}")
        if other:
            print(f"       (also signed itself: {', '.join(other[:3])})")

    print(f"\n{'=' * 78}\nNOT NAMEABLE")
    for kk, vv in refused.most_common():
        print(f"  {kk:<48} {vv}")

    if not a.execute:
        print("\nDry run. Nothing was written. Re-run with --execute.")
        return
    for cid, _addr, _was, first, last, _sigs in take:
        props = {}
        if first:
            props["firstname"] = first
        if last:
            props["lastname"] = last
        hs("PATCH", f"/crm/v3/objects/contacts/{cid}", json={"properties": props})
    print(f"\nnamed {len(take)} contact(s)")


if __name__ == "__main__":
    main()
