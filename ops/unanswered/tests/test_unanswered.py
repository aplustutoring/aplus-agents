"""Pure-logic tests — no network, no state writes.

Run: python3 -m pytest ops/unanswered/tests/ -q  (from repo root)

The messages below are verbatim from 2026-09-14 to 09-16. Every one of them
is a case this agent exists because of.
"""
import importlib.util
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("unanswered", HERE / "unanswered.py")
ua = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ua)


@pytest.fixture
def cfg():
    with open(HERE / "config.yml") as f:
        return yaml.safe_load(f)


# ── detection: the four real asks ────────────────────────────────────────────

def test_inna_asking_roman_for_a_call(cfg):
    why = ua.personal_ask(
        "Dear Roman, I hope that you are doing well. Can you give me a call "
        "when you get a chance. Thank you!", cfg)
    assert why


def test_annie_leaving_her_number(cfg):
    assert ua.personal_ask("Please feel free to call me at 661-904-3139.", cfg)


def test_mary_asking_janelle_by_name(cfg):
    assert "Janelle" in ua.personal_ask("Janelle can you please call me", cfg)


def test_psat_parent_opening_with_a_first_name(cfg):
    why = ua.personal_ask(
        "Hey Roman. Michael has the PSAT coming up in about a month. We'd "
        "like to start some prep work with him.", cfg)
    assert "Roman" in why


# ── detection: what must NOT trip it ─────────────────────────────────────────

def test_a_thank_you_naming_the_helper_is_not_an_ask(cfg):
    assert ua.personal_ask("Thank you Paola!", cfg) == ""
    assert ua.personal_ask("Thanks Janelle, that works", cfg) == ""


def test_a_reaction_is_not_an_ask(cfg):
    assert ua.personal_ask('Loved “Hi Roman, all set for Monday”', cfg) == ""


def test_ordinary_scheduling_is_not_an_ask(cfg):
    assert ua.personal_ask("Tuesdays and Thursdays 3pm for both days", cfg) == ""
    assert ua.personal_ask("", cfg) == ""
    assert ua.personal_ask(None, cfg) == ""


def test_staff_names_match_on_a_word_boundary(cfg):
    names = cfg["detect"]["staff_first_names"]
    assert ua.named_staff("this is romantic", names) == ""
    assert ua.named_staff("ask Kathy about it", names) == ""
    assert ua.named_staff("can Roman help", names) == "roman"


# ── the self-healing half ────────────────────────────────────────────────────

def _contact(last_contacted):
    return {"id": "C1", "properties": {"notes_last_contacted": last_contacted}}


def test_answered_when_someone_called_after_the_text(cfg):
    # Mary Gonzalez texted 21:00:48 and Janelle called back 68 seconds later.
    assert ua.answered_since(_contact("2026-09-16T21:01:56Z"),
                             "2026-09-16 21:00:48", cfg)


def test_not_answered_when_the_last_touch_predates_the_text(cfg):
    assert not ua.answered_since(_contact("2026-09-16T18:00:00Z"),
                                 "2026-09-16 21:00:48", cfg)


def test_never_contacted_is_not_answered(cfg):
    assert not ua.answered_since(_contact(""), "2026-09-16 21:00:48", cfg)
    assert not ua.answered_since(None, "2026-09-16 21:00:48", cfg)


def test_open_ask_closes_itself_once_anyone_makes_contact(cfg, monkeypatch):
    """The whole point. Annie Wolfstein was on the phone with Paola at the
    moment the old check called her neglected."""
    state = {"open": {"sms1": {"contact_id": "C1", "task_id": "T9",
                               "at": "2026-09-15 21:47:16", "label": "Annie Wolfstein"}}}
    monkeypatch.setattr(ua, "hs_req",
                        lambda m, p, payload=None, params=None:
                        _contact("2026-09-15T22:32:39Z"))
    completed = []
    monkeypatch.setattr(ua, "complete_task", lambda tid, dry: completed.append(tid))
    closed = ua.resolve_open_asks(cfg, state, dry_run=False)
    assert completed == ["T9"]
    assert state["open"] == {}
    assert closed[0]["who"] == "Annie Wolfstein"


def test_open_ask_stays_open_while_nobody_has_replied(cfg, monkeypatch):
    state = {"open": {"sms1": {"contact_id": "C1", "task_id": "T9",
                               "at": "2026-09-15 21:47:16", "label": "Annie"}}}
    monkeypatch.setattr(ua, "hs_req",
                        lambda m, p, payload=None, params=None:
                        _contact("2026-09-15T10:00:00Z"))
    monkeypatch.setattr(ua, "complete_task",
                        lambda tid, dry: pytest.fail("must not close an open ask"))
    assert ua.resolve_open_asks(cfg, state, dry_run=False) == []
    assert "sms1" in state["open"]


