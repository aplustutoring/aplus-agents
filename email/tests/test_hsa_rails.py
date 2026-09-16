"""IEM HSA cohort deals on the existing rails (spec docs/specs/cohort-intake-spec.md).

- sms: the hsa template never asks for a time; the welcome email fills the
  program tokens from the deal's [Agent] HSA props; the subject is scrubbed.
- owner_assign: group parity, odd → A-L seat, even → M-Z seat.
- deal_sync: a deal carrying hsa_sessions passes the charter guard and runs
  the HSA after-sync (ES contact spike + ONE group invoice task).
- invoice_sweep: $0 invoices never reach the overdue nag.
- presend: cohort_welcome has a standing go on the email channel.
- one family with two cohort kids = one text + one welcome (rail rule).
"""
import pytest

from src import deal_sync as dsy, hsa_sync, invoice_sweep, owner_assign as oa, router, sms
from src.presend import Decision

HSA_DESC = ("IEM High School Academy English 9 Intervention, Cohort 1 (Group 4)\n"
            "Session calendar: Sep 21 (2026), Sep 28, Oct 5\n"
            "No class: Nov 23 to 27 (Thanksgiving week); week of Mar 8\n")


def _hsa_deal(did="H1", student="Diego", group="C1-G4", owner="227538487"):
    return {"id": did, "properties": {
        "dealname": f"Reyna - {student} Reyna - Ocean Grove Charter School - IEM HSA English 9",
        "pipeline": "5119061", "dealstage": "5119062", "createdate": "2026-09-15T12:00:00Z",
        "schedule_preferences": "Monday 10:00 AM PT weekly from Sep 21, 2026",
        "hubspot_owner_id": owner, "student_first_name": student,
        "is_the_family_currently_being_tutored_by_us_": "",
        "hsa_cohort": "1", "hsa_group": group, "hsa_sessions": "25", "hsa_start": "2026-09-21",
        "hsa_slot": "Monday 10:00 AM", "teacher_of_record_name": "Karen Ortiz",
        "teacher_of_record_email": "kortiz@ieminc.org", "parent_email": "reyna@x.com",
        "date_of_last_lesson_in_this_deal": "2027-05-10", "description": HSA_DESC, "amount": "1250"}}


# ─── sms: text copy + welcome tokens ─────────────────────────────────────────

SMS_CFG = {
    "sms": {"enabled": True, "justcall_number": "+18188691627", "start_date": "2026-09-03",
            "send_hour_start_pt": 0, "send_hour_end_pt": 24, "fallback_alert": "kath",
            "pipelines": {"5119061": {"template": "hsa", "welcome": True,
                                      "welcome_template": "templates/welcome_hsa.html",
                                      "welcome_subject": "__STUDENT__'s tutoring starts __START__ — __SUBJECT__, __SLOT__"}},
            "welcome": {"from": "A+ <admin@wetutorathome.com>"},
            "templates": {
                "hsa_confirm": "Hi {first_name}, {student} is set: {schedule}. Reply with questions.",
                "hsa_ask": "Hi {first_name}, {student} is set: {schedule}. Reply with questions.",
                "hsa_multi_confirm": "Hi {first_name}, {students} are set. Reply with questions.",
                "hsa_multi_ask": "Hi {first_name}, {students} are set. Reply with questions."}},
    "po_inbox": {"schedule_ask_fallback": "no schedule on file"},
    "hubspot": {"bcc_log_address": "bcc@hubspot.test"},
    "staff": {"kath": {"name": "Kath", "hubspot_owner_id": "513215050", "slack_user_id": "UK"}},
}


