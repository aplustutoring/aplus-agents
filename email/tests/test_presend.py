"""Pre-send gate: the six checklist items as code (knowledge/journey/00).
The Gonzalez case is the regression: support-line traffic + a text from the
charter_sales line must HOLD and name the M-Z scheduler."""
from datetime import datetime, timedelta, timezone

import pytest

from src import presend
from src.justcall_client import JustCallUnavailable

CFG = {
    "presend": {
        "enabled": True, "season_start": "2026-08-15", "thread_window_days": 14,
        "min_gap_hours": 20, "max_sms_per_day": 2, "max_few": 25,
        "lines": {"charter_sales": "+18185736644", "sales": "+18185736644",
                  "support": "+18188691627", "conference": "+18188506284"},
        "line_owner": {"charter_sales": "charter_sales", "sales": "sales",
                       "support": "scheduler_split", "conference": "sales"},
        "standing_go": ["po_welcome"],
        "stop_line_exempt": ["po_welcome", "po_push", "tor_confirm"],
        "purposes": {"po_welcome": {}, "po_push": {}, "tor_confirm": {}, "lead_relay": {},
                     "tutor_ask": {}},
    },
    "sms": {"send_hour_start_pt": 0, "send_hour_end_pt": 24},
    "scheduler_split": {"a_to_l": "janelle", "m_to_z": "yolanda"},
    "roles": {"scheduler_a_l": "janelle", "scheduler_m_z": "yolanda",
              "scheduling_lead": "mandy", "charter_sales": "paola", "sales": "danielle"},
    "staff": {"janelle": {"name": "Janelle", "hubspot_owner_id": "J1", "slack_user_id": "UJ"},
              "yolanda": {"name": "Yolanda", "hubspot_owner_id": "Y1", "slack_user_id": "UY"},
              "mandy": {"name": "Mandy", "hubspot_owner_id": "M1", "slack_user_id": "UM"},
              "paola": {"name": "Paola", "hubspot_owner_id": "P1", "slack_user_id": "UP"},
              "danielle": {"name": "Danielle", "hubspot_owner_id": "D1", "slack_user_id": "UD"}},
}

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)   # 11 AM PT


def _staff(key):
    c = CFG
    st = c["staff"]
    if key in st:
        return st[key]
    return st.get(c["roles"].get(key, ""), {})


def _contact(**over):
    p = {"firstname": "Mary", "lastname": "Gonzalez", "phone": "+18187216225",
         "a_persona": "Family", "sms_opt_out": "", "hs_email_optout": ""}
    p.update(over)
    return {"id": "C1", "properties": p}


@pytest.fixture
def wired(monkeypatch):
    presend._reset_cache()
    state = {"deals": [], "texts": {}, "inbound": [], "tickets": [], "jc_fail": False,
             "notes": [], "patches": [], "audit": []}
    monkeypatch.setattr(presend, "cfg", lambda: CFG)
    monkeypatch.setattr(presend, "staff", _staff)
    import src.router as router
    monkeypatch.setattr(router, "cfg", lambda: CFG)
    import src.sms as sms
    monkeypatch.setattr(sms, "cfg", lambda: CFG)
    monkeypatch.setattr(presend.hs, "get_contact_deals", lambda cid: state["deals"])
    monkeypatch.setattr(presend.hs, "contact_inbound_since", lambda cid, since: state["inbound"])
    monkeypatch.setattr(presend.hs, "open_tickets_for_contact", lambda cid: state["tickets"])
    monkeypatch.setattr(presend.hs, "add_contact_note", lambda cid, body: state["notes"].append((cid, body)) or {})
    monkeypatch.setattr(presend.hs, "patch_contact_props", lambda cid, props: state["patches"].append((cid, props)) or {})
    monkeypatch.setattr(presend.audit, "append", lambda r: state["audit"].append(r))

    def _index(since_days=90):
        if state["jc_fail"]:
            raise JustCallUnavailable("boom")
        return state["texts"]
    monkeypatch.setattr(presend.jc, "index_by_number", _index)
    # bypass the 5-minute per-process cache: tests mutate the index between calls
    monkeypatch.setattr(presend, "_jc_index", lambda days: _index(days))
    return state


