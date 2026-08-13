"""READ-ONLY cross-reference: recent PO deals ↔ Teachworks invoices.

For every charter deal with a po_number created since AFTER_ISO, resolve the
family (the deal's non-TOR contact), pull that customer's Teachworks invoices
(both accounts), and report which deals have a matching invoice (same dollar
amount, invoice dated on/after the deal) and which have NOTHING — i.e. Kath's
STEP 1 (convert PO → TW invoice) hasn't happened or wasn't linked.

Runs in GitHub Actions (tw-invoice-xref workflow) where the tokens live.
Writes nothing anywhere — output is the run log.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from src import hubspot_client as hs, teachworks_client as tw

AFTER_MS = 1786406400000   # 2026-08-07T00:00:00Z — the new-pipeline era


def _recent_po_deals() -> list[dict]:
    body = {"filterGroups": [{"filters": [
        {"propertyName": "po_number", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": str(AFTER_MS)},
    ]}],
        "properties": ["dealname", "po_number", "amount", "invoice__",
                       "invoice_submitted_date", "teacher_of_record_email"],
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
        "limit": 100}
    res = hs._write("POST", "/crm/v3/objects/deals/search", body)
    return res.get("results", []) if isinstance(res, dict) else []


def _family_email(deal: dict) -> str:
    tor = ((deal.get("properties") or {}).get("teacher_of_record_email") or "").lower()
    for c in hs.get_deal_contacts(deal["id"]):
        cp = c.get("properties") or {}
        em = (cp.get("email") or "").strip().lower()
        if not em or em == tor:
            continue
        if "Teacher of Record" in (cp.get("a_persona") or ""):
            continue
        return em
    return ""


def _invoices_for(email: str) -> list[dict]:
    out = []
    for acct, token in tw.accounts().items():
        try:
            for cust in tw.tw_get("customers", {"email": email}, token=token):
                for inv in tw.tw_get("invoices", {"customer_id": cust.get("id")},
                                     token=token):
                    out.append({"acct": acct,
                                "id": inv.get("id"),
                                "number": inv.get("number") or inv.get("invoice_number"),
                                "date": str(inv.get("date") or inv.get("created_at") or "")[:10],
                                "due": str(inv.get("due_date") or "")[:10],
                                "total": inv.get("total") or inv.get("amount"),
                                "status": inv.get("status"),
                                "desc": str(inv.get("description") or "")[:60]})
        except Exception as e:  # noqa: BLE001 — report, don't die
            print(f"  ⚠️  TW lookup failed for {email} [{acct}]: {e}", file=sys.stderr)
    return out


def main() -> None:
    deals = _recent_po_deals()
    print(f"PO deals since 2026-08-07 with a po_number: {len(deals)}\n")
    fam_cache: dict[str, list[dict]] = {}
    by_family: dict[str, list] = defaultdict(list)
    for d in deals:
        em = _family_email(d)
        by_family[em or "(no family contact)"].append(d)
        if em and em not in fam_cache:
            fam_cache[em] = _invoices_for(em)

    missing = 0
    for em, ds in by_family.items():
        invs = fam_cache.get(em, [])
        print(f"══ {em} — {len(invs)} TW invoice(s) on file")
        for inv in invs:
            print(f"   TW inv {inv['number'] or inv['id']} [{inv['acct']}] "
                  f"date {inv['date']} due {inv['due']} total {inv['total']} "
                  f"status {inv['status']} {inv['desc']}")
        for d in ds:
            p = d.get("properties") or {}
            amt = p.get("amount")
            try:
                match = [i for i in invs
                         if i.get("total") is not None
                         and abs(float(i["total"]) - float(amt or 0)) < 0.01
                         and (i.get("date") or "") >= "2026-08-07"]
            except (TypeError, ValueError):
                match = []
            stamped = p.get("invoice__") or ""
            if match:
                nums = ", ".join(str(m["number"] or m["id"]) for m in match)
                flag = "" if stamped else "  (deal Invoice # NOT filled)"
                print(f"   ✔ {p.get('dealname')} | PO {p.get('po_number')} | "
                      f"${amt} → TW invoice {nums}{flag}")
            else:
                missing += 1
                print(f"   ✘ {p.get('dealname')} | PO {p.get('po_number')} | "
                      f"${amt} → NO matching TW invoice")
        print()
    print(f"SUMMARY: {len(deals)} deals, {len(deals) - missing} matched, "
          f"{missing} with NO matching TW invoice.")


if __name__ == "__main__":
    main()
