"""personal_line — tutoring texts on a personal phone, handed to a scheduler.

The agent reads Roman's own mobile, so most of these tests are about what it
must NOT do. Written from the Inna Volodinsky miss of 2026-09-18: told in
writing to use the support line, replied on the personal line anyway, waited
eight and a half hours.
"""
import datetime as dt

import pytest

from src import personal_line as pl

LINE = "+18185736293"
NOW = dt.datetime(2026, 9, 18, 17, 0, tzinfo=dt.timezone.utc)


def _at(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def _t(direction, minutes_ago, text="hello", line=LINE):
    return {"at": _at(minutes_ago), "direction": direction, "line": line, "text": text}


CFG = {
    "personal_line": {"enabled": True, "line": LINE, "lookback_days": 2,
                      "grace_minutes": 20, "min_confidence": 0.7,
                      "max_relays_per_run": 8, "fallback_role": "charter_sales"},
    "scheduler_split": {"a_to_l": "scheduler_a_l", "m_to_z": "scheduler_m_z"},
    "roles": {"scheduler_a_l": "janelle", "scheduler_m_z": "yolanda",
              "charter_sales": "paola"},
    "staff": {"janelle": {"name": "Janelle", "slack_user_id": "UJ"},
              "yolanda": {"name": "Yolanda", "slack_user_id": "UY"},
              "paola": {"name": "Paola", "slack_user_id": "UP"}},
}


# ── the verdict parser refuses to leak on bad output ────────────────────────
def test_malformed_model_output_is_personal():
    for bad in ("", "   ", "I think this is about tutoring", "{not json",
                '{"confidence": 0.9}', "null"):
        v = pl.parse_verdict(bad)
        assert v["tutoring"] is False, bad


def test_a_clean_yes_is_parsed():
    v = pl.parse_verdict('```json\n{"tutoring": true, "confidence": 0.93, '
                         '"student": "Myron", "family_last_name": "Volodinsky", '
                         '"urgency": "today", "reason": "parent about lessons"}\n```')
    assert v["tutoring"] is True and v["confidence"] == 0.93
    assert v["student"] == "Myron"


def test_a_non_numeric_confidence_does_not_crash_and_stays_low():
    v = pl.parse_verdict('{"tutoring": true, "confidence": "very"}')
    assert v["confidence"] == 0.0


def test_a_classifier_exception_answers_personal(monkeypatch):
    monkeypatch.setattr(pl, "cfg", lambda: CFG)

    class Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("API down")
    v = pl.classify("Hi, can we move Myron's lesson?", client=Boom())
    assert v["tutoring"] is False


# ── when it speaks ──────────────────────────────────────────────────────────
def test_a_message_he_already_answered_is_not_surfaced():
    thread = {"texts": [_t("inbound", 120, "can we move Tuesday?"),
                        _t("outgoing", 100, "sure, done")], "calls": []}
    assert pl.unhandled_inbound(thread, LINE, 20, NOW) == []


def test_a_call_back_counts_as_answering_it():
    """He picks up his own phone. A watcher reading only texts called three
    phoned-back families neglected on 2026-09-15."""
    thread = {"texts": [_t("inbound", 120, "call me about Myron")],
              "calls": [{"at": _at(100), "direction": "outgoing"}]}
    assert pl.unhandled_inbound(thread, LINE, 20, NOW) == []


def test_a_fresh_message_waits_out_the_grace_period():
    """Do not DM a scheduler over his shoulder while he is typing."""
    thread = {"texts": [_t("inbound", 5, "quick question about Myron")], "calls": []}
    assert pl.unhandled_inbound(thread, LINE, 20, NOW) == []


def test_a_message_past_grace_with_no_reply_is_surfaced():
    thread = {"texts": [_t("inbound", 45, "quick question about Myron")], "calls": []}
    got = pl.unhandled_inbound(thread, LINE, 20, NOW)
    assert len(got) == 1 and got[0]["text"] == "quick question about Myron"


def test_traffic_on_another_line_is_not_this_agent_s_business():
    """The support line has a team. This agent watches one number."""
    thread = {"texts": [_t("inbound", 45, "hello", line="+18188691627")], "calls": []}
    assert pl.unhandled_inbound(thread, LINE, 20, NOW) == []


def test_a_reply_on_a_different_line_does_not_count_as_answering_this_one():
    thread = {"texts": [_t("inbound", 45, "about Myron"),
                        _t("outgoing", 30, "hi", line="+18188691627")], "calls": []}
    assert len(pl.unhandled_inbound(thread, LINE, 20, NOW)) == 1


# ── routing ─────────────────────────────────────────────────────────────────
def test_the_student_surname_picks_the_scheduler(monkeypatch):
    monkeypatch.setattr(pl, "cfg", lambda: CFG)
    monkeypatch.setattr(pl, "scheduler_for_last_name",
                        lambda last: (("scheduler_m_z", []) if last[0].upper() >= "M"
                                      else ("scheduler_a_l", [])))
    role, _why = pl.target_scheduler({"family_last_name": "Volodinsky"}, {})
    assert role == "scheduler_m_z"
    role, _why = pl.target_scheduler({"family_last_name": "Aase"}, {})
    assert role == "scheduler_a_l"


def test_no_surname_falls_back_and_says_so(monkeypatch):
    monkeypatch.setattr(pl, "cfg", lambda: CFG)
    role, why = pl.target_scheduler({}, {})
    assert role == "charter_sales" and "no surname" in why


# ── the privacy contract ────────────────────────────────────────────────────
@pytest.fixture
def wired(monkeypatch):
    state = {"dms": [], "audit": [], "index": {}, "verdicts": {}}
    monkeypatch.setattr(pl, "cfg", lambda: CFG)
    monkeypatch.setattr(pl, "DRY_RUN", False)
    monkeypatch.setattr(pl, "staff", lambda k: CFG["staff"].get(CFG["roles"].get(k, k), {}))
    monkeypatch.setattr(pl.jc, "index_by_number", lambda days: state["index"])
    monkeypatch.setattr(pl, "classify",
                        lambda body, client=None: state["verdicts"].get(body,
                                                                        {"tutoring": False,
                                                                         "confidence": 0.0}))
    monkeypatch.setattr(pl, "_contact_for", lambda n: {"properties": {
        "firstname": "Inna", "lastname": "Volodinsky"}})
    monkeypatch.setattr(pl, "scheduler_for_last_name", lambda last: ("scheduler_m_z", []))
    monkeypatch.setattr(pl.slack_client, "dm",
                        lambda uid, text: state["dms"].append((uid, text)))
    monkeypatch.setattr(pl.audit, "append", lambda r: state["audit"].append(r))
    monkeypatch.setattr(pl.audit, "personal_line_seen", lambda: set())
    return state


PRIVATE = "Dinner at 7? Mum says hi and the tickets are booked."
TUTORING = ("I am just afraid he will be overwhelmed and crack. "
            "Let Calvin decide how shall we approach the passing.")


def test_a_personal_message_leaves_no_trace_anywhere(wired):
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 45, PRIVATE)], "calls": []}}
    pl.run()
    assert wired["dms"] == []
    assert len(wired["audit"]) == 1
    rec = wired["audit"][0]
    assert rec["action_taken"] == "personal_line_ignored"
    # the whole row, serialised, must not contain the message
    blob = str(rec)
    for word in ("Dinner", "Mum", "tickets"):
        assert word not in blob


