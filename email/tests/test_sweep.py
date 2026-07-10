"""reconcile_handled — the agent-side replacement for the Service Hub workflow."""
from src import sla_sweep as sw

STAGES = {"hubspot": {"ticket_stages": {"handled": "H", "closed": "C"}}}


def _setup(monkeypatch, replied: bool):
    flips = []
    monkeypatch.setattr(sw, "cfg", lambda: STAGES)
    monkeypatch.setattr(sw, "_latest_tickets", lambda: {
        "T1": {"thread_id": "th1", "category": "scheduling", "receipt_message_id": None, "sla_due": "x"}
    })
    monkeypatch.setattr(sw, "_is_resolved", lambda tid: False)
    monkeypatch.setattr(sw.hs, "thread_has_outbound_reply", lambda th, ex=None, after_ts=None: replied)
    monkeypatch.setattr(sw.hs, "update_ticket_stage", lambda tid, st: flips.append((tid, st)))
    monkeypatch.setattr(sw.audit, "append", lambda r: None)
    return flips


def test_flips_to_handled_when_human_replied(monkeypatch):
    flips = _setup(monkeypatch, replied=True)
    assert sw.reconcile_handled() == 1
    assert flips == [("T1", "H")]


def test_no_flip_without_reply(monkeypatch):
    flips = _setup(monkeypatch, replied=False)
    assert sw.reconcile_handled() == 0
    assert flips == []


def test_no_flip_when_stage_unconfigured(monkeypatch):
    monkeypatch.setattr(sw, "cfg", lambda: {"hubspot": {"ticket_stages": {"handled": "REPLACE_STAGE_WAITING_ON_CONTACT"}}})
    assert sw.reconcile_handled() == 0


def test_breach_levels_three_tiers():
    import datetime as dt
    from src.business_hours import LA, add_business_hours
    due = dt.datetime(2026, 6, 9, 13, 0, tzinfo=LA)      # Tue 1pm
    rec = {"sla_due": due.isoformat(), "category": "scheduling"}  # 90-min (1.5h) SLA
    second = add_business_hours(due, 1.5)
    third = add_business_hours(second, 1.5)
    assert sw._breach_level(rec, due) == 0
    assert sw._breach_level(rec, add_business_hours(due, 1)) == 1
    assert sw._breach_level(rec, add_business_hours(second, 1)) == 2
    assert sw._breach_level(rec, add_business_hours(third, 1)) == 3


def test_tutor_facing_flips_to_tutor_stage(monkeypatch):
    flips = []
    monkeypatch.setattr(sw, "cfg", lambda: {"hubspot": {
        "ticket_stages": {"handled": "FAMILY"},
        "handled_stage_tutor": "TUTOR",
        "tutor_facing_categories": ["tutor_document", "recruitment"],
    }})
    monkeypatch.setattr(sw, "_latest_tickets", lambda: {
        "T1": {"thread_id": "th1", "category": "tutor_document", "receipt_message_id": "r1"},
        "T2": {"thread_id": "th2", "category": "scheduling", "receipt_message_id": None},
    })
    monkeypatch.setattr(sw, "_is_resolved", lambda tid: False)
    monkeypatch.setattr(sw.hs, "thread_has_outbound_reply", lambda th, ex=None, after_ts=None: True)
    monkeypatch.setattr(sw.hs, "update_ticket_stage", lambda tid, st: flips.append((tid, st)))
    monkeypatch.setattr(sw.audit, "append", lambda r: None)
    assert sw.reconcile_handled() == 2
    assert ("T1", "TUTOR") in flips     # tutor_document → Waiting on Tutor
    assert ("T2", "FAMILY") in flips    # scheduling → Waiting on Family


def test_outbound_reply_only_counts_after_ticket(monkeypatch):
    from src import hubspot_client as hs
    msgs = [{"type": "MESSAGE", "direction": "OUTGOING", "id": "old", "createdAt": "2026-06-10T10:00:00Z"},
            {"type": "MESSAGE", "direction": "OUTGOING", "id": "new", "createdAt": "2026-06-12T10:00:00Z"}]
    monkeypatch.setattr(hs, "get_messages", lambda th: msgs)
    # ticket created 6/11: the 6/10 reply must NOT count; the 6/12 one must.
    assert hs.thread_has_outbound_reply("t", after_ts="2026-06-11T00:00:00Z") is True
    assert hs.thread_has_outbound_reply("t", after_ts="2026-06-12T12:00:00Z") is False
    assert hs.thread_has_outbound_reply("t") is True  # no filter → any reply
