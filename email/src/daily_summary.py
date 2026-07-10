"""Daily end-of-day summary (6 PM PT every day), DM'd to a chosen staffer.

Reads today's activity from the committed audit log and posts a recap. Scheduled
via dual UTC crons; a PT-hour gate ensures it fires once at 18:00 PT regardless of
DST. Set FORCE_RUN=true (or DRY_RUN) to bypass the gate for testing.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime

from . import audit, slack_client
from .business_hours import LA, now_la
from .config import DRY_RUN, cfg


def gather_today() -> dict:
    today = now_la().date()
    by_cat: Counter = Counter()
    by_owner: Counter = Counter()
    drafts = junk = escalations = total = deals_moved = 0
    deal_moves: list = []   # each: {deal_name, from, to}
    for r in audit._iter_records():
        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LA).date()
        except ValueError:
            continue
        if d != today:
            continue
        action = r.get("action_taken")
        if action == "ticket_created":
            total += 1
            by_cat[r.get("category", "unknown")] += 1
            if r.get("owner"):
                by_owner[r["owner"]] += 1
            if r.get("draft_posted"):
                drafts += 1
            moves = (r.get("deal_moved") or {}).get("moves", [])
            deals_moved += len(moves)
            deal_moves.extend(moves)
        elif action == "junk_archived":
            junk += 1
            by_cat["junk"] += 1
        elif action == "escalation":
            escalations += 1
    return {
        "date": today.isoformat(), "total": total, "by_category": dict(by_cat),
        "by_owner": dict(by_owner), "drafts": drafts, "junk": junk,
        "escalations": escalations, "deals_moved": deals_moved,
        "deal_moves": deal_moves,
    }


def ticket_eod_stats() -> dict:
    """Tickets created/closed today vs yesterday + a breakdown of the still-open ones.

    Created = first audit record per ticket (reopen records don't double-count).
    Closed = HubSpot tickets whose stage hit Done, bucketed by close date.
    """
    from .business_hours import prev_business_day
    from .config import cfg
    today = now_la().date()
    yday = prev_business_day(today)   # previous BUSINESS day (Fri on a Mon)
    done_stage = cfg()["hubspot"]["ticket_stages"]["closed"]

    first_seen: dict = {}   # ticket_id -> (date, category, owner)
    for r in audit._iter_records():
        tid = r.get("ticket_id")
        if not tid or r.get("action_taken") != "ticket_created":
            continue
        if str(r.get("message_id", "")).startswith("reopen:"):
            continue
        if tid in first_seen:
            continue
        ts = r.get("timestamp", "")
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LA).date()
        except ValueError:
            continue
        first_seen[tid] = (d, r.get("category", "?"), r.get("owner") or "unassigned")

    stages = {"1378066770": "Needs Approval", "131537027": "Working on it",
              "2": "Waiting on Family", "3": "Waiting on Tutor",
              "943335739": "Charter Docs", "131537028": "Stuck", "4": "Done"}
    out = {"created": {today: 0, yday: 0}, "closed": {today: 0, yday: 0}, "open": []}
    from . import hubspot_client as hs

    # Created + still-open: from the audit's first-seen dates.
    for tid, (d, cat, owner) in first_seen.items():
        if d == today:
            out["created"][today] += 1
        elif d == yday:
            out["created"][yday] += 1
        if d < yday:   # still include weekend (Sat/Sun) arrivals on a Monday
            continue
        try:
            t = hs.get_ticket(tid)
            stage = (t.get("properties") or {}).get("hs_pipeline_stage")
        except Exception:  # noqa: BLE001
            continue
        if stage != done_stage:
            out["open"].append({"ticket": tid, "category": cat, "owner": owner,
                                "stage": stages.get(stage, stage), "created": d.isoformat()})

    # Closed: any ticket whose closed_date lands today/yesterday (PT), regardless of
    # when it was created — the true operational "closed that day" number.
    midnight_yday = datetime.combine(yday, datetime.min.time(), tzinfo=LA)
    start_ms = str(int(midnight_yday.timestamp() * 1000))
    after = None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "closed_date", "operator": "GTE", "value": start_ms}]}],
            "properties": ["closed_date"], "limit": 100}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/tickets/search", body)
        if not isinstance(res, dict):
            break
        for t in res.get("results", []):
            cd = (t.get("properties") or {}).get("closed_date")
            if not cd:
                continue
            try:
                cdate = datetime.fromisoformat(cd.replace("Z", "+00:00")).astimezone(LA).date()
            except ValueError:
                continue
            if cdate == today:
                out["closed"][today] += 1
            elif cdate == yday:
                out["closed"][yday] += 1
        after = (res.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return out


def format_ticket_eod(s: dict) -> str:
    from .business_hours import prev_business_day
    today = now_la().date()
    yday = prev_business_day(today)
    ylabel = yday.strftime("%a")   # e.g. "Fri" when today is Mon
    lines = [
        "*🎫 Tickets EOD:*",
        f"  Today: created {s['created'][today]} · closed {s['closed'][today]}"
        f"  |  {ylabel}: created {s['created'][yday]} · closed {s['closed'][yday]}",
    ]
    # "New since {yday}" = anything created after the last business day (weekend + today) —
    # weekend arrivals are NOT a backlog; schedulers are off Sat/Sun. "Carried over" =
    # still open from the last business day or earlier (the real attention list).
    new_since = [o for o in s["open"] if o["created"] > yday.isoformat()]
    carried = [o for o in s["open"] if o["created"] <= yday.isoformat()]
    for label, group in ((f"New since {ylabel} (incl. weekend)", new_since),
                         ("⚠️ Carried over — still open from a prior business day", carried)):
        if group:
            lines.append(f"  *{label} ({len(group)}):*")
            for o in group:
                lines.append(f"    • {o['category']} → {o['owner']} [{o['stage']}] (in {o['created']})")
    if not s["open"]:
        lines.append("  ✅ Nothing open from the last business day.")
    return "\n".join(lines)


def format_summary(m: dict) -> str:
    cats = "\n".join(f"  • {k}: {v}" for k, v in sorted(m["by_category"].items())) or "  • none"
    owners = "\n".join(f"  • {k}: {v}" for k, v in sorted(m["by_owner"].items())) or "  • none"
    return (
        f"*📬 Daily Email Summary — {m['date']}*\n"
        f"Triaged today: *{m['total']}*  |  drafts ready: {m['drafts']}  "
        f"|  junk filed: {m['junk']}  |  escalations: {m['escalations']}  "
        f"|  💸 deals auto-moved: *{m.get('deals_moved', 0)}*\n"
        + (("*💸 Deals moved today (undo if any look wrong):*\n"
            + "\n".join(f"  • {mv.get('deal_name')}: {mv.get('from')} → {mv.get('to')}"
                        for mv in m.get("deal_moves", [])) + "\n")
           if m.get("deal_moves") else "")
        + f"*By category:*\n{cats}\n*By owner:*\n{owners}"
    )


def run() -> None:
    force = DRY_RUN or os.getenv("FORCE_RUN", "").lower() == "true"
    if not force and now_la().hour != 18:
        print(f"not 6 PM PT (hour={now_la().hour}); skipping daily summary")
        return
    m = gather_today()
    text = format_summary(m)
    try:
        text += "\n" + format_ticket_eod(ticket_eod_stats())
    except Exception as e:  # noqa: BLE001 — EOD section is best-effort
        print(f"  ⚠️  ticket EOD section failed (non-fatal): {e}")
    print(text)
    ds = cfg().get("daily_summary", {})
    recipient = cfg()["staff"].get(ds.get("recipient", "roman"), {})
    slack_client.dm(recipient.get("slack_user_id", ""), text)
    if ds.get("also_channel"):
        slack_client.post_message(cfg()["slack"]["digest_channel"], text)
    print("=== daily summary sent ===")


if __name__ == "__main__":
    run()
