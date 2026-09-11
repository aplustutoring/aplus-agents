"""Low-balance renewal agent — alert parsing, the staged case (email day 0,
text + teacher day 1, retention risk day 7, lost day 28), private pay,
routing, guardrails."""
import datetime as dt

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

TIERS = {"online": [{"name": "Improvement", "hours": 8, "rate": 88}, {"name": "Prep", "hours": 20, "rate": 83},
                    {"name": "Success", "hours": 50, "rate": 73}, {"name": "Soar", "hours": 100, "rate": 68}],
         "in_person": [{"name": "Improvement", "hours": 8, "rate": 115}, {"name": "Prep", "hours": 20, "rate": 108},
                       {"name": "Success", "hours": 50, "rate": 103}, {"name": "Soar", "hours": 100, "rate": 93}]}


def _cfg(armed=False, **over):
    c = {
        "hubspot": {"ticket_stages": {"needs_approval": "1", "closed": "4"},
                    "bcc_log_address": "bcc@x", "portal_id": "6312752"},
        "ticket_fields": {"priority_map": {"normal": "MEDIUM"}, "category_map": {"low_balance": "new_deal_po"},
                          "category_default": "GENERAL_INQUIRY", "source": "EMAIL"},
        "staff": {"paola": SEAT, "roman": ROMAN},
        "roles": {"charter_sales": "paola", "visionary": "roman"},
        "deal_sync": {"charter_pipelines": ["907748", "72281989"], "in_person_pipelines": ["3067397"]},
        "deal_automation": {"stop_stage_patterns": ["stopped", "closed lost"]},
        "sms": {"justcall_number": "+18188691627", "send_hour_start_pt": 8, "send_hour_end_pt": 20},
        "low_balance": {
            "enabled": True, "armed": armed, "max_hours": 4, "owner": "charter_sales", "notify": ["charter_sales"],
            "escalate_to": "visionary", "family_text_after_days": 1, "retention_risk_days": 7,
            "lost_after_days": 21, "reengagement_list_id": "", "draft_unsent_nag_hours": 24,
            "sla_hours": 8, "priority": "normal", "no_teacher_email_pipelines": ["72281989"],
            "sms_template_with_tutor": "Hi {first_name}, it's {sender_first} with A+ Tutoring. {student} has been working with {tutor_first} and we want to keep that progress going. {student} has {hours} left on the current PO. Please submit a new PO, or ask your teacher of record to. Reply here with any questions.",
            "sms_template": "Hi {first_name}, it's {sender_first} with A+ Tutoring. {student} has {hours} left on the current PO. Please submit a new PO, or ask your teacher of record to. Reply here with any questions.",
            "positivity": {"enabled": False, "model": "m", "max_tokens": 120, "notes_window_days": 30},
            "family_email": {"mode": "send", "template": "templates/low_balance_charter.html",
                             "from": "{sender_name}, A+ Tutoring <admin@wetutorathome.com>",
                             "reply_to": "{sender_email}",
                             "subject": "{student}'s tutoring hours are running low"},
            "private_pay": {"template": "templates/low_balance_private.html",
                            "subject": "{student}'s next tutoring package",
                            "pricing_token": "2026", "tiers": TIERS},
            "tor_email": {"mode": "draft", "mailbox": "seat",
                          "subject": "New PO for {student} (A+ Tutoring)",
                          "body": "Hi {tor_first},\n\n{student} has {hours} left on the current PO{po_ref}.\n\n{sender_name}"},
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
RECENT = {"tutor_first": "Sarah", "sessions": 6, "since": "2026-08-22", "subjects": ["Math"],
          "notes": [], "notes_fields_seen": [], "first_session": "2026-08-25", "ok": True, "found": True}
# Teachworks answered, student not found: opens with flags (nothing to verify
# against; tests that want the parked path pass found + 0 sessions)
NO_RECENT = {"tutor_first": "", "sessions": 0, "since": "", "subjects": [], "notes": [],
             "notes_fields_seen": [], "first_session": "", "ok": True, "found": False}
MSG = {"id": "m-alert-1", "text": ALERT, "subject": "Package Balance Alert"}


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
    assert lb.case_key(a, dt.datetime(2026, 9, 8)) == "low-balance:26/27:taylor-rodriguez:charter-ilead"
    assert lb.season(dt.datetime(2027, 3, 1)) == "26/27"
    assert lb.season(dt.datetime(2027, 8, 1)) == "27/28"


def test_charter_detection(monkeypatch):
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    assert lb.is_charter_package("Charter - iLEAD")
    assert lb.is_charter_package("Improvement Package", "907748")
    assert not lb.is_charter_package("2025 - Prep Package", "default")


def test_first_name_handles_teachworks_last_first():
    assert lb._first_name("Torres, Maria") == "Maria"          # the replay's "Torres," bug
    assert lb._first_name("Sarah Lee") == "Sarah"
    assert lb._first_name("Torres,") == "Torres"
    assert lb._first_name("") == ""


# ── harness ──────────────────────────────────────────────────────────────

class Harness:
    def __init__(self, monkeypatch, cfgv, deals=None, contact=CONTACT, open_cases=None,
                 in_window=True, recent=None, positivity="", replied=False, ticket_open=True):
        self.tickets, self.notes, self.dms, self.patches = [], [], [], []
        self.sms, self.emails, self.private, self.drafts, self.recs = [], [], [], [], []
        self.stage_updates, self.stamps = [], []
        monkeypatch.setattr(lb, "cfg", lambda: cfgv)
        monkeypatch.setattr(lb, "staff", lambda k: cfgv["staff"].get(cfgv["roles"].get(k, k), {}))
        monkeypatch.setattr(lb, "_student_deals", lambda f, l, after=None: list(deals or []))
        monkeypatch.setattr(lb, "_family_contact", lambda a: contact)
        monkeypatch.setattr(lb, "open_cases", lambda: dict(open_cases or {}))
        monkeypatch.setattr(lb, "_in_sms_window", lambda: in_window)
        monkeypatch.setattr(lb, "_tw_recent", lambda a, d: dict(recent if recent is not None else NO_RECENT))
        monkeypatch.setattr(lb, "_positivity", lambda s, t, n, client=None: positivity)
        monkeypatch.setattr(lb, "_parent_replied", lambda c, s, l: replied)
        monkeypatch.setattr(lb, "_ticket_open", lambda c: ticket_open)
        monkeypatch.setattr(lb, "_send_sms", lambda p, b: self.sms.append((p, b)) or {"ok": True})
        monkeypatch.setattr(lb, "_send_email",
                            lambda to, subj, tpl, ctx, c: self.emails.append((to, subj, tpl, ctx)))
        monkeypatch.setattr(lb, "_tor_draft",
                            lambda to, s, b, c, seat: self.drafts.append((to, s, b, seat)) or
                            {"id": "d1", "message": {"id": "m1", "threadId": "t9"}})
        self.tor_sent = []
        monkeypatch.setattr(lb, "_tor_send",
                            lambda to, s, b, c, seat: self.tor_sent.append((to, s, b, seat)))
        monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Charter Schools - Traditional")
        monkeypatch.setattr(lb.hs, "create_ticket",
                            lambda *a, **k: self.tickets.append((a, k)) or {"id": "T1"})
        monkeypatch.setattr(lb.hs, "link_thread_to_ticket", lambda t, i: {})
        monkeypatch.setattr(lb.hs, "add_ticket_note", lambda t, b: self.notes.append((t, b)))
        monkeypatch.setattr(lb.hs, "update_ticket_stage", lambda t, s: self.stage_updates.append((t, s)))
        monkeypatch.setattr(lb.hs, "ticket_url", lambda t: f"https://hs/t/{t}")

        def fake_write(method, path, payload=None):
            self.patches.append((method, path, payload))
            if "/deals/" in path:
                self.stamps.append((path.rsplit("/", 1)[1], (payload or {}).get("properties")))
            return {"id": "X"}
        monkeypatch.setattr(lb.hs, "_write", fake_write)
        monkeypatch.setattr(lb.slack_client, "dm", lambda u, t: self.dms.append((u, t)) or {"ok": True})
        monkeypatch.setattr(lb.audit, "append", lambda r: self.recs.append(r))

    def opened(self):
        return next(r for r in self.recs if r.get("action_taken") == "low_balance_opened")

    def stage(self):
        return [p.get("retention_stage") for _d, p in self.stamps if p and p.get("retention_stage")]

    def send_pending(self, cases, armed=True):
        """The day-0 email step, as the sweep runs it (forced past the sibling delay)."""
        lb._send_pending_emails(cases, dt.datetime(2026, 9, 10, 9, 5), SEAT, lb.cfg()["low_balance"], armed, True)


# ── day 0: the case ───────────────────────────────────────────────────────

def test_held_case_files_ticket_and_dm_but_sends_nothing(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=False), deals=[DEAL], recent=RECENT)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened"
    assert rec["message_id"] == "low-balance:26/27:taylor-rodriguez:charter-ilead"
    assert h.tickets and h.tickets[0][0][0].startswith("Low balance: Taylor Rodriguez (iLead), 4 hours left")
    assert h.tickets[0][0][1] == "81494333" and h.tickets[0][0][4] == "3167401"
    assert not h.sms and not h.emails and not h.drafts
    assert rec["armed"] is False and rec["charter"] is True
    assert len(h.dms) == 1 and h.dms[0][0] == "UPAO"
    assert "Agent not armed" in h.dms[0][1] and "Day 1" in h.dms[0][1]
    assert not any("/tasks" in p for _m, p, _b in h.patches)          # ticket, not task
    assert h.stage() == ["low_hours"]
    assert any(r.get("message_id") == "m-alert-1" and r["action_taken"] == "low_balance_alert_processed"
               for r in h.recs)


def test_day0_queues_the_email_and_stores_the_rest_for_the_sweep(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL], recent=RECENT,
                positivity="Lately Taylor has been mastering fractions.")
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert not h.emails and not h.sms and not h.drafts               # nothing leaves at alert time
    assert rec["email_pending"] and rec["to_email"] == "jessicalujanbd@gmail.com"
    assert rec["personal_line"] == (" Taylor has been working with Sarah. "
                                    "Lately Taylor has been mastering fractions.")
    # the sweep sends it (one per family), and stamps the deal
    h.send_pending({rec["message_id"]: rec})
    assert len(h.emails) == 1
    to, subj, tpl, ctx = h.emails[0]
    assert to == "jessicalujanbd@gmail.com" and subj == "Taylor's tutoring hours are running low"
    assert tpl.endswith("low_balance_charter.html") and ctx["sender_email"] == "paola@wetutorathome.com"
    assert ctx["personal_line"] == rec["personal_line"] and ctx["progress"] == "that progress"
    assert any(r["action_taken"] == "low_balance_email_sent" for r in h.recs)
    assert h.stamps[-1][1]["retention_last_notice_sent"]
    stamp0 = dict(h.stamps[0][1])
    assert stamp0["retention_stage"] == "low_hours" and stamp0["retention_low_balance_alert_date"]
    assert "retention_last_notice_sent" not in stamp0          # nothing sent at alert time
    assert rec["sms_body"].startswith("Hi Jessica, it's Paola with A+ Tutoring. Taylor has been working "
                                      "with Sarah and we want to keep that progress going. Taylor has 4 hours or less left")
    assert "Kylee" not in rec["sms_body"] and "iLead" not in rec["sms_body"] and "fractions" not in rec["sms_body"]
    assert rec["phone"] == "+1 909-454-8581" and rec["tor_email"] == "kylee@ileadexploration.org"
    assert rec["tor_subject"] == "New PO for Taylor (A+ Tutoring)"
    assert rec["tor_body"].startswith("Hi Kylee,") and "the current PO (PO 3114143406)." in rec["tor_body"]
    assert "Rodriguez" not in rec["tor_body"]
    assert rec["tor_mailbox"] == "paola@wetutorathome.com"
    assert "—" not in rec["sms_body"] and "--" not in rec["sms_body"]


