"""Cancellation re-engagement follow-up: min(+90 days, Sep 1) + sample email."""
import datetime as dt

from src import main


def test_summer_landing_bumps_to_sept1():
    # Apr 1 → +90 = Jun 30 (blackout) → Sep 1
    assert main._followup_due_date(dt.date(2026, 4, 1)) == dt.date(2026, 9, 1)
    # Feb 1 → +90 ≈ May 2 (blackout) → Sep 1
    assert main._followup_due_date(dt.date(2026, 2, 1)) == dt.date(2026, 9, 1)


def test_holiday_landing_bumps_to_jan2():
    # Sep 21 → +90 = Dec 20 (holiday window) → Jan 2
    assert main._followup_due_date(dt.date(2026, 9, 21)) == dt.date(2027, 1, 2)
    # Oct 3 → +90 = Jan 1 (holiday window end) → Jan 2
    assert main._followup_due_date(dt.date(2026, 10, 3)) == dt.date(2027, 1, 2)
    # Oct 1 → +90 = Dec 30 (in window) → Jan 2
    assert main._followup_due_date(dt.date(2026, 10, 1)) == dt.date(2027, 1, 2)


def test_normal_dates_kept():
    # Jun 10 → +90 = Sep 8 (no blackout) → keep
    assert main._followup_due_date(dt.date(2026, 6, 10)) == dt.date(2026, 9, 8)
    # Sep 5 → +90 = Dec 4 (before the Dec 18 holiday window) → keep
    assert main._followup_due_date(dt.date(2026, 9, 5)) == dt.date(2026, 12, 4)


def test_creates_followup_task_with_sample(monkeypatch):
    tasks, enrolled = [], []
    monkeypatch.setattr(main.hs, "create_task", lambda *a, **k: tasks.append(a) or {"id": "T"})
    monkeypatch.setattr(main.hs, "enroll_contact_in_workflow", lambda wf, em: enrolled.append((wf, em)))
    monkeypatch.setattr(main, "now_la", lambda: dt.datetime(2026, 6, 10, 12, 0, tzinfo=main.LA))
    line = main._cancellation_followup("C1", "fam@x.com", "O1", "MEDIUM", "Layla", "Schnider",
                                       {"cancellation_type": "pause", "cancellation_reason": "summer"})
    assert tasks, "a follow-up task was created"
    subject, body, owner, due_ms, prio, cid = tasks[0]
    assert "Re-engage" in subject and "Schnider" in subject
    assert "Layla" in body                 # sample email personalized to the student
    assert owner == "O1" and cid == "C1"
    assert "2026-09-08" in line             # Jun 10 + 90 = Sep 8 (not a blackout month)
    assert enrolled == []                   # no workflow configured → no enrollment


def test_enrolls_when_workflow_configured(monkeypatch):
    enrolled = []
    cfgd = {"cancellation_followup": {"enabled": True, "days": 90, "by_date": "09-01",
                                      "assign_to": "owner", "reengage_workflow_id": "WF1"}, "staff": {}}
    monkeypatch.setattr(main, "cfg", lambda: cfgd)
    monkeypatch.setattr(main, "now_la", lambda: dt.datetime(2026, 6, 10, 12, 0, tzinfo=main.LA))
    monkeypatch.setattr(main.hs, "create_task", lambda *a, **k: {"id": "T"})
    monkeypatch.setattr(main.hs, "enroll_contact_in_workflow", lambda wf, em: enrolled.append((wf, em)))
    line = main._cancellation_followup("C1", "fam@x.com", "O1", "MEDIUM", "Layla", "Schnider",
                                       {"cancellation_type": "stop"})
    assert enrolled == [("WF1", "fam@x.com")]
    assert "Enrolled" in line


def test_enroll_endpoint_url(monkeypatch):
    from src import hubspot_client as hs
    calls = []
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: calls.append((m, p)) or {})
    hs.enroll_contact_in_workflow("123", "a@b.com")
    assert calls == [("POST", "/automation/v2/workflows/123/enrollments/contacts/a@b.com")]
