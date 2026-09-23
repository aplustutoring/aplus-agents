"""inbound_watch — messages that bear on work already open.

Pinned from two failures on 2026-09-18:
  Ashley Clay texted the answer to the question her open PO task was waiting on.
  Jeff Werner chased twice over five days and nothing re-armed.
"""
import datetime as dt

import pytest

from src import inbound_watch as iw

NOW = dt.datetime(2026, 9, 18, 18, 0, tzinfo=dt.timezone.utc)


def _dt(days=0, hours=0):
    return NOW - dt.timedelta(days=days, hours=hours)


def _iso(days=0, hours=0):
    return _dt(days, hours).isoformat()


CFG = {
    "staff": {
        "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539", "slack_user_id": "UY"},
        "emily":   {"name": "Emily",   "hubspot_owner_id": "39191217", "slack_user_id": "UE"},
    },
    "escalation": {"level2": None, "level3": "emily"},
    "inbound_watch": {
        "enabled": True, "sms_lookback_days": 30, "digest_channel": "C_D",
        "chase": {"enabled": True, "min_messages": 2, "after_hours": 4,
                  "repeat_every_hours": 24, "max_per_run": 10},
        "answers": {"enabled": False},
    },
}


# ── what counts as a chase ──────────────────────────────────────────────────
def test_last_outbound_reads_every_channel():
    ev = {"emails": [{"at": _iso(days=5), "direction": "outbound"}],
          "sms": [{"at": _iso(days=2), "direction": "outgoing"}],
          "calls": [{"at": _iso(days=1), "direction": "outgoing"}]}
    assert iw.last_outbound_at(ev) == _dt(days=1)


def test_a_call_back_counts_as_an_answer():
    """Version 1 of the waiting checker read only texts and called three families
    neglected while Paola was on the phone with them."""
    ev = {"emails": [], "calls": [{"at": _iso(hours=1), "direction": "outgoing"}],
          "sms": [{"at": _iso(hours=3), "direction": "inbound"},
                  {"at": _iso(hours=2), "direction": "inbound"}]}
    assert iw.unanswered_inbound(ev) == []


def test_unanswered_inbound_is_only_what_came_after_our_last_word():
    ev = {"emails": [{"at": _iso(days=6), "direction": "inbound", "text": "old, answered"},
                     {"at": _iso(days=5), "direction": "outbound", "text": "our reply"},
                     {"at": _iso(days=4), "direction": "inbound", "text": "the attachments"},
                     {"at": _iso(days=2), "direction": "inbound", "text": "just following up"}],
          "sms": [], "calls": []}
    msgs = iw.unanswered_inbound(ev)
    assert [m["text"] for m in msgs] == ["the attachments", "just following up"]


def test_one_unanswered_message_is_not_a_chase():
    """A single message is a normal queue and the SLA ladder owns it."""
    msgs = [{"at": _dt(days=3), "text": "hi", "channel": "email"}]
    assert iw.is_chase(msgs, 2, 4, NOW) is False


def test_two_unanswered_messages_past_the_bar_is_a_chase():
    msgs = [{"at": _dt(days=3), "text": "the attachments", "channel": "email"},
            {"at": _dt(days=1), "text": "just following up", "channel": "email"}]
    assert iw.is_chase(msgs, 2, 4, NOW) is True


def test_two_messages_minutes_apart_is_not_yet_a_chase():
    """Someone sending a second thought straight after the first is not late."""
    msgs = [{"at": _dt(hours=1), "text": "one", "channel": "text"},
            {"at": _dt(hours=0), "text": "and also", "channel": "text"}]
    assert iw.is_chase(msgs, 2, 4, NOW) is False


