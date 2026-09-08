"""One-off backfill for August 2026 charter PO deals (dispatch-only workflow).

Fixes the two gaps the 2026-09-03 property audit found on deals created since
8/1 in the Charter pipeline:

  1. parent_email / parent_phone blank while the parent IS an associated
     contact  → stamp from the contact whose name matches the deal-name parent
     (same heuristic the Teachworks sync uses; the TOR never matches).
  2. number_of_hours_in_this_po blank while amount is set (iLead multi-PO
     batches, 8/16-8/24) → hours = amount / $75 iLead rate, only when the
     division lands on a clean quarter-hour; anything else is reported, not
     guessed.

DRY_RUN=true prints every intended PATCH and writes nothing.
"""
from __future__ import annotations

import os

import requests

from . import hubspot_client as hs, teachworks_client as tw
from .config import DRY_RUN, cfg
from .deal_sync import _contact_matches_dealname

SINCE = os.environ.get("BACKFILL_SINCE", "2026-08-01T00:00:00Z")
ILEAD_RATE = 75.0


def _search(body: dict) -> dict:
    """Deal search is a READ (HubSpot just uses POST for it) — bypass the DRY_RUN
    write short-circuit so dry runs still see the real deals."""
    r = requests.post(f"{hs.HS_BASE}/crm/v3/objects/deals/search",
                      headers=hs._headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def _po_deals() -> list[dict]:
    out, after = [], None
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "EQ",
             "value": cfg()["po_inbox"]["deal_pipeline_id"]},
            {"propertyName": "createdate", "operator": "GTE", "value": SINCE}]}],
        "properties": ["dealname", "amount", "po_number", "parent_email", "parent_phone",
                       "number_of_hours_in_this_po", "student_school"],
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}], "limit": 100}
    while len(out) < 500:
        if after:
            body["after"] = after
        res = _search(body)
        out.extend(res.get("results", []))
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


def _parent_contact(deal_id: str, dealname: str) -> dict | None:
    try:
        assoc = hs._get(f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
    except Exception:  # noqa: BLE001
        return None
    ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
    for cid in ids[:5]:
        try:
            c = hs._get(f"/crm/v3/objects/contacts/{cid}",
                        {"properties": "email,firstname,lastname,phone,mobilephone"})
        except Exception:  # noqa: BLE001
            continue
        if _contact_matches_dealname(c.get("properties") or {}, dealname):
            return c
    return None


def _gold_deals() -> list[dict]:
    gold = cfg()["deal_sync"].get("gold_amount_pipelines", ["default", "16547180"])
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": list(gold)},
            {"propertyName": "createdate", "operator": "GTE", "value": SINCE}]}],
        "properties": ["dealname", "amount", "pipeline"],
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}], "limit": 100}
    return _search(body).get("results", [])


def _first_contact_email(deal_id: str) -> str:
    try:
        assoc = hs._get(f"/crm/v3/objects/deals/{deal_id}/associations/contacts")
        ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
        if ids:
            c = hs._get(f"/crm/v3/objects/contacts/{ids[0]}", {"properties": "email"})
            return ((c.get("properties") or {}).get("email") or "").lower()
    except Exception:  # noqa: BLE001
        pass
    return ""


