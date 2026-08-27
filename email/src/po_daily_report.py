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
from .config import cfg, staff


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


def _all_po_deals() -> list[dict]:
    """Every deal carrying a po_number (portal-wide, paginated) — the
    duplicate check must see history, not just today."""
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "po_number", "operator": "HAS_PROPERTY"}]}],
            "properties": ["dealname", "po_number", "createdate", "pipeline"],
            "limit": 200}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        if not isinstance(res, dict):
            break
        out += res.get("results", [])
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


def _normalize_po(raw: str) -> str:
    """POs are stored bare (no 'PO' prefix) but normalize defensively."""
    s = (raw or "").strip().lower()
    for pre in ("po#", "po ", "po-", "#"):
        if s.startswith(pre):
            s = s[len(pre):].strip()
    return s


def _is_real_po(po: str) -> bool:
    """A real PO number contains digits and is at least 4 chars. Batch labels
    humans typed instead ('summer2025' is digits+words but a label; 'pending',
    'n/a', 'amy chapin po', '0', '.') are placeholder values — reported as a
    count, not as duplicates. First live sweep 2026-08-26: ~270 deals carry
    placeholders."""
    if len(po) < 4 or not any(c.isdigit() for c in po):
        return False
    known_labels = ("summer", "pending", "n/a", "none", "tbd")
    return not any(k in po for k in known_labels)


ACTION_SINCE = "2026-08-01"   # Roman 2026-08-26: act on Aug 2026 forward only,
                              # no retroactive cleanup of historic data.


def _family_key(dealname: str) -> str:
    """STUDENT + SCHOOL segments of 'Parent - Student - School N - YY/YY' —
    the parent name is unreliable (two parent contacts for one kid flagged a
    false positive: Claire Dennis / Dennis Levin, same Gianna). Falls back to
    the parent segment for short names."""
    parts = [s.strip().lower() for s in (dealname or "").split(" - ")]
    if len(parts) >= 3:
        school = parts[2].split("(")[0].strip().rstrip("0123456789 ")
        return f"{parts[1]}|{school}"
    return parts[0] if parts else ""


def find_duplicate_pos(deals: list[dict]) -> tuple[dict[str, list[dict]], int]:
    """(VIOLATIONS {po: [deal props,...]}, placeholder_deal_count).

    Roman's rules (2026-08-26):
    - one PO split across a family's monthly deals is FINE;
    - Heartland issues ONE PO form for MULTIPLE students, so cross-family on
      Heartland deals is FINE;
    - a VIOLATION is the same PO (a) across different families outside
      Heartland, or (b) on the same exact dealname twice (deal
      double-created), Heartland included;
    - ACTION WINDOW: only groups touching a deal created on/after Aug 2026
      are flagged — no retroactive cleanup.
    Placeholder values are a data gap, counted separately, never flagged."""
    by_po: dict[str, list[dict]] = {}
    placeholders = 0
    for d in deals:
        p = d.get("properties") or {}
        po = _normalize_po(p.get("po_number"))
        if not po:
            continue
        if not _is_real_po(po):
            placeholders += 1
            continue
        by_po.setdefault(po, []).append(p)
    violations: dict[str, list[dict]] = {}
    for po, ds in by_po.items():
        if len(ds) < 2:
            continue
        if not any(str(p.get("createdate") or "")[:10] >= ACTION_SINCE for p in ds):
            continue                      # historic-only group: not our problem
        names = [str(p.get("dealname") or "").strip().lower() for p in ds]
        same_deal_twice = len(names) != len(set(names))
        fams = {_family_key(p.get("dealname")) for p in ds}
        all_heartland = all("heartland" in n for n in names)
        cross_family = len(fams) > 1 and not all_heartland
        if cross_family or same_deal_twice:
            violations[po] = ds
    return violations, placeholders


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


def _dupe_lines() -> list[str]:
    """Red-flag section: real PO numbers appearing on more than one deal,
    plus a one-line count of placeholder PO values (data gap, not billing)."""
    try:
        dupes, placeholders = find_duplicate_pos(_all_po_deals())
    except Exception as e:  # noqa: BLE001 — the dup check must not kill the report
        return [f"⚠️ duplicate-PO check failed: {e}"]
    lines: list[str] = []
    if dupes:
        lines.append(f"🚩 *DUPLICATE PO NUMBERS — {len(dupes)} PO(s) on multiple "
                     f"deals (one PO must never bill twice):*")
        for po, ds in sorted(dupes.items(), key=lambda kv: -len(kv[1]))[:10]:
            names = "; ".join(f"{p.get('dealname')} ({str(p.get('createdate') or '')[:10]})"
                              for p in ds[:4])
            lines.append(f"  • PO {po} on {len(ds)} deals: {names}")
        if len(dupes) > 10:
            lines.append(f"  … and {len(dupes) - 10} more")
    if placeholders:
        lines.append(f"ℹ️ {placeholders} deal(s) carry a placeholder instead of a "
                     f"real PO number (summer2025 / pending / name labels).")
    return lines


def run() -> None:
    roman = staff("roman")
    day = now_la().strftime("%a %b %-d")
    dupe_lines = _dupe_lines()
    deals = _todays_po_deals()
    if not deals:
        msg = f"📦 *PO day report — {day}*: no POs came in today."
        if dupe_lines:
            msg += "\n" + "\n".join(dupe_lines)
        slack_client.dm(roman.get("slack_user_id"), msg)
        print(msg)
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
    lines += dupe_lines
    msg = "\n".join(lines)
    slack_client.dm(roman.get("slack_user_id"), msg)
    print(msg)


if __name__ == "__main__":
    run()
