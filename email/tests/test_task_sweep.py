"""task_sweep — reads open HubSpot Tasks for monitored seats, digests overdue
and due-today per owner, DMs only past dm_after_days on a cadence, and posts a
Monday completion scoreboard. Pins the behavior shipped 2026-08-28."""
import datetime as dt

from src import task_sweep as ts
from src.business_hours import LA

# A Thursday, so weekly stats do NOT fire unless a test asks for them.
NOW = dt.datetime(2026, 8, 27, 8, 0, tzinfo=LA)

CFG = {
    "staff": {
        "paola":    {"name": "Paola",    "hubspot_owner_id": "81494333",  "slack_user_id": "UP"},
        "danielle": {"name": "Danielle", "hubspot_owner_id": "227538487", "slack_user_id": "UD"},
    },
    "task_sweep": {"enabled": True, "channel": "CCHAN",
                   "monitor": ["paola", "danielle"],
                   "dm_after_days": 3, "dm_repeat_days": 3, "horizon_days": 30,
                   "per_person_cap": 8, "weekly_stats_weekday": 0},
    "hubspot": {"portal_id": "6312752"},
}


def _iso(days_ago: float) -> str:
    return (NOW - dt.timedelta(days=days_ago)).isoformat()


def _task(tid, owner="81494333", due_days_ago=5.0, subject="Call the family",
          status="NOT_STARTED", completed_days_ago=None):
    p = {"hs_task_subject": subject, "hs_task_status": status,
         "hs_timestamp": _iso(due_days_ago), "hubspot_owner_id": owner}
    if completed_days_ago is not None:
        p["hs_task_completion_date"] = _iso(completed_days_ago)
    return {"id": tid, "properties": p}


def _setup(monkeypatch, tasks, completed=None, last_nag=None, cfg=None, now=NOW):
    dms, posts, records = [], [], []
    monkeypatch.setattr(ts, "cfg", lambda: cfg or CFG)
    monkeypatch.setattr(ts, "now_la", lambda: now)
    monkeypatch.setattr(ts.hs, "cfg", lambda: cfg or CFG)
    monkeypatch.setattr(ts.hs, "search_open_tasks", lambda owners: tasks)
    monkeypatch.setattr(ts.hs, "search_completed_tasks",
                        lambda owners, since: completed or [])
    monkeypatch.setattr(ts.audit, "last_task_nag", lambda tid: last_nag)
    monkeypatch.setattr(ts.audit, "bulk_closed_task_ids", lambda: {"BULK1"})
    monkeypatch.setattr(ts.audit, "append", lambda r: records.append(r))
    monkeypatch.setattr(ts.slack_client, "dm", lambda uid, msg: dms.append((uid, msg)))
    monkeypatch.setattr(ts.slack_client, "post_message",
                        lambda ch, msg: posts.append((ch, msg)))
    return dms, posts, records


def test_overdue_task_lands_in_the_digest(monkeypatch):
    _, posts, _ = _setup(monkeypatch, [_task("T1", due_days_ago=5)])
    ts.run()
    assert len(posts) == 1 and posts[0][0] == "CCHAN"
    assert "Paola" in posts[0][1] and "5d overdue" in posts[0][1]


def test_clean_board_posts_nothing(monkeypatch):
    dms, posts, _ = _setup(monkeypatch, [_task("T1", due_days_ago=-2)])  # due in 2 days
    ts.run()
    assert posts == [] and dms == []


def test_due_later_today_is_not_overdue(monkeypatch):
    # Due at 5pm today, swept at 8am: digest says due today, and no DM.
    due_today = NOW.replace(hour=17)
    task = {"id": "T1", "properties": {
        "hs_task_subject": "Send the quote", "hs_task_status": "NOT_STARTED",
        "hs_timestamp": due_today.isoformat(), "hubspot_owner_id": "81494333"}}
    dms, posts, _ = _setup(monkeypatch, [task])
    ts.run()
    assert "due today" in posts[0][1] and "overdue" not in posts[0][1]
    assert dms == []


def test_dm_waits_for_the_threshold(monkeypatch):
    dms, _, _ = _setup(monkeypatch, [_task("T1", due_days_ago=2)])
    ts.run()
    assert dms == []


