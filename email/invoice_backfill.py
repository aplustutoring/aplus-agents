"""VERIFIED invoice-submitted backfill for the 2026-08-07..09 sweep backlog.

The 69 deals the first invoice-sweep run flagged (service months Mar–Jun 2026,
~$17.5k) were billed to the schools but never stamped in HubSpot (Roman,
2026-08-11). Instead of blind-stamping, each deal is verified against
Teachworks: a matching invoice (same family, same amount — preferring one whose
due date lands in the deal's service month, each invoice claimable ONCE) in a
submitted-ish status (Paid/Approved/Sent) proves the billing happened. Verified
deals get invoice_submitted_date = end of service month + the pipeline's
Invoice Submitted stage. No match (or only a 'Saved' draft) → EXCEPTION list
for Kath, never stamped.

APPLY=1 writes; default is a dry-run report. Runs in Actions (tokens live
there): workflow tw-invoice-backfill.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import sys

from src import hubspot_client as hs, teachworks_client as tw

APPLY = os.environ.get("APPLY") == "1"
SUBMITTED_STATUSES = ("paid", "approved", "sent")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_NAME_TAG = re.compile(r"\((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\)"
                       r"\s*(\d{2})/(\d{2})", re.I)


def _swept_deal_ids() -> list[str]:
    ids = []
    for line in open("state/audit_log.jsonl"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("source") == "invoice_sweep" and \
                "2026-08-07" <= (r.get("timestamp") or "") < "2026-08-10":
            ids.append(str(r["deal_id"]))
    return ids


def _service_month(dealname: str):
    m = _NAME_TAG.search(dealname or "")
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    year = 2000 + int(m.group(2) if month >= 8 else m.group(3))
    return year, month


def _invoice_submitted_stage(pipeline_id: str) -> str | None:
    data = hs._get("/crm/v3/pipelines/deals")
    for p in data.get("results", []):
        if str(p.get("id")) == str(pipeline_id):
            for s in p.get("stages", []):
                if "invoice submitted" in (s.get("label") or "").lower():
                    return s.get("id")
    return None


def _family_email(deal: dict) -> str:
    tor = ((deal.get("properties") or {}).get("teacher_of_record_email") or "").lower()
    for c in hs.get_deal_contacts(deal["id"]):
        cp = c.get("properties") or {}
        em = (cp.get("email") or "").strip().lower()
        if em and em != tor and "Teacher of Record" not in (cp.get("a_persona") or ""):
            return em
    return ""


def _invoices(email: str, parent_first: str, parent_last: str) -> list[dict]:
    out = []
    for _acct, token in tw.accounts().items():
        try:
            for cust in tw.customers_for_family(email, parent_last, parent_first, token=token):
                for inv in tw.tw_get("invoices", {"customer_id": cust.get("id")}, token=token):
                    out.append({"id": inv.get("id"),
                                "due": str(inv.get("due_date") or "")[:7],
                                "total": inv.get("total") or inv.get("amount"),
                                "status": str(inv.get("status") or "").lower()})
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  TW lookup failed for {email}: {e}", file=sys.stderr)
    return out


def main() -> None:
    ids = _swept_deal_ids()
    print(f"{'APPLY' if APPLY else 'DRY-RUN'}: {len(ids)} swept deals\n")
    res = hs._write("POST", "/crm/v3/objects/deals/batch/read",
                    {"inputs": [{"id": i} for i in ids],
                     "properties": ["dealname", "amount", "pipeline", "dealstage",
                                    "invoice_submitted_date", "teacher_of_record_email"]})
    deals = res.get("results", []) if isinstance(res, dict) else []
    stage_cache: dict = {}
    fam_cache: dict = {}
    claimed: set = set()
    stamped, exceptions = 0, []
    for d in sorted(deals, key=lambda x: (x.get("properties") or {}).get("dealname") or ""):
        p = d.get("properties") or {}
        name, amt = p.get("dealname"), p.get("amount")
        if p.get("invoice_submitted_date"):
            print(f"  · already stamped: {name}")
            continue
        sm = _service_month(name or "")
        email = _family_email(d)
        if not email:
            exceptions.append((name, amt, "no family contact/email on deal"))
            continue
        parent = (name or "").split(" - ")[0].split()
        key = (email, parent[0] if parent else "", " ".join(parent[1:]))
        if key not in fam_cache:
            fam_cache[key] = _invoices(email, key[1], key[2])
        invs = fam_cache[key]
        try:
            amt_f = float(amt or 0)
        except (TypeError, ValueError):
            exceptions.append((name, amt, "unparseable amount"))
            continue
        cands = [i for i in invs if i["id"] not in claimed
                 and i.get("total") is not None
                 and abs(float(i["total"]) - amt_f) < 0.01]
        month_pref = f"{sm[0]}-{sm[1]:02d}" if sm else None
        pick = next((i for i in cands
                     if month_pref and i["due"] == month_pref
                     and i["status"] in SUBMITTED_STATUSES), None) \
            or next((i for i in cands if i["status"] in SUBMITTED_STATUSES), None)
        if not pick:
            why = ("invoice exists but status "
                   + cands[0]["status"] if cands else "NO matching TW invoice")
            exceptions.append((name, amt, why))
            continue
        claimed.add(pick["id"])
        if sm:
            last = calendar.monthrange(sm[0], sm[1])[1]
            sub_date = f"{sm[0]}-{sm[1]:02d}-{last:02d}"
        else:
            sub_date = pick["due"] + "-28" if pick["due"] else None
        pid = p.get("pipeline")
        if pid not in stage_cache:
            stage_cache[pid] = _invoice_submitted_stage(pid)
        props = {"invoice_submitted_date": sub_date, "invoice__": str(pick["id"])}
        if stage_cache[pid]:
            props["dealstage"] = stage_cache[pid]
        print(f"  ✔ {name} ${amt} → TW inv {pick['id']} ({pick['status']}, due {pick['due']}) "
              f"→ stamp {sub_date}" + ("" if stage_cache[pid] else "  [stage NOT found]"))
        if APPLY:
            hs._write("PATCH", f"/crm/v3/objects/deals/{d['id']}", {"properties": props})
        stamped += 1
    print(f"\n{'STAMPED' if APPLY else 'WOULD STAMP'}: {stamped}")
    print(f"EXCEPTIONS ({len(exceptions)}):")
    for n, a, why in exceptions:
        print(f"  ✘ {n} ${a} — {why}")


if __name__ == "__main__":
    main()
