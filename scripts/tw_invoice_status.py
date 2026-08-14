#!/usr/bin/env python3
"""READ-ONLY: per-invoice payment status for every contact on a HubSpot list.

For each contact on --list-id: find their Teachworks customer records (email
match, both accounts), list every invoice since --since with number / date /
due / total / STATUS, and summarize paid vs outstanding per family and
overall. Built for Roman's "are all invoices paid?" scrub of the charter gap
Hot list (3107), reusable for any list.

Auth (env): HUBSPOT_PRIVATE_APP_TOKEN (or HUBSPOT_API_KEY),
TEACHWORKS_TOKEN (or TEACHWORKS_TOKEN_ONLINE), TEACHWORKS_TOKEN_INPERSON.
"""

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
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

PAID_STATUSES = {"paid"}  # everything else (Sent, Approved, Draft, Overdue...) = outstanding


def tw_get(endpoint, params=None, token=None):
    headers = {"Authorization": f"Token token={token}", "Content-Type": "application/json"}
    params = dict(params or {})
    params["per_page"] = 80
    params["page"] = 1
    results = []
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
        results.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return results


def list_contacts(list_id):
    ids, after = [], None
    while True:
        url = f"{HS_BASE}/crm/v3/lists/{list_id}/memberships?limit=250"
        if after:
            url += f"&after={after}"
        r = requests.get(url, headers=H, timeout=30)
        r.raise_for_status()
        j = r.json()
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            break
    out = []
    for i in range(0, len(ids), 100):
        r = requests.post(f"{HS_BASE}/crm/v3/objects/contacts/batch/read", headers=H,
                          json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                                "properties": ["firstname", "lastname", "email"]}, timeout=30)
        r.raise_for_status()
        for row in r.json()["results"]:
            p = row["properties"]
            out.append(((p.get("firstname") or "").strip(), (p.get("lastname") or "").strip(),
                        (p.get("email") or "").strip().lower()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-id", required=True)
    ap.add_argument("--since", default="2025-08-01")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN or not TW_TOKENS:
        sys.exit("Missing HubSpot or Teachworks tokens")

    grand = defaultdict(float)
    for first, last, email in sorted(list_contacts(args.list_id), key=lambda x: x[1]):
        print(f"\n■ {first} {last} <{email}>")
        found = False
        for acct, token in TW_TOKENS.items():
            custs = tw_get("customers", {"email": email}, token=token) if email else []
            for cust in custs:
                invoices = [i for i in tw_get("invoices", {"customer_id": cust["id"]},
                                              token=token)
                            if str(i.get("date") or "") >= args.since
                            and (i.get("status") or "") != "Void"]
                for inv in sorted(invoices, key=lambda i: str(i.get("date"))):
                    found = True
                    status = (inv.get("status") or "?")
                    total = float(inv.get("total") or 0)
                    bucket = "paid" if status.lower() in PAID_STATUSES else "outstanding"
                    grand[bucket] += total
                    grand[f"n_{bucket}"] += 1
                    print(f"   inv {inv.get('number') or inv.get('id')} [{acct}] "
                          f"date {str(inv.get('date'))[:10]} due {str(inv.get('due_date'))[:10]} "
                          f"${total:,.2f}  {status.upper()}")
        if not found:
            print("   (no Teachworks invoices since window start)")

    print(f"\n══ TOTALS since {args.since} ══")
    print(f"  PAID:        {int(grand['n_paid'])} invoices, ${grand['paid']:,.2f}")
    print(f"  OUTSTANDING: {int(grand['n_outstanding'])} invoices, ${grand['outstanding']:,.2f}")


if __name__ == "__main__":
    main()
