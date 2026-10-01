"""End-of-day PO ⇄ Teachworks report — one Slack DM to Roman (6 PM PT cron).

What came in today (every deal born with a po_number, gross value) and how
many already have a Teachworks invoice created — Kath's same-day STEP 1
conversion — with the misses named. A deal counts as covered when Kath stamped
`Invoice #` on it, or a TW invoice matching its amount was created on/after the
deal (each invoice claimable once).

It also carries the standing cross-reference (Roman, 2026-10-01): every charter
deal must tie to whatever its pipeline's billing model requires, which is NOT
the same everywhere. Traditional Vendor Funds and the Level Up pipelines take a
PO per student; IEM Inc. bills the school directly on one charge and correctly
has none. Models are declared in config, and a pipeline with no model declared
is reported rather than assumed.

Where the invoice covers a cohort GROUP rather than a student (IEM HSA, keyed
on hsa_group), one number anywhere in the group satisfies the group and a group
with none is named once instead of three times.

Read-only + one DM (Roman, 2026-08-13:
"at the end of each day i get a slack message that tells me the value of the
POs that came in and corresponds them to how many teachworks invoices created").
"""
from __future__ import annotations

from datetime import datetime

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


def _waiting_on_parent_lines() -> list[str]:
    """Every PO deal still NEEDS PARENT, every day, until it resolves. Roman
    2026-09-11: "I just can't have deals falling through" and "I can't have my
    team getting 50 DMs" — so the standing list lives in the one report Roman
    already reads, and nobody gets a new DM for it."""
    try:
        from .po_inbox import _open_chases
        chases = [c for lst in _open_chases().values() for c in lst]
    except Exception as e:  # noqa: BLE001 - the report never fails on this
        print(f"  \u26a0\ufe0f  open-chase list failed (non-fatal): {e}")
        return []
    if not chases:
        return []
    today = now_la().date()
    out = [f"\U0001f6a7 Waiting on parent info ({len(chases)} PO deal(s), nothing can be "
           f"scheduled or invoiced until it lands):"]
    for c in sorted(chases, key=lambda x: x.get("timestamp") or ""):
        try:
            opened = datetime.fromisoformat(c.get("timestamp") or "").date()
            age = f"{(today - opened).days}d"
        except (TypeError, ValueError):
            age = "?"
        out.append(f"  \u2022 {c.get('deal_name')} \u2014 {age}, asked {c.get('chase_to') or '?'}"
                   + (f" (PO {c.get('po_number')})" if c.get("po_number") else ""))
    return out


# Stages where nothing is owed either way.
_DEAD_STAGES = {"Stopped", "Hours Reassigned"}


def _billing_models() -> dict:
    return (cfg().get("deal_billing_models") or {})


def _stage_labels() -> dict:
    res = hs._get("/crm/v3/pipelines/deals")
    return {s["id"]: s["label"] for p in res.get("results", [])
            for s in p.get("stages", [])}


def _live_charter_deals() -> list[dict]:
    """Every deal this school year in a pipeline we have a model for."""
    models = (_billing_models().get("pipelines") or {})
    pipes = [k for k in models if k != "default" and models[k] != "none"]
    if not pipes:
        return []
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "IN", "values": pipes},
            {"propertyName": "createdate", "operator": "GTE",
             "value": _season_start()}]}],
            # The grouping fields come from config, so naming a new one there
            # does not need a code change. Without this the group path silently
            # never fires: p.get("hsa_group") is None when it was not asked for,
            # which read as "no group" and reported three deals instead of one
            # group on the first live run.
            "properties": (["dealname", "po_number", "invoice__",
                            "invoice_number", "dealstage", "pipeline", "amount"]
                           + sorted(set((_billing_models().get("invoice_groups")
                                         or {}).values()))),
            "limit": 100}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        if not isinstance(res, dict):
            return out
        out += res.get("results", [])
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            return out


def _season_start() -> str:
    """July 1 of the current school year."""
    n = now_la()
    return f"{n.year if n.month >= 7 else n.year - 1}-07-01"


def _has(p: dict, *names: str) -> bool:
    return any((p.get(n) or "").strip() for n in names)


