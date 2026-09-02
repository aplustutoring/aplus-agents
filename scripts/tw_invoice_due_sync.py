#!/usr/bin/env python3
"""Sync Teachworks invoice DUE DATES onto their HubSpot charter deals, and
report what is ready to submit.

Why this exists
---------------
Charter invoicing runs: PO arrives -> invoice created in Teachworks (that is
what grants the student their hours) -> hours get used -> Kath submits the
invoice to the school in the OPS portal -> net 30.

The submit step happens in OPS, which we cannot read, so HubSpot only knows
about it if someone records it. And the rule for WHEN to submit (Roman,
2026-09-02) is "at least one day past the invoice due date" — but the due date
lives on the Teachworks invoice, not in HubSpot. `invoice_due_date` exists on
the deal and was populated on 75 of 157 26/27 deals, never by an agent.

So: copy the authoritative due date across. That turns "what should Kath submit
today?" into a plain HubSpot view she can keep open:

    Pipeline is a charter pipeline
    Invoice #            is known
    Invoice Submitted Date  is empty
    Invoice Due Date     is before today

No new property, no new tool for her to learn, and the date comes from the
system that actually owns it.

Read-only against Teachworks. Writes exactly one HubSpot field.

    python3 scripts/tw_invoice_due_sync.py             # dry run
    python3 scripts/tw_invoice_due_sync.py --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "email"))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

HS_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
H = {"Authorization": f"Bearer {HS_TOKEN}", "Content-Type": "application/json"}
TW_BASE = "https://api.teachworks.com/v1"
CHARTER_PIPELINES = ["907748", "72281989", "88841552"]
OWNERS = {"80047202": "Janelle", "86868539": "Yolanda", "513215050": "Kath",
          "81494333": "Paola", "227538487": "Danielle", "39191217": "Emily"}


def tw_accounts() -> dict:
    out = {}
    for name, var in (("online", "TEACHWORKS_TOKEN"), ("in_person", "TEACHWORKS_TOKEN_INPERSON")):
        if os.getenv(var):
            out[name] = os.environ[var]
    return out


def tw_invoices(token: str) -> list[dict]:
    """Every invoice on one Teachworks account (80/page)."""
    out, page = [], 1
    while page <= 200:
        r = requests.get(f"{TW_BASE}/invoices", timeout=40,
                         headers={"Authorization": f"Token token={token}",
                                  "Content-Type": "application/json"},
                         params={"per_page": 80, "page": page})
        if r.status_code == 403:          # rate limited
            continue
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out += rows
        if len(rows) < 80:
            break
        page += 1
    return out


def hs_charter_deals(since: dt.datetime) -> list[dict]:
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "createdate", "operator": "GTE",
             "value": str(int(since.timestamp() * 1000))},
            {"propertyName": "pipeline", "operator": "IN", "values": CHARTER_PIPELINES}]}],
            "properties": ["dealname", "invoice__", "invoice_due_date",
                           "invoice_submitted_date", "dealstage", "amount",
                           "hubspot_owner_id"], "limit": 100}
        if after:
            body["after"] = after
        r = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                          headers=H, json=body, timeout=40)
        r.raise_for_status()
        j = r.json()
        out += j.get("results", [])
        after = (j.get("paging") or {}).get("next", {}).get("after")
        if not after:
            return out


def as_date(v) -> dt.date | None:
    if not v:
        return None
    s = str(v)
    try:
        if s.isdigit():
            return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc).date()
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write invoice_due_date")
    ap.add_argument("--since", default="2026-08-01", help="school year start")
    ap.add_argument("--debug", action="store_true", help="print TW invoice shape")
    args = ap.parse_args()
    today = dt.date.today()
    since = dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc)

    accounts = tw_accounts()
    if not accounts:
        sys.exit("No Teachworks token in the environment.")
    # Index by EVERY identifier the invoice carries. Teachworks exposes both an
    # internal id and a human invoice number, and which one Kath types into the
    # deal's Invoice # varies; keying on one of them matched 1 deal out of 157.
    due_by_invoice: dict[str, dt.date] = {}
    for name, token in accounts.items():
        rows = tw_invoices(token)
        if rows and args.debug:
            print(f"  sample invoice keys: {sorted(rows[0].keys())}")
            for r in rows[:3]:
                print(f"    id={r.get('id')!r} number={r.get('number')!r} "
                      f"invoice_number={r.get('invoice_number')!r} "
                      f"due_date={r.get('due_date')!r}")
        n = 0
        for i in rows:
            d = as_date(i.get("due_date") or i.get("due"))
            if not d:
                continue
            for key in (i.get("invoice_number"), i.get("number"), i.get("id")):
                k = str(key or "").strip()
                if k:
                    due_by_invoice[k] = d
            n += 1
        print(f"teachworks[{name}]: {len(rows)} invoices, {n} with a due date")
    print(f"due-date keys indexed: {len(due_by_invoice)}\n")

    deals = hs_charter_deals(since)
    prop = lambda d, k: (d["properties"].get(k) or "").strip()
    amt = lambda d: float(d["properties"].get("amount") or 0)
    print(f"charter deals since {args.since}: {len(deals)}")

    to_stamp, unmatched = [], []
    for d in deals:
        num = prop(d, "invoice__")
        if not num:
            continue
        due = due_by_invoice.get(num)
        if not due:
            unmatched.append(d)
            continue
        if as_date(prop(d, "invoice_due_date")) != due:
            to_stamp.append((d, due))

    print(f"  invoice # stamped, due date found : {len(deals) - len(unmatched)}")
    print(f"  invoice # stamped, NO TW match    : {len(unmatched)}")
    if unmatched and args.debug:
        print("   unmatched Invoice # values (first 15):",
              [prop(d, "invoice__") for d in unmatched[:15]])
    print(f"  due date to write / correct       : {len(to_stamp)}\n")

    # what this unlocks: the queue Kath actually works
    ready = [(d, due_by_invoice[prop(d, "invoice__")]) for d in deals
             if prop(d, "invoice__") and not prop(d, "invoice_submitted_date")
             and due_by_invoice.get(prop(d, "invoice__"))
             and (today - due_by_invoice[prop(d, "invoice__")]).days >= 1]
    print(f"READY TO SUBMIT (>= 1 day past due, not submitted): "
          f"{len(ready)} deals, ${sum(amt(d) for d, _ in ready):,.0f}")
    by = defaultdict(lambda: [0, 0.0])
    for d, _ in ready:
        k = OWNERS.get(prop(d, "hubspot_owner_id"), "-")
        by[k][0] += 1
        by[k][1] += amt(d)
    for k, (n, v) in sorted(by.items(), key=lambda x: -x[1][1]):
        print(f"   {k:<10}{n:>4} deals  ${v:>9,.0f}")
    for d, due in sorted(ready, key=lambda x: x[1])[:20]:
        print(f"     due {due}  {(today - due).days:>4}d ago  ${amt(d):>7,.0f}  "
              f"inv#{prop(d,'invoice__'):<8}{d['properties']['dealname'][:42]}")

    if not args.apply:
        print(f"\nDRY RUN — would write invoice_due_date on {len(to_stamp)} deals.")
        return

    ok = 0
    for d, due in to_stamp:
        r = requests.patch(f"https://api.hubapi.com/crm/v3/objects/deals/{d['id']}",
                           headers=H, timeout=30,
                           json={"properties": {"invoice_due_date": due.isoformat()}})
        if r.status_code < 300:
            ok += 1
        else:
            print(f"   FAIL {d['id']}: {r.status_code} {r.text[:90]}")
    print(f"\nstamped invoice_due_date on {ok}/{len(to_stamp)} deals")


if __name__ == "__main__":
    main()