def test_four_hours_or_less_is_the_line(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL])
    for hours in ("6.0", "4.5"):
        body = ALERT.replace("4.0 unused hours", f"{hours} unused hours")
        rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
        assert rec["action_taken"] == "low_balance_above_threshold"
    assert not h.tickets and not h.emails and not h.dms
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened" and h.tickets


def test_level_up_terri_teacher_is_blocked_on_the_record(monkeypatch):
    terri = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "72281989"}}
    Harness(monkeypatch, _cfg(armed=True), deals=[terri])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["email_pending"] and rec["tor_blocked"] is True
    assert any("no-teacher-email" in f for f in rec["flags"])


def test_private_pay_gets_one_upgrade_email_and_no_text(monkeypatch):
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": "",
                                      "teacher_of_record_email": ""}}
    h = Harness(monkeypatch, _cfg(armed=True, charter_only=False), deals=[gold], recent=RECENT)
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    body = ALERT.replace("Charter - iLEAD", "2026 - Prep Package")
    rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
    assert rec["charter"] is False and rec["private_pay"] is True
    assert rec["private_tier"] == "Prep"
    assert "Prep package at $83 an hour" in rec["upgrade_line"] and "$73 an hour" in rec["upgrade_line"]
    assert rec["sms_body"] == "" and rec["tor_body"] == ""
    assert h.tickets[0][0][0] == "Low balance: Taylor Rodriguez (private pay), 4 hours left"
    assert "auto-renews" in h.dms[0][1]
    h.send_pending({rec["message_id"]: rec})
    to, subj, tpl, ctx = h.emails[0]
    assert subj == "Taylor's next tutoring package" and tpl.endswith("low_balance_private.html")
    assert ctx["upgrade_line"] == rec["upgrade_line"]
    assert not h.sms and not h.drafts