def _text(at, direction, line, text="hi"):
    return {"at": at, "direction": direction, "line": line, "agent": "", "text": text}


def _recent(hours_ago=2):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S")


# ── a, b, purpose ───────────────────────────────────────────────────
def test_opt_out_blocks(wired):
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(sms_opt_out="true"),
                      body="x", confirmed=True, now=NOW)
    assert d.verdict == "block" and "opted out" in d.reasons[0]


def test_quiet_hours_hold(wired, monkeypatch):
    import src.sms as sms
    monkeypatch.setattr(sms, "_in_send_window", lambda now=None: False)
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("quiet hours" in r for r in d.reasons)


def test_unknown_purpose_blocks(wired):
    d = presend.check("C1", "sms", "charter_sales", "mystery", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "block" and "unknown purpose" in d.reasons[0]


# ── c. stage -> line ────────────────────────────────────────────────
def test_lead_from_support_line_blocks(wired):
    d = presend.check("C1", "sms", "support", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "block" and "lead audience must go from the charter_sales line" in d.reasons[0]


def test_family_with_deal_from_lead_line_blocks(wired):
    wired["deals"] = [{"id": "D1", "createdate": "2026-09-01T00:00:00Z"}]
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "block" and "scheduling audience must go from the support line" in d.reasons[0]
    assert d.audience == "scheduling"


def test_tutor_persona_forces_support(wired):
    c = _contact(a_persona="Tutors", lastname="Bretz")
    d = presend.check("C1", "sms", "charter_sales", "tutor_ask", contact=c, body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "block" and d.audience == "tutor"


# ── d. the Gonzalez case ────────────────────────────────────────────
def test_gonzalez_support_thread_holds_and_names_the_scheduler(wired):
    wired["texts"] = {"8187216225": {"texts": [
        _text(_recent(30), "outgoing", "18188691627", "Yes, that's right, we need the PO"),
        _text(_recent(29), "incoming", "18188691627", "Salamat")], "calls": []}}
    d = presend.check("C1", "sms", "charter_sales", "lead_relay", contact=_contact(),
                      body="Christa can do 1-3. Reply STOP to opt out.", confirmed=True, now=NOW)
    assert d.verdict == "hold"
    assert any("active thread on the support line" in r for r in d.reasons)
    # scheduler_split is by last name: G is A-L, so Janelle (who did in fact
    # close the Gonzalez thread on 2026-09-09: "Thanks again Janelle")
    assert d.owner and d.owner["name"] == "Janelle"


def test_unanswered_reply_on_other_line_holds_same_line_is_in_thread(wired):
    wired["texts"] = {"8187216225": {"texts": [
        _text(_recent(5), "outgoing", "18188691627"),
        _text(_recent(1), "incoming", "18188691627", "Can you call me")], "calls": []}}
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(),
                      body="x. Reply STOP to opt out.", confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("unanswered reply" in r for r in d.reasons)
    assert not d.in_thread
    wired["texts"] = {"8187216225": {"texts": [
        _text(_recent(1), "incoming", "18185736644", "YES")], "calls": []}}
    d2 = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                       confirmed=True, now=NOW)
    assert d2.verdict == "allow" and d2.in_thread


def test_unanswered_inbox_reply_holds(wired):
    wired["inbound"] = [{"at": "2026-09-09T10:00:00Z", "thread_id": "T9", "answered": False}]
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("thread T9" in r for r in d.reasons)


def test_open_scheduler_ticket_holds(wired):
    wired["tickets"] = [{"id": "TK1", "properties": {"hubspot_owner_id": "Y1", "subject": "Reschedule"}}]
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("owned by scheduling" in r for r in d.reasons)


def test_justcall_unavailable_holds_not_allows(wired):
    wired["jc_fail"] = True
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                      confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("could not verify JustCall" in r for r in d.reasons)


# ── e. frequency ────────────────────────────────────────────────────
def test_recent_agent_outbound_holds_unless_in_thread(wired):
    ms = str(int((datetime.now(timezone.utc) - timedelta(hours=3)).timestamp() * 1000))
    c = _contact(agent_last_outbound_at=ms, agent_last_outbound_seat="charter_sales")
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=c, body="x", confirmed=True, now=NOW)
    assert d.verdict == "hold" and any("inside the 20h gap" in r for r in d.reasons)
    wired["texts"] = {"8187216225": {"texts": [
        _text(_recent(1), "incoming", "18185736644", "YES")], "calls": []}}
    d2 = presend.check("C1", "sms", "charter_sales", "po_push", contact=c, body="x", confirmed=True, now=NOW)
    assert d2.verdict == "allow" and d2.in_thread


# ── f. standing go ──────────────────────────────────────────────────
def test_standing_go_allows_without_confirm(wired):
    wired["deals"] = [{"id": "D1", "createdate": "2026-09-01T00:00:00Z"}]
    d = presend.check("C1", "sms", "support", "po_welcome", contact=_contact(), body="Hi!", now=NOW)
    assert d.verdict == "allow"


def test_no_standing_go_holds_then_confirm_allows(wired):
    d = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x", now=NOW)
    assert d.verdict == "hold" and any("no standing go" in r for r in d.reasons)
    d2 = presend.check("C1", "sms", "charter_sales", "po_push", contact=_contact(), body="x",
                       confirmed=True, now=NOW)
    assert d2.verdict == "allow"


# ── g. STOP line ────────────────────────────────────────────────────
def test_cold_sms_without_stop_blocks_but_in_thread_allows(wired):
    d = presend.check("C1", "sms", "charter_sales", "lead_relay", contact=_contact(), body="hello",
                      confirmed=True, now=NOW)
    assert d.verdict == "block" and any("STOP line" in r for r in d.reasons)
    wired["texts"] = {"8187216225": {"texts": [
        _text(_recent(1), "incoming", "18185736644", "Which days?")], "calls": []}}
    d2 = presend.check("C1", "sms", "charter_sales", "lead_relay", contact=_contact(), body="hello",
                       confirmed=True, now=NOW)
    assert d2.verdict == "allow"


# ── record_send / has_replied_since ─────────────────────────────────
def test_record_send_writes_note_props_audit_in_order(wired):
    presend.record_send("C1", "sms", "charter_sales", "po_push", "+18187216225", "body", "one_to_few", True)
    assert wired["notes"][0][1].startswith("[Agent] outbound sms from=charter_sales purpose=po_push")
    assert wired["patches"][0][1]["agent_last_outbound_seat"] == "charter_sales"
    assert wired["audit"][0]["action_taken"] == "outbound_sent"


def test_record_send_note_failure_still_audits(wired, monkeypatch):
    def boom(cid, body):
        raise RuntimeError("hubspot down")
    monkeypatch.setattr(presend.hs, "add_contact_note", boom)
    presend.record_send("C1", "sms", "charter_sales", "po_push", "+1", "b", "x", True)
    assert wired["audit"] and wired["audit"][0]["ok"] is True


def test_has_replied_since_merges_sources(wired):
    wired["inbound"] = [{"at": "2026-09-09T10:00:00Z", "thread_id": "T1", "answered": True}]
    wired["texts"] = {"8187216225": {"texts": [
        _text("2026-09-09T12:00:00", "incoming", "18185736644", "YES")], "calls": []}}
    r = presend.has_replied_since("C1", "+18187216225", "2026-09-08T00:00:00Z")
    assert len(r["email"]) == 1 and len(r["sms"]) == 1 and r["latest"] == "2026-09-09T12:00:00"
    assert r["sms"][0]["line"] == "charter_sales"


# ── parity with the bulk messenger ──────────────────────────────────
def test_lines_and_max_few_match_messenger_config():
    import pathlib
    import yaml
    from src.config import cfg as real_cfg
    root = pathlib.Path(__file__).resolve().parents[2]
    m = yaml.safe_load(open(root / "ops" / "messenger" / "config.yml"))
    pc = real_cfg().get("presend") or {}
    assert pc["max_few"] == m["min_bulk"]
    for k, v in (m.get("sms") or {}).get("numbers", {}).items():
        if k in pc["lines"]:
            assert pc["lines"][k] == v, k