# ── the Werner case ─────────────────────────────────────────────────────────
@pytest.fixture
def wired(monkeypatch):
    state = {"dms": [], "posts": [], "notes": [], "audit": [], "patched": [],
             "tickets": [], "ev": {}, "tasks": [], "contacts": [{"id": "1436401"}]}
    monkeypatch.setattr(iw, "cfg", lambda: CFG)
    monkeypatch.setattr(iw, "DRY_RUN", False)
    monkeypatch.setattr(iw, "staff", lambda k: CFG["staff"].get(k, {}))
    monkeypatch.setattr(iw.jc, "index_by_number", lambda days: {})
    monkeypatch.setattr(iw.hs, "search_open_tickets", lambda: state["tickets"])
    monkeypatch.setattr(iw.tr, "gather", lambda t, idx: state["ev"])
    monkeypatch.setattr(iw.hs, "get_ticket_contacts", lambda tid: state["contacts"])
    monkeypatch.setattr(iw.hs, "add_ticket_note",
                        lambda tid, body: state["notes"].append((tid, body)))
    monkeypatch.setattr(iw.hs, "ticket_url", lambda tid: f"url/{tid}")
    monkeypatch.setattr(iw.hs, "_now_ms", lambda: "1789750000000")
    monkeypatch.setattr(iw.slack_client, "dm",
                        lambda uid, text: state["dms"].append((uid, text)))
    monkeypatch.setattr(iw.slack_client, "post_message",
                        lambda ch, text: state["posts"].append((ch, text)))
    monkeypatch.setattr(iw.audit, "append", lambda r: state["audit"].append(r))
    monkeypatch.setattr(iw.audit, "last_inbound_chase", lambda tid: None)
    monkeypatch.setattr(iw.audit, "inbound_answers_stamped", lambda: set())
    monkeypatch.setattr(iw, "_contact_tasks", lambda cid: state["tasks"])

    def _write(method, path, payload=None):
        state["patched"].append((method, path, payload))
        return {}
    monkeypatch.setattr(iw.hs, "_write", _write)
    return state


def _werner_ev():
    return {
        "ticket_id": "48570169480", "subject": "Werner, Iris — Study Plan",
        "contact": "Jeff Werner", "owner_id": "86868539",
        "emails": [
            {"at": _iso(days=6), "direction": "inbound", "text": "ISEE prep test"},
            {"at": _iso(days=5, hours=22), "direction": "outbound", "text": "do you have results"},
            {"at": _iso(days=5), "direction": "inbound", "text": "see attached"},
            {"at": _iso(days=3), "direction": "inbound", "text": "Just following up - thank you!"},
            {"at": _iso(hours=12), "direction": "inbound",
             "text": "Just want to make sure you guys are still interested?"},
        ],
        "sms": [], "calls": []}


def test_werner_chase_is_detected_and_both_seats_told(wired):
    wired["tickets"] = [{"id": "48570169480", "properties": {}}]
    wired["ev"] = _werner_ev()
    iw.run(now=NOW)
    assert len(wired["dms"]) == 2                      # owner and the last-resort seat
    assert {d[0] for d in wired["dms"]} == {"UY", "UE"}
    assert "3 times" in wired["dms"][0][1]
    assert "still interested" in wired["dms"][0][1]    # their own words, not a summary
    rec = wired["audit"][0]
    assert rec["action_taken"] == "inbound_chase" and rec["messages"] == 3


def test_a_reply_task_closed_while_they_waited_is_reopened(wired):
    """The Werner task was marked COMPLETED on 9/15 with no reply ever sent."""
    wired["tickets"] = [{"id": "48570169480", "properties": {}}]
    wired["ev"] = _werner_ev()
    wired["tasks"] = [{"id": "116840226975", "properties": {
        "hs_task_subject": "Reply: scheduling — jeffwerner1",
        "hs_task_status": "COMPLETED",
        "hs_task_completion_date": _iso(days=3, hours=2),
        "hs_task_body": "Parent Jeff Werner is inquiring about test prep"}}]
    iw.run(now=NOW)
    patches = [p for p in wired["patched"] if p[0] == "PATCH"]
    assert len(patches) == 1
    props = patches[0][2]["properties"]
    assert props["hs_task_status"] == "NOT_STARTED"
    assert "still waiting" in props["hs_task_body"]
    assert "Parent Jeff Werner is inquiring" in props["hs_task_body"]   # original kept


