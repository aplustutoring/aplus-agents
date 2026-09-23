"""
Ticket pesters read as a DM from Roman (2026-09-18), and never go silent
because a secret is missing: no user token means a bot DM, never nothing.
"""

from src import slack_client as sc
from src import ticket_reasoner as tr


def _capture(monkeypatch):
    calls = []

    def fake_call(endpoint, payload, token=None):
        calls.append({"endpoint": endpoint, "payload": payload, "token": token})
        return {"ok": True}

    monkeypatch.setattr(sc, "_call", fake_call)
    monkeypatch.setattr(sc, "DRY_RUN", False)
    monkeypatch.setattr(sc, "SLACK_BOT_TOKEN", "xoxb-bot")
    return calls


def test_dm_as_visionary_uses_the_user_token(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setattr(sc, "SLACK_USER_TOKEN_VISIONARY", "xoxp-roman")
    sc.dm("U_KATH", "hello", as_role="visionary")
    assert calls[0]["token"] == "xoxp-roman"
    assert calls[0]["payload"]["channel"] == "U_KATH"


def test_dm_falls_back_to_the_bot_without_a_user_token(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setattr(sc, "SLACK_USER_TOKEN_VISIONARY", "")
    sc.dm("U_KATH", "hello", as_role="visionary")
    assert calls and calls[0]["token"] is None, "bot token path, not silence"


def test_dm_without_as_role_is_unchanged(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setattr(sc, "SLACK_USER_TOKEN_VISIONARY", "xoxp-roman")
    sc.dm("U_KATH", "hello")
    assert calls[0]["token"] is None


def test_unknown_seat_falls_back_to_the_bot(monkeypatch):
    calls = _capture(monkeypatch)
    sc.dm("U_KATH", "hello", as_role="charter_admin")
    assert calls[0]["token"] is None


EV = {"ticket_id": "48451800625", "age_hours": 70,
      "subject": "new_po — Heartland Charter School (PO PF252648)"}
V = {"verdict": "BALL_IN_COURT", "reason": "the school is waiting on our invoice"}
URL = "https://app.hubspot.com/contacts/6312752/record/0-5/48451800625"


def test_pester_text_is_first_person_and_plain():
    text = tr.pester_text("Kath", EV, V, URL)
    assert text.startswith("Kath, this ticket has been open 3 days")
    assert "the school is waiting on our invoice." in text
    assert "Where are we on it?" in text and URL in text
    assert "BALL_IN_COURT" not in text and "⏰" not in text
    assert "—" not in text and "--" not in text


def test_pester_text_handles_one_day_and_no_reason():
    text = tr.pester_text("Emily", {"ticket_id": "1", "age_hours": 25, "subject": "x"},
                          {"verdict": "WAITING", "reason": ""}, URL)
    assert "open 1 day and" in text
    assert "x. Where are we on it?" in text


def test_pester_sends_as_the_configured_seat(monkeypatch):
    sent = []
    monkeypatch.setattr(tr.slack_client, "dm",
                        lambda uid, text, as_role=None: sent.append((uid, text, as_role)))
    monkeypatch.setattr(tr.hs, "ticket_url", lambda tid: URL)
    monkeypatch.setattr(tr.audit, "append", lambda rec: None)
    monkeypatch.setattr(tr, "cfg", lambda: {"reasoner": {"pester_as": "visionary"}})
    monkeypatch.setattr(tr, "staff", lambda key: {
        "charter_admin": {"name": "Kath", "slack_user_id": "U_KATH"},
        "operations": {"name": "Emily", "slack_user_id": "U_EMILY"},
    }[key])
    tr._pester(EV, V, ["charter_admin", "operations"])
    assert [s[0] for s in sent] == ["U_KATH", "U_EMILY"]
    assert all(s[2] == "visionary" for s in sent)
    assert sent[0][1].startswith("Kath,") and sent[1][1].startswith("Emily,")


def test_ladder_skips_the_deleted_level2(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: {
        "reasoner": {"owner_after_hours": 24, "supervisor_after_hours": 48,
                     "last_resort_after_hours": 96},
        "escalation": {"level2": None, "level3": "operations"}})
    assert tr.pester_targets(50, "charter_admin") == ["charter_admin"]
    assert tr.pester_targets(100, "charter_admin") == ["charter_admin", "operations"]