# ── routing and config ───────────────────────────────────────────────────────

def test_a_named_person_gets_the_task(cfg):
    owner_id, key = ua.owner_for(cfg, "janelle")
    assert key == "janelle" and owner_id == 80047202


def test_an_unnamed_ask_goes_to_the_default(cfg):
    owner_id, key = ua.owner_for(cfg, "")
    assert key == cfg["hubspot"]["default_owner"]
    assert owner_id == cfg["hubspot"]["owners"][key]


def test_unknown_numbers_still_alert(cfg):
    # A stranger asking us to call them is more urgent, not less.
    assert cfg["resolve"]["alert_unknown_numbers"] is True


def test_guards_are_present(cfg):
    assert cfg["guards"]["max_alerts_per_run"] >= 1
    assert cfg["guards"]["one_open_ask_per_contact"] is True
    assert cfg["resolve"]["touch_property"] == "notes_last_contacted"


def test_phone_digits_normalises():
    assert ua.phone_digits("+1 (661) 904-3139") == "6619043139"
    assert ua.phone_digits("16619043139") == "6619043139"
    assert ua.phone_digits("12345") == ""


def test_inbound_fetch_starts_at_page_zero(cfg, monkeypatch):
    """JustCall pages from 0; starting at 1 skips the newest 100 texts and a
    short window comes back empty (the 2026-09-12 monitor failure)."""
    seen = []

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"data": []}

    def fake(url, headers=None, timeout=None, params=None):
        seen.append(params.get("page"))
        return R()

    monkeypatch.setattr(ua.requests, "get", fake)
    ua.fetch_inbound_texts(cfg)
    assert seen[0] == 0


def test_cursor_is_built_in_the_account_clock(cfg, monkeypatch):
    """The bug that blinded this agent for a week.

    from_datetime is read in the account clock (PT); the rows come back UTC.
    The workflow set no TZ, so datetime.now() on the runner was UTC and every
    run asked for a window 7 hours in the future. JustCall answered HTTP 200
    with 0 of 0, so 2026-09-17 to 09-23 is a week of green runs, seen.json
    empty, and nobody watching the thing that was meant to be watching.

    Reproduced live 2026-09-23: the same call with a UTC cursor returned 0
    rows, with a PT cursor 66 rows (27 inbound).
    """
    import time as _time
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    # Stand where the runner stands. On a PT laptop the old naive now() would
    # have passed this test while still being broken in production.
    monkeypatch.setenv("TZ", "UTC")
    _time.tzset()

    seen = []

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"data": []}

    def fake(url, headers=None, timeout=None, params=None):
        if "from_datetime" in (params or {}):
            seen.append(params["from_datetime"])
        return R()

    monkeypatch.setattr(ua.requests, "get", fake)
    ua.fetch_inbound_texts(cfg)

    tz = ZoneInfo(cfg["justcall"]["account_timezone"])
    want = (datetime.now(timezone.utc).astimezone(tz)
            - timedelta(minutes=int(cfg["justcall"]["lookback_minutes"])))
    asked = datetime.strptime(seen[0], "%Y-%m-%d %H:%M:%S")
    _time.tzset()   # monkeypatch restores TZ; make the process agree again
    assert abs((asked - want.replace(tzinfo=None)).total_seconds()) < 120, (
        "cursor %s is not on the account clock (expected near %s)" % (asked, want))


def test_empty_window_with_a_fresh_text_in_the_account_goes_red(cfg, monkeypatch):
    """Never report peace on a window you cannot trust.

    The week of silence was survivable only because nothing complained. An
    empty window is believable when the account is quiet too, and a lie when
    the newest text landed after the window opened.
    """
    class R:
        status_code = 200

        def __init__(self, data):
            self._d = data

        def json(self):
            return {"data": self._d}

    fresh = [{"sms_date": "2099-01-01", "sms_time": "12:00:00",
              "direction": "Incoming"}]

    def fake(url, headers=None, timeout=None, params=None):
        # the windowed walk is empty; the unbounded sanity check is not
        return R([] if "from_datetime" in (params or {}) else fresh)

    monkeypatch.setattr(ua.requests, "get", fake)
    with pytest.raises(RuntimeError, match="cursor"):
        ua.fetch_inbound_texts(cfg)


def test_empty_window_is_accepted_when_the_account_is_quiet_too(cfg, monkeypatch):
    class R:
        status_code = 200

        def __init__(self, data):
            self._d = data

        def json(self):
            return {"data": self._d}

    stale = [{"sms_date": "2000-01-01", "sms_time": "12:00:00",
              "direction": "Incoming"}]

    def fake(url, headers=None, timeout=None, params=None):
        return R([] if "from_datetime" in (params or {}) else stale)

    monkeypatch.setattr(ua.requests, "get", fake)
    assert ua.fetch_inbound_texts(cfg) == []