def test_a_task_completed_before_they_started_waiting_is_left_alone(wired):
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    wired["tasks"] = [{"id": "old", "properties": {
        "hs_task_subject": "Reply: scheduling", "hs_task_status": "COMPLETED",
        "hs_task_completion_date": _iso(days=30), "hs_task_body": ""}}]
    iw.run(now=NOW)
    assert [p for p in wired["patched"] if p[0] == "PATCH"] == []


def test_non_reply_tasks_are_never_reopened(wired):
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    wired["tasks"] = [{"id": "x", "properties": {
        "hs_task_subject": "QTL Charter Call 1: Ashley Clay", "hs_task_status": "COMPLETED",
        "hs_task_completion_date": _iso(days=1), "hs_task_body": ""}}]
    iw.run(now=NOW)
    assert [p for p in wired["patched"] if p[0] == "PATCH"] == []


def test_answered_thread_says_nothing(wired):
    ev = _werner_ev()
    ev["emails"].append({"at": _iso(hours=1), "direction": "outbound", "text": "sorry, here we go"})
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = ev
    iw.run(now=NOW)
    assert wired["dms"] == [] and wired["audit"] == []


# ── guards ──────────────────────────────────────────────────────────────────
def test_justcall_failure_refuses_to_run(monkeypatch, wired):
    """An empty index makes every phone look silent, and silence is what this
    sweep acts on."""
    def boom(days):
        raise iw.jc.JustCallUnavailable("HTTP 500")
    monkeypatch.setattr(iw.jc, "index_by_number", boom)
    monkeypatch.setattr(iw.hs, "search_open_tickets",
                        lambda: pytest.fail("must not sweep on a blind index"))
    iw.run(now=NOW)


def test_disabled_does_nothing(monkeypatch, wired):
    monkeypatch.setattr(iw, "cfg", lambda: {**CFG, "inbound_watch": {"enabled": False}})
    monkeypatch.setattr(iw.jc, "index_by_number",
                        lambda d: pytest.fail("must not read while disabled"))
    iw.run(now=NOW)


def test_dry_run_writes_nothing(monkeypatch, wired):
    monkeypatch.setattr(iw, "DRY_RUN", True)
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    iw.run(now=NOW)
    assert wired["dms"] == [] and wired["notes"] == [] and wired["audit"] == []
    assert wired["posts"] == []


def test_recent_chase_is_not_repeated(monkeypatch, wired):
    monkeypatch.setattr(iw.audit, "last_inbound_chase", lambda tid: _iso(hours=2))
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    iw.run(now=NOW)
    assert wired["dms"] == []


def test_a_day_old_chase_fires_again(monkeypatch, wired):
    monkeypatch.setattr(iw.audit, "last_inbound_chase", lambda tid: _iso(days=2))
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    iw.run(now=NOW)
    assert len(wired["dms"]) == 2


def test_one_digest_per_run(wired):
    wired["tickets"] = [{"id": "T", "properties": {}}]
    wired["ev"] = _werner_ev()
    iw.run(now=NOW)
    assert len(wired["posts"]) == 1 and wired["posts"][0][0] == "C_D"


# ── the Ashley leg ──────────────────────────────────────────────────────────
def test_promise_phrases_match_what_a_parent_actually_types():
    assert iw.promise_in("As of now I'm waiting for it to be approved through the school "
                         "and they will send you the purchase order")
    assert iw.promise_in("I submitted the request yesterday")
    assert iw.promise_in("Hi, just checking on the schedule") is None
    assert iw.promise_in("") is None


