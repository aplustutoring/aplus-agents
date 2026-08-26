#!/usr/bin/env python3
"""Charter campaign revenue report, validated against Teachworks invoices.

The attribution chain per family: campaign email -> engagement -> 26/27
charter deal (HubSpot, created on/after campaign start) -> ACTUAL Teachworks
invoices (both accounts) -> paid vs outstanding. HubSpot deal amounts are
intent; TW invoices are revenue; Paid is cash.

Scans every campaign queue list, finds converters, cross-references invoices
by family email (both TW accounts), prints the funnel and the per-family
ledger. READ-ONLY everywhere.

Auth (env / CI secrets): HUBSPOT_PRIVATE_APP_TOKEN,
TEACHWORKS_TOKEN (online), TEACHWORKS_TOKEN_INPERSON.
"""

import argparse
import os
import sys
import time
from collections import Counter
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
TW_TOKENS = {}
if os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", ""):
    TW_TOKENS["online"] = os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", "")
if os.getenv("TEACHWORKS_TOKEN_INPERSON", ""):
    TW_TOKENS["in person"] = os.getenv("TEACHWORKS_TOKEN_INPERSON", "")
HS_BASE = "https://api.hubapi.com"
TW_BASE = "https://api.teachworks.com/v1"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
CH = {"907748", "72281989", "88841552", "5119061", "1066195"}
CAMPAIGN_LISTS = {"3146": "winback-1", "3162": "never-started", "3163": "no-lesson",
                  "3164": "multi", "3188": "cold-revival"}


def tw_get(endpoint, params=None, token=None):
    headers = {"Authorization": f"Token token={token}", "Content-Type": "application/json"}
    params = dict(params or {})
    params["per_page"] = 80
    params["page"] = 1
    out = []
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
        out.extend(data)
        if len(data) < 80:
            break
        params["page"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-18", help="campaign start (deal + invoice window)")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN or not TW_TOKENS:
        sys.exit("missing tokens")
    SINCE = args.since

    # 1. campaign contacts (deduped; first list wins for segment label)
    seg = {}
    for lid, label in CAMPAIGN_LISTS.items():
        after = None
        while True:
            j = requests.get(f"{HS_BASE}/crm/v3/lists/{lid}/memberships?limit=250"
                             + (f"&after={after}" if after else ""), headers=H, timeout=30).json()
            for m in j.get("results", []):
                seg.setdefault(str(m["recordId"]), label)
            after = (j.get("paging", {}).get("next") or {}).get("after")
            if not after:
                break
    ids = sorted(seg)
    props = {}
    for i in range(0, len(ids), 100):
        r = requests.post(f"{HS_BASE}/crm/v3/objects/contacts/batch/read", headers=H, timeout=30,
                          json={"inputs": [{"id": c} for c in ids[i:i + 100]],
                                "properties": ["firstname", "lastname", "email",
                                               "hs_email_last_send_date", "hs_email_last_open_date",
                                               "hs_email_last_reply_date"]})
        for row in r.json()["results"]:
            props[str(row["id"])] = row["properties"]

    # 2. converters: charter deal created since SINCE
    deal_of = {}
    for i in range(0, len(ids), 100):
        a = requests.post(f"{HS_BASE}/crm/v4/associations/contact/deal/batch/read", headers=H,
                          json={"inputs": [{"id": c} for c in ids[i:i + 100]]}, timeout=30).json()
        for row in a.get("results", []):
            deal_of[str(row["from"]["id"])] = [str(t["toObjectId"]) for t in row.get("to", [])]
        time.sleep(0.05)
    all_d = sorted({d for ds in deal_of.values() for d in ds})
    deals = {}
    for i in range(0, len(all_d), 100):
        r = requests.post(f"{HS_BASE}/crm/v3/objects/deals/batch/read", headers=H, timeout=30,
                          json={"inputs": [{"id": d} for d in all_d[i:i + 100]],
                                "properties": ["dealname", "pipeline", "createdate", "amount"]})
        for row in r.json()["results"]:
            deals[str(row["id"])] = row["properties"]
    converters = {}
    for cid in ids:
        conv = [deals[d] for d in deal_of.get(cid, [])
                if d in deals and deals[d].get("pipeline") in CH
                and (deals[d].get("createdate") or "")[:10] >= SINCE]
        if conv:
            converters[cid] = conv

    # 3. funnel
    sent = [c for c in ids if (props[c].get("hs_email_last_send_date") or "")[:10] >= SINCE]
    opened = [c for c in ids if (props[c].get("hs_email_last_open_date") or "")[:10] >= SINCE]
    replied = [c for c in ids if (props[c].get("hs_email_last_reply_date") or "")[:10] >= SINCE]
    print(f"══ FUNNEL since {SINCE} ══")
    print(f"  audience {len(ids)} | emailed {len(sent)} | opened {len(opened)} "
          f"({len(opened) * 100 // max(len(sent), 1)}%) | replied {len(replied)} | "
          f"CONVERTED {len(converters)} families")
    print("  converters by segment:", dict(Counter(seg[c] for c in converters)))

    # 4. per-converter invoice validation
    print(f"\n══ REVENUE LEDGER (deal $ vs Teachworks invoices, both accounts) ══")
    tot_deal = tot_inv = tot_paid = 0.0
    no_invoice = []
    for cid, conv in sorted(converters.items(),
                            key=lambda x: -sum(float(p.get("amount") or 0) for p in x[1])):
        p = props[cid]
        email = (p.get("email") or "").strip().lower()
        deal_sum = sum(float(x.get("amount") or 0) for x in conv)
        inv_sum = paid_sum = 0.0
        n_inv = 0
        for acct, tok in TW_TOKENS.items():
            for cust in (tw_get("customers", {"email": email}, token=tok) if email else []):
                for inv in tw_get("invoices", {"customer_id": cust["id"]}, token=tok):
                    if (str(inv.get("date") or "")[:10] >= SINCE
                            and (inv.get("status") or "") != "Void"):
                        amt = float(inv.get("total") or 0)
                        inv_sum += amt
                        n_inv += 1
                        if (inv.get("status") or "").lower() == "paid":
                            paid_sum += amt
        tot_deal += deal_sum
        tot_inv += inv_sum
        tot_paid += paid_sum
        flag = "" if n_inv else "   <-- NO TW INVOICE YET (Kath queue)"
        if not n_inv:
            no_invoice.append(f"{p.get('firstname')} {p.get('lastname')}")
        print(f"  {p.get('firstname')} {p.get('lastname'):<16} [{seg[cid]}] "
              f"deals {len(conv)} ${deal_sum:,.0f} | TW invoices {n_inv} ${inv_sum:,.0f} "
              f"(paid ${paid_sum:,.0f}){flag}")

    print(f"\n══ TOTALS ══")
    print(f"  HubSpot deal value (intent):   ${tot_deal:,.0f}")
    print(f"  TW invoiced (real revenue):    ${tot_inv:,.0f}")
    print(f"  TW paid (cash collected):      ${tot_paid:,.0f}")
    print(f"  Converters without an invoice: {len(no_invoice)}"
          + (f" ({', '.join(no_invoice)})" if no_invoice else ""))


if __name__ == "__main__":
    main()