def test_dm_fires_past_the_threshold_and_is_audited(monkeypatch):
    dms, _, records = _setup(monkeypatch, [_task("T1", due_days_ago=4)])
    ts.run()
    assert [u for u, _ in dms] == ["UP"]
    assert records[0]["action_taken"] == "task_nag" and records[0]["task_id"] == "T1"


def test_one_bundled_dm_per_owner_never_one_per_task(monkeypatch):
    # 246 overdue on day one — a DM per task is the reasoner's 102-DM mistake.
    tasks = [_task(f"T{i}", due_days_ago=5 + i) for i in range(15)]
    dms, _, records = _setup(monkeypatch, tasks)
    ts.run()
    assert len(dms) == 1
    assert "15 HubSpot task(s)" in dms[0][1]
    assert "and 5 more" in dms[0][1]        # dm_list_cap 10
    assert len(records) == 15               # every eligible task stamped, shown or not


def test_dm_cadence_holds_between_nags(monkeypatch):
    dms, _, _ = _setup(monkeypatch, [_task("T1", due_days_ago=10)], last_nag=_iso(1))
    ts.run()
    assert dms == []


def test_dm_fires_again_once_cadence_elapses(monkeypatch):
    dms, _, _ = _setup(monkeypatch, [_task("T1", due_days_ago=10)], last_nag=_iso(4))
    ts.run()
    assert len(dms) == 1


def test_unmonitored_owner_is_ignored(monkeypatch):
    dms, posts, _ = _setup(monkeypatch, [_task("T1", owner="999999", due_days_ago=30)])
    ts.run()
    assert posts == [] and dms == []


def test_digest_caps_per_person_and_says_so(monkeypatch):
    tasks = [_task(f"T{i}", due_days_ago=5 + i) for i in range(12)]
    _, posts, _ = _setup(monkeypatch, tasks)
    ts.run()
    assert "and 4 more overdue" in posts[0][1]


def test_monday_appends_the_scoreboard(monkeypatch):
    monday = dt.datetime(2026, 8, 24, 8, 0, tzinfo=LA)
    done_on_time = _task("D1", due_days_ago=3, status="COMPLETED", completed_days_ago=4)
    done_late = _task("D2", owner="227538487", due_days_ago=5,
                      status="COMPLETED", completed_days_ago=2)
    _, posts, _ = _setup(monkeypatch, [], completed=[done_on_time, done_late], now=monday)
    ts.run()
    assert len(posts) == 1
    body = posts[0][1]
    assert "Completed last 7 days" in body
    assert "Paola: 1 done (1 on time)" in body
    assert "Danielle: 1 done (0 on time, 1 late)" in body


def test_bulk_closed_tasks_stay_off_the_scoreboard(monkeypatch):
    monday = dt.datetime(2026, 8, 24, 8, 0, tzinfo=LA)
    bulk = _task("BULK1", due_days_ago=200, status="COMPLETED", completed_days_ago=1)
    real = _task("D1", due_days_ago=3, status="COMPLETED", completed_days_ago=4)
    _, posts, _ = _setup(monkeypatch, [], completed=[bulk, real], now=monday)
    ts.run()
    assert "Paola: 1 done" in posts[0][1]  # the remediation closure is not counted


def test_stale_backlog_is_never_itemized_or_dmed(monkeypatch):
    # Years-old open tasks (717 on day one) must not flood the digest or DMs.
    dms, posts, _ = _setup(monkeypatch, [_task("T1", due_days_ago=400)])
    ts.run()
    assert posts == [] and dms == []


def test_monday_counts_the_stale_backlog(monkeypatch):
    monday = dt.datetime(2026, 8, 24, 8, 0, tzinfo=LA)
    tasks = [_task(f"T{i}", due_days_ago=400 + i) for i in range(3)]
    _, posts, _ = _setup(monkeypatch, tasks, now=monday)
    ts.run()
    assert "Stale backlog" in posts[0][1] and "Paola 3" in posts[0][1]


def test_disabled_config_is_a_noop(monkeypatch):
    cfg = {**CFG, "task_sweep": {**CFG["task_sweep"], "enabled": False}}
    dms, posts, _ = _setup(monkeypatch, [_task("T1")], cfg=cfg)
    ts.run()
    assert posts == [] and dms == []