def test_alert_on_an_untouched_po_is_parked_until_the_first_lesson(monkeypatch):
    # Zie Rojas / Cooper Doyal: 4.0 unused on a 4-hour PO, nothing attended yet
    fresh = {**NO_RECENT, "ok": True, "found": True, "sessions": 0}
    four = {"id": "4h", "properties": {**DEAL["properties"], "number_of_hours_in_this_po": "4"}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[four], recent=fresh)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))          # 4.0 unused of a 4 h PO
    assert rec["action_taken"] == "low_balance_deferred" and rec["message_id"] == "m-alert-1"
    assert rec["alert"]["student"] == "Taylor Rodriguez" and rec["po_hours"] == "4"
    assert not h.tickets and not h.emails and not h.dms and not h.stamps
    # the hourly sweep re-checks: first lesson attended → the case opens normally
    monkeypatch.setattr(lb, "deferred_alerts", lambda: {rec["case_key"]: rec})
    h2 = Harness(monkeypatch, _cfg(armed=True), deals=[four], recent={**RECENT, "sessions": 1})
    monkeypatch.setattr(lb, "deferred_alerts", lambda: {rec["case_key"]: rec})
    lb._recheck_deferred(dt.datetime.now(dt.timezone.utc))
    assert h2.tickets and any(r["action_taken"] == "low_balance_opened" for r in h2.recs)
    # parked too long → let go, audited, nothing sent
    stale = {**rec, "deferred_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=31)).isoformat()}
    h3 = Harness(monkeypatch, _cfg(armed=True), deals=[four], recent=fresh)
    monkeypatch.setattr(lb, "deferred_alerts", lambda: {rec["case_key"]: stale})
    lb._recheck_deferred(dt.datetime.now(dt.timezone.utc))
    assert not h3.tickets and any(r["action_taken"] == "low_balance_defer_expired" for r in h3.recs)


def test_park_never_on_a_lookup_miss_or_when_hours_were_used(monkeypatch):
    fresh = {**NO_RECENT, "ok": True, "found": True, "sessions": 0}
    # no deal → nothing to park against → opens with flags
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], recent=fresh)
    assert lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))["action_taken"] == "low_balance_opened"
    # Teachworks did not find the student (Ariana Fiore, Kailyn Marie) → opens
    h2 = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL], recent={**NO_RECENT, "found": False})
    assert lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))["action_taken"] == "low_balance_opened"
    # the alert's own numbers say hours were used (4.0 left of a 5 h PO) → opens
    h3 = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL], recent=fresh)
    assert lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))["action_taken"] == "low_balance_opened"
    assert h.tickets and h2.tickets and h3.tickets


def test_deferred_alerts_folds_the_audit_log(monkeypatch):
    recs = [
        {"message_id": "m1", "action_taken": "low_balance_deferred", "case_key": "k:a", "alert": {"student": "A"}},
        {"message_id": "m2", "action_taken": "low_balance_deferred", "case_key": "k:b", "alert": {"student": "B"}},
        {"message_id": "k:b", "action_taken": "low_balance_opened", "case_key": "k:b"},
        {"message_id": "m3", "action_taken": "low_balance_deferred", "case_key": "k:c", "alert": {"student": "C"}},
        {"message_id": "k:c:defer-expired", "action_taken": "low_balance_defer_expired", "case_key": "k:c"},
    ]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    assert list(lb.deferred_alerts()) == ["k:a"]


def test_charter_only_declines_private_pay_and_out_of_pocket(monkeypatch):
    # Roman 2026-09-10: "only on charter service codes, excluding out of pocket"
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": ""}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[gold], recent=RECENT)      # charter_only defaults on
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    for pkg in ("*2026 - Current - Prep Package (20)", "CHARTER - Out of Pocket"):
        body = ALERT.replace("Charter - iLEAD", pkg)
        assert lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body)) is None
    assert not h.tickets and not h.emails and not h.sms and not h.drafts and not h.dms and not h.stamps
    assert [r["action_taken"] for r in h.recs] == ["low_balance_out_of_scope"] * 2
    # a charter alert still opens a case
    h2 = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL])
    assert lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))["action_taken"] == "low_balance_opened"
    assert h2.tickets


def test_out_of_pocket_charter_family_is_private_pay():
    assert not lb.is_charter_package("CHARTER - Out of Pocket")


