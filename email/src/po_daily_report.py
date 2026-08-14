"""End-of-day PO ⇄ Teachworks report — one Slack DM to Roman (6 PM PT cron).

What came in today (every deal born with a po_number, gross value) and how
many already have a Teachworks invoice created — Kath's same-day STEP 1
conversion — with the misses named. A deal counts as covered when Kath stamped
`Invoice #` on it, or a TW invoice matching its amount was created on/after the
deal (each invoice claimable once). Read-only + one DM (Roman, 2026-08-13:
"at the end of each day i get a slack message that tells me the value of the
POs that came in and corresponds them to how many teachworks invoices created").
"""
from __future__ import annotations

from . import hubspot_client as hs, slack_client, teachworks_client as tw
from .business_hours import now_la
from .config import cfg


def _todays_po_deals() -> list[dict]:
    start = now_la().replace(hour=0, minute=0, second=0, microsecond=0)
    body = {"filterGroups": [{"filters": [
        {"propertyName": "po_number", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE",
         "value": str(int(start.timestamp() * 1000))}]}],
        "properties": ["dealname", "po_number", "amount", "invoice__",
                       "teacher_of_record_email", "createdate"],
        "limit": 100}
    res = hs._write("POST", "/crm/v3/objects/deals/search", body)
    return res.get("results", []) if isinstance(res, dict) else []


def _family_email(deal: dict) -> str:
    tor = ((deal.get("properties") or {}).get("teacher_of_record_email") or "").lower()
    for c in hs.get_deal_contacts(deal["id"]):
        cp = c.get("properties") or {}
        em = (cp.get("email") or "").strip().lower()
        if em and em != tor and "Teacher of Record" not in (cp.get("a_persona") or ""):
            return em
    return ""


def _family_invoices(email: str, parent_first: str, parent_last: str) -> list[dict]:
    out = []
    for _acct, token in tw.accounts().items():
        try:
            for cust in tw.customers_for_family(email, parent_last, parent_first,
                                                token=token):
                for inv in tw.tw_get("invoices", {"customer_id": cust.get("id")},
                                     token=token):
                    out.append({"id": inv.get("id"),
                                "date": str(inv.get("date") or inv.get("created_at") or "")[:10],
                                "total": inv.get("total") or inv.get("amount")})
        except Exception as e:  # noqa: BLE001 — a TW hiccup must not kill the report
            print(f"  ⚠️  TW lookup failed for {email}: {e}")
    return out


def _covered(deal: dict, invoices: list[dict], claimed: set) -> bool:
    """Kath stamped Invoice # on the deal, or a TW invoice matching the amount
    exists dated on/after the deal's creation day (claimed once)."""
    p = deal.get("properties") or {}
    if (p.get("invoice__") or "").strip():
        return True
    try:
        amt = float(p.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    created_day = str(p.get("createdate") or "")[:10]
    for inv in invoices:
        if inv["id"] in claimed or inv.get("total") is None:
            continue
        try:
            match = abs(float(inv["total"]) - amt) < 0.01
        except (TypeError, ValueError):
            continue
        if match and (inv.get("date") or "") >= created_day:
            claimed.add(inv["id"])
            return True
    return False


def run() -> None:
    roman = cfg()["staff"].get("roman", {})
    day = now_la().strftime("%a %b %-d")
    deals = _todays_po_deals()
    if not deals:
        slack_client.dm(roman.get("slack_user_id"),
                        f"📦 *PO day report — {day}*: no POs came in today.")
        print("no POs today")
        return
    fam_cache: dict = {}
    claimed: set = set()
    covered, missing = [], []
    total = 0.0
    for d in deals:
        p = d.get("properties") or {}
        try:
            total += float(p.get("amount") or 0)
        except (TypeError, ValueError):
            pass
        em = _family_email(d)
        if em and em not in fam_cache:
            parent = (p.get("dealname") or "").split(" - ")[0].split()
            fam_cache[em] = _family_invoices(
                em, parent[0] if parent else "",
                " ".join(parent[1:]) if len(parent) > 1 else "")
        if em and _covered(d, fam_cache.get(em, []), claimed):
            covered.append(p)
        else:
            missing.append(p)
    cov_val = sum(float(p.get("amount") or 0) for p in covered)
    lines = [f"📦 *PO day report — {day}*",
             f"{len(deals)} PO deal(s) came in, *${total:,.2f}* total.",
             f"🧾 Teachworks invoices created: *{len(covered)}/{len(deals)}* deals "
             f"covered (${cov_val:,.2f})."]
    if missing:
        lines.append("Still needing a TW invoice:")
        lines += [f"  • {p.get('dealname')} — ${p.get('amount')} "
                  f"(PO {p.get('po_number')})" for p in missing]
    msg = "\n".join(lines)
    slack_client.dm(roman.get("slack_user_id"), msg)
    print(msg)


if __name__ == "__main__":
    run()
