"""Bulk workflow call lists → daily ration (task_sweep, 2026-09-10).

A HubSpot workflow enrolling a list drops one CALL task per contact, all due
the day they land: charter_sales got 98 on 2026-09-01 and 189 on 2026-09-04
and had 426 overdue tasks nine days later. The sweep now spreads any
(owner, workflow) group of >= min_batch open tasks over business days in
creation order, per_day per day, and recomputes every run.
"""
import datetime as dt

from src import task_sweep as ts
from src.business_hours import LA

# A Thursday, so the weekend skip is exercised and weekly stats stay off.
NOW = dt.datetime(2026, 8, 27, 8, 0, tzinfo=LA)

CFG = {
    "staff": {
        "paola": {"name": "Paola", "hubspot_owner_id": "81494333", "slack_user_id": "UP"},
    },
    "task_sweep": {"enabled": True, "channel": "CCHAN", "monitor": ["paola"],
                   "dm_after_days": 3, "dm_repeat_days": 3, "horizon_days": 30,
                   "per_person_cap": 8, "weekly_stats_weekday": 0,
                   "autoclose_invoice_tasks": False},
    "hubspot": {"portal_id": "6312752"},
}
RATION_CFG = {**CFG, "task_sweep": {**CFG["task_sweep"],
                                    "ration": {"enabled": True, "per_day": 15,
                                               "min_batch": 25}}}


def _iso(days_ago: float) -> str:
    return (NOW - dt.timedelta(days=days_ago)).isoformat()


def _wf_call(tid, n, wf="Charter Prospects - Cold Revival", due_days_ago=5.0,
             ttype="CALL", source="AUTOMATION_PLATFORM"):
    return {"id": tid, "properties": {
        "hs_task_subject": f"Charter prospect call: Family {n}",
        "hs_task_status": "NOT_STARTED", "hubspot_owner_id": "81494333",
        "hs_timestamp": _iso(due_days_ago), "hs_task_type": ttype,
        "hs_object_source": source, "hs_object_source_detail_1": wf,
        # creation order = n; a tiny offset keeps the sort stable and explicit
        "hs_createdate": _iso(6.0 - n / 1000.0)}}


def _setup(monkeypatch, tasks, cfg=None):
    dms, posts, records, updates = [], [], [], []
    monkeypatch.setattr(ts, "cfg", lambda: cfg or RATION_CFG)
    monkeypatch.setattr(ts, "now_la", lambda: NOW)
    monkeypatch.setattr(ts.hs, "cfg", lambda: cfg or RATION_CFG)
    monkeypatch.setattr(ts.hs, "search_open_tasks", lambda owners: tasks)
    monkeypatch.setattr(ts.hs, "search_completed_tasks", lambda owners, since: [])
    monkeypatch.setattr(ts.hs, "batch_update_task_due", lambda ups: updates.extend(ups))
    monkeypatch.setattr(ts.audit, "last_task_nag", lambda tid: None)
    monkeypatch.setattr(ts.audit, "bulk_closed_task_ids", lambda: set())
    monkeypatch.setattr(ts.audit, "append", lambda r: records.append(r))
    monkeypatch.setattr(ts.slack_client, "dm", lambda uid, msg: dms.append((uid, msg)))
    monkeypatch.setattr(ts.slack_client, "post_message",
                        lambda ch, msg: posts.append((ch, msg)))
    return dms, posts, records, updates


def _due_dates(updates):
    return [dt.datetime.fromtimestamp(ms / 1000, tz=LA).date() for _tid, ms in updates]