@pytest.fixture
def wired(monkeypatch):
    recorded, sent, deals, mails = [], [], [], []
    monkeypatch.setattr(sms, "cfg", lambda: SMS_CFG)
    monkeypatch.setattr(sms, "staff", lambda k: SMS_CFG["staff"].get(k, {}))
    monkeypatch.setattr(sms.audit, "append", lambda r: recorded.append(r))
    monkeypatch.setattr(sms.audit, "_iter_records", lambda: iter(list(recorded)))
    monkeypatch.setattr(sms, "_jc_send", lambda to, body: sent.append((to, body)) or {})
    monkeypatch.setattr(sms.slack_client, "dm", lambda u, t: {"ok": True})
    monkeypatch.setattr(sms.hs, "stage_label", lambda p, s: "Pre-Lesson")
    monkeypatch.setattr(sms.hs, "_write", lambda m, p, b=None: {"results": deals})
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Reyna", "phone": "+18185550101",
                                   "email": "reyna@x.com"}})
    monkeypatch.setattr(dsy, "_deal_contact", lambda did, name="": {"id": "C1"})
    monkeypatch.setattr(sms.presend, "check", lambda *a, **k: Decision("allow"))
    monkeypatch.setattr(sms.presend, "record_send", lambda *a, **k: None)
    monkeypatch.setattr(sms.presend, "enabled", lambda: False)
    monkeypatch.setattr(sms, "DRY_RUN", False)
    monkeypatch.setattr(sms.requests, "post",
                        lambda url, headers=None, json=None, timeout=None:
                        mails.append(json) or type("R", (), {"raise_for_status": lambda self: None})())
    return {"recorded": recorded, "sent": sent, "deals": deals, "mails": mails}


def test_cohort_text_confirms_the_iem_slot_and_never_asks(wired):
    wired["deals"].append(_hsa_deal())
    sms.run_sweep()
    assert wired["sent"] == [("+18185550101",
                              "Hi Reyna, Diego is set: Monday 10:00 AM PT weekly from Sep 21, 2026. Reply with questions.")]
    body = wired["sent"][0][1].lower()
    assert "change" not in body and "what days" not in body


def test_welcome_email_fills_program_tokens_and_scrubs_the_subject(wired):
    wired["deals"].append(_hsa_deal())
    sms.run_sweep()
    assert len(wired["mails"]) == 1
    mail = wired["mails"][0]
    assert mail["to"] == ["reyna@x.com"] and mail["bcc"] == ["bcc@hubspot.test"]
    assert mail["subject"] == "Diego's tutoring starts Monday, September 21, 2026, English 9, Monday 10:00 AM"
    assert "—" not in mail["subject"]
    html = mail["html"]
    assert "Hi Reyna," in html
    assert "Diego is enrolled in IEM's High School Academy English 9 tutoring group (Cohort 1)" in html
    assert "starting <strong>Monday, September 21, 2026</strong>" in html
    assert "every <strong>Monday 10:00 AM</strong>" in html
    assert "Forward it once to Karen Ortiz, Diego's ES" in html
    assert "(all 25 dates): Sep 21 (2026), Sep 28, Oct 5." in html
    assert "No sessions during Nov 23 to 27 (Thanksgiving week); week of Mar 8." in html
    assert "__" not in html                       # no token left behind
    assert "—" not in html


def test_two_cohort_kids_one_family_is_one_text_and_one_welcome(wired):
    wired["deals"].append(_hsa_deal("H1", "Diego", "C1-G4"))
    wired["deals"].append(_hsa_deal("H2", "Maya", "C1-G3"))
    sms.run_sweep()
    assert len(wired["sent"]) == 1 and "Diego and Maya are set" in wired["sent"][0][1]
    assert len(wired["mails"]) == 1
    assert sorted(r["deal_id"] for r in wired["recorded"] if r["action_taken"] == "sms_sent") == ["H1", "H2"]


def test_other_pipelines_keep_first_name_only(monkeypatch):
    # a non-HSA welcome carries no deal tokens; __FIRST_NAME__ still swaps
    monkeypatch.setattr(sms, "cfg", lambda: {**SMS_CFG, "sms": {**SMS_CFG["sms"],
                        "welcome": {"template": "templates/welcome_charter.html"}}})
    sms._send_welcome("x@y.com", "Ana")          # DRY_RUN path: loads + renders


def test_welcome_fields_are_empty_strings_when_the_deal_has_none():
    f = sms.welcome_fields({"dealname": "Lara Perkins - Nomi"})
    assert set(f) == set(sms.HSA_TOKENS) and all(v == "" for v in f.values())


# ─── owner_assign: group parity ───────────────────────────────────────────────

STAFF = {"janelle": {"name": "Janelle", "hubspot_owner_id": "80047202"},
         "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539"},
         "danielle": {"name": "Danielle", "hubspot_owner_id": "227538487"}}
OA_CFG = {"owner_assign": {"enabled": True, "pipelines": ["19120821"],
                           "group_parity": {"5119061": {"property": "hsa_group",
                                                        "odd": "janelle", "even": "yolanda"}}},
          "scheduler_split": {"a_to_l": "janelle", "m_to_z": "yolanda"}}


