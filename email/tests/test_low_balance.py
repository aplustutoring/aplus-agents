"""Low-balance renewal agent — alert parsing, case lifecycle, routing, guardrails."""
import datetime as dt

import pytest

from src import low_balance as lb

ALERT = """Hi APlus Tutoring Inc,

This message is to inform you that the Charter - iLEAD  package balance
for Taylor Rodriguez has reached the level of 4 hours
and is currently at 4.0 unused hours.

CUSTOMER DETAILS
Name:  Jessica Lujan
Email: jessicalujanbd@gmail.com
Home Phone:
Mobile Phone: +1 909-454-8581
Student: Taylor Rodriguez"""

CANCEL = "Layla Schnider has cancelled the lesson scheduled for Friday."

SEAT = {"name": "Paola", "hubspot_owner_id": "81494333", "slack_user_id": "UPAO",
        "email": "paola@wetutorathome.com"}
ROMAN = {"name": "Roman", "slack_user_id": "UROM"}


def _cfg(armed=False, **over):
    c = {
        "hubspot": {"ticket_stages": {"needs_approval": "1", "closed": "4"},
                    "bcc_log_address": "bcc@x", "portal_id": "6312752"},
        "ticket_fields": {"priority_map": {"normal": "MEDIUM"}, "category_map": {"low_balance": "new_deal_po"},
                          "category_default": "GENERAL_INQUIRY", "source": "EMAIL"},
        "staff": {"paola": SEAT, "roman": ROMAN},
        "roles": {"charter_sales": "paola", "visionary": "roman"},
        "deal_sync": {"charter_pipelines": ["907748", "72281989"]},
        "deal_automation": {"stop_stage_patterns": ["stopped", "closed lost"]},
        "sms": {"justcall_number": "+18188691627", "send_hour_start_pt": 8, "send_hour_end_pt": 20},
        "low_balance": {
            "enabled": True, "armed": armed, "max_hours": 4, "owner": "charter_sales", "notify": ["charter_sales"],
            "escalate_to": "visionary", "escalate_days": 10, "follow_up_business_days": 3,
            "draft_unsent_nag_hours": 24, "sla_hours": 8, "priority": "normal",
            "no_teacher_email_pipelines": ["72281989"],
            "sms_template": "Hi {first_name}, it's {sender_first} with A+ Tutoring.{personal_sms} {student} has {hours} left on the current PO. Please submit a new PO, or ask your teacher of record to. Reply here with any questions.",
            "positivity": {"enabled": False, "model": "m", "max_tokens": 120},
            "family_email": {"mode": "send", "template": "templates/low_balance_charter.html",
                             "from": "{sender_name}, A+ Tutoring <admin@wetutorathome.com>",
                             "reply_to": "{sender_email}",
                             "subject": "{student}'s tutoring hours are running low"},
            "tor_email": {"mode": "draft", "mailbox": "seat",
                          "subject": "New PO for {student_full} (A+ Tutoring)",
                          "body": "Hi {tor_first},\n\n{student_full} has {hours} left on PO {po_number}.\n\n{sender_name}"},
        },
    }
    c["low_balance"].update(over)
    return c


DEAL = {"id": "64250037589", "properties": {
    "dealname": "Jessica Lujan - Taylor Rodriguez - iLead 1 - 26/27", "pipeline": "907748",
    "dealstage": "907774", "createdate": "2026-08-22T04:05:07.868Z", "po_number": "3114143406",
    "number_of_hours_in_this_po": "5", "teacher_of_record_name": "Kylee Cooper-Robles",
    "teacher_of_record_email": "kylee@ileadexploration.org", "student_school": "iLEAD Exploration",
    "student_first_name": "Taylor", "student_last_name_if_diff_from_parent": "Rodriguez"}}
CONTACT = {"id": "3167401", "properties": {"email": "jessicalujanbd@gmail.com", "firstname": "Jessica",
                                           "lastname": "Lujan", "mobilephone": "+19094548581"}}


