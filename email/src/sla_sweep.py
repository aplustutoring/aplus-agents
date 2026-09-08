"""Hourly SLA sweep + escalation chain.

1x breach (past due, ticket still open) → DM the owner (the scheduler).
2x breach (one more SLA window past)    → DM the supervisor who watches the owners (Mandy).
3x breach (two more SLA windows past)   → DM the last resort (Emily) + move ticket to Stuck.
Targets are config-driven (escalation.level2 / level3). Level 2 is skipped if the
supervisor is already the owner. Never re-pings a given level twice per ticket.
"""
from __future__ import annotations

from datetime import datetime

from . import audit, hubspot_client as hs, slack_client
from .business_hours import add_business_hours, now_la
from .config import cfg


def _latest_tickets() -> dict[str, dict]:
    """ticket_id → its latest SLA-bearing audit record (latest wins). A `ticket_reopened`
    record (customer replied to a waiting ticket) carries a fresh sla_due that supersedes
    the original `ticket_created` clock, so a reopen is treated as newly due rather than
    an instant breach."""
    tickets = {}
    for r in audit._iter_records():
        # po_processed = PO-inbox tickets — they carry sla_due too, and their
        # breaches were invisible to this sweep until 2026-08-14 (the Taylion
        # convert-to-invoice ticket sat past SLA with zero escalation)
        if (r.get("action_taken") in ("ticket_created", "ticket_reopened", "po_processed")
                and r.get("ticket_id") and r.get("sla_due")):
            tickets[r["ticket_id"]] = r
    return tickets


def _is_resolved(ticket_id: str) -> bool:
    stages = cfg()["hubspot"]["ticket_stages"]
    try:
        t = hs.get_ticket(ticket_id)
    except Exception:  # noqa: BLE001
        return False
    stage = (t.get("properties") or {}).get("hs_pipeline_stage")
    resolved = {stages.get("handled"), stages.get("closed"),
                cfg()["hubspot"].get("handled_stage_tutor")}  # Waiting on Tutor counts too
    return stage in resolved


def _breach_level(rec: dict, now: datetime) -> int:
    """0 on time; 1 past due; 2 past due by one more SLA window; 3 by two more."""
    due = datetime.fromisoformat(rec["sla_due"])
    if now <= due:
        return 0
    sla_hours = cfg()["routing"].get(rec.get("category"), {}).get("sla_hours")
    if not sla_hours:
        return 1
    second = add_business_hours(due, sla_hours)
    if now <= second:
        return 1
    third = add_business_hours(second, sla_hours)
    if now <= third:
        return 2
    return 3


def reconcile_handled() -> int:
    """Flip tickets to Handled when a human has replied on the thread.

    Replaces the Service Hub 'handled-on-reply' workflow (not available without
    Service Hub). The agent's own doc-receipt is excluded so it never self-resolves.
    """
    hs_cfg = cfg()["hubspot"]
    handled = hs_cfg["ticket_stages"].get("handled")
    if not handled or str(handled).startswith("REPLACE"):
        return 0
    tutor_stage = hs_cfg.get("handled_stage_tutor")
    tutor_cats = set(hs_cfg.get("tutor_facing_categories") or [])
    flipped = 0
    for ticket_id, rec in _latest_tickets().items():
        thread_id = rec.get("thread_id")
        if not thread_id or _is_resolved(ticket_id):
            continue
        try:
            if hs.thread_has_outbound_reply(thread_id, rec.get("receipt_message_id"),
                                            after_ts=rec.get("timestamp")):
                # Category-aware: tutor-facing tickets go to "Waiting on Tutor".
                stage = tutor_stage if (tutor_stage and rec.get("category") in tutor_cats) else handled
                hs.update_ticket_stage(ticket_id, stage)
                audit.append({"ticket_id": ticket_id, "thread_id": thread_id,
                              "category": rec.get("category"), "action_taken": "auto_handled"})
                flipped += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  reconcile error on ticket {ticket_id}: {e}")
    return flipped


def _owner_key_by_id(owner_id: str) -> str:
    """HubSpot owner id → staff key, so the aging sweep can DM the owner of a
    ticket it never saw created."""
    for key, s in (cfg().get("staff") or {}).items():
        if str(s.get("hubspot_owner_id") or "") == str(owner_id or ""):
            return key
    return ""


def _days_since(iso: str | None, now: datetime) -> float:
    if not iso:
        return 0.0
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=now.tzinfo)
    return (now - t).total_seconds() / 86400.0


