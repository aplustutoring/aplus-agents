#!/usr/bin/env python3
"""
Charter Re-Engagement Gap Analysis
==================================

Cross-references HubSpot charter deals against Teachworks invoices to find
families with a charter deal since Aug 2025 who have NOT renewed for 26/27,
then builds an Excel workbook and a HubSpot static list for re-engagement.

One-off run for Aug 2026, but structured to be scheduled weekly later.

Usage:
  # Full run (needs HUBSPOT_PRIVATE_APP_TOKEN; Teachworks from --tw-json or env key)
  python3 scripts/charter_gap_analysis.py [--tw-json tw_data.json] [--out ~/Desktop/charter_gap_analysis.xlsx]

  # Teachworks-only fetch stage (for GitHub Actions where TEACHWORKS_API_KEY lives)
  python3 scripts/charter_gap_analysis.py --fetch-teachworks tw_data.json

  # Skip the HubSpot static-list step
  python3 scripts/charter_gap_analysis.py --skip-list

Auth (same env vars as ops/scorecard/aplus_weekly_sync.py):
  TEACHWORKS_API_KEY          — Teachworks API (read-only use here)
  HUBSPOT_PRIVATE_APP_TOKEN   — HubSpot Private App (falls back to HUBSPOT_API_KEY)

Writes:
  - Excel workbook (default ~/Desktop/charter_gap_analysis.xlsx), 4 tabs
  - ~/Desktop/non_marketable_gap_contacts.csv
  - One HubSpot static list (the ONLY HubSpot write; no property/contact edits)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone

import requests

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
PORTAL_ID = "6312752"

CHARTER_PIPELINES = {
    "907748":   "Charter Schools - Traditional Vendor Funds",
    "72281989": "Terri iLead Level Up",
    "88841552": "Amy iLead Level Up",
    "5119061":  "IEM Inc.",
    "1066195":  "CFGC",
}

# Deals / invoices window start
DEFAULT_WINDOW_START = "2025-08-01"

# RENEWED = charter deal created on/after this date OR "26/27" in dealname
DEFAULT_RENEWAL_CUTOFF = "2026-06-01"
DEFAULT_RENEWAL_TOKEN = "26/27"

# School-staff email domains to exclude. student.* subdomains stay as family.
SCHOOL_DOMAINS = {
    "ileadexploration.org", "ileadav.org", "ileadlancaster.org", "ieminc.org",
    "viedu.org", "gormanlc.org", "eliteacademic.com", "heartlandcharterschool.com",
    "compasscharters.org", "pacificcharters.org", "pacificcoastacademy.org",
    "granitemountainschool.com", "heartwoodcharterschool.org",
    "theblueridgeacademy.com", "hcs.k12.ca.us", "forestcharter.com",
    "taylion.com", "suncoastprep.org", "sageoak.education",
}

HOT_DAYS = 90  # invoiced within 90 days → "Hot", else "Win-back"

LIST_NAME = "Charter Re-Engagement 26/27 - Gap Families (Aug 2026)"

HS_BASE = "https://api.hubapi.com"
TW_BASE = "https://api.teachworks.com/v1"

HUBSPOT_TOKEN = None  # set in main()
TEACHWORKS_API_KEY = None


# ─────────────────────────────────────────────
# TEACHWORKS API (read-only) — same pattern as aplus_weekly_sync.py
# ─────────────────────────────────────────────
def tw_get(endpoint, params=None):
    headers = {
        "Authorization": f"Token token={TEACHWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    params = params or {}
    results = []
    params["per_page"] = 80  # Teachworks API max is 80 per page
    params["page"] = 1
    while True:
        for attempt in range(3):
            r = requests.get(f"{TW_BASE}/{endpoint}", headers=headers, params=params, timeout=30)
            if r.status_code == 403:
                wait = 5 * (attempt + 1)
                print(f"      ⏳ Teachworks rate limit, retrying in {wait}s...")
                time.sleep(wait)
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


def fetch_teachworks(window_start, window_end):
    """Pull invoices in the window plus all customers (for email/name lookup)."""
    print(f"  Teachworks: invoices {window_start} → {window_end} ...")
    invoices = tw_get("invoices", {
        "date[gte]": window_start,
        "date[lte]": window_end,
    })
    print(f"    {len(invoices)} invoices")
    print("  Teachworks: customers (all pages) ...")
    customers = tw_get("customers")
    print(f"    {len(customers)} customers")
    return {"invoices": invoices, "customers": customers,
            "window_start": window_start, "window_end": window_end}


# ─────────────────────────────────────────────
# HUBSPOT API
# ─────────────────────────────────────────────
def hs_request(method, endpoint, payload=None, params=None):
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
    for attempt in range(5):
        r = requests.request(method, f"{HS_BASE}{endpoint}", headers=headers,
                             json=payload, params=params, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", 5 * (attempt + 1)))
            print(f"      ⏳ HubSpot rate limit, retrying in {wait}s...")
            time.sleep(wait)
            continue
        return r
    return r


def hs_ok(method, endpoint, payload=None, params=None):
    r = hs_request(method, endpoint, payload, params)
    if r.status_code >= 400:
        raise RuntimeError(f"HubSpot {method} {endpoint} → {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def fetch_charter_deals(window_start):
    """All deals created on/after window_start in the charter pipelines."""
    start_ms = int(datetime.strptime(window_start, "%Y-%m-%d")
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    deals, after = [], None
    while True:
        payload = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "IN",
                 "values": list(CHARTER_PIPELINES.keys())},
                {"propertyName": "createdate", "operator": "GTE", "value": str(start_ms)},
            ]}],
            "properties": ["dealname", "pipeline", "dealstage", "createdate", "amount"],
            "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
            "limit": 200,
        }
        if after:
            payload["after"] = after
        data = hs_ok("POST", "/crm/v3/objects/deals/search", payload)
        deals.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.25)  # search API rate limit is tighter
    return deals


def fetch_deal_contact_associations(deal_ids):
    """deal id → [contact ids] via v4 batch read."""
    assoc = {}
    for i in range(0, len(deal_ids), 100):
        chunk = deal_ids[i:i + 100]
        data = hs_ok("POST", "/crm/v4/associations/deal/contact/batch/read",
                     {"inputs": [{"id": d} for d in chunk]})
        for row in data.get("results", []):
            frm = str(row["from"]["id"])
            assoc[frm] = [str(t["toObjectId"]) for t in row.get("to", [])]
    return assoc


def fetch_contacts(contact_ids):
    """contact id → properties dict."""
    props = ["firstname", "lastname", "email", "phone", "hs_marketable_status"]
    out = {}
    ids = list(contact_ids)
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        data = hs_ok("POST", "/crm/v3/objects/contacts/batch/read",
                     {"properties": props, "inputs": [{"id": c} for c in chunk]})
        for row in data.get("results", []):
            out[str(row["id"])] = row.get("properties", {}) or {}
    return out


# ─────────────────────────────────────────────
# CLASSIFICATION HELPERS
# ─────────────────────────────────────────────
def email_domain(email):
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower()


def is_school_staff(email):
    """True if the email is on a school-staff domain. student.* subdomains are family."""
    dom = email_domain(email)
    if not dom:
        return False
    if dom.startswith("student."):
        return False
    if dom in SCHOOL_DOMAINS:
        return True
    return any(dom.endswith("." + d) for d in SCHOOL_DOMAINS)


def deal_is_renewal(deal, renewal_cutoff_ms, renewal_token):
    p = deal.get("properties", {})
    created = p.get("createdate") or ""
    name = (p.get("dealname") or "")
    try:
        created_ms = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        created_ms = 0
    return created_ms >= renewal_cutoff_ms or renewal_token in name


def norm_name(first, last):
    s = f"{(first or '').strip().lower()} {(last or '').strip().lower()}".strip()
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────
# TEACHWORKS AGGREGATION
# ─────────────────────────────────────────────
def aggregate_invoices(tw_data):
    """Per Teachworks customer: last_invoice_date, total_invoiced, invoice_count.
    Void invoices excluded from aggregates."""
    customers = {str(c.get("id")): c for c in tw_data["customers"]}
    agg = {}
    void_count = 0
    for inv in tw_data["invoices"]:
        if (inv.get("status") or "").lower() == "void":
            void_count += 1
            continue
        cid = str(inv.get("customer_id") or "")
        cust = customers.get(cid, {})
        rec = agg.setdefault(cid, {
            "customer_id": cid,
            "first_name": cust.get("first_name") or "",
            "last_name": cust.get("last_name") or "",
            "name": (cust.get("full_name")
                     or f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()
                     or inv.get("customer_name") or ""),
            "email": (cust.get("email") or "").strip().lower(),
            "last_invoice_date": "",
            "total_invoiced": 0.0,
            "invoice_count": 0,
        })
        inv_date = (inv.get("date") or "")[:10]
        rec["last_invoice_date"] = max(rec["last_invoice_date"], inv_date)
        rec["total_invoiced"] += float(inv.get("total") or 0)
        rec["invoice_count"] += 1
    print(f"    {len(agg)} invoiced customers ({void_count} void invoices excluded)")
    return agg


# ─────────────────────────────────────────────
# EXCEL / CSV OUTPUT
# ─────────────────────────────────────────────
def write_workbook(path, tabs):
    """tabs: list of (title, header_row, rows)"""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for title, header, rows in tabs:
        ws = wb.create_sheet(title=title[:31])
        ws.append(header)
        for c in ws[1]:
            c.font = Font(bold=True)
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "A2"
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(width + 2, 50)
    wb.save(path)


# ─────────────────────────────────────────────
# HUBSPOT STATIC LIST (the only HubSpot write)
# ─────────────────────────────────────────────
def create_static_list(name, contact_ids):
    r = hs_request("POST", "/crm/v3/lists", {
        "name": name,
        "objectTypeId": "0-1",
        "processingType": "MANUAL",
    })
    if r.status_code == 403:
        raise PermissionError(
            "HubSpot returned 403 creating the list — the Private App token is missing the "
            "crm.lists.write scope. Add it in Settings → Integrations → Private Apps, then re-run "
            "with --list-only (analysis outputs are already written).")
    if r.status_code >= 400:
        raise RuntimeError(f"List create failed → {r.status_code}: {r.text[:500]}")
    list_id = str(r.json()["list"]["listId"])
    print(f"    List created: id={list_id}")

    for i in range(0, len(contact_ids), 100):
        chunk = contact_ids[i:i + 100]
        rr = hs_request("PUT", f"/crm/v3/lists/{list_id}/memberships/add", chunk)
        if rr.status_code == 403:
            raise PermissionError(
                "HubSpot returned 403 adding list memberships — missing crm.lists.write scope. "
                "Add it in Settings → Integrations → Private Apps, then re-run with --list-only.")
        if rr.status_code >= 400:
            raise RuntimeError(f"Membership add failed → {rr.status_code}: {rr.text[:500]}")
        time.sleep(0.2)

    # verify membership count
    total, after = 0, None
    while True:
        params = {"limit": 250}
        if after:
            params["after"] = after
        data = hs_ok("GET", f"/crm/v3/lists/{list_id}/memberships", params=params)
        total += len(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return list_id, total


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    global HUBSPOT_TOKEN, TEACHWORKS_API_KEY

    ap = argparse.ArgumentParser(description="Charter re-engagement gap analysis")
    ap.add_argument("--fetch-teachworks", metavar="OUT_JSON",
                    help="Fetch Teachworks invoices+customers to JSON and exit (Actions stage)")
    ap.add_argument("--tw-json", metavar="FILE",
                    help="Load Teachworks data from JSON instead of calling the API")
    ap.add_argument("--out", default=os.path.expanduser("~/Desktop/charter_gap_analysis.xlsx"))
    ap.add_argument("--non-marketable-csv",
                    default=os.path.expanduser("~/Desktop/non_marketable_gap_contacts.csv"))
    ap.add_argument("--start", default=DEFAULT_WINDOW_START, help="Deal/invoice window start")
    ap.add_argument("--renewal-cutoff", default=DEFAULT_RENEWAL_CUTOFF)
    ap.add_argument("--renewal-token", default=DEFAULT_RENEWAL_TOKEN)
    ap.add_argument("--skip-list", action="store_true", help="Skip the HubSpot static-list step")
    ap.add_argument("--list-only", metavar="GAP_IDS_JSON", nargs="?", const="",
                    help="Only (re)create the static list from cached gap ids JSON")
    ap.add_argument("--cache", default=None,
                    help="Directory to cache raw pulls / gap ids (default: alongside --out)")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        # repo-root .env (script lives in scripts/)
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
        load_dotenv()
    except ImportError:
        pass

    TEACHWORKS_API_KEY = os.getenv("TEACHWORKS_API_KEY")
    HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN") or os.getenv("HUBSPOT_API_KEY")

    today = date.today()
    window_end = today.isoformat()
    cache_dir = args.cache or os.path.dirname(os.path.abspath(os.path.expanduser(args.out)))

    # ---- Teachworks-only fetch stage (runs in GitHub Actions) ----
    if args.fetch_teachworks:
        if not TEACHWORKS_API_KEY:
            sys.exit("TEACHWORKS_API_KEY not set")
        data = fetch_teachworks(args.start, window_end)
        with open(args.fetch_teachworks, "w") as f:
            json.dump(data, f)
        print(f"Wrote {args.fetch_teachworks}")
        return

    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN not set")

    gap_ids_path = os.path.join(cache_dir, "charter_gap_contact_ids.json")

    # ---- list-only mode: recreate list from cached ids ----
    if args.list_only is not None:
        src = args.list_only or gap_ids_path
        with open(src) as f:
            gap_ids = json.load(f)
        list_id, count = create_static_list(LIST_NAME, gap_ids)
        print(f"List {list_id}: {count} members (expected {len(gap_ids)})")
        print(f"https://app.hubspot.com/contacts/{PORTAL_ID}/objectLists/{list_id}")
        return

    # ═══ STEP 1 — HubSpot charter deals + contacts ═══
    print("STEP 1 — HubSpot charter deals + contacts")
    deals = fetch_charter_deals(args.start)
    print(f"    {len(deals)} deals across {len(CHARTER_PIPELINES)} pipelines")

    renewal_cutoff_ms = int(datetime.strptime(args.renewal_cutoff, "%Y-%m-%d")
                            .replace(tzinfo=timezone.utc).timestamp() * 1000)
    deal_ids = [str(d["id"]) for d in deals]
    deal_by_id = {str(d["id"]): d for d in deals}
    assoc = fetch_deal_contact_associations(deal_ids)
    all_contact_ids = sorted({c for ids in assoc.values() for c in ids})
    print(f"    {len(all_contact_ids)} unique associated contacts")
    contacts = fetch_contacts(all_contact_ids)

    # contact → deals; classify
    contact_deals = {}
    for did, cids in assoc.items():
        for cid in cids:
            contact_deals.setdefault(cid, []).append(deal_by_id[did])

    families, staff = {}, {}
    for cid, cdeals in contact_deals.items():
        p = contacts.get(cid, {})
        email = (p.get("email") or "").strip().lower()
        rec = {
            "id": cid,
            "first": p.get("firstname") or "",
            "last": p.get("lastname") or "",
            "email": email,
            "phone": p.get("phone") or "",
            "marketable": p.get("hs_marketable_status"),
            "renewed": any(deal_is_renewal(d, renewal_cutoff_ms, args.renewal_token)
                           for d in cdeals),
            "deals": [d.get("properties", {}).get("dealname", "") for d in cdeals],
        }
        (staff if is_school_staff(email) else families)[cid] = rec

    renewed = {cid: r for cid, r in families.items() if r["renewed"]}
    gap = {cid: r for cid, r in families.items() if not r["renewed"]}
    no_email = sum(1 for r in families.values() if not r["email"])
    print(f"    Families: {len(families)}  (staff excluded: {len(staff)}, no-email kept: {no_email})")
    print(f"    RENEWED: {len(renewed)}   GAP: {len(gap)}")

    # sanity check vs expectations
    def wildly_off(actual, expected):
        return abs(actual - expected) > max(0.25 * expected, 15)
    warnings = []
    for label, actual, expected in [("families", len(families), 439),
                                    ("renewed", len(renewed), 11),
                                    ("gap", len(gap), 428)]:
        if wildly_off(actual, expected):
            warnings.append(f"⚠️  {label}={actual} vs expected ~{expected}")
    for w in warnings:
        print(f"    {w}")

    # ═══ STEP 2 — Teachworks invoices ═══
    print("STEP 2 — Teachworks invoices")
    if args.tw_json:
        with open(args.tw_json) as f:
            tw_data = json.load(f)
        print(f"    Loaded {len(tw_data['invoices'])} invoices / "
              f"{len(tw_data['customers'])} customers from {args.tw_json}")
    else:
        if not TEACHWORKS_API_KEY:
            sys.exit("TEACHWORKS_API_KEY not set and no --tw-json provided")
        tw_data = fetch_teachworks(args.start, window_end)
    tw_agg = aggregate_invoices(tw_data)

    # ═══ STEP 3 — Merge ═══
    print("STEP 3 — Merge (email first, then normalized name)")
    tw_by_email, tw_by_name = {}, {}
    for rec in tw_agg.values():
        if rec["email"]:
            tw_by_email.setdefault(rec["email"], rec)
        nm = norm_name(rec["first_name"], rec["last_name"]) or rec["name"].strip().lower()
        if nm:
            tw_by_name.setdefault(nm, rec)

    matched_tw_ids = set()
    for rec in families.values():
        tw = tw_by_email.get(rec["email"]) if rec["email"] else None
        how = "email" if tw else None
        if not tw:
            tw = tw_by_name.get(norm_name(rec["first"], rec["last"]))
            how = "name" if tw else None
        rec["tw"] = tw
        rec["match"] = how
        if tw:
            matched_tw_ids.add(tw["customer_id"])

    matched = sum(1 for r in families.values() if r["tw"])
    print(f"    Matched {matched}/{len(families)} families to Teachworks "
          f"({sum(1 for r in families.values() if r['match'] == 'email')} by email, "
          f"{sum(1 for r in families.values() if r['match'] == 'name')} by name)")
    unmatched_tw = [r for cid, r in tw_agg.items() if cid not in matched_tw_ids]
    print(f"    Unmatched: {len(families) - matched} HubSpot families, "
          f"{len(unmatched_tw)} invoiced Teachworks customers")

    # ═══ STEP 4 — Excel workbook ═══
    print("STEP 4 — Excel workbook")

    def hs_link(cid):
        return f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-1/{cid}"

    def months_since(d):
        if not d:
            return ""
        delta = (today - date.fromisoformat(d)).days
        return round(delta / 30.44, 1)

    def segment(d):
        if not d:
            return ""
        return "Hot" if (today - date.fromisoformat(d)).days <= HOT_DAYS else "Win-back"

    gap_sorted = sorted(gap.values(), key=lambda r: -(r["tw"]["total_invoiced"] if r["tw"] else 0))
    prio_rows = [
        [r["last"], r["first"], r["email"], r["phone"],
         r["tw"]["last_invoice_date"], round(r["tw"]["total_invoiced"], 2),
         r["tw"]["invoice_count"], months_since(r["tw"]["last_invoice_date"]),
         segment(r["tw"]["last_invoice_date"]), hs_link(r["id"])]
        for r in gap_sorted if r["tw"]
    ]
    never_rows = [
        [r["last"], r["first"], r["email"], r["phone"],
         "; ".join(r["deals"])[:200], hs_link(r["id"])]
        for r in sorted(gap.values(), key=lambda r: (r["last"], r["first"])) if not r["tw"]
    ]
    renewed_rows = [
        [r["last"], r["first"], r["email"], r["phone"],
         "; ".join(r["deals"])[:200], hs_link(r["id"])]
        for r in sorted(renewed.values(), key=lambda r: (r["last"], r["first"]))
    ]
    mismatch_rows = [
        [rec["name"], rec["email"], rec["last_invoice_date"],
         round(rec["total_invoiced"], 2), rec["invoice_count"]]
        for rec in sorted(unmatched_tw, key=lambda x: -x["total_invoiced"])
    ]

    out_path = os.path.expanduser(args.out)
    write_workbook(out_path, [
        ("GAP - Priority Targets",
         ["last", "first", "email", "phone", "last_invoice_date", "total_invoiced",
          "invoice_count", "months_since_last_invoice", "segment", "hubspot_link"],
         prio_rows),
        ("GAP - Deal But Never Invoiced",
         ["last", "first", "email", "phone", "deals", "hubspot_link"], never_rows),
        ("Renewed 26-27",
         ["last", "first", "email", "phone", "deals", "hubspot_link"], renewed_rows),
        ("Mismatches",
         ["teachworks_name", "email", "last_invoice_date", "total_invoiced",
          "invoice_count"], mismatch_rows),
    ])
    print(f"    Wrote {out_path}")
    print(f"    Tab counts: priority={len(prio_rows)}  never-invoiced={len(never_rows)}  "
          f"renewed={len(renewed_rows)}  mismatches={len(mismatch_rows)}")

    # cache gap ids so the list step can be re-run standalone
    gap_ids = sorted(gap.keys(), key=int)
    with open(gap_ids_path, "w") as f:
        json.dump(gap_ids, f)

    # marketable status breakdown + CSV of non-marketable gap contacts
    marketable = [r for r in gap.values() if str(r["marketable"]).lower() == "true"]
    non_marketable = [r for r in gap.values() if str(r["marketable"]).lower() != "true"]
    print(f"    Gap marketable status: {len(marketable)} marketable, "
          f"{len(non_marketable)} non-marketable")
    csv_path = os.path.expanduser(args.non_marketable_csv)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contact_id", "last", "first", "email", "phone",
                    "hs_marketable_status", "hubspot_link"])
        for r in sorted(non_marketable, key=lambda r: (r["last"], r["first"])):
            w.writerow([r["id"], r["last"], r["first"], r["email"], r["phone"],
                        r["marketable"], hs_link(r["id"])])
    print(f"    Wrote {csv_path} ({len(non_marketable)} rows)")

    # ═══ STEP 5 — HubSpot static list ═══
    if args.skip_list:
        print("STEP 5 — skipped (--skip-list)")
        return
    print("STEP 5 — HubSpot static list")
    list_id, count = create_static_list(LIST_NAME, gap_ids)
    status = "✅ matches" if count == len(gap_ids) else "⚠️ MISMATCH"
    print(f"    List {list_id}: {count} members vs {len(gap_ids)} gap contacts → {status}")
    print(f"    https://app.hubspot.com/contacts/{PORTAL_ID}/objectLists/{list_id}")


if __name__ == "__main__":
    main()