# ── parsing ──────────────────────────────────────────────────────────────

def test_parse_alert_reads_every_fact():
    a = lb.parse_alert(ALERT)
    assert a["package"] == "Charter - iLEAD"
    assert a["student"] == "Taylor Rodriguez" and a["student_first"] == "Taylor"
    assert a["student_last"] == "Rodriguez"
    assert a["level"] == 4 and a["hours"] == 4.0 and a["unit"] == "hours"
    assert a["parent_name"] == "Jessica Lujan" and a["parent_last"] == "Lujan"
    assert a["parent_email"] == "jessicalujanbd@gmail.com"
    assert a["parent_phone"] == "+1 909-454-8581"


def test_parse_alert_ignores_other_teachworks_mail():
    assert lb.parse_alert(CANCEL) is None
    assert lb.parse_alert("") is None


def test_parse_alert_survives_html_and_lessons():
    html = ALERT.replace("\n", "<br>").replace("4.0 unused hours", "2 unused lessons") \
                .replace("level of 4 hours", "level of 2 lessons")
    a = lb.parse_alert(html)
    assert a and a["unit"] == "lessons" and a["hours"] == 2


def test_sender_gate():
    assert lb.is_teachworks_sender(["notifications@teachworks.com"])
    assert not lb.is_teachworks_sender(["mom@gmail.com"])


def test_case_key_is_per_student_package_season():
    a = lb.parse_alert(ALERT)
    d = dt.datetime(2026, 9, 8)
    assert lb.case_key(a, d) == "low-balance:26/27:taylor-rodriguez:charter-ilead"
    assert lb.season(dt.datetime(2027, 3, 1)) == "26/27"
    assert lb.season(dt.datetime(2027, 8, 1)) == "27/28"


def test_charter_detection(monkeypatch):
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    assert lb.is_charter_package("Charter - iLEAD")
    assert lb.is_charter_package("Improvement Package", "907748")
    assert not lb.is_charter_package("2025 - Prep Package", "default")


# ── the case ─────────────────────────────────────────────────────────────

RECENT = {"tutor_first": "Sarah", "sessions": 6, "since": "2026-08-22", "subjects": ["Math"],
          "notes": [], "notes_fields_seen": []}
NO_RECENT = {"tutor_first": "", "sessions": 0, "since": "", "subjects": [], "notes": [],
             "notes_fields_seen": []}


class Harness:
    def __init__(self, monkeypatch, cfgv, deals=None, contact=CONTACT, open_cases=None,
                 in_window=True, recent=None, positivity=""):
        self.tickets, self.notes, self.tasks, self.dms = [], [], [], []
        self.sms, self.emails, self.drafts, self.recs = [], [], [], []
        self.stage_updates = []
        monkeypatch.setattr(lb, "cfg", lambda: cfgv)
        monkeypatch.setattr(lb, "_tw_recent", lambda a, d: dict(recent if recent is not None else NO_RECENT))
        monkeypatch.setattr(lb, "_positivity", lambda s, t, n, client=None: positivity)
        monkeypatch.setattr(lb, "staff", lambda k: cfgv["staff"].get(cfgv["roles"].get(k, k), {}))
        monkeypatch.setattr(lb, "_student_deals", lambda f, l, after=None: list(deals or []))
        monkeypatch.setattr(lb, "_family_contact", lambda a: contact)
        monkeypatch.setattr(lb, "open_cases", lambda: dict(open_cases or {}))
        monkeypatch.setattr(lb, "_in_sms_window", lambda: in_window)
        monkeypatch.setattr(lb, "_send_sms", lambda p, b: self.sms.append((p, b)) or {"ok": True})
        monkeypatch.setattr(lb, "_send_family_email",
                            lambda to, ctx, c: self.emails.append((to, ctx)))
        monkeypatch.setattr(lb, "_tor_draft",
                            lambda to, s, b, c, seat: self.drafts.append((to, s, b, seat)) or
                            {"id": "d1", "message": {"id": "m1", "threadId": "t9"}})
        monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Charter Schools - Traditional")
        monkeypatch.setattr(lb.hs, "create_ticket",
                            lambda *a, **k: self.tickets.append((a, k)) or {"id": "T1"})
        monkeypatch.setattr(lb.hs, "link_thread_to_ticket", lambda t, i: {})
        monkeypatch.setattr(lb.hs, "add_ticket_note", lambda t, b: self.notes.append((t, b)))
        monkeypatch.setattr(lb.hs, "create_task",
                            lambda *a, **k: self.tasks.append((a, k)) or {"id": "K1"})
        monkeypatch.setattr(lb.hs, "update_ticket_stage",
                            lambda t, s: self.stage_updates.append((t, s)))
        monkeypatch.setattr(lb.hs, "ticket_url", lambda t: f"https://hs/t/{t}")
        monkeypatch.setattr(lb.slack_client, "dm", lambda u, t: self.dms.append((u, t)) or {"ok": True})
        monkeypatch.setattr(lb.audit, "append", lambda r: self.recs.append(r))

    def opened(self):
        return next(r for r in self.recs if r.get("action_taken") == "low_balance_opened")


