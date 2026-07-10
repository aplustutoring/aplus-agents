import datetime as dt

from src import hourly_update as hu
from src.business_hours import LA


def _cfg(until="2026-06-24"):
    return {"hourly_update": {"enabled": True, "recipient": "roman", "until": until,
                              "business_hours_only": True},
            "staff": {"roman": {"slack_user_id": "U1"}}}


def _prep(monkeypatch):
    monkeypatch.setattr(hu, "DRY_RUN", False)
    monkeypatch.delenv("FORCE_RUN", raising=False)


def test_skips_after_until(monkeypatch):
    _prep(monkeypatch)
    sent = []
    monkeypatch.setattr(hu, "cfg", lambda: _cfg("2026-06-09"))   # window ended
    monkeypatch.setattr(hu, "now_la", lambda: dt.datetime(2026, 6, 10, 12, 0, tzinfo=LA))
    monkeypatch.setattr(hu.slack_client, "dm", lambda u, t: sent.append(t))
    hu.run()
    assert sent == []


def test_skips_outside_business_hours(monkeypatch):
    _prep(monkeypatch)
    sent = []
    monkeypatch.setattr(hu, "cfg", lambda: _cfg())
    monkeypatch.setattr(hu, "now_la", lambda: dt.datetime(2026, 6, 10, 7, 0, tzinfo=LA))  # 7am
    monkeypatch.setattr(hu.slack_client, "dm", lambda u, t: sent.append(t))
    hu.run()
    assert sent == []


def test_sends_in_window(monkeypatch):
    _prep(monkeypatch)
    sent = []
    monkeypatch.setattr(hu, "cfg", lambda: _cfg())
    monkeypatch.setattr(hu, "now_la", lambda: dt.datetime(2026, 6, 10, 12, 0, tzinfo=LA))  # Wed noon
    monkeypatch.setattr(hu, "recent_items", lambda h=1: ["scheduling → yolanda"])
    monkeypatch.setattr(hu, "gather_today", lambda: {"total": 3, "junk": 1, "escalations": 0})
    monkeypatch.setattr(hu.slack_client, "dm", lambda u, t: sent.append((u, t)))
    hu.run()
    assert sent and sent[0][0] == "U1" and "scheduling → yolanda" in sent[0][1]