def test_bulk_list_is_spread_over_business_days(monkeypatch):
    tasks = [_wf_call(f"C{n}", n) for n in range(40)]
    dms, posts, records, updates = _setup(monkeypatch, tasks)
    ts.run()
    days = _due_dates(updates)
    assert len(updates) == 40
    # NOW is Thu 8/27: 15 today, 15 Fri 8/28, 10 Mon 8/31 — the weekend is skipped.
    assert days.count(dt.date(2026, 8, 27)) == 15
    assert days.count(dt.date(2026, 8, 28)) == 15
    assert days.count(dt.date(2026, 8, 31)) == 10
    assert updates[0][0] == "C0"                       # creation order preserved
    assert dms == []                                   # nothing is overdue any more
    assert posts and "40 bulk call tasks rationed to 15/day" in posts[0][1]
    assert "'Charter Prospects - Cold Revival' 40" in posts[0][1]
    assert "last batch due Aug 31" in posts[0][1]
    assert "15 due today" in posts[0][1]
    assert any(r.get("action_taken") == "tasks_rationed" and r.get("count") == 40
               for r in records)


def test_ration_is_per_owner_with_hot_workflows_first(monkeypatch):
    # Two bulk lists on one owner share ONE daily ration — 15/day total, not
    # 15 per workflow — and the workflow named first in `order` drains first
    # even though its tasks were created later.
    cold = [_wf_call(f"C{n}", n) for n in range(30)]                  # older
    qtl = [_wf_call(f"Q{n}", n + 100, wf="QTL New Customer v2") for n in range(30)]
    cfg = {**RATION_CFG, "task_sweep": {**RATION_CFG["task_sweep"],
                                        "ration": {"enabled": True, "per_day": 15,
                                                   "min_batch": 25,
                                                   "order": ["QTL", "Cold Revival"]}}}
    _, posts, _, updates = _setup(monkeypatch, cold + qtl, cfg=cfg)
    ts.run()
    days = _due_dates(updates)
    assert days.count(dt.date(2026, 8, 27)) == 15                     # one owner, one ration
    assert days.count(dt.date(2026, 8, 28)) == 15
    assert days.count(dt.date(2026, 8, 31)) == 15
    assert days.count(dt.date(2026, 9, 1)) == 15
    first_30 = [tid for tid, _ in updates[:30]]
    assert all(tid.startswith("Q") for tid in first_30)
    assert "60 bulk call tasks rationed to 15/day" in posts[0][1]
    assert "last batch due Sep 1" in posts[0][1]


def test_small_workflow_groups_are_left_alone(monkeypatch):
    tasks = [_wf_call(f"Q{n}", n, wf="QTL New Customer v2") for n in range(10)]
    dms, posts, _, updates = _setup(monkeypatch, tasks)
    ts.run()
    assert updates == []
    assert "10 overdue" in posts[0][1]                 # still reported as overdue
    assert len(dms) == 1                               # and still nagged


def test_manual_and_agent_tasks_are_never_rationed(monkeypatch):
    tasks = ([_wf_call(f"M{n}", n, source="CRM_UI") for n in range(30)]
             + [_wf_call(f"T{n}", n + 100, ttype="TODO") for n in range(30)])
    _, _, _, updates = _setup(monkeypatch, tasks)
    ts.run()
    assert updates == []


def test_rerun_only_rewrites_tasks_whose_day_changed(monkeypatch):
    tasks = [_wf_call(f"C{n}", n) for n in range(30)]
    for n in range(15):                                # first batch already dated today
        tasks[n]["properties"]["hs_timestamp"] = NOW.replace(hour=9).isoformat()
    _, _, _, updates = _setup(monkeypatch, tasks)
    ts.run()
    assert sorted(tid for tid, _ in updates) == sorted(f"C{n}" for n in range(15, 30))


def test_ration_is_off_without_config(monkeypatch):
    tasks = [_wf_call(f"C{n}", n) for n in range(40)]
    _, posts, _, updates = _setup(monkeypatch, tasks, cfg=CFG)
    ts.run()
    assert updates == []
    assert "40 overdue" in posts[0][1]


def test_a_failed_redate_keeps_the_sweep_alive(monkeypatch):
    tasks = [_wf_call(f"C{n}", n) for n in range(30)]
    _, posts, _, _ = _setup(monkeypatch, tasks)

    def boom(ups):
        raise RuntimeError("hubspot down")

    monkeypatch.setattr(ts.hs, "batch_update_task_due", boom)
    ts.run()                                           # must not raise
    assert posts and "rationed" not in posts[0][1]     # no false "done" claim