MSG = {"id": "m-alert-1", "text": ALERT, "subject": "Package Balance Alert"}


def test_held_case_files_ticket_and_dm_but_sends_nothing(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=False), deals=[DEAL])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened"
    assert rec["message_id"] == "low-balance:26/27:taylor-rodriguez:charter-ilead"
    assert h.tickets and h.tickets[0][0][0].startswith("Low balance: Taylor Rodriguez (iLead), 4 hours left")
    assert h.tickets[0][0][1] == "81494333"            # the seat owns it
    assert h.tickets[0][0][4] == "3167401"             # linked to the family
    assert not h.sms and not h.emails and not h.drafts
    assert rec["armed"] is False and rec["charter"] is True
    # the seat sees exactly what WOULD go out
    assert len(h.dms) == 1 and h.dms[0][0] == "UPAO"
    assert "No outreach (agent not armed)" in h.dms[0][1]
    assert "Taylor has 4 hours or less left" in h.dms[0][1]      # the customer copy
    assert "has 4 hours left on Charter - iLEAD" in h.dms[0][1]  # the exact balance, staff-facing
    assert "kylee@ileadexploration.org" in h.dms[0][1]
    assert h.tasks and "Low balance follow-up: Taylor Rodriguez" in h.tasks[0][0][0]
    # a second audit line carries the alert's own message id for triage dedupe
    assert any(r.get("message_id") == "m-alert-1" and r["action_taken"] == "low_balance_alert_processed"
               for r in h.recs)


def test_armed_case_texts_emails_and_drafts_from_the_seat(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert h.sms == [("+1 909-454-8581",
                      "Hi Jessica, it's Paola with A+ Tutoring. Taylor has 4 hours or less left on the "
                      "current PO. Please submit a new PO, or ask your teacher of record to. "
                      "Reply here with any questions.")]
    assert "Kylee" not in h.sms[0][1] and "iLead" not in h.sms[0][1]   # no teacher, no school
    assert h.emails and h.emails[0][0] == "jessicalujanbd@gmail.com"
    assert h.emails[0][1]["sender_email"] == "paola@wetutorathome.com"
    to, subj, body, seat = h.drafts[0]
    assert to == "kylee@ileadexploration.org"
    assert subj == "New PO for Taylor Rodriguez (A+ Tutoring)"
    assert body.startswith("Hi Kylee,") and "PO 3114143406" in body and body.endswith("Paola")
    assert "4 hours or less" in body and "4 hours left" not in body
    assert rec["tor_mailbox"] == "paola@wetutorathome.com" and rec["tor_draft_id"] == "d1"
    assert rec["sms_sent"] and rec["email_sent"] == "jessicalujanbd@gmail.com"
    assert "—" not in h.sms[0][1] and "--" not in h.sms[0][1]


def test_quiet_hours_queue_the_text_for_the_sweep(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL], in_window=False)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert not h.sms and rec["sms_pending"] and rec["phone"] == "+1 909-454-8581"
    assert "queued" in rec["sms_body"] or rec["sms_body"].startswith("Hi Jessica")
    # the sweep sends it once the window opens (case still open, armed)
    case = dict(rec, opened_at=dt.datetime.now(dt.timezone.utc).isoformat())
    h2 = Harness(monkeypatch, _cfg(armed=True), deals=[], in_window=True,
                 open_cases={rec["message_id"]: case})
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 9, 9, 3))
    lb.run_sweep()
    assert h2.sms == [("+1 909-454-8581", rec["sms_body"])]