def backfill_gold_amounts() -> None:
    """Gold + Gold-Renewal deals → the family's most CURRENT Teachworks invoice
    total, SPLIT EVENLY when several sibling deals share the same invoice
    (Roman, 2026-09-04: 'split shared totals'). Idempotent: recomputes stamped
    deals whose share drifted (e.g. a full total stamped before the split rule)."""
    deals = _gold_deals()
    print(f"gold amounts: {len(deals)} Gold/Renewal deals since {SINCE[:10]}")
    inv_cache: dict = {}
    groups: dict = {}   # (email, invoice number) → [(deal, invoice)]
    for d in deals:
        email = _first_contact_email(d["id"])
        if not email:
            if ((d.get("properties") or {}).get("amount") or "").strip() in ("", "0", "0.0"):
                print(f"  ⚠️  no contact email: {(d.get('properties') or {}).get('dealname')}")
            continue
        if email not in inv_cache:
            inv = None
            for acct, token in tw.accounts().items():
                cust = tw.find_customer_by_email(email, token)
                if cust:
                    inv = tw.latest_invoice(cust.get("id"), token)
                    if inv:
                        break
            inv_cache[email] = inv
        inv = inv_cache[email]
        if not inv:
            if ((d.get("properties") or {}).get("amount") or "").strip() in ("", "0", "0.0"):
                print(f"  ⚠️  no TW invoice found for {email}: {(d.get('properties') or {}).get('dealname')}")
            continue
        groups.setdefault((email, str(inv.get("number"))), []).append((d, inv))
    filled = skipped = 0
    for (email, number), members in groups.items():
        inv = members[0][1]
        share = round(inv["total"] / len(members), 2)
        for d, _ in members:
            p = d.get("properties") or {}
            cur = (p.get("amount") or "").strip()
            blankish = cur in ("", "0", "0.0")
            # untouched unless blank, or holding the UNSPLIT full total of a shared invoice
            needs = blankish or (len(members) > 1 and cur in (str(inv["total"]),
                                                              f"{inv['total']:g}",
                                                              f"{inv['total']:.1f}"))
            if not needs:
                skipped += 1
                continue
            split_bit = f" (1/{len(members)} of ${inv['total']:g})" if len(members) > 1 else ""
            print(f"  {'[DRY] ' if DRY_RUN else ''}{p.get('dealname', '?')[:55]} ← amount "
                  f"${share:g}{split_bit} (TW invoice {number}, {inv.get('date') or '?'})")
            filled += 1
            if not DRY_RUN:
                try:
                    hs._write("PATCH", f"/crm/v3/objects/deals/{d['id']}",
                              {"properties": {"amount": str(share)}})
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  PATCH failed for {d['id']}: {e}")
    print(f"gold amounts done: stamped {filled}, untouched {skipped}")


def run() -> None:
    deals = _po_deals()
    print(f"backfill: {len(deals)} charter PO deals since {SINCE[:10]} (DRY_RUN={DRY_RUN})")
    stamped = hours_fixed = skipped = 0
    for d in deals:
        p = d.get("properties") or {}
        patch: dict = {}
        # parent stamp from the associated parent contact
        if not (p.get("parent_email") or "").strip():
            c = _parent_contact(d["id"], p.get("dealname") or "")
            cp = (c or {}).get("properties") or {}
            email = (cp.get("email") or "").lower()
            if email and not email.endswith("@wetutorathome.com"):
                patch["parent_email"] = email
                phone = cp.get("phone") or cp.get("mobilephone")
                if phone and not (p.get("parent_phone") or "").strip():
                    patch["parent_phone"] = phone
            else:
                print(f"  ⚠️  no matching parent contact: {p.get('dealname')}")
        # hours from amount at the iLead rate — clean quarter-hours only
        if (not (p.get("number_of_hours_in_this_po") or "").strip()
                and (p.get("amount") or "").strip()
                and "ilead" in (p.get("student_school") or p.get("dealname") or "").lower()):
            try:
                hours = float(p["amount"]) / ILEAD_RATE
            except ValueError:
                hours = -1
            if hours > 0 and abs(hours * 4 - round(hours * 4)) < 0.001:
                patch["number_of_hours_in_this_po"] = round(hours, 2)
                hours_fixed += 1
            else:
                print(f"  ⚠️  amount {p.get('amount')} not clean at $75/hr: {p.get('dealname')}")
        if not patch:
            skipped += 1
            continue
        if "parent_email" in patch:
            stamped += 1
        print(f"  {'[DRY] ' if DRY_RUN else ''}{p.get('dealname', '?')[:60]} ← {patch}")
        if not DRY_RUN:
            try:
                hs._write("PATCH", f"/crm/v3/objects/deals/{d['id']}", {"properties": patch})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  PATCH failed for {d['id']}: {e}")
    print(f"backfill done: parent stamped {stamped}, hours fixed {hours_fixed}, untouched {skipped}")
    backfill_gold_amounts()


if __name__ == "__main__":
    run()
