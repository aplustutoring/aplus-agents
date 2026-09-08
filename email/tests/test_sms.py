"""Agent-owned SMS sweep — family grouping, template variants, fences.
Copy + rules locked by Roman 2026-09-01: name the kid, 'their', brand voice,
pending-approval OAs text normally, unset-tutored gets the ASK variant."""
import pytest

from src import deal_sync as dsy, sms


BASE_CFG = {
    "sms": {"enabled": True, "justcall_number": "+18188691627",
            "start_date": "2026-08-29", "send_hour_start_pt": 0,
            "send_hour_end_pt": 24, "fallback_alert": "kath",
            "pipelines": {"907748": {"template": "charter_po"}},
            "templates": {
                "charter_po_confirm":
                    "Hi {first_name}! Confirm {student}'s schedule: {schedule}.",
                "charter_po_ask":
                    "Hi {first_name}! What times work for {student}'s sessions?",
                "charter_po_multi_confirm":
                    "Hi {first_name}! Confirm schedules for {students}.",
                "charter_po_multi_ask":
                    "Hi {first_name}! What times work for {students}?"}},
    "po_inbox": {"schedule_ask_fallback": "no schedule on file, please reply"},
    "staff": {"kath": {"name": "Kath", "hubspot_owner_id": "513215050",
                       "slack_user_id": "UKATH"},
              "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539",
                          "slack_user_id": "UYO"}},
}


def _deal(did, tutored="Yes", sched="Tuesdays 2 pm", owner="86868539",
          student="Ana"):
    return {"id": did, "properties": {
        "dealname": f"Parent Perez - {student} Diaz - iLead {did}", "pipeline": "907748",
        "dealstage": "907749", "createdate": "2026-08-29T12:00:00Z",
        "schedule_preferences": sched, "hubspot_owner_id": owner,
        "student_first_name": student,
        "is_the_family_currently_being_tutored_by_us_": tutored}}


@pytest.fixture
def wired(monkeypatch):
    recorded, sent, dms = [], [], []
    deals = []
    monkeypatch.setattr(sms, "cfg", lambda: BASE_CFG)
    monkeypatch.setattr(sms, "staff", lambda k: BASE_CFG["staff"].get(k, {}))
    monkeypatch.setattr(sms.audit, "append", lambda r: recorded.append(r))
    monkeypatch.setattr(sms.audit, "_iter_records", lambda: iter(list(recorded)))
    monkeypatch.setattr(sms, "_jc_send", lambda to, body: sent.append((to, body)) or {})
    monkeypatch.setattr(sms.slack_client, "dm", lambda u, t: dms.append((u, t)) or {"ok": True})
    monkeypatch.setattr(sms.hs, "stage_label", lambda p, s: "Pre-Lesson")
    monkeypatch.setattr(sms.hs, "_write", lambda m, p, b=None: {"results": deals})
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria", "phone": "+15551234567"}})
    monkeypatch.setattr(dsy, "_deal_contact", lambda did, name="": {"id": "C1"})
    return {"recorded": recorded, "sent": sent, "dms": dms, "deals": deals}


def test_schedule_known_sends_confirm_with_student_name(wired):
    wired["deals"].append(_deal("D1"))
    sms.run_sweep()
    assert wired["sent"] == [("+15551234567",
                              "Hi Maria! Confirm Ana's schedule: Tuesdays 2 pm.")]


def test_no_schedule_sends_ask_variant(wired):
    # the old flow pasted the ask-fallback INTO the confirm sentence — the ask
    # template replaces that incoherence
    wired["deals"].append(_deal("D2", sched=""))
    sms.run_sweep()
    assert wired["sent"] == [("+15551234567",
                              "Hi Maria! What times work for Ana's sessions?")]


def test_ask_fallback_string_is_not_a_schedule(wired):
    wired["deals"].append(_deal("D3", sched="no schedule on file, please reply"))
    sms.run_sweep()
    assert "What times work" in wired["sent"][0][1]


def test_tutored_unset_still_texts(wired):
    # Roman 2026-09-01: unverifiable tutoring must not silence the family —
    # asking for a schedule needs no verification (the Villa case)
    wired["deals"].append(_deal("D4", tutored="", sched=""))
    sms.run_sweep()
    assert len(wired["sent"]) == 1
    assert "What times work" in wired["sent"][0][1]