def test_level_up_terri_never_emails_the_teacher(monkeypatch):
    terri = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "72281989"}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[terri])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert h.sms and h.emails and not h.drafts
    assert any("no-teacher-email" in f for f in rec["flags"])


def test_non_charter_package_is_ticket_only(monkeypatch):
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": ""}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[gold])
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    body = ALERT.replace("Charter - iLEAD", "2025 - Prep Package")
    rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
    assert rec["charter"] is False and rec["armed"] is False
    assert h.tickets and not h.sms and not h.emails and not h.drafts
    assert "not a charter package" in h.dms[0][1]


def test_repeat_alert_adds_a_note_and_never_re_texts(monkeypatch):
    prior = {"ticket_id": "T1", "student": "Taylor Rodriguez"}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL],
                open_cases={"low-balance:26/27:taylor-rodriguez:charter-ilead": prior})
    rec = lb.handle_alert("thr2", {**MSG, "id": "m-alert-2"}, lb.parse_alert(ALERT.replace("4.0 unused", "2.5 unused")))
    assert rec["action_taken"] == "low_balance_repeat" and rec["ticket_id"] == "T1"
    assert not h.sms and not h.emails and not h.drafts and not h.tickets and not h.dms
    assert h.notes and "2.5 hours" in h.notes[0][1]


def test_missing_family_and_deal_are_flagged_not_fatal(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], contact=None)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened"
    assert any("family contact NOT found" in f for f in rec["flags"])
    assert any("no deal found" in f for f in rec["flags"])
    assert not h.drafts                                  # no TOR to write to
    assert h.sms                                         # phone came from the alert itself
    assert "🚩" in h.dms[0][1]


def test_four_hours_or_less_is_the_line(monkeypatch):
    # Roman 2026-09-09: "4 hours or less". 4.0 opens a case; 4.5 and 6 do not.
    h = Harness(monkeypatch, _cfg(armed=True, max_hours=4), deals=[DEAL])
    for hours in ("6.0", "4.5"):
        body = ALERT.replace("4.0 unused hours", f"{hours} unused hours")
        rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
        assert rec["action_taken"] == "low_balance_above_threshold"
    assert not h.tickets and not h.sms and not h.dms
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened" and h.tickets


def test_disabled_agent_only_audits(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True, enabled=False), deals=[DEAL])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_disabled" and not h.tickets


# ── the sweep ────────────────────────────────────────────────────────────

def _case(**over):
    base = {"message_id": "low-balance:26/27:taylor-rodriguez:charter-ilead", "student": "Taylor Rodriguez",
            "school": "iLead", "ticket_id": "T1", "deal_id": "64250037589",
            "opened_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()}
    base.update(over)
    return base


def test_sweep_closes_case_when_the_new_po_lands(monkeypatch):
    case = _case()
    new_po = {"id": "777", "properties": {"dealname": "Jessica Lujan - Taylor Rodriguez - iLead 2 - 26/27",
                                          "po_number": "3114150000", "createdate": "2026-09-10T00:00:00Z"}}
    h = Harness(monkeypatch, _cfg(), deals=[new_po], open_cases={case["message_id"]: case})
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 3))
    lb.run_sweep()
    assert h.stage_updates == [("T1", "4")]
    assert any(r["action_taken"] == "low_balance_resolved" and "3114150000" in r["reason"] for r in h.recs)
    assert not h.dms