def test_an_unsure_classifier_is_treated_as_personal(wired):
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 45, TUTORING)], "calls": []}}
    wired["verdicts"] = {TUTORING: {"tutoring": True, "confidence": 0.55}}
    pl.run()
    assert wired["dms"] == []
    assert wired["audit"][0]["action_taken"] == "personal_line_ignored"


def test_the_inna_message_reaches_the_right_scheduler(wired):
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 510, TUTORING)], "calls": []}}
    wired["verdicts"] = {TUTORING: {"tutoring": True, "confidence": 0.92,
                                    "student": "Myron", "family_last_name": "Volodinsky",
                                    "urgency": "today"}}
    pl.run(now=NOW)
    assert len(wired["dms"]) == 1
    uid, text = wired["dms"][0]
    assert uid == "UY"                       # M-Z scheduler
    assert "Inna Volodinsky" in text
    assert "overwhelmed and crack" in text   # her own words, not a summary
    assert "8.5h ago" in text
    assert "support line" in text            # tells them where to answer from
    assert wired["audit"][0]["action_taken"] == "personal_line_relayed"


def test_it_never_replies_to_the_family(wired, monkeypatch):
    sends = []
    monkeypatch.setattr(pl.jc, "index_by_number", lambda days: wired["index"])
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 45, TUTORING)], "calls": []}}
    wired["verdicts"] = {TUTORING: {"tutoring": True, "confidence": 0.95,
                                    "family_last_name": "Volodinsky"}}
    pl.run()
    assert sends == []                       # nothing in this module can send an SMS
    assert not hasattr(pl, "_jc_send")


# ── guards ──────────────────────────────────────────────────────────────────
def test_disabled_reads_nothing(monkeypatch, wired):
    monkeypatch.setattr(pl, "cfg", lambda: {**CFG, "personal_line": {"enabled": False}})
    monkeypatch.setattr(pl.jc, "index_by_number",
                        lambda d: pytest.fail("must not read the phone while disabled"))
    pl.run()


def test_no_line_configured_refuses_to_run(monkeypatch, wired):
    monkeypatch.setattr(pl, "cfg", lambda: {**CFG, "personal_line": {"enabled": True}})
    monkeypatch.setattr(pl.jc, "index_by_number",
                        lambda d: pytest.fail("must not read without a line"))
    pl.run()


def test_justcall_failure_refuses_to_run(monkeypatch, wired):
    def boom(days):
        raise pl.jc.JustCallUnavailable("HTTP 500")
    monkeypatch.setattr(pl.jc, "index_by_number", boom)
    pl.run()
    assert wired["dms"] == []


def test_dry_run_tells_nobody(monkeypatch, wired):
    monkeypatch.setattr(pl, "DRY_RUN", True)
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 45, TUTORING)], "calls": []}}
    wired["verdicts"] = {TUTORING: {"tutoring": True, "confidence": 0.95,
                                    "family_last_name": "Volodinsky"}}
    pl.run()
    assert wired["dms"] == [] and wired["audit"] == []


def test_a_message_already_judged_is_not_judged_again(monkeypatch, wired):
    monkeypatch.setattr(pl.audit, "personal_line_seen",
                        lambda: {f"8184623808:{_at(510)}"})
    wired["index"] = {"8184623808": {"texts": [_t("inbound", 510, TUTORING)], "calls": []}}
    wired["verdicts"] = {TUTORING: {"tutoring": True, "confidence": 0.95}}
    pl.run()
    assert wired["dms"] == [] and wired["audit"] == []
