"""The one-shot sweep that gives back the notices the pre-deal override took."""
from src.backfill_notice_owners import (TASK_PREFIXES, _misrouted,
                                        _surname_from_subject, _target_owner)


def test_surname_comes_off_the_ticket_subject():
    assert _surname_from_subject("Sterling, Sam — Cancellation") == "Sterling"
    assert _surname_from_subject("Adams, Mia — Reschedule") == "Adams"


def test_subject_without_a_surname_is_refused():
    # the local-part fallback: no comma, so no family name we can trust
    assert _surname_from_subject("notifications — Cancellation") is None
    assert _surname_from_subject("") is None


def test_sterling_goes_to_the_m_z_scheduler():
    key, last, why = _target_owner("Sterling, Sam — Cancellation")
    assert (key, last, why) == ("yolanda", "Sterling", "")


def test_no_surname_leaves_the_ticket_alone():
    key, _, why = _target_owner("notifications — Scheduling")
    assert key is None and why


def test_only_notice_senders_are_swept(monkeypatch):
    # A real pre-deal lead (Deanna Smith) is what the override is FOR — the
    # sweep must walk past it and take only the no-reply notices.
    rows = [
        {"action_taken": "ticket_created", "predeal_intake": True,
         "category": "cancellation", "ticket_id": "1", "contact_id": "notice"},
        {"action_taken": "ticket_created", "predeal_intake": True,
         "category": "scheduling", "ticket_id": "2", "contact_id": "family"},
        {"action_taken": "ticket_created", "category": "cancellation",
         "ticket_id": "3", "contact_id": "notice"},          # never misrouted
        {"action_taken": "ticket_created", "predeal_intake": True,
         "category": "new_po", "ticket_id": "4", "contact_id": "notice"},   # not the split's
    ]
    monkeypatch.setattr("src.backfill_notice_owners.audit._iter_records", lambda: iter(rows))
    got = _misrouted(lambda cid: cid == "notice")
    assert [r["ticket_id"] for r in got] == ["1"]


def test_a_retriaged_thread_counts_once(monkeypatch):
    rows = [
        {"action_taken": "ticket_created", "predeal_intake": True, "category": "cancellation",
         "ticket_id": "7", "contact_id": "notice", "timestamp": "2026-09-01"},
        {"action_taken": "ticket_created", "predeal_intake": True, "category": "cancellation",
         "ticket_id": "7", "contact_id": "notice", "timestamp": "2026-09-20"},
    ]
    monkeypatch.setattr("src.backfill_notice_owners.audit._iter_records", lambda: iter(rows))
    got = _misrouted(lambda cid: True)
    assert len(got) == 1 and got[0]["timestamp"] == "2026-09-20"


def test_task_prefixes_match_what_triage_writes():
    # main.py: f"Reply: {category} — {contact_name}" and f"Re-engage: {label} ({ctype})"
    assert "Reply: cancellation — notifications".startswith(TASK_PREFIXES)
    assert "Re-engage: Sterling (stop)".startswith(TASK_PREFIXES)
    assert not "Reply: new_po — mom".startswith(TASK_PREFIXES)