def billing_gaps(deals: list[dict], stages: dict) -> dict:
    """Which deals do not match their own pipeline's billing model.

    Split by model on purpose. On 2026-10-01 a single global rule flagged all
    eight IEM Inc. deals as "missing a PO" and put $11,250 at risk in a report
    to Roman. They bill the school directly and were correct; the real exposure
    was three deals missing an invoice. A check that cries wolf on an entire
    pipeline every day gets muted in a week.

    And where a pipeline invoices a GROUP (invoice_groups in config), the group
    is the unit: one number anywhere in it satisfies all of it, and a group
    with none is reported once rather than per deal.
    """
    models = (_billing_models().get("pipelines") or {})
    groups_by_pipe = (_billing_models().get("invoice_groups") or {})
    out: dict = {"no_po": [], "no_invoice": [], "unknown_pipeline": [],
                 "no_invoice_groups": []}
    # first pass: which groups have an invoice anywhere in them
    invoiced_group: dict = {}
    for d in deals:
        p = d.get("properties") or {}
        field = groups_by_pipe.get(str(p.get("pipeline")))
        g = (p.get(field) or "").strip() if field else ""
        if not g:
            continue
        key = (str(p.get("pipeline")), g)
        invoiced_group[key] = (invoiced_group.get(key, False)
                               or _has(p, "invoice__", "invoice_number"))
    pending: dict = {}

    for d in deals:
        p = d.get("properties") or {}
        stage = stages.get(p.get("dealstage"), "")
        if stage in _DEAD_STAGES:
            continue
        model = models.get(str(p.get("pipeline")))
        if model is None:
            out["unknown_pipeline"].append(p)
            continue
        if model == "none":
            continue
        if model == "po_and_invoice" and not _has(p, "po_number"):
            out["no_po"].append(p)
        # An invoice is only owed once service has started. Pre-Lesson deals
        # are not late, they are early.
        if stage == "Pre-Lesson" or _has(p, "invoice__", "invoice_number"):
            continue
        field = groups_by_pipe.get(str(p.get("pipeline")))
        g = (p.get(field) or "").strip() if field else ""
        if not g:
            out["no_invoice"].append(p)
            continue
        key = (str(p.get("pipeline")), g)
        if invoiced_group.get(key):
            continue                 # a sibling in this group carries the number
        pending.setdefault(g, []).append(p)

    for g, ps in sorted(pending.items()):
        out["no_invoice_groups"].append({"group": g, "deals": ps})
    return out


def _billing_lines() -> list[str]:
    bm = _billing_models()
    if not bm.get("enabled"):
        return []
    try:
        stages = _stage_labels()
        deals = _live_charter_deals()
    except Exception as e:  # noqa: BLE001 — the report must survive this section
        return [f"⚠️ billing cross-reference could not run: {e}"]
    if not deals:
        return []
    gaps = billing_gaps(deals, stages)
    n = (len(gaps["no_po"]) + len(gaps["no_invoice"])
         + len(gaps["unknown_pipeline"])
         + sum(len(g["deals"]) for g in gaps.get("no_invoice_groups") or []))
    if not n:
        return [f"🔗 Every one of the {len(deals)} charter deals this year ties to "
                f"its PO and invoice."]
    lines = [f"🔗 *Cross-reference: {n} of {len(deals)} charter deals do not tie up.*"]
    if gaps["no_po"]:
        money = sum(float(p.get("amount") or 0) for p in gaps["no_po"])
        lines.append(f"  No PO, where the school issues one per student "
                     f"(${money:,.0f}):")
        lines += [f"    • {p.get('dealname')}" for p in gaps["no_po"][:10]]
    if gaps["no_invoice"]:
        money = sum(float(p.get("amount") or 0) for p in gaps["no_invoice"])
        lines.append(f"  Service started, no invoice number on the deal "
                     f"(${money:,.0f}):")
        lines += [f"    • {p.get('dealname')} — ${p.get('amount')}"
                  for p in gaps["no_invoice"][:10]]
    for grp in gaps.get("no_invoice_groups") or []:
        ps = grp["deals"]
        money = sum(float(p.get("amount") or 0) for p in ps)
        who = ", ".join((p.get("dealname") or "").split(" - ")[1]
                        if " - " in (p.get("dealname") or "") else "?"
                        for p in ps)
        lines.append(f"  Group *{grp['group']}* has no invoice number on any of "
                     f"its {len(ps)} deal(s) (${money:,.0f}): {who}")
    if gaps["unknown_pipeline"]:
        lines.append(f"  {len(gaps['unknown_pipeline'])} deal(s) in a pipeline with "
                     f"no billing model declared, so nothing was checked. Add it to "
                     f"deal_billing_models.pipelines in email/config.yaml:")
        lines += [f"    • {p.get('dealname')}"
                  for p in gaps["unknown_pipeline"][:5]]
    return lines


def run() -> None:
    roman = staff("roman")
    day = now_la().strftime("%a %b %-d")
    dupe_lines = _dupe_lines()
    waiting_lines = _waiting_on_parent_lines()
    deals = _todays_po_deals()
    if not deals:
        msg = f"📦 *PO day report — {day}*: no POs came in today."
        if dupe_lines:
            msg += "\n" + "\n".join(dupe_lines)
        if waiting_lines:
            msg += "\n" + "\n".join(waiting_lines)
        # A quiet PO day is exactly when an untied deal should still surface.
        bl = _billing_lines()
        if bl:
            msg += "\n" + "\n".join(bl)
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
    lines += waiting_lines
    lines += _billing_lines()
    msg = "\n".join(lines)
    slack_client.dm(roman.get("slack_user_id"), msg)
    print(msg)


if __name__ == "__main__":
    run()
