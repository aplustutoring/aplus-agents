#!/usr/bin/env python3
"""Monday queue digest (Roman 2026-09-16, STEP 7): per pipeline and per seat,
open tickets by stage and age, the oldest open one, entered and closed last
week by outcome, SLA breaches, overdue tasks per seat, machine-created tasks
last week against the ceiling. Renewals adds the trailing 4-week renewal rate
= renewed / (renewed + not renewing + no response), counted per family.

Posts to case_engine.digest.channel (Leadership team). DRY_RUN=true prints.
Deterministic: no prompt.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "email"))

from src import case_engine as ce, hubspot_client as hs, slack_client  # noqa: E402
from src.business_hours import now_la  # noqa: E402
from src.config import DRY_RUN, cfg, staff  # noqa: E402

PIPES = ["renewals", "support", "tutor"]
LABEL = {"renewals": "Renewals", "support": "Support", "tutor": "Tutor Accountability"}


def _owners() -> dict:
    out = {}
    for key, rec in (cfg().get("staff") or {}).items():
        if rec.get("hubspot_owner_id"):
            out[str(rec["hubspot_owner_id"])] = rec.get("name", key)
    return out


def _stage_labels(name: str) -> dict:
    return {str(v): k.replace("_", " ") for k, v in ce.pipeline(name)["stages"].items()}


def _week_ms(days: int = 7) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)


def pipeline_section(name: str, owners: dict) -> tuple[list[str], dict]:
    open_ = ce.open_tickets(name)
    labels = _stage_labels(name)
    by_stage = collections.Counter(labels.get(str((t.get("properties") or {}).get("hs_pipeline_stage")), "?") for t in open_)
    by_owner = collections.Counter(owners.get(str((t.get("properties") or {}).get("hubspot_owner_id")), "unassigned") for t in open_)
    ages = sorted(((ce.age_days((t.get("properties") or {}).get("createdate")), t) for t in open_), key=lambda x: -x[0])
    oldest = ages[0] if ages else None
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    breaches = [t for t in open_ if (t.get("properties") or {}).get("sla_due_at") and int((t["properties"]["sla_due_at"])) < now_ms]
    closed = ce.tickets_closed_since(name, _week_ms())
    by_outcome = collections.Counter(labels.get(str((t.get("properties") or {}).get("hs_pipeline_stage")), "?") for t in closed)
    entered = [t for t in open_ + closed if ((t.get("properties") or {}).get("createdate") or "") >= _iso(_week_ms())]
    lines = [f"*{LABEL[name]}*: {len(open_)} open"
             + (" (" + ", ".join(f"{k} {v}" for k, v in by_stage.most_common()) + ")" if by_stage else "")]
    if by_owner:
        lines.append("  by seat: " + ", ".join(f"{k} {v}" for k, v in by_owner.most_common()))
    if oldest:
        p = oldest[1].get("properties") or {}
        lines.append(f"  oldest: {oldest[0]}d, {p.get('subject', '')[:60]} ({owners.get(str(p.get('hubspot_owner_id')), 'unassigned')})")
    lines.append(f"  last 7 days: {len(entered)} entered, {len(closed)} closed"
                 + (" (" + ", ".join(f"{k} {v}" for k, v in by_outcome.most_common()) + ")" if by_outcome else ""))
    lines.append(f"  SLA breaches: {len(breaches)}")
    stats = {"open": len(open_), "closed": len(closed), "breaches": len(breaches)}
    if name == "renewals":
        closed4 = ce.tickets_closed_since(name, _week_ms(28))
        fam = {}
        for t in closed4:
            p = t.get("properties") or {}
            key = (p.get("subject") or "").split(" - ")[0].lower()   # per family, not per sibling
            fam[key] = labels.get(str(p.get("hs_pipeline_stage")), "?")
        c = collections.Counter(fam.values())
        denom = c.get("renewed", 0) + c.get("not renewing", 0) + c.get("no response", 0)
        rate = (c.get("renewed", 0) / denom) if denom else None
        lines.append(f"  trailing 4-week renewal rate: {f'{rate:.0%}' if rate is not None else 'n/a'} "
                     f"(renewed {c.get('renewed', 0)}, not renewing {c.get('not renewing', 0)}, no response {c.get('no response', 0)}, per family)")
        risk = [t for t in open_ if (t.get("properties") or {}).get("retention_risk") == "true"]
        lines.append(f"  retention risk flagged: {len(risk)}")
        # closest to zero first (Roman 2026-09-23: the board works by balance, not by age)
        lowest = []
        for t in open_:
            p = t.get("properties") or {}
            try:
                lowest.append((float(p.get("hours_left")), p))
            except (TypeError, ValueError):
                continue
        lowest.sort(key=lambda x: x[0])
        if lowest:
            lines.append("  lowest balances: " + "; ".join(
                f"{p.get('subject', '').split(':', 1)[-1].split(',')[0].strip()} {h:g} h "
                f"({owners.get(str(p.get('hubspot_owner_id')), 'unassigned')})" for h, p in lowest[:5]))
        # fleet-health defect: a charter or private-pay renewal owned by charter_sales
        cs = str((staff("charter_sales") or {}).get("hubspot_owner_id") or "")
        defects = [t for t in open_ if str((t.get("properties") or {}).get("hubspot_owner_id")) == cs
                   and (t.get("properties") or {}).get("funding_type") in ("charter", "private_pay")]
        if defects:
            lines.append(f"  :warning: DEFECT: {len(defects)} charter/private-pay renewal(s) owned by charter_sales")
    return lines, stats


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def tasks_section(owners: dict) -> list[str]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    ids = list(owners.keys())
    overdue = hs._search_all("/crm/v3/objects/tasks/search", [
        {"propertyName": "hs_task_status", "operator": "NOT_IN", "values": ["COMPLETED", "DEFERRED"]},
        {"propertyName": "hs_timestamp", "operator": "LT", "value": str(now_ms)},
        {"propertyName": "hubspot_owner_id", "operator": "IN", "values": ids}],
        ["hubspot_owner_id", "hs_task_subject"])
    by_owner = collections.Counter(owners.get(str((t.get("properties") or {}).get("hubspot_owner_id")), "?") for t in overdue)
    created = hs._search_all("/crm/v3/objects/tasks/search", [
        {"propertyName": "hs_createdate", "operator": "GTE", "value": str(_week_ms())},
        {"propertyName": "hubspot_owner_id", "operator": "IN", "values": ids}],
        ["hubspot_owner_id", "hs_task_subject", "hs_created_by_user_id"])
    machine = [t for t in created if not (t.get("properties") or {}).get("hs_created_by_user_id")]
    ceiling = int((cfg().get("tasks") or {}).get("daily_ceiling_per_owner") or 0)
    by_owner_m = collections.Counter(owners.get(str((t.get("properties") or {}).get("hubspot_owner_id")), "?") for t in machine)
    lines = [f"*Tasks*: {len(overdue)} overdue" + (" (" + ", ".join(f"{k} {v}" for k, v in by_owner.most_common()) + ")" if by_owner else ""),
             f"  machine-created last 7 days: {len(machine)} of {len(created)}"
             + (f", ceiling {ceiling}/seat/day" if ceiling else "")
             + (" (" + ", ".join(f"{k} {v}" for k, v in by_owner_m.most_common()) + ")" if by_owner_m else "")]
    return lines


def build() -> str:
    owners = _owners()
    out = [f"*Monday queue digest, {now_la().strftime('%b %-d')}*"]
    for name in PIPES:
        try:
            lines, _ = pipeline_section(name, owners)
        except Exception as e:  # noqa: BLE001
            lines = [f"*{LABEL[name]}*: read failed ({str(e)[:80]})"]
        out += lines
    try:
        out += tasks_section(owners)
    except Exception as e:  # noqa: BLE001
        out.append(f"*Tasks*: read failed ({str(e)[:80]})")
    return "\n".join(out)


def main() -> None:
    text = build()
    channel = ((cfg().get("case_engine") or {}).get("digest") or {}).get("channel") or ""
    print(text)
    if DRY_RUN or not channel or os.environ.get("QUEUE_DIGEST_PRINT_ONLY") == "1":
        print("[DRY_RUN] not posted")
        return
    slack_client.post_message(channel, text)


if __name__ == "__main__":
    main()
