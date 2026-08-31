"""aging_sweep — nags on EVERY open ticket, not just the ones the agent filed.

The escalation chain in run() walks the audit log, so hand-made CRM tickets and
call-agent tickets were never swept, and it pings each level once and then goes
quiet forever. These tests pin the behavior that replaces that (Roman 2026-08-26).
"""
import datetime as dt

from src import sla_sweep as sw
from src.business_hours import LA

NOW = dt.datetime(2026, 8, 26, 12, 0, tzinfo=LA)

CFG = {
    "staff": {
        "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539", "slack_user_id": "UY"},
        "mandy":   {"name": "Mandy",   "hubspot_owner_id": "80047201", "slack_user_id": "UM"},
        "emily":   {"name": "Emily",   "hubspot_owner_id": "39191217", "slack_user_id": "UE"},
    },
    "escalation": {"level2": "mandy", "level3": "emily"},
    "aging_sweep": {"enabled": True, "nag_after_days": 7, "supervisor_after_days": 14,
                    "last_resort_after_days": 30, "repeat_every_days": 7},
    "hubspot": {"portal_id": "6312752"},
}


def _iso(days_ago: float) -> str:
    return (NOW - dt.timedelta(days=days_ago)).isoformat()


def _ticket(tid, owner="86868539", age=10.0, quiet=10.0, subject="A ticket"):
    return {"id": tid, "properties": {
        "subject": subject, "hubspot_owner_id": owner,
        "createdate": _iso(age), "hs_lastmodifieddate": _iso(quiet)}}


def _setup(monkeypatch, tickets, last_nag=None, cfg=None):
    dms, records = [], []
    monkeypatch.setattr(sw, "cfg", lambda: cfg or CFG)
    monkeypatch.setattr(sw, "now_la", lambda: NOW)
    monkeypatch.setattr(sw.hs, "search_open_tickets", lambda: tickets)
    monkeypatch.setattr(sw.hs, "ticket_url", lambda tid: f"url/{tid}")
    monkeypatch.setattr(sw.audit, "last_aging_nag", lambda tid: last_nag)
    monkeypatch.setattr(sw.audit, "append", lambda r: records.append(r))
    monkeypatch.setattr(sw.slack_client, "dm", lambda uid, msg: dms.append((uid, msg)))
    return dms, records


def test_quiet_ticket_nags_the_owner(monkeypatch):
    dms, records = _setup(monkeypatch, [_ticket("T1", age=10, quiet=10)])
    assert sw.aging_sweep() == 1
    assert [u for u, _ in dms] == ["UY"]
    assert records[0]["action_taken"] == "aging_nag"


def test_recently_touched_ticket_is_left_alone(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=90, quiet=2)])
    assert sw.aging_sweep() == 0
    assert dms == []


def test_supervisor_joins_after_two_weeks(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=20, quiet=20)])
    sw.aging_sweep()
    assert sorted(u for u, _ in dms) == ["UM", "UY"]


def test_last_resort_joins_after_thirty_days(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=135, quiet=49)])
    sw.aging_sweep()
    assert sorted(u for u, _ in dms) == ["UE", "UM", "UY"]


def test_cadence_holds_between_nags(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=40, quiet=40)], last_nag=_iso(3))
    assert sw.aging_sweep() == 0
    assert dms == []


def test_nags_again_once_the_cadence_elapses(monkeypatch):
    """The whole point: an old ticket keeps making noise instead of going silent."""
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=135, quiet=40)], last_nag=_iso(8))
    assert sw.aging_sweep() == 1
    assert dms


def test_unassigned_ticket_still_reaches_the_supervisor(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", owner="", age=20, quiet=20)])
    sw.aging_sweep()
    assert [u for u, _ in dms] == ["UM"]


def test_owner_is_never_double_dmed_when_they_are_also_the_supervisor(monkeypatch):
    dms, _ = _setup(monkeypatch, [_ticket("T1", owner="80047201", age=40, quiet=40)])
    sw.aging_sweep()
    assert sorted(u for u, _ in dms) == ["UE", "UM"]


def test_disabled_by_config(monkeypatch):
    cfg = dict(CFG, aging_sweep={"enabled": False})
    dms, _ = _setup(monkeypatch, [_ticket("T1", age=99, quiet=99)], cfg=cfg)
    assert sw.aging_sweep() == 0
    assert dms == []


def test_hubspot_failure_is_not_fatal(monkeypatch):
    _setup(monkeypatch, [])

    def boom():
        raise RuntimeError("429")

    monkeypatch.setattr(sw.hs, "search_open_tickets", boom)
    assert sw.aging_sweep() == 0


def test_covers_a_ticket_the_agent_never_filed(monkeypatch):
    """Renee Weber: made by hand in the CRM, 135 days old, never once pinged."""
    dms, records = _setup(monkeypatch, [
        _ticket("44377308932", owner="39191217", age=135, quiet=49,
                subject="Renee Weber")])
    assert sw.aging_sweep() == 1
    assert records[0]["age_days"] == 135.0
    assert any("Renee Weber" in m for _, m in dms)
