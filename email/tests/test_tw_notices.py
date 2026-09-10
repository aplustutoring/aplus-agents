"""Teachworks system notices are archived before the classifier (2026-09-10).

The classifier rated "Low Package Balance for ..." mail junk at 0.82, under
the 0.9 archive bar, so router.resolve held it as `unknown` and the Stuck
seat got a "Reply: unknown — notifications" task per notice: 35 in nine days,
none completed. A system notice is decided by sender + subject, not a score.
"""
import pytest

from src import main

TW = "notifications@teachworks.com"
LOW = "Low Package Balance for Elle Labeaune - *2026 - Current - Improvement Package (8)"


def test_low_balance_from_teachworks_is_a_notice():
    assert main.teachworks_notice_kind([TW], LOW) == "low_balance"


def test_same_subject_from_a_person_is_not_a_notice():
    assert main.teachworks_notice_kind(["parent@example.com"], LOW) is None


def test_teachworks_cancellation_mail_still_reaches_the_classifier():
    # rules.md: Teachworks cancellation notifications ARE `cancellation`.
    assert main.teachworks_notice_kind([TW], "Lesson Cancellation - Emma Li") is None


def test_notice_is_archived_without_contact_ticket_or_task(monkeypatch):
    rec = {"archived": [], "audit": []}
    monkeypatch.setattr(main.audit, "already_processed", lambda mid: False)
    monkeypatch.setattr(main.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(main.hs, "sender_email", lambda m: TW)
    monkeypatch.setattr(main.hs, "archive_thread", lambda tid: rec["archived"].append(tid))
    for name in ("find_contact_by_email", "create_contact", "create_ticket", "create_task"):
        monkeypatch.setattr(main.hs, name,
                            lambda *a, _n=name, **k: pytest.fail(f"{_n} must not run"))
    monkeypatch.setattr(main, "classify",
                        lambda *a, **k: pytest.fail("classifier must not run"))
    msg = {"id": "m1", "subject": LOW, "text": "package balance has reached 4 hours",
           "senders": [{"deliveryIdentifier": {"value": TW}}]}
    out = main.process_message("thread-tw", msg)
    assert rec["archived"] == ["thread-tw"]
    assert out["action_taken"] == "tw_notice_archived"
    assert out["notice_kind"] == "low_balance"
    assert rec["audit"] and rec["audit"][0]["category"] == "teachworks_notice"