def test_sweep_closes_case_when_the_deal_stops(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(), deals=[], open_cases={case["message_id"]: case})
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: {"properties": {"pipeline": "907748", "dealstage": "x"}})
    monkeypatch.setattr(lb.hs, "stage_label", lambda p, s: "Stopped")
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 3))
    lb.run_sweep()
    assert h.stage_updates == [("T1", "4")]
    assert any("not continuing" in r.get("reason", "") for r in h.recs)


def test_sweep_escalates_stalled_cases_once(monkeypatch):
    case = _case(opened_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=12)).isoformat())
    h = Harness(monkeypatch, _cfg(), deals=[], open_cases={case["message_id"]: case})
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: {"properties": {"pipeline": "907748", "dealstage": "x"}})
    monkeypatch.setattr(lb.hs, "stage_label", lambda p, s: "Post-Lesson")
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 20, 9, 3))
    lb.run_sweep()
    assert {u for u, _ in h.dms} == {"UPAO", "UROM"}
    assert "NO PO after 10+ days" in h.dms[0][1] and "Taylor Rodriguez" in h.dms[0][1]
    assert any(r["action_taken"] == "low_balance_escalated" for r in h.recs)
    # already escalated → silent
    h2 = Harness(monkeypatch, _cfg(), deals=[], open_cases={case["message_id"]: {**case, "escalated": True}})
    lb.run_sweep()
    assert not h2.dms


def test_sweep_self_gates_to_the_top_of_the_hour(monkeypatch):
    h = Harness(monkeypatch, _cfg(), deals=[], open_cases={"k": _case()})
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 40))
    lb.run_sweep()
    assert not h.recs and not h.dms


def test_open_cases_folds_state_from_the_audit_log(monkeypatch):
    recs = [
        {"message_id": "low-balance:26/27:a:b", "action_taken": "low_balance_opened", "student": "A B"},
        {"message_id": "low-balance:26/27:a:b:sms", "action_taken": "low_balance_sms_sent"},
        {"message_id": "low-balance:26/27:c:d", "action_taken": "low_balance_opened", "student": "C D"},
        {"message_id": "low-balance:26/27:c:d:resolved", "action_taken": "low_balance_resolved"},
        {"message_id": "low-balance:26/27:a:b:escalated", "action_taken": "low_balance_escalated"},
    ]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    cases = lb.open_cases()
    assert list(cases) == ["low-balance:26/27:a:b"]
    assert cases["low-balance:26/27:a:b"]["sms_sent"] and cases["low-balance:26/27:a:b"]["escalated"]


def test_template_renders_without_leftover_tokens_or_em_dashes(monkeypatch):
    from pathlib import Path
    tpl = Path(__file__).resolve().parents[1] / "templates" / "low_balance_charter.html"
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    ctx = lb._context(lb.parse_alert(ALERT), DEAL, CONTACT, SEAT)     # no Teachworks data
    out = lb._render(tpl.read_text(), ctx)
    assert "{" not in out.replace("{{", "") and "—" not in out
    assert "It's Paola with A+ Tutoring. A quick heads up: Taylor has <strong>4 hours or less</strong>" in out
    assert "iLead" not in out and "iLEAD" not in out and "Kylee" not in out   # no school, no teacher
    ctx = lb._context(lb.parse_alert(ALERT), DEAL, CONTACT, SEAT, RECENT,
                      "Lately Taylor has been building confidence with fractions.")
    out = lb._render(tpl.read_text(), ctx)
    assert ("It's Paola with A+ Tutoring. Taylor has had 6 sessions with Sarah since this PO "
            "started on August 22. Lately Taylor has been building confidence with fractions. "
            "A quick heads up:") in out


# ── personalisation ──────────────────────────────────────────────────────