def test_negative_balance_parses():
    a = lb.parse_alert(ALERT.replace("4.0 unused hours", "-0.5 unused hours"))
    assert a and a["hours"] == -0.5


def test_private_pay_in_person_tiers_and_unknown_tier(monkeypatch):
    inp = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "3067397", "po_number": ""}}
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    a = lb.parse_alert(ALERT.replace("Charter - iLEAD", "2026 - Soar 100"))
    ctx = lb._context(a, inp, CONTACT, SEAT)
    p = lb._private_ctx(a, inp, ctx, _cfg()["low_balance"])
    assert p["modality"] == "in-person" and p["current_tier"] == "Soar" and p["next_tier"] == ""
    assert "Success (50 hours) is $103 an hour" in p["upgrade_line"]   # top tier → general line
    a2 = lb.parse_alert(ALERT.replace("Charter - iLEAD", "2026 Mystery Pack"))
    p2 = lb._private_ctx(a2, inp, ctx, _cfg()["low_balance"])
    assert p2["current_tier"] == "" and "lower rates" in p2["upgrade_line"]


def test_private_pay_old_pricing_gets_no_auto_email(monkeypatch):
    # Roman 2026-09-10: the upgrade email quotes 2026 rates, so a family on
    # an older service code never gets it; the seat has the rate conversation
    # from the ticket instead.
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": "",
                                      "teacher_of_record_email": ""}}
    h = Harness(monkeypatch, _cfg(armed=True, charter_only=False), deals=[gold], recent=RECENT)
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    body = ALERT.replace("Charter - iLEAD", "2025 - Prep Package")
    rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
    assert rec["private_pay"] is True and rec["private_old_pricing"] is True
    assert rec["email_pending"] is False and rec["upgrade_line"] == ""
    h.send_pending({rec["message_id"]: rec})
    assert not h.emails and not h.sms and not h.drafts   # nothing goes out, even armed
    assert "Old pricing" in str(h.tickets) + str(h.notes)


def test_private_pay_routes_to_commissioned_scheduler(monkeypatch):
    # Roman 2026-09-10: schedulers get commission on private-pay upgrades, so
    # the ticket, the DM, and the sender identity are the assigned scheduler's.
    from src import router
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": "",
                                      "teacher_of_record_email": ""}}
    cfgv = _cfg(armed=True, charter_only=False)            # dormant path: charter_only is the live default
    cfgv["staff"]["yolanda"] = {"name": "Yolanda", "hubspot_owner_id": "86868539",
                                "slack_user_id": "UYO", "email": "yolanda@wetutorathome.com"}
    cfgv["roles"]["scheduler_m_z"] = "yolanda"
    h = Harness(monkeypatch, cfgv, deals=[gold], recent=RECENT)
    monkeypatch.setattr(router, "scheduler_for_last_name", lambda ln: ("scheduler_m_z", []))
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    body = ALERT.replace("Charter - iLEAD", "2026 - Prep Package")
    rec = lb.handle_alert("thr1", {**MSG, "text": body}, lb.parse_alert(body))
    assert rec["owner"] == "scheduler_m_z"
    assert h.tickets[0][0][1] == "86868539"                # ticket owner = the scheduler
    assert h.dms and all(u == "UYO" for u, _t in h.dms)    # DM only the scheduler, not Paola
    h.send_pending({rec["message_id"]: rec})
    _to, _subj, _tpl, ctx = h.emails[0]
    assert ctx["sender_first"] == "Yolanda"                # from-name + sign-off
    assert ctx["sender_email"] == "yolanda@wetutorathome.com"   # reply-to


def test_repeat_alert_adds_a_note_and_never_re_sends(monkeypatch):
    prior = {"ticket_id": "T1", "student": "Taylor Rodriguez"}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[DEAL],
                open_cases={"low-balance:26/27:taylor-rodriguez:charter-ilead": prior})
    rec = lb.handle_alert("thr2", {**MSG, "id": "m-alert-2"},
                          lb.parse_alert(ALERT.replace("4.0 unused", "2.5 unused")))
    assert rec["action_taken"] == "low_balance_repeat" and rec["ticket_id"] == "T1"
    assert not h.emails and not h.sms and not h.drafts and not h.tickets and not h.dms
    assert h.notes and "2.5 hours" in h.notes[0][1]


def test_missing_family_and_deal_are_flagged_not_fatal(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], contact=None)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened"
    assert any("family contact NOT found" in f for f in rec["flags"])
    assert any("no deal found" in f for f in rec["flags"])
    assert rec["email_pending"]                         # the alert itself carries the email
    assert rec["phone"] == "+1 909-454-8581" and rec["tor_email"] == ""
    assert h.tickets[0][0][0].startswith("Low balance: Taylor Rodriguez (school unknown)")
    assert "your charter school" not in h.dms[0][1] and "🚩" in h.dms[0][1]
    assert not h.stamps                                 # no deal → nothing to stamp


def test_tor_email_resolved_from_name_when_deal_has_none(monkeypatch):
    from src import po_inbox
    no_email = {"id": "9", "properties": {**DEAL["properties"], "teacher_of_record_email": ""}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[no_email], recent=RECENT)
    monkeypatch.setattr(po_inbox, "_tor_by_name",
                        lambda f, l: [{"id": "77", "properties": {"email": "kylee@ileadexploration.org"}}]
                        if (f, l) == ("Kylee", "Cooper-Robles") else [])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["tor_email"] == "kylee@ileadexploration.org"
    monkeypatch.setattr(po_inbox, "_tor_by_name",
                        lambda f, l: [{"properties": {"email": "a@x"}}, {"properties": {"email": "b@x"}}])
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: {"results": []})
    Harness(monkeypatch, _cfg(armed=True), deals=[no_email], recent=RECENT)
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["tor_email"] == "" and any("no teacher-of-record email" in f for f in rec["flags"])


