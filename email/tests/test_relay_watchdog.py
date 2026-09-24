"""Relay watchdog: a cron run that finds an old new deal means the doorbell is dead."""
from datetime import datetime, timedelta, timezone

from src import relay_watchdog as rw

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)
CFG = {"relay_watchdog": {"enabled": True, "max_lag_minutes": 10, "notify": "visionary"}}


def _deal(did, minutes_old, name="Lesly Elenes - Adrian"):
    cd = (NOW - timedelta(minutes=minutes_old)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"id": did, "properties": {"dealname": name, "createdate": cd}}


def _wire(monkeypatch, cfg=None, seen=(), records=()):
    calls = {"dm": [], "audit": []}
    monkeypatch.setattr(rw, "cfg", lambda: cfg or CFG)
    monkeypatch.setattr(rw.audit, "_iter_records", lambda: iter(list(records)))
    monkeypatch.setattr(rw, "staff", lambda k: {"name": "Roman", "slack_user_id": "UROMAN"})
    monkeypatch.setattr(rw.audit, "already_processed", lambda k: k in seen)
    monkeypatch.setattr(rw.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(rw.slack_client, "dm", lambda u, t: calls["dm"].append((u, t)))
    return calls


def test_cron_run_with_stale_deal_dms_once_per_deal(monkeypatch):
    calls = _wire(monkeypatch)
    missed = rw.check([_deal("D1", 17), _deal("D2", 3)], event_name="schedule", now=NOW)
    assert [m["id"] for m in missed] == ["D1"]
    assert len(calls["dm"]) == 1 and calls["dm"][0][0] == "UROMAN"
    assert "17 min ago" in calls["dm"][0][1] and "Lesly Elenes" in calls["dm"][0][1]
    assert calls["audit"][0]["message_id"] == "relay-miss:D1"


def test_dispatch_run_never_fires(monkeypatch):
    calls = _wire(monkeypatch)
    assert rw.check([_deal("D1", 90)], event_name="workflow_dispatch", now=NOW) == []
    assert rw.check([_deal("D1", 90)], event_name="", now=NOW) == []  # local run
    assert calls["dm"] == []


def test_already_flagged_deal_is_quiet(monkeypatch):
    calls = _wire(monkeypatch, seen={"relay-miss:D1"})
    assert rw.check([_deal("D1", 40)], event_name="schedule", now=NOW) == []
    assert calls["dm"] == []


def test_disabled_and_fresh_deals_are_quiet(monkeypatch):
    calls = _wire(monkeypatch, cfg={"relay_watchdog": {"enabled": False}})
    assert rw.check([_deal("D1", 40)], event_name="schedule", now=NOW) == []
    _wire(monkeypatch)
    assert rw.check([_deal("D1", 9)], event_name="schedule", now=NOW) == []
    assert calls["dm"] == []


def test_deal_already_handled_by_deal_sync_is_not_a_relay_miss(monkeypatch):
    """Hazel Barnett, 2026-09-10: a deal re-fetched only because an error holds
    the cursor was flagged as a dead doorbell. Any deal_sync record (synced,
    deferred, errored) means a run handled it."""
    calls = _wire(monkeypatch, records=[
        {"source": "deal_sync", "message_id": "error:deal:D1", "action_taken": "error"},
        {"source": "deal_sync", "message_id": "deferred:deal:D2", "deal_id": "D2",
         "action_taken": "sync_deferred"},
        {"source": "sms", "message_id": "sms-sent:D3", "deal_id": "D3"}])
    missed = rw.check([_deal("D1", 1684), _deal("D2", 90), _deal("D3", 40)],
                      event_name="schedule", now=NOW)
    assert [m["id"] for m in missed] == ["D3"]
    assert len(calls["dm"]) == 1