def _oa_wire(monkeypatch, fetched=None):
    calls = {"patch": [], "audit": [], "get": []}
    monkeypatch.setattr(oa, "cfg", lambda: OA_CFG)
    monkeypatch.setattr(router, "cfg", lambda: OA_CFG)
    monkeypatch.setattr(oa, "staff", lambda k: STAFF[k])
    monkeypatch.setattr(oa.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(oa.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(oa.hs, "_write", lambda m, p, body=None: calls["patch"].append(body) or {})
    monkeypatch.setattr(oa.hs, "_get", lambda p, params=None: calls["get"].append(p) or
                        {"properties": {"hsa_group": fetched}})
    return calls


def test_odd_group_goes_to_janelle_even_to_yolanda(monkeypatch):
    calls = _oa_wire(monkeypatch)
    rec = oa.maybe_assign(_hsa_deal("H1", group="C1-G3"), contact={"properties": {"lastname": "Zamora"}})
    assert rec["owner"] == "janelle"                      # odd beats the Z last name
    assert calls["patch"] == [{"properties": {"hubspot_owner_id": "80047202"}}]
    rec = oa.maybe_assign(_hsa_deal("H2", group="C1-G4"), contact={"properties": {"lastname": "Adams"}})
    assert rec["owner"] == "yolanda" and rec["last_name_source"] == "hsa_group"


def test_group_number_restarts_each_cohort_and_is_read_from_the_deal(monkeypatch):
    calls = _oa_wire(monkeypatch, fetched="C2-G1")
    d = _hsa_deal("H3", group="")
    d["properties"].pop("hsa_group")
    rec = oa.maybe_assign(d, contact=None)
    assert calls["get"] and rec["owner"] == "janelle" and rec["last_name"] == "C2-G1"


def test_no_group_number_leaves_the_deal_and_does_not_mark_it(monkeypatch):
    calls = _oa_wire(monkeypatch, fetched="")
    d = _hsa_deal("H4", group="")
    assert oa.maybe_assign(d, contact=None) is None
    assert calls["patch"] == [] and calls["audit"] == []


def test_group_number_parser():
    assert oa.group_number("C1-G4") == 4 and oa.group_number("12") == 12
    assert oa.group_number("") is None and oa.group_number("Group A") is None


# ─── deal_sync: guard exemption + HSA after-sync ──────────────────────────────

def _ds_wire(monkeypatch):
    calls = {"created": [], "students": [], "tasks": [], "audit": [], "slack": [], "tw_contact": []}
    monkeypatch.setattr(dsy, "cfg", lambda: {
        "deal_sync": {"enabled": True, "dry_run_first": False, "in_person_pipelines": [],
                      "charter_pipelines": ["5119061"], "exclude_pipelines": [],
                      "charter_student_billing": "Package", "private_student_billing": "Service List Cost"},
        "internal": {"domain": "wetutorathome.com"}, "slack": {"digest_channel": "CTEST"},
        "hsa": {"enabled": True, "pipeline": "5119061", "invoice_owner": "kath", "flag_to": ["danielle"]},
        "hubspot": {"portal_id": "6312752"},
        "staff": {"kath": {"name": "Kath", "hubspot_owner_id": "513215050"}}})
    monkeypatch.setattr(hsa_sync, "cfg", dsy.cfg)
    monkeypatch.setattr(hsa_sync, "staff", lambda k: {"kath": {"name": "Kath", "hubspot_owner_id": "513215050"}}[k])
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(dsy.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(hsa_sync.audit, "already_processed", lambda k: any(r.get("message_id") == k for r in calls["audit"]))
    monkeypatch.setattr(hsa_sync.audit, "append", lambda r: calls["audit"].append(r))
    # the ES is the associated TOR contact; the family contact matches nothing in the name
    monkeypatch.setattr(dsy, "_deal_contact", lambda d, n="": {"properties": {
        "email": "reyna.family@gmail.com", "firstname": "Reyna", "lastname": "Reyna"}})
    monkeypatch.setattr(dsy.hs, "pipeline_label", lambda p: "IEM Inc")
    monkeypatch.setattr(dsy.tw, "accounts", lambda: {"online": "tok1"})
    monkeypatch.setattr(dsy.tw, "find_customer_by_email", lambda e, t: None)
    monkeypatch.setattr(dsy.tw, "create_family", lambda f, t: calls["created"].append(f) or {"id": 77})
    monkeypatch.setattr(dsy.tw, "tw_get", lambda ep, p=None, token=None: [])
    monkeypatch.setattr(dsy.tw, "create_student", lambda f, t: calls["students"].append(f))
    monkeypatch.setattr(dsy.slack_client, "post_message", lambda ch, txt: calls["slack"].append(txt))
    monkeypatch.setattr(hsa_sync.hs, "_get", lambda p, params=None: {"properties": _hsa_deal()["properties"]})
    monkeypatch.setattr(hsa_sync.hs, "_search_all", lambda path, filters, props: [
        _hsa_deal("H1", "Diego"), _hsa_deal("H2", "Maya"), _hsa_deal("H3", "Owen")])
    monkeypatch.setattr(hsa_sync.hs, "create_task",
                        lambda subject, body, owner_id, due_ms, priority="MEDIUM", contact_id=None:
                        calls["tasks"].append((subject, owner_id, body)) or {"id": "T1"})
    monkeypatch.setattr(hsa_sync.tw, "add_additional_contact",
                        lambda cust, fields, token: calls["tw_contact"].append((cust, fields)) or (False, "HTTP 404: not found"))
    return calls


def test_cohort_deal_passes_the_charter_guard_and_syncs(monkeypatch):
    calls = _ds_wire(monkeypatch)
    d = _hsa_deal()
    d["properties"]["dealname"] = "Some Other Name - Diego Reyna - Ocean Grove Charter School - IEM HSA English 9"
    rec = dsy.sync_deal(d)
    assert rec["action_taken"] == "tw_synced" and calls["created"]
    assert calls["students"][0]["billing_method"] == "Package"
    assert not calls["slack"]                                  # no needs-review post


def test_es_contact_spike_falls_back_to_a_task_on_the_deal_owner(monkeypatch):
    calls = _ds_wire(monkeypatch)
    rec = dsy.sync_deal(_hsa_deal())
    assert calls["tw_contact"][0][0] == 77 and calls["tw_contact"][0][1]["email"] == "kortiz@ieminc.org"
    assert rec["hsa_tor_contact"] == "task"
    tor_tasks = [t for t in calls["tasks"] if t[0].startswith("Add ES Karen Ortiz")]
    assert tor_tasks and tor_tasks[0][1] == "227538487"        # the deal owner
    assert "HTTP 404" in tor_tasks[0][2]


def test_group_invoice_task_is_one_per_group_summed_over_siblings(monkeypatch):
    calls = _ds_wire(monkeypatch)
    dsy.sync_deal(_hsa_deal("H1", "Diego"))
    dsy.sync_deal(_hsa_deal("H2", "Maya"))
    inv = [t for t in calls["tasks"] if t[0].startswith("HSA group invoice")]
    assert len(inv) == 1                                       # second sibling reuses it
    assert inv[0][0] == "HSA group invoice — C1-G4 ($3,750.00, 3 students)"
    assert inv[0][1] == "513215050"                            # charter_admin
    assert "$0/hr" in inv[0][2] and "ONE invoice to IEM for $3,750.00" in inv[0][2]
    assert any(r["action_taken"] == "hsa_group_invoice_task" and r["total"] == 3750.0
               for r in calls["audit"])


def test_es_contact_api_success_makes_no_task(monkeypatch):
    calls = _ds_wire(monkeypatch)
    monkeypatch.setattr(hsa_sync.tw, "add_additional_contact", lambda c, f, t: (True, "additional contact 9"))
    rec = dsy.sync_deal(_hsa_deal())
    assert rec["hsa_tor_contact"] == "api"
    assert not [t for t in calls["tasks"] if t[0].startswith("Add ES")]


# ─── lesson-series verification (LOCKED: no lesson on a no-class date) ───────

def _lessons(dates):
    return [{"from_date": d, "status": "Scheduled"} for d in dates]


def test_verify_lessons_flags_a_no_class_booking_once_a_day(monkeypatch):
    calls = {"dm": [], "audit": []}
    from datetime import date as _date
    monkeypatch.setattr(hsa_sync, "cfg", lambda: {
        "hsa": {"enabled": True, "pipeline": "5119061", "flag_to": ["danielle"], "lesson_check_days": 60},
        "hubspot": {"portal_id": "6312752"},
        "staff": {"danielle": {"slack_user_id": "UD", "hubspot_owner_id": "227538487"},
                  "janelle": {"slack_user_id": "UJ", "hubspot_owner_id": "80047202"}}})
    monkeypatch.setattr(hsa_sync, "staff", lambda k: {"danielle": {"slack_user_id": "UD"}}[k])
    monkeypatch.setattr(hsa_sync, "now_la", lambda: __import__("datetime").datetime(2026, 9, 22, 8, 0))
    monkeypatch.setattr(hsa_sync.audit, "already_processed", lambda k: any(r["message_id"] == k for r in calls["audit"]))
    monkeypatch.setattr(hsa_sync.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(hsa_sync.slack_client, "dm", lambda u, t: calls["dm"].append((u, t)))
    monkeypatch.setattr(hsa_sync.hs, "_search_all", lambda *a: [_hsa_deal(owner="80047202")])
    monkeypatch.setattr(hsa_sync.tw, "accounts", lambda: {"online": "t"})
    # 25 Mondays straight through, no skips: 3 land on no-class dates
    mondays = [str(_date(2026, 9, 21) + __import__("datetime").timedelta(days=7 * i)) for i in range(25)]
    def tw_get(ep, params=None, token=None):
        return ({"customers": [{"id": 1}], "students": [{"id": 5, "first_name": "Diego"}]}
                .get(ep, _lessons(mondays)))
    monkeypatch.setattr(hsa_sync.tw, "tw_get", tw_get)
    hsa_sync.verify_lessons()
    assert len(calls["dm"]) == 2 and {u for u, _ in calls["dm"]} == {"UJ", "UD"}
    assert "on no-class dates: Nov 23, Nov 30, Dec 21" in calls["dm"][0][1]
    assert "Skip dates:" in calls["dm"][0][1]
    hsa_sync.verify_lessons()                                  # same day: no second DM
    assert len(calls["dm"]) == 2


def test_verify_lessons_accepts_a_correct_series(monkeypatch):
    calls = {"dm": [], "audit": []}
    monkeypatch.setattr(hsa_sync, "cfg", lambda: {"hsa": {"enabled": True, "pipeline": "5119061"},
                                                  "hubspot": {}, "staff": {}})
    monkeypatch.setattr(hsa_sync, "now_la", lambda: __import__("datetime").datetime(2026, 9, 22, 8, 0))
    monkeypatch.setattr(hsa_sync.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(hsa_sync.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(hsa_sync.slack_client, "dm", lambda u, t: calls["dm"].append((u, t)))
    monkeypatch.setattr(hsa_sync.hs, "_search_all", lambda *a: [_hsa_deal()])
    monkeypatch.setattr(hsa_sync.tw, "accounts", lambda: {"online": "t"})
    from agents.cohort_intake import cohort as C
    good = [d.isoformat() for d in C.session_dates(C.resolve_cohort("1, 9/21/26"), C.parse_slot("Mon 10:00 AM"))]
    def tw_get(ep, params=None, token=None):
        return ({"customers": [{"id": 1}], "students": [{"id": 5, "first_name": "Diego"}]}
                .get(ep, _lessons(good)))
    monkeypatch.setattr(hsa_sync.tw, "tw_get", tw_get)
    hsa_sync.verify_lessons()
    assert calls["dm"] == []
    assert any(r["action_taken"] == "hsa_lessons_verified" and r["count"] == 25 for r in calls["audit"])


# ─── invoice sweep ignores $0 ─────────────────────────────────────────────────

def test_overdue_nag_ignores_zero_dollar_invoices(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(invoice_sweep.hs, "stage_label", lambda p, s: "Post-Lesson")
    deals = [{"id": "Z", "properties": {"invoice__": "54001", "amount": "0", "dealname": "Zero",
                                        "lessons_fulfilled_date": "2026-09-01"}},
             {"id": "R", "properties": {"invoice__": "54002", "amount": "1250", "dealname": "Real",
                                        "lessons_fulfilled_date": "2026-09-01"}}]
    items = invoice_sweep._overdue_items(deals, datetime(2026, 9, 15), ["post-lesson"], 1)
    assert [i["deal_id"] for i in items] == ["R"]