def aging_sweep() -> int:
    """Nag on every OPEN ticket that has gone quiet, whatever created it.

    The escalation chain in run() reads the audit log, so it only covers tickets
    the agents filed, and it pings each level exactly once and then never again.
    This pass reads HubSpot directly and re-nags on a cadence, so an old ticket
    keeps making noise instead of going silent (Roman 2026-08-26).
    """
    acfg = cfg().get("aging_sweep") or {}
    if not acfg.get("enabled"):
        return 0
    staff = cfg()["staff"]
    esc = cfg().get("escalation", {})
    nag = float(acfg.get("nag_after_days", 7))
    sup = float(acfg.get("supervisor_after_days", 14))
    last = float(acfg.get("last_resort_after_days", 30))
    repeat = float(acfg.get("repeat_every_days", 7))
    now = now_la()

    try:
        tickets = hs.search_open_tickets()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  aging sweep could not list open tickets: {e}")
        return 0

    nagged = 0
    for t in tickets:
        p = t.get("properties") or {}
        quiet = _days_since(p.get("hs_lastmodifieddate"), now)
        if quiet < nag:
            continue
        tid = t["id"]
        # Cadence: one nag per repeat_every_days, however old the ticket is.
        # No prior nag means never nagged, which must NOT read as "just nagged".
        prior = audit.last_aging_nag(tid)
        if prior and _days_since(prior, now) < repeat:
            continue
        age = _days_since(p.get("createdate"), now)
        owner_key = _owner_key_by_id(p.get("hubspot_owner_id"))
        subject = (p.get("subject") or "(no subject)")[:70]
        url = hs.ticket_url(tid)
        targets = [owner_key]
        if age >= sup:
            targets.append(esc.get("level2"))
        if age >= last:
            targets.append(esc.get("level3"))
        seen, sent = set(), False
        for key in targets:
            if not key or key in seen:
                continue
            seen.add(key)
            who = staff.get(key, {})
            if not who.get("slack_user_id"):
                continue
            slack_client.dm(who["slack_user_id"], (
                f"🕸️ Ticket open {age:.0f}d, untouched {quiet:.0f}d — "
                f"*{subject}* (owner {owner_key or 'unassigned'}). {url}"))
            sent = True
        if sent:
            audit.append({"ticket_id": tid, "owner": owner_key,
                          "action_taken": "aging_nag",
                          "age_days": round(age, 1), "quiet_days": round(quiet, 1)})
            nagged += 1
    return nagged


def run() -> None:
    print(f"=== SLA sweep ({now_la().isoformat()}) ===")
    handled = reconcile_handled()
    if handled:
        print(f"  reconciled {handled} ticket(s) → Handled")
    staff = cfg()["staff"]
    esc = cfg().get("escalation", {})
    l2_key, l3_key = esc.get("level2"), esc.get("level3")
    now = now_la()
    escalated = 0

    for ticket_id, rec in _latest_tickets().items():
        level = _breach_level(rec, now)
        if level == 0 or _is_resolved(ticket_id):
            continue
        already = audit.escalation_levels_pinged(ticket_id)
        owner_key = rec.get("owner")
        cat = rec.get("category")

        for lvl in range(1, level + 1):
            if lvl in already:
                continue
            url = hs.ticket_url(ticket_id)
            age = rec.get("sla_due")
            if lvl == 1:  # the owner (scheduler)
                tgt = staff.get(owner_key or "", {})
                msg = f"⏰ SLA breach: *{cat}* past due ({age}). {url}"
            elif lvl == 2:  # supervisor who watches the owners (Mandy)
                if l2_key and l2_key == owner_key:
                    continue  # supervisor is already the owner — pinged at lvl 1
                tgt = staff.get(l2_key or "", {})
                msg = (f"🚨 2x SLA breach: *{cat}* (owner {owner_key}) due {age}. "
                       f"Please check in with them. {url}")
            else:  # lvl 3 → last resort (Emily) + move to Stuck
                tgt = staff.get(l3_key or "", {})
                msg = (f"🆘 3x SLA breach — last resort: *{cat}* (owner {owner_key}) "
                       f"due {age}, still open. {url}")
                stuck = cfg()["hubspot"].get("stuck_stage")
                if stuck:
                    try:
                        hs.update_ticket_stage(ticket_id, stuck)
                    except Exception as e:  # noqa: BLE001
                        print(f"  ⚠️  could not move ticket {ticket_id} to Stuck: {e}")
            slack_client.dm(tgt.get("slack_user_id", ""), msg)
            audit.append({
                "ticket_id": ticket_id,
                "category": cat,
                "owner": owner_key,
                "action_taken": "escalation",
                "breach_level": lvl,
            })
            escalated += 1

    print(f"=== escalated {escalated} breach level(s) ===")
    aged = aging_sweep()
    print(f"=== nagged {aged} aging ticket(s) ===")


if __name__ == "__main__":
    run()