@pytest.fixture
def answers_wired(monkeypatch, wired):
    monkeypatch.setattr(iw, "cfg", lambda: {**CFG, "inbound_watch": {
        **CFG["inbound_watch"],
        "chase": {"enabled": False},
        "answers": {"enabled": True, "task_prefixes": ["PO request:"],
                    "promise_pushes_due_days": 7, "max_per_run": 25}}})
    monkeypatch.setattr(iw.hs, "_search_all", lambda path, f, p: wired["open_tasks"])
    monkeypatch.setattr(iw, "_task_contact_ids", lambda tid: ["249080775607"])
    monkeypatch.setattr(iw, "_contact_phones", lambda cid: ["5305595178"])
    monkeypatch.setattr(iw.jc, "index_by_number", lambda d: wired["sms"])
    wired["open_tasks"], wired["sms"] = [], {}
    return wired


ASHLEY_TASK = {"id": "117052496020", "properties": {
    "hs_task_subject": "PO request: Ashley Clay - Trace ",
    "hs_task_body": "Awaiting email confirmation from EF.",
    "hs_createdate": _iso(days=1), "hs_timestamp": _iso(days=0),
    "hubspot_owner_id": "81494333"}}

ASHLEY_TEXT = {"at": _iso(hours=2), "direction": "inbound",
               "text": "As of now I'm waiting for it to be approved through the school and "
                       "they will send you the purchase order so we can schedule the sessions."}


def test_ashley_answer_is_stamped_and_the_due_date_moves_out(answers_wired):
    answers_wired["open_tasks"] = [ASHLEY_TASK]
    answers_wired["sms"] = {"5305595178": {"texts": [ASHLEY_TEXT], "calls": []}}
    iw.run(now=NOW)
    patches = [p for p in answers_wired["patched"] if p[0] == "PATCH"]
    assert len(patches) == 1
    props = patches[0][2]["properties"]
    assert "the family answered this by text" in props["hs_task_body"]
    assert "Awaiting email confirmation from EF." in props["hs_task_body"]   # original kept
    due = dt.datetime.fromtimestamp(int(props["hs_timestamp"]) / 1000, dt.timezone.utc)
    assert (due - _dt(hours=2)).days == 7


def test_a_text_that_predates_the_task_is_not_its_answer(answers_wired):
    answers_wired["open_tasks"] = [ASHLEY_TASK]
    answers_wired["sms"] = {"5305595178": {
        "texts": [{**ASHLEY_TEXT, "at": _iso(days=5)}], "calls": []}}
    iw.run(now=NOW)
    assert [p for p in answers_wired["patched"] if p[0] == "PATCH"] == []


def test_our_own_outbound_never_counts_as_their_answer(answers_wired):
    answers_wired["open_tasks"] = [ASHLEY_TASK]
    answers_wired["sms"] = {"5305595178": {
        "texts": [{**ASHLEY_TEXT, "direction": "outgoing"}], "calls": []}}
    iw.run(now=NOW)
    assert [p for p in answers_wired["patched"] if p[0] == "PATCH"] == []


def test_the_same_answer_is_never_stamped_twice(monkeypatch, answers_wired):
    """Otherwise the due date walks a week further out on every single run."""
    key = f"117052496020:{_dt(hours=2).isoformat()}"
    monkeypatch.setattr(iw.audit, "inbound_answers_stamped", lambda: {key})
    answers_wired["open_tasks"] = [ASHLEY_TASK]
    answers_wired["sms"] = {"5305595178": {"texts": [ASHLEY_TEXT], "calls": []}}
    iw.run(now=NOW)
    assert [p for p in answers_wired["patched"] if p[0] == "PATCH"] == []


def test_tasks_outside_the_configured_prefixes_are_ignored(answers_wired):
    answers_wired["open_tasks"] = [{"id": "x", "properties": {
        "hs_task_subject": "QTL Charter Call 1: Ashley Clay", "hs_task_body": "",
        "hs_createdate": _iso(days=1), "hs_timestamp": _iso()}}]
    answers_wired["sms"] = {"5305595178": {"texts": [ASHLEY_TEXT], "calls": []}}
    iw.run(now=NOW)
    assert [p for p in answers_wired["patched"] if p[0] == "PATCH"] == []
