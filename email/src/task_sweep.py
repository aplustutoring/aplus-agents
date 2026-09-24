"""Daily task-completion sweep — do assigned HubSpot Tasks actually get done?

Two agents create HubSpot Tasks (email follow-ups, call-agent handoffs) and
humans make more by hand, but nothing ever read one back: a task past its due
date made no noise anywhere. This sweep reads every open task owned by the
monitored seats straight from HubSpot each weekday morning and:

1. Posts ONE channel digest (silent when clean): per owner, what is overdue
   and what is due today.
2. DMs an owner only once a task is dm_after_days past due, re-DMing on a
   dm_repeat_days cadence via the audit log — never a daily drumbeat.
3. On the weekly stats day, appends a completion scoreboard to the digest:
   tasks each owner completed in the last 7 days, on time vs late.

Deterministic sweep — no reasoning, no CARE pointer. The ONE write it makes is
auto-closing tasks whose completion signal already exists in the CRM (see
_autoclose_done_tasks): on 2026-08-31 ten "Convert PO to TW invoice" tasks sat
NOT_STARTED while every one of their invoices (54528-54537) was already filled
in — Kath does the work, the task list keeps the phantom. Nagging someone about
finished work is how a queue stops being read at all.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from . import audit, hubspot_client as hs, slack_client
from .business_hours import _is_business_day, now_la
from .config import cfg


RATION_DUE_HOUR = 9   # rationed tasks come due at 9 AM PT on their day


def _next_business_day(d):
    d = d + timedelta(days=1)
    while not _is_business_day(d):
        d = d + timedelta(days=1)
    return d


def _ration_bulk_tasks(tasks: list[dict], owners: dict[str, str], now: datetime,
                       rcfg: dict) -> list[str]:
    """Turn bulk workflow call lists into a daily ration.

    A workflow enrolling a list creates one CALL task per contact, every one
    due the day it lands: charter_sales received 98 on 2026-09-01 and 189 on
    2026-09-04 and had 426 overdue tasks nine days later. Nobody works a list
    of 287 same-day calls; the digest just reports the whole thing overdue
    and the DM nags about it forever. So: for each owner, every workflow with
    at least min_batch open tasks of the configured types is pooled into ONE
    queue (workflows matching `order` first, then oldest first) and re-dated
    per_day per business day starting today. Recomputed on every run from the
    same ordering, so finished calls pull the remaining ones forward and a
    task is only rewritten when its date actually changes. Mutates the
    in-memory hs_timestamp too, so this run's buckets see the new dates.
    Returns digest lines (one per rationed owner)."""
    if not rcfg.get("enabled"):
        return []
    per_day = max(1, int(rcfg.get("per_day", 15)))
    min_batch = int(rcfg.get("min_batch", 25))
    types = {str(t).upper() for t in (rcfg.get("task_types") or ["CALL"])}
    sources = {str(s).upper() for s in (rcfg.get("sources") or ["AUTOMATION_PLATFORM"])}
    order = [str(s).lower() for s in (rcfg.get("order") or [])]
    groups: dict[str, dict[str, list[dict]]] = {}   # owner → workflow → tasks
    for t in tasks:
        p = t.get("properties") or {}
        key = owners.get(str(p.get("hubspot_owner_id") or ""))
        if not key:
            continue
        if (p.get("hs_task_type") or "").upper() not in types:
            continue
        if (p.get("hs_object_source") or "").upper() not in sources:
            continue
        wf = p.get("hs_object_source_detail_1") or "(unnamed workflow)"
        groups.setdefault(key, {}).setdefault(wf, []).append(t)

    def _rank(wf: str) -> int:
        """Position of the first `order` entry the workflow name contains;
        workflows named nowhere in `order` go last."""
        low = wf.lower()
        for i, needle in enumerate(order):
            if needle in low:
                return i
        return len(order)

    staff = cfg()["staff"]
    start = now.date()
    while not _is_business_day(start):
        start = start + timedelta(days=1)
    lines, updates = [], []
    for key, by_wf in sorted(groups.items()):
        # The ration is per OWNER: four bulk lists at 15/day each is still 60
        # calls a day (the live dry run on 2026-09-10 had exactly that). One
        # queue per person, hot workflows first, then oldest first.
        kept = {wf: ts for wf, ts in by_wf.items() if len(ts) >= min_batch}
        if not kept:
            continue
        queue = [t for wf, ts in kept.items() for t in ts]
        queue.sort(key=lambda t: (_rank((t.get("properties") or {}).get("hs_object_source_detail_1") or ""),
                                  (t.get("properties") or {}).get("hs_createdate") or "",
                                  str(t.get("id"))))
        day, moved = start, 0
        for i, t in enumerate(queue):
            if i and i % per_day == 0:
                day = _next_business_day(day)
            p = t["properties"]
            due = _parse_ts(p.get("hs_timestamp"), now)
            if due and due.date() == day:
                continue
            target = datetime.combine(day, time(RATION_DUE_HOUR), tzinfo=now.tzinfo)
            updates.append((str(t["id"]), int(target.timestamp() * 1000)))
            p["hs_timestamp"] = target.isoformat()
            moved += 1
        name = (staff.get(key) or {}).get("name", key)
        breakdown = ", ".join(f"'{wf}' {len(ts)}"
                              for wf, ts in sorted(kept.items(), key=lambda kv: _rank(kv[0])))
        lines.append(f"🗂 *{name}*: {len(queue)} bulk call tasks rationed to "
                     f"{per_day}/day ({breakdown}) — last batch due "
                     f"{day.strftime('%b %-d')} ({moved} re-dated this run)")
        audit.append({"message_id": f"tasks-rationed:{key}:{now.date().isoformat()}",
                      "source": "task_sweep", "action_taken": "tasks_rationed",
                      "owner": key, "workflows": {wf: len(ts) for wf, ts in kept.items()},
                      "count": len(queue), "moved": moved, "per_day": per_day,
                      "last_due": day.isoformat()})
    if updates:
        try:
            hs.batch_update_task_due(updates)
            print(f"  🗂 re-dated {len(updates)} bulk call task(s)")
        except Exception as e:  # noqa: BLE001 — a failed re-date must not kill the sweep
            print(f"  ⚠️  ration batch update failed: {e}")
            return []
    return lines


def _parse_ts(raw: str | None, now: datetime) -> datetime | None:
    """A HubSpot datetime property as returned by /search — ISO8601 string,
    or epoch ms from older payloads. None when unset/unparseable."""
    if not raw:
        return None
    s = str(raw)
    try:
        if s.isdigit():
            return datetime.fromtimestamp(int(s) / 1000.0, tz=now.tzinfo)
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone(now.tzinfo) if t.tzinfo else t.replace(tzinfo=now.tzinfo)
    except (ValueError, OSError, OverflowError):
        return None


def _monitored_owners() -> dict[str, str]:
    """hubspot_owner_id → staff key for every seat in task_sweep.monitor."""
    c = cfg()
    staff = c.get("staff") or {}
    out = {}
    for key in (c.get("task_sweep") or {}).get("monitor") or []:
        rec = staff.get(key) or {}
        if rec.get("hubspot_owner_id"):
            out[str(rec["hubspot_owner_id"])] = key
    return out


def _bucket_open_tasks(tasks: list[dict], owners: dict[str, str], now: datetime,
                       horizon_days: int) -> dict[str, dict]:
    """staff key → {overdue: [(days_over, subject, tid, due)], due_today: [...],
    stale: int}. Overdue means the due DATE has passed — a task due later today
    is not late at 8am, it is due today. Tasks overdue past horizon_days are
    dead backlog, not live accountability: on the day this shipped the four
    monitored owners held 717 open tasks, almost all months-to-years old, so
    itemizing or DMing them would bury the real signal. They are counted as
    `stale` and surfaced once a week as a single line."""
    today = now.date()
    buckets: dict[str, dict] = {}
    for t in tasks:
        p = t.get("properties") or {}
        key = owners.get(str(p.get("hubspot_owner_id") or ""))
        due = _parse_ts(p.get("hs_timestamp"), now)
        if not key or not due:
            continue
        subject = (p.get("hs_task_subject") or "(no subject)")[:70]
        b = buckets.setdefault(key, {"overdue": [], "due_today": [], "stale": 0})
        days_over = (today - due.date()).days
        if days_over > horizon_days:
            b["stale"] += 1
        elif days_over > 0:
            b["overdue"].append((days_over, subject, t["id"], due))
        elif days_over == 0:
            b["due_today"].append((0, subject, t["id"], due))
    for b in buckets.values():
        b["overdue"].sort(reverse=True)
    return buckets


def _stale_lines(buckets: dict[str, dict]) -> list[str]:
    staff = cfg()["staff"]
    counts = {k: b["stale"] for k, b in buckets.items() if b.get("stale")}
    if not counts:
        return []
    named = ", ".join(f"{(staff.get(k) or {}).get('name', k)} {n}"
                      for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    return ["", f"🧹 *Stale backlog* (overdue past the horizon, not nagged): {named}"]


def _digest_lines(buckets: dict[str, dict], per_person_cap: int) -> list[str]:
    staff = cfg()["staff"]
    lines = []
    for key in sorted(buckets, key=lambda k: -len(buckets[k]["overdue"])):
        b = buckets[key]
        if not b["overdue"] and not b["due_today"]:
            continue
        name = (staff.get(key) or {}).get("name", key)
        parts = []
        if b["overdue"]:
            parts.append(f"{len(b['overdue'])} overdue")
        if b["due_today"]:
            parts.append(f"{len(b['due_today'])} due today")
        lines.append(f"*{name}* — {', '.join(parts)}")
        for days, subject, tid, _due in b["overdue"][:per_person_cap]:
            lines.append(f"  • {days}d overdue: {subject} {hs.task_url(tid)}")
        hidden = len(b["overdue"]) - per_person_cap
        if hidden > 0:
            lines.append(f"  • …and {hidden} more overdue")
    return lines


def _weekly_stats_lines(owners: dict[str, str], now: datetime) -> list[str]:
    """Last-7-days completion scoreboard: done on time vs late per owner."""
    since_ms = int((now - timedelta(days=7)).timestamp() * 1000)
    try:
        done = hs.search_completed_tasks(list(owners), since_ms)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  weekly stats: could not list completed tasks: {e}")
        return []
    staff = cfg()["staff"]
    bulk_closed = audit.bulk_closed_task_ids()
    tally: dict[str, list[int]] = {}  # key → [on_time, late]
    for t in done:
        if str(t.get("id")) in bulk_closed:
            continue  # backlog remediation, not a human finishing a task
        p = t.get("properties") or {}
        key = owners.get(str(p.get("hubspot_owner_id") or ""))
        finished = _parse_ts(p.get("hs_task_completion_date"), now)
        due = _parse_ts(p.get("hs_timestamp"), now)
        if not key or not finished:
            continue
        row = tally.setdefault(key, [0, 0])
        # No due date cannot be "late" — count it as on time.
        row[1 if (due and finished.date() > due.date()) else 0] += 1
    if not tally:
        return []
    lines = ["", "📈 *Completed last 7 days:*"]
    for key, (on_time, late) in sorted(tally.items(), key=lambda kv: -sum(kv[1])):
        name = (staff.get(key) or {}).get("name", key)
        late_note = f", {late} late" if late else ""
        lines.append(f"  • {name}: {on_time + late} done ({on_time} on time{late_note})")
    return lines


def _days_since_iso(iso: str | None, now: datetime) -> float:
    t = _parse_ts(iso, now)
    return (now - t).total_seconds() / 86400.0 if t else 1e9


# The subject reads "Convert PO to TW invoice — Student (School, PO 123, $60)",
# so the real number is always COMMA-terminated. Anchoring on that comma beats
# a digit-leading rule: it excludes the literal "PO to" of the prefix (which
# matched on this test's first run) while still accepting letter-leading PO
# numbers like Blue Ridge's PF593736 and Lake View's 105712-C029-LVC.
_PO_IN_SUBJECT = re.compile(r"\bPO\s+([A-Za-z0-9][A-Za-z0-9-]*),")


def _autoclose_done_tasks(tasks: list[dict], tcfg: dict) -> set[str]:
    """Close invoice-conversion tasks whose deal ALREADY carries an Invoice #.

    The task says "do X"; the deal proves X is done. Kath fills Invoice # (the
    real completion signal) and moves on, leaving the task open forever — ten
    such phantoms on 2026-08-31, all with invoices already created. Returns
    the ids closed so this run's digest/DMs ignore them."""
    if not tcfg.get("autoclose_invoice_tasks", True):
        return set()
    marker = (tcfg.get("invoice_task_marker") or "convert po to tw invoice").lower()
    done: set[str] = set()
    for t in tasks:
        p = t.get("properties") or {}
        subject = (p.get("hs_task_subject") or "")
        if marker not in subject.lower():
            continue
        m = _PO_IN_SUBJECT.search(subject)
        if not m:
            continue
        po_num = m.group(1).strip().rstrip(",")
        try:
            deals = hs.find_deals_by_po_number(po_num)
        except Exception as e:  # noqa: BLE001 — never let a lookup kill the sweep
            print(f"  ⚠️  autoclose lookup failed for PO {po_num}: {e}")
            continue
        if not deals:
            continue
        inv = ((deals[0].get("properties") or {}).get("invoice__") or "").strip()
        if not inv:
            continue
        done.add(str(t["id"]))
        audit.append({"message_id": f"task-autoclosed:{t['id']}", "source": "task_sweep",
                      "action_taken": "task_autoclosed", "task_id": str(t["id"]),
                      "po_number": po_num, "invoice": inv, "subject": subject[:120]})
    if done:
        try:
            hs.batch_complete_tasks(sorted(done))
            print(f"  ✅ auto-closed {len(done)} invoice task(s) already invoiced")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  auto-close batch failed: {e}")
            return set()
    return done