def test_disabled_agent_only_audits(monkeypatch):
    h = Harness(monkeypatch, _cfg(armed=True, enabled=False), deals=[DEAL])
    rec = lb.handle_alert("thr1", MSG, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_disabled" and not h.tickets


# ── the sweep: day 1, renewed, stopped, risk, lost ────────────────────────

def _case(**over):
    base = {"message_id": "low-balance:26/27:taylor-rodriguez:charter-ilead", "student": "Taylor Rodriguez",
            "school": "iLead", "ticket_id": "T1", "deal_id": "64250037589", "contact_id": "3167401",
            "charter": True, "parent_email": "jessicalujanbd@gmail.com", "to_email": "jessicalujanbd@gmail.com",
            "email_pending": True, "email_sent": "jessicalujanbd@gmail.com", "first_name": "Jessica",
            "student_first": "Taylor", "tutor_first": "Sarah", "hours": 4.0,
            "personal_line": " Taylor has been working with Sarah.",
            "phone": "+1 909-454-8581", "sms_body": "Hi Jessica, text body.", "opted_out": False,
            "tor_email": "kylee@ileadexploration.org", "tor_subject": "New PO for Taylor (A+ Tutoring)",
            "tor_body": "Hi Kylee, body.", "tor_mailbox": "paola@wetutorathome.com", "tor_blocked": False,
            "opened_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1, hours=2)).isoformat()}
    base.update(over)
    return base


def _active_deal(monkeypatch):
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: {"properties": {"pipeline": "907748", "dealstage": "x"}})
    monkeypatch.setattr(lb.hs, "stage_label", lambda p, s: "Post-Lesson")


def test_day1_texts_and_drafts_when_no_po_and_no_reply(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 3))
    lb.run_sweep(force=True)
    assert h.sms == [("+1 909-454-8581", "Hi Jessica, text body.")]
    assert h.drafts and h.drafts[0][0] == "kylee@ileadexploration.org"
    rec = next(r for r in h.recs if r["action_taken"] == "low_balance_family_contacted")
    assert rec["sms_sent"] and rec["tor_draft_id"] == "d1" and rec["tor_mailbox"] == "paola@wetutorathome.com"
    assert h.stage() == ["teacher_contacted"]
    assert h.notes and "Day 1" in h.notes[0][1]
    assert h.dms and h.dms[0][0] == "UPAO" and "Day 1" in h.dms[0][1]


def test_day1_teacher_email_sends_automatically_in_send_mode(monkeypatch):
    # Roman 2026-09-10: "i want paolas email to be automatic" — tor_email.mode
    # send skips the Gmail draft and sends via Resend, replies to the seat.
    case = _case()
    cfgv = _cfg(armed=True)
    cfgv["low_balance"]["tor_email"]["mode"] = "send"
    h = Harness(monkeypatch, cfgv, deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 3))
    lb.run_sweep(force=True)
    assert h.tor_sent and h.tor_sent[0][0] == "kylee@ileadexploration.org"
    assert not h.drafts                                       # no Gmail draft in send mode
    rec = next(r for r in h.recs if r["action_taken"] == "low_balance_family_contacted")
    assert rec.get("tor_emailed") and not rec.get("tor_draft_id")
    assert h.stage() == ["teacher_contacted"]


def test_new_alert_after_renewal_starts_next_cycle(monkeypatch):
    # 4-hour POs (iLEAD et al.): the renewal PO is born low, so the next
    # Teachworks alert is the NEXT cycle, not a repeat. The stale case closes
    # as renewed and the full sequence runs again (Roman 2026-09-10).
    prior = _case()
    new_po = {"id": "999", "properties": {**DEAL["properties"], "po_number": "NEXT111",
                                          "dealname": "Jessica Lujan - Taylor Rodriguez - iLead 2 - 26/27"}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[new_po], recent=RECENT,
                open_cases={prior["message_id"]: prior})
    rec = lb.handle_alert("thr2", {**MSG, "id": "m-alert-2"}, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_opened"        # a fresh case, not a repeat
    resolved = [r for r in h.recs if r["action_taken"] == "low_balance_resolved"]
    assert resolved and "NEXT111" in resolved[0]["reason"]
    assert len(h.tickets) == 1                                # a new ticket for the new cycle
    assert rec["email_pending"]                               # day-0 email queues again


def test_repeat_alert_with_no_renewal_stays_quiet(monkeypatch):
    prior = _case()
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], recent=RECENT,
                open_cases={prior["message_id"]: prior})
    rec = lb.handle_alert("thr2", {**MSG, "id": "m-alert-3"}, lb.parse_alert(ALERT))
    assert rec["action_taken"] == "low_balance_repeat"
    assert not h.tickets and not h.emails and not h.sms


def test_day1_never_leads_the_email(monkeypatch):
    case = _case(email_sent=None)          # email not out yet (say, no window) → no text either
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case}, in_window=False)
    _active_deal(monkeypatch)
    monkeypatch.setattr(lb, "_send_pending_emails", lambda *a, **k: set())
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts


def test_siblings_get_one_email_one_text_and_one_teacher_draft(monkeypatch):
    ez = _case(message_id="k:ezekiel", student="Ezekiel Melara", student_first="Ezekiel", ticket_id="T1",
               deal_id="d1", first_name="Mayra", to_email="schoolmve@gmail.com", parent_email="schoolmve@gmail.com",
               phone="+17143537555", tutor_first="Sarah", personal_line=" Ezekiel has been working with Sarah.",
               sms_body="single ez", tor_body="Hi Kylee,\n\nsingle ez", tor_subject="New PO for Ezekiel (A+ Tutoring)")
    ma = _case(message_id="k:mario", student="Mario Melara", student_first="Mario", ticket_id="T2",
               deal_id="d2", first_name="Mayra", to_email="schoolmve@gmail.com", parent_email="schoolmve@gmail.com",
               phone="+17143537555", tutor_first="Ana", personal_line=" Mario has been working with Ana.",
               sms_body="single ma", tor_body="Hi Kylee,\n\nsingle ma", tor_subject="New PO for Mario (A+ Tutoring)")
    cases = {"k:ezekiel": ez, "k:mario": ma}
    cfgv = _cfg(armed=True,
                sms_template_multi="Hi {first_name}, {students} have been working with {tutor_first}. Each has {hours} left.",
                tor_email={"mode": "draft", "mailbox": "seat", "subject": "x", "body": "x",
                           "subject_multi": "New POs for {students} (A+ Tutoring)",
                           "body_multi": "{greeting}\n\nHope you are well.{personal_line} {po_lines} Could you issue new POs?\n\n{sender_name}"},
                family_email={"mode": "send", "template": "templates/low_balance_charter.html",
                              "template_multi": "templates/low_balance_charter_multi.html",
                              "from": "{sender_name} <admin@wetutorathome.com>", "reply_to": "{sender_email}",
                              "subject": "{student}'s tutoring hours are running low",
                              "subject_multi": "{students}: tutoring hours are running low"})
    h = Harness(monkeypatch, cfgv, deals=[], open_cases=cases)
    # day 0: one email for the family
    h.send_pending({k: {**c, "email_sent": None} for k, c in cases.items()})
    assert len(h.emails) == 1
    to, subj, tpl, ctx = h.emails[0]
    assert to == "schoolmve@gmail.com" and subj == "Ezekiel and Mario: tutoring hours are running low"
    assert tpl.endswith("low_balance_charter_multi.html") and ctx["students"] == "Ezekiel and Mario"
    assert ctx["personal_line"] == " Ezekiel has been working with Sarah. Mario has been working with Ana."
    assert sum(1 for r in h.recs if r["action_taken"] == "low_balance_email_sent") == 2
    # day 1: one text, one teacher draft, both naming both kids
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert h.sms == [("+17143537555", "Hi Mayra, Ezekiel and Mario have been working with Ana and Sarah. "
                                      "Each has 4 hours or less left.")]
    assert len(h.drafts) == 1
    to, subj, body, _seat = h.drafts[0]
    assert to == "kylee@ileadexploration.org" and subj == "New POs for Ezekiel and Mario (A+ Tutoring)"
    assert body.startswith("Hi Kylee,") and "Ezekiel's current PO has 4 hours or less left." in body \
        and "Mario's current PO has 4 hours or less left." in body
    assert sum(1 for r in h.recs if r["action_taken"] == "low_balance_family_contacted") == 2
    assert len([d for d in h.dms if "Day 1" in d[1]]) == 1


def test_sibling_without_a_deal_borrows_the_teacher(monkeypatch):
    ez = _case(message_id="k:ezekiel", student="Ezekiel Melara", student_first="Ezekiel", ticket_id="T1",
               deal_id=None, to_email="schoolmve@gmail.com", phone="+17143537555", package="Charter - Sky Mountain",
               tor_email="", tor_body="", tor_subject="", first_name="Mayra", sms_body="single ez")
    ma = _case(message_id="k:mario", student="Mario Melara", student_first="Mario", ticket_id="T2",
               deal_id="d2", to_email="schoolmve@gmail.com", phone="+17143537555", package="Charter - Sky Mountain",
               tor_email="pdeker@ieminc.org", tor_body="Hi Paula,\n\nsingle ma", tor_subject="New PO for Mario (A+ Tutoring)",
               first_name="Mayra", sms_body="single ma")
    cases = {"k:ezekiel": ez, "k:mario": ma}
    cfgv = _cfg(armed=True, sms_template_multi="Hi {first_name}, {students} each have {hours} left.",
                tor_email={"mode": "draft", "mailbox": "seat", "subject": "x", "body": "x",
                           "subject_multi": "New POs for {students} (A+ Tutoring)",
                           "body_multi": "{greeting}\n\n{po_lines}\n\n{sender_name}"})
    h = Harness(monkeypatch, cfgv, deals=[], open_cases=cases)
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert len(h.drafts) == 1 and h.drafts[0][0] == "pdeker@ieminc.org"
    assert h.drafts[0][1] == "New POs for Ezekiel and Mario (A+ Tutoring)"
    assert "Ezekiel's current PO" in h.drafts[0][2] and "Mario's current PO" in h.drafts[0][2]


def test_student_deals_falls_back_to_the_deal_name(monkeypatch):
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    calls = []
    named = {"id": "9", "properties": {"dealname": "Mayra Aguilar - Ezekiel Melara - Sky Mountain 2 - 26/27",
                                       "po_number": "555", "createdate": "2026-08-30T00:00:00Z"}}
    # the property search returns the WRONG Ezekiel (Garcia): the surname filter
    # empties it and the name fallback must still run
    garcia = {"id": "7", "properties": {"dealname": "Mishla Garcia - Ezekiel Garcia - Heartland 1 - 26/27",
                                        "student_first_name": "Ezekiel", "po_number": "444"}}
    def fake_write(m, p, body=None):
        calls.append(body["filterGroups"][0]["filters"][0]["propertyName"])
        return {"results": [garcia] if calls[-1] == "student_first_name" else [named]}
    monkeypatch.setattr(lb.hs, "_write", fake_write)
    assert lb._student_deals("Ezekiel", "Melara") == [named]
    assert calls == ["student_first_name", "dealname"]
    # multi-word surname matches on any token
    calls.clear()
    kd = {"id": "8", "properties": {"dealname": "Juan DaVault - Kailyn DaVault - iLead 1 - 26/27", "po_number": "1"}}
    monkeypatch.setattr(lb.hs, "_write", lambda m, p, body=None: {"results": [kd]})
    assert lb._student_deals("Kailyn", "Marie DaVault") == [kd]


def test_day1_waits_for_the_next_business_morning(monkeypatch):
    # opened Tuesday 09:00 PT → not due Tuesday, due Wednesday 08:00+
    opened = dt.datetime(2026, 9, 8, 16, 0, tzinfo=dt.timezone.utc)     # 09:00 PT
    case = _case(opened_at=opened.isoformat())
    monkeypatch.setattr(lb, "cfg", lambda: _cfg(armed=True))
    monkeypatch.setattr(lb, "_in_sms_window", lambda: True)
    assert not lb._day1_due(case, dt.datetime(2026, 9, 8, 15, 0), 1)
    assert lb._day1_due(case, dt.datetime(2026, 9, 9, 9, 0), 1)
    # opened Friday → due Monday, never Saturday
    fri = dt.datetime(2026, 9, 11, 17, 0, tzinfo=dt.timezone.utc)
    case_f = _case(opened_at=fri.isoformat())
    assert not lb._day1_due(case_f, dt.datetime(2026, 9, 12, 10, 0), 1)
    assert lb._day1_due(case_f, dt.datetime(2026, 9, 14, 9, 0), 1)