def test_text_carries_tutor_and_sessions_when_teachworks_has_them(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL], recent=RECENT)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert h.sms[0][1].startswith("Hi Jessica, it's Paola with A+ Tutoring. Taylor has had 6 sessions "
                                  "with Sarah on this PO. Taylor has 4 hours or less left")
    assert rec["tutor_first"] == "Sarah" and rec["sessions_on_po"] == 6


def test_personal_line_variants():
    a = lb.parse_alert(ALERT)
    assert lb._personal(a, NO_RECENT, "") == ("", "")
    sms, line = lb._personal(a, {**RECENT, "sessions": 1}, "")
    assert sms == " Taylor has had 1 session with Sarah on this PO."
    assert line == " Taylor has had 1 session with Sarah since this PO started on August 22."
    sms, line = lb._personal(a, {**RECENT, "sessions": 0}, "")
    assert sms == line == " Taylor has been working with Sarah."
    _sms, line = lb._personal(a, RECENT, "Lately Taylor loves fractions.")
    assert line.endswith("August 22. Lately Taylor loves fractions.")


class _FakeClaude:
    def __init__(self, text):
        self.text = text
        self.messages = self
    def create(self, **kw):
        import types
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=self.text)])


def test_positivity_is_off_by_default_and_validated(monkeypatch):
    notes = ["Worked on fractions and word problems, Taylor is getting faster and more confident."]
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())                    # enabled: False
    assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude("Lately Taylor has been mastering fractions.")) == ""
    on = _cfg(positivity={"enabled": True, "model": "m", "max_tokens": 120})
    monkeypatch.setattr(lb, "cfg", lambda: on)
    assert lb._positivity("Taylor", "Sarah", [], client=_FakeClaude("x")) == ""          # no notes, no call
    assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude(
        "Lately Taylor has been mastering fractions with Sarah")) == "Lately Taylor has been mastering fractions with Sarah."
    for bad in ("NONE", "Taylor scored 92 on the quiz.", "Great job Taylor!",
                "Taylor — a star.", " ".join(["word"] * 31)):
        assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude(bad)) == ""


def test_tw_recent_reads_tutor_sessions_and_note_fields(monkeypatch):
    from src import teachworks_client as tw
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    monkeypatch.setattr(tw, "accounts", lambda: {"online": "tok"})
    monkeypatch.setattr(tw, "customers_for_family", lambda e, l, f, token=None: [{"id": 7}])
    def fake_get(endpoint, params=None, token=None):
        if endpoint == "students":
            return [{"id": 1, "first_name": "Taylor"}, {"id": 2, "first_name": "Sibling"}]
        assert params["student_id"] == 1 and params["from_date[gte]"] == "2026-08-22"
        return [
            {"from_date": "2026-09-01", "status": "Attended", "employee_name": "Sarah Lee",
             "name": "Math Tutoring", "participants": [
                 {"student_name": "Taylor Rodriguez", "status": "Attended",
                  "notes": "Worked on fractions and word problems; Taylor is getting more confident."}]},
            {"from_date": "2026-08-25", "status": "Attended", "employee_name": "Sarah Lee",
             "name": "Math Tutoring", "participants": [{"student_name": "Taylor Rodriguez", "status": "Attended"}]},
            {"from_date": "2026-08-28", "status": "Cancelled", "employee_name": "Sarah Lee"},
            {"from_date": "2099-01-01", "status": "Scheduled", "employee_name": "Sarah Lee"},
        ]
    monkeypatch.setattr(tw, "tw_get", fake_get)
    r = lb._tw_recent(lb.parse_alert(ALERT), DEAL)
    assert r["tutor_first"] == "Sarah" and r["sessions"] == 2 and r["since"] == "2026-08-22"
    assert r["subjects"] == ["Math Tutoring"] and r["notes_fields_seen"] == ["notes"]
    assert r["notes"][0].startswith("Worked on fractions")
    # a Teachworks hiccup never blocks the case
    monkeypatch.setattr(tw, "tw_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503")))
    assert lb._tw_recent(lb.parse_alert(ALERT), DEAL)["sessions"] == 0