def test_tutored_no_alerts_owner_then_sends_next_cycle(wired):
    wired["deals"].append(_deal("D5", tutored="No"))
    sms.run_sweep()
    assert wired["sent"] == []                       # cycle 1: owner heads-up only
    assert wired["dms"] and wired["dms"][0][0] == "UYO"
    assert "Ana" in wired["dms"][0][1]               # the alert names the kid too
    sms.run_sweep()
    assert len(wired["sent"]) == 1                   # cycle 2: family texts
    sms.run_sweep()
    assert len(wired["sent"]) == 1                   # never again for this deal


def test_siblings_collapse_to_one_multi_text(wired):
    # a 2-kid PO day (the Canales case) = ONE text naming both kids
    wired["deals"] += [_deal("D6", student="Ana"), _deal("D7", student="Bo"),
                       _deal("D8", student="Bo")]
    sms.run_sweep()
    assert len(wired["sent"]) == 1
    assert wired["sent"][0][1] == "Hi Maria! Confirm schedules for Ana and Bo."
    sent_markers = [r for r in wired["recorded"] if r["action_taken"] == "sms_sent"]
    assert {r["deal_id"] for r in sent_markers} == {"D6", "D7", "D8"}


def test_family_24h_dedupe_across_cycles(wired):
    wired["deals"].append(_deal("D9"))
    sms.run_sweep()
    wired["deals"].append(_deal("D10", student="Cy"))   # new PO, same family, same day
    sms.run_sweep()
    assert len(wired["sent"]) == 1                      # second kid rides the 24h window
    assert any(r.get("deduped_with_recent_family_text") for r in wired["recorded"])


def test_missing_start_date_disables_sweep(wired, monkeypatch):
    bad = {**BASE_CFG, "sms": {**BASE_CFG["sms"]}}
    bad["sms"].pop("start_date")
    monkeypatch.setattr(sms, "cfg", lambda: bad)
    wired["deals"].append(_deal("D11"))
    sms.run_sweep()
    assert wired["sent"] == []


def test_quiet_hours_defers(wired, monkeypatch):
    quiet = {**BASE_CFG, "sms": {**BASE_CFG["sms"],
                                 "send_hour_start_pt": 0, "send_hour_end_pt": 0}}
    monkeypatch.setattr(sms, "cfg", lambda: quiet)
    wired["deals"].append(_deal("D12"))
    sms.run_sweep()
    assert wired["sent"] == [] and wired["recorded"] == []   # deferred, not skipped


def test_no_phone_skips_audited(wired, monkeypatch):
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria"}})
    wired["deals"].append(_deal("D13"))
    sms.run_sweep()
    assert wired["sent"] == []
    assert any(r.get("reason") == "no family phone" for r in wired["recorded"])


def test_send_failure_three_strikes_flags_staff(wired, monkeypatch):
    def boom(to, body):
        raise RuntimeError("jc down")
    monkeypatch.setattr(sms, "_jc_send", boom)
    wired["deals"].append(_deal("D14"))
    sms.run_sweep()
    sms.run_sweep()
    sms.run_sweep()
    sms.run_sweep()                                   # 4th cycle: capped, no retry
    errs = [r for r in wired["recorded"] if r["action_taken"] == "sms_error"]
    assert len(errs) == 3
    assert any("manually" in t for _, t in wired["dms"])


def test_em_dash_scrubbed_from_body(wired, monkeypatch):
    dashed = {**BASE_CFG, "sms": {**BASE_CFG["sms"], "templates":
              {**BASE_CFG["sms"]["templates"],
               "charter_po_confirm": "Hi {first_name} — confirm: {schedule}"}}}
    monkeypatch.setattr(sms, "cfg", lambda: dashed)
    wired["deals"].append(_deal("D15"))
    sms.run_sweep()
    assert "—" not in wired["sent"][0][1]


# ── What-to-Expect welcome email rides the text (Roman 2026-09-03, Option A) ──

def _welcome_cfg():
    cfg = {**BASE_CFG, "sms": {**BASE_CFG["sms"],
           "pipelines": {"907748": {"template": "charter_po", "welcome": True}},
           "welcome": {"template": "templates/welcome_charter.html"}}}
    return cfg