def test_day1_skipped_when_the_family_replied(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case}, replied=True)
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts
    assert any(r["action_taken"] == "low_balance_family_replied" for r in h.recs)
    assert h.notes and "replied" in h.notes[0][1]


def test_day1_skipped_when_paola_already_closed_the_ticket(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case}, ticket_open=False)
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts


def test_day1_respects_terri_and_opt_out(monkeypatch):
    case = _case(tor_blocked=True, opted_out=True)
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts
    assert h.stage() == ["family_contacted"]
    assert "opted out" in h.notes[0][1]


def test_day1_held_when_not_armed(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(armed=False), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts and "Not armed" in h.notes[0][1]


def test_day1_happens_once(monkeypatch):
    case = _case(day1_done=True)
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h.sms and not h.drafts


def test_sweep_closes_renewed_when_the_new_po_lands(monkeypatch):
    case = _case()
    new_po = {"id": "777", "properties": {"dealname": "Jessica Lujan - Taylor Rodriguez - iLead 2 - 26/27",
                                          "po_number": "3114150000", "createdate": "2026-09-10T00:00:00Z"}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[new_po], open_cases={case["message_id"]: case})
    lb.run_sweep(force=True)
    assert h.stage_updates == [("T1", "4")] and h.stage() == ["renewed"]
    assert any(r["action_taken"] == "low_balance_resolved" and "3114150000" in r["reason"] for r in h.recs)
    assert not h.sms and not h.dms


def test_sweep_closes_not_renewing_when_the_deal_stops(monkeypatch):
    case = _case()
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case})
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: {"properties": {"pipeline": "907748", "dealstage": "x"}})
    monkeypatch.setattr(lb.hs, "stage_label", lambda p, s: "Stopped")
    lb.run_sweep(force=True)
    assert h.stage_updates == [("T1", "4")]
    assert h.stamps[-1][1] == {"retention_stage": "not_renewing", "retention_lost_reason": "stopped"}


def test_private_pay_case_renews_on_any_new_deal(monkeypatch):
    case = _case(charter=False, sms_body="", tor_body="")
    new_deal = {"id": "778", "properties": {"dealname": "Jessica Lujan - Taylor", "po_number": "",
                                            "createdate": "2026-09-10T00:00:00Z"}}
    h = Harness(monkeypatch, _cfg(armed=True), deals=[new_deal], open_cases={case["message_id"]: case})
    lb.run_sweep(force=True)
    assert h.stage() == ["renewed"] and not h.sms


def test_day7_turns_the_ticket_into_a_retention_risk_once(monkeypatch):
    case = _case(day1_done=True, opened_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)).isoformat())
    h = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    patch = next(p for m, path, p in h.patches if "/tickets/T1" in path)
    assert patch["properties"]["subject"].startswith("RETENTION RISK: Taylor Rodriguez (iLead)")
    assert patch["properties"]["hs_ticket_priority"] == "HIGH"
    assert h.stage() == ["retention_risk"]
    assert {u for u, _ in h.dms} == {"UPAO", "UROM"} and "RETENTION RISK" in h.dms[0][1]
    assert any(r["action_taken"] == "low_balance_escalated" for r in h.recs)
    h2 = Harness(monkeypatch, _cfg(armed=True), deals=[], open_cases={case["message_id"]: {**case, "escalated": True}})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert not h2.dms and not h2.patches


def test_day28_closes_lost_and_queues_reengagement(monkeypatch):
    case = _case(day1_done=True, escalated=True,
                 opened_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=29)).isoformat())
    h = Harness(monkeypatch, _cfg(armed=True, reengagement_list_id="3300"), deals=[],
                open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert h.stage_updates == [("T1", "4")]
    assert h.stamps[-1][1] == {"retention_stage": "lost", "retention_lost_reason": "no_response"}
    assert any(m == "PUT" and "/lists/3300/memberships/add" in p and b == ["3167401"] for m, p, b in h.patches)
    assert any(r["action_taken"] == "low_balance_resolved" and "Lost" in r["reason"] for r in h.recs)


def test_sweep_self_gates_to_the_top_of_the_hour(monkeypatch):
    h = Harness(monkeypatch, _cfg(), deals=[], open_cases={"k": _case()})
    monkeypatch.setattr(lb, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 40))
    lb.run_sweep()
    assert not h.recs and not h.dms


def test_open_cases_folds_state_from_the_audit_log(monkeypatch):
    recs = [
        {"message_id": "low-balance:26/27:a:b", "action_taken": "low_balance_opened", "student": "A B"},
        {"message_id": "low-balance:26/27:a:b:day1", "action_taken": "low_balance_family_contacted",
         "tor_draft_id": "d9", "tor_mailbox": "paola@x", "timestamp": "2026-09-10T15:00:00+00:00"},
        {"message_id": "low-balance:26/27:c:d", "action_taken": "low_balance_opened", "student": "C D"},
        {"message_id": "low-balance:26/27:c:d:resolved", "action_taken": "low_balance_resolved"},
        {"message_id": "low-balance:26/27:a:b:escalated", "action_taken": "low_balance_escalated"},
        {"message_id": "low-balance:26/27:e:f", "action_taken": "low_balance_opened", "student": "E F"},
        {"message_id": "low-balance:26/27:e:f:replied", "action_taken": "low_balance_family_replied"},
    ]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    cases = lb.open_cases()
    assert set(cases) == {"low-balance:26/27:a:b", "low-balance:26/27:e:f"}
    ab = cases["low-balance:26/27:a:b"]
    assert ab["day1_done"] and ab["tor_draft_id"] == "d9" and ab["escalated"] and ab["day1_at"]
    assert cases["low-balance:26/27:e:f"]["replied"]