def run() -> None:
    tcfg = cfg().get("task_sweep") or {}
    now = now_la()
    print(f"=== Task sweep ({now.isoformat()}) ===")
    if not tcfg.get("enabled"):
        print("  disabled in config; nothing to do")
        return
    owners = _monitored_owners()
    if not owners:
        print("  ⚠️  task_sweep.monitor resolved to no staff; check config")
        return
    try:
        tasks = hs.search_open_tasks(list(owners))
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  could not list open tasks (missing tasks read scope?): {e}")
        return
    # Close what is provably already done BEFORE bucketing, so nobody is
    # nagged about work whose completion is sitting in the CRM.
    closed = _autoclose_done_tasks(tasks, tcfg)
    if closed:
        tasks = [t for t in tasks if str(t["id"]) not in closed]
    # Spread bulk workflow call lists over business days BEFORE bucketing, so
    # only today's ration counts as due and nothing in the list is "overdue".
    ration_lines = _ration_bulk_tasks(tasks, owners, now, tcfg.get("ration") or {})
    buckets = _bucket_open_tasks(tasks, owners, now,
                                 int(tcfg.get("horizon_days", 30)))

    # ── Channel digest, silent when clean ─────────────────────────
    lines = _digest_lines(buckets, int(tcfg.get("per_person_cap", 8)))
    if now.weekday() == int(tcfg.get("weekly_stats_weekday", 0)):
        lines += _weekly_stats_lines(owners, now)
        lines += _stale_lines(buckets)
    if ration_lines:
        lines += [""] + ration_lines
    if lines:
        header = f"📋 *Task sweep* ({now.strftime('%a %b %-d')})"
        slack_client.post_message(tcfg.get("channel", ""), "\n".join([header] + lines))
        print(f"  digest posted ({sum(len(b['overdue']) for b in buckets.values())} overdue)")
    else:
        print("  clean — no digest")

    # ── DM escalation past dm_after_days, on a cadence ────────────
    # ONE bundled DM per owner per run — never one per task. The first live
    # count was 246 overdue tasks inside the horizon; per-task DMs would have
    # been the reasoner's 102-DM mistake all over again. Every eligible task is
    # audit-stamped (shown or not) so the cadence holds for the whole set; the
    # channel digest carries the full itemized picture.
    dm_after = float(tcfg.get("dm_after_days", 3))
    repeat = float(tcfg.get("dm_repeat_days", 3))
    dm_cap = int(tcfg.get("dm_list_cap", 10))
    staff = cfg()["staff"]
    dmed = 0
    for key, b in buckets.items():
        uid = (staff.get(key) or {}).get("slack_user_id")
        if not uid:
            continue
        eligible = [(days, subject, tid, due) for days, subject, tid, due in b["overdue"]
                    if days >= dm_after
                    and _days_since_iso(audit.last_task_nag(tid), now) >= repeat]
        if not eligible:
            continue
        lines = [f"⏰ You have {len(eligible)} HubSpot task(s) overdue "
                 f"{dm_after:.0f}+ days. Complete them or push the due dates:"]
        for days, subject, tid, due in eligible[:dm_cap]:
            lines.append(f"  • {days}d: {subject} (due {due.strftime('%b %-d')}) {hs.task_url(tid)}")
        if len(eligible) > dm_cap:
            lines.append(f"  • …and {len(eligible) - dm_cap} more (full list in the digest)")
        slack_client.dm(uid, "\n".join(lines))
        for days, _subject, tid, _due in eligible:
            audit.append({"task_id": tid, "owner": key,
                          "action_taken": "task_nag", "days_overdue": days})
        dmed += 1
    print(f"=== DMed {dmed} owner(s) about overdue tasks ===")





def run_with_liveness() -> None:
    """task-sweep entrypoint: the daily sweep, plus the Monday sender-workflow
    liveness digest (see sender_liveness.py — no sender flow dies silently)."""
    run()
    from .business_hours import now_la as _now
    if _now().weekday() == 0:
        try:
            from . import sender_liveness
            sender_liveness.run()
        except Exception as e:  # noqa: BLE001 — the digest must never fail the sweep
            print(f"sender_liveness error (non-fatal): {e}")


if __name__ == "__main__":
    run_with_liveness()