def test_welcome_email_sent_with_the_text(wired, monkeypatch):
    monkeypatch.setattr(sms, "cfg", lambda: _welcome_cfg())
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria", "phone": "+15551234567",
                                   "email": "maria@x.com"}})
    emails = []
    monkeypatch.setattr(sms, "_send_welcome",
                        lambda to, first, pconf=None: emails.append((to, first, pconf)))
    wired["deals"].append(_deal("D20"))
    sms.run_sweep()
    assert len(wired["sent"]) == 1
    assert emails and emails[0][:2] == ("maria@x.com", "Maria")
    assert any(r.get("welcome_email_to") == "maria@x.com" for r in wired["recorded"])


def test_welcome_failure_never_voids_the_text(wired, monkeypatch):
    monkeypatch.setattr(sms, "cfg", lambda: _welcome_cfg())
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria", "phone": "+15551234567",
                                   "email": "maria@x.com"}})
    def boom(to, first, pconf=None):
        raise RuntimeError("resend down")
    monkeypatch.setattr(sms, "_send_welcome", boom)
    wired["deals"].append(_deal("D21"))
    sms.run_sweep()
    assert len(wired["sent"]) == 1                     # text still delivered + audited
    assert any(r["action_taken"] == "sms_sent" for r in wired["recorded"])
    assert any(r["action_taken"] == "welcome_email_error" for r in wired["recorded"])
    assert any("forward the welcome" in t for _, t in wired["dms"])
    sms.run_sweep()
    assert len(wired["sent"]) == 1                     # and never re-texts over it


def test_no_welcome_id_means_text_only(wired, monkeypatch):
    emails = []
    monkeypatch.setattr(sms, "_send_welcome",
                        lambda to, first, pconf=None: emails.append((to, first, pconf)))
    wired["deals"].append(_deal("D22"))
    sms.run_sweep()
    assert len(wired["sent"]) == 1 and emails == []


def test_pipeline_welcome_override_reaches_send(wired, monkeypatch):
    # gold/trial carry their own template+subject; the pipeline conf must
    # arrive at _send_welcome intact
    cfgv = {**BASE_CFG, "sms": {**BASE_CFG["sms"],
            "pipelines": {"907748": {"template": "charter_po", "welcome": True,
                                     "welcome_template": "templates/welcome_trial.html",
                                     "welcome_subject": "Trial subject"}},
            "welcome": {"template": "templates/welcome_charter.html"}}}
    monkeypatch.setattr(sms, "cfg", lambda: cfgv)
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria", "phone": "+15551234567",
                                   "email": "maria@x.com"}})
    got = []
    monkeypatch.setattr(sms, "_send_welcome",
                        lambda to, first, pconf=None: got.append(pconf))
    wired["deals"].append(_deal("D23"))
    sms.run_sweep()
    assert got and got[0]["welcome_template"] == "templates/welcome_trial.html"


def test_gold_trial_templates_render_clean():
    from src.config import ROOT
    for name in ("welcome_gold_inperson.html", "welcome_trial.html"):
        tpl = (ROOT / "templates" / name).read_text()
        assert tpl.count("__FIRST_NAME__") == 1, name
        assert "—" not in tpl, name
        assert "my direct #" not in tpl, name


def test_welcome_template_renders_clean():
    # the real template: loads via ROOT, placeholder swaps, no em dashes
    from src.config import ROOT
    tpl = (ROOT / "templates/welcome_charter.html").read_text()
    assert tpl.count("__FIRST_NAME__") == 1
    assert "—" not in tpl                       # locked outbound rule
    assert "my direct #" not in tpl             # the old flow's stale timing line
    sms._send_welcome("test@x.com", "Ana")      # DRY_RUN: exercises load + render


def test_sender_liveness_digest_flags_quiet_flows(monkeypatch, tmp_path):
    from src import sender_liveness as sl
    monkeypatch.setattr(sl, "SNAP", tmp_path / "snap.json")
    monkeypatch.setattr(sl, "cfg", lambda: {"sender_liveness": {"channel": "CCH"}})
    monkeypatch.setattr(sl, "_sender_flows",
                        lambda: {"1": "Flow A", "2": "Flow B"})
    counts = {"Flow A": 10, "Flow B": 5}
    monkeypatch.setattr(sl, "_enrollment_totals", lambda: dict(counts))
    posts = []
    monkeypatch.setattr(sl.slack_client, "post_message",
                        lambda ch, t: posts.append((ch, t)))
    sl.run()                       # first run: snapshot only, no digest
    assert posts == []
    counts["Flow A"] = 14          # A moved, B stayed flat
    sl.run()
    assert len(posts) == 1
    assert "Flow B" in posts[0][1] and "Flow A" not in posts[0][1].split("ZERO")[1]