# ── copy ─────────────────────────────────────────────────────────────────

def test_personal_line_variants():
    a = lb.parse_alert(ALERT)
    assert lb._personal(a, NO_RECENT, "") == ("", "")
    assert lb._personal(a, RECENT, "") == (" Taylor has been working with Sarah.",) * 2
    sms, line = lb._personal(a, RECENT, "Lately Taylor loves fractions.")
    assert sms == " Taylor has been working with Sarah."
    assert line == " Taylor has been working with Sarah. Lately Taylor loves fractions."
    assert lb._personal(a, NO_RECENT, "Lately Taylor loves fractions.") == ("", " Lately Taylor loves fractions.")


class _FakeClaude:
    def __init__(self, text):
        self.text = text
        self.messages = self

    def create(self, **kw):
        import types
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=self.text)])


def test_positivity_is_validated_and_never_invented(monkeypatch):
    notes = ["Worked on fractions and word problems, Taylor is getting faster and more confident."]
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())                    # enabled: False in the test cfg
    assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude("Lately Taylor has been mastering fractions.")) == ""
    on = _cfg(positivity={"enabled": True, "model": "m", "max_tokens": 120, "notes_window_days": 30})
    monkeypatch.setattr(lb, "cfg", lambda: on)
    assert lb._positivity("Taylor", "Sarah", [], client=_FakeClaude("x")) == ""          # no notes, no sentence
    assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude(
        "Lately Taylor has been mastering fractions")) == "Lately Taylor has been mastering fractions."
    for bad in ("NONE", "Taylor scored 92 on the quiz.", "Great job Taylor!",
                "Taylor — a star.", " ".join(["word"] * 31)):
        assert lb._positivity("Taylor", "Sarah", notes, client=_FakeClaude(bad)) == ""


def test_tw_recent_reads_tutor_and_only_last_month_of_notes(monkeypatch):
    from src import teachworks_client as tw
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    monkeypatch.setattr(lb, "_today", lambda: dt.date(2026, 9, 9))
    monkeypatch.setattr(tw, "accounts", lambda: {"online": "tok"})
    monkeypatch.setattr(tw, "customers_for_family", lambda e, l, f, token=None: [{"id": 7}])

    def fake_get(endpoint, params=None, token=None):
        if endpoint == "students":
            return [{"id": 1, "first_name": "Taylor"}, {"id": 2, "first_name": "Sibling"}]
        assert params["student_id"] == 1 and params["from_date[gte]"] == "2026-08-22"
        return [
            {"from_date": "2026-09-01", "status": "Attended", "employee_name": "Torres, Sarah",
             "name": "Math Tutoring", "participants": [
                 {"student_name": "Taylor Rodriguez", "status": "Attended",
                  "notes": "Worked on fractions and word problems; Taylor is getting more confident."}]},
            {"from_date": "2026-08-25", "status": "Attended", "employee_name": "Torres, Sarah",
             "name": "Math Tutoring", "participants": [{"student_name": "Taylor Rodriguez", "status": "Attended"}]},
            {"from_date": "2026-07-30", "status": "Attended", "employee_name": "Torres, Sarah",
             "name": "Math Tutoring", "participants": [
                 {"student_name": "Taylor Rodriguez", "status": "Attended",
                  "notes": "STALE NOTE from July that must not be used for the sentence."}]},
            {"from_date": "2026-08-28", "status": "Cancelled", "employee_name": "Torres, Sarah"},
            {"from_date": "2099-01-01", "status": "Scheduled", "employee_name": "Torres, Sarah"},
        ]
    monkeypatch.setattr(tw, "tw_get", fake_get)
    r = lb._tw_recent(lb.parse_alert(ALERT), DEAL)
    assert r["ok"] and r["found"] and r["first_session"] == "2026-07-30"
    assert r["tutor_first"] == "Sarah" and r["sessions"] == 3 and r["since"] == "2026-08-22"
    assert r["subjects"] == ["Math Tutoring"] and r["notes_fields_seen"] == ["notes"]
    assert len(r["notes"]) == 1 and r["notes"][0].startswith("Worked on fractions")
    monkeypatch.setattr(tw, "tw_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503")))
    assert lb._tw_recent(lb.parse_alert(ALERT), DEAL)["sessions"] == 0


def test_templates_render_clean(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(lb, "cfg", lambda: _cfg())
    a = lb.parse_alert(ALERT)
    tpl = Path(__file__).resolve().parents[1] / "templates" / "low_balance_charter.html"
    out = lb._render(tpl.read_text(), lb._context(a, DEAL, CONTACT, SEAT))
    assert "{" not in out and "—" not in out
    assert ("Taylor's tutoring hours are running low, with <strong>4 hours or less</strong> left on the "
            "current PO. We would love to keep Taylor's progress going.") in out
    assert "iLead" not in out and "Kylee" not in out and "vendor" not in out and "referral" not in out
    out = lb._render(tpl.read_text(), lb._context(a, DEAL, CONTACT, SEAT, RECENT,
                                                  "Lately Taylor has been building confidence with fractions."))
    assert ("current PO. Taylor has been working with Sarah. Lately Taylor has been building confidence "
            "with fractions. We would love to keep that progress going.") in out
    assert "has had" not in out and "August" not in out                 # no duration, ever
    # private pay
    gold = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default"}}
    a2 = lb.parse_alert(ALERT.replace("Charter - iLEAD", "2026 - Prep Package"))
    pctx = lb._private_ctx(a2, gold, lb._context(a2, gold, CONTACT, SEAT, RECENT), _cfg()["low_balance"])
    tpl2 = Path(__file__).resolve().parents[1] / "templates" / "low_balance_private.html"
    out2 = lb._render(tpl2.read_text(), pctx)
    assert "{" not in out2 and "—" not in out2
    assert "Taylor's current tutoring package is almost used up. Taylor has been working with Sarah." in out2
    assert "Prep package at $83 an hour. Moving to Success (50 hours) brings that to $73 an hour" in out2
    assert "renews on its own" in out2 and "Rodriguez" not in out2
