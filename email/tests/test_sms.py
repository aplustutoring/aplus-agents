"""Agent-owned SMS sweep (2026-08-28): branch semantics, fences, dedupe."""
import pytest

from src import deal_sync as dsy, sms


BASE_CFG = {
    "sms": {"enabled": True, "justcall_number": "+18188691627",
            "start_date": "2026-08-29", "send_hour_start_pt": 0,
            "send_hour_end_pt": 24, "fallback_alert": "kath",
            "pipelines": {"907748": {"template": "charter_po"}},
            "templates": {"charter_po":
                          "Hi {first_name}, schedule: {schedule_preferences}"}},
    "po_inbox": {"schedule_ask_fallback": "no schedule on file, please reply"},
    "staff": {"kath": {"name": "Kath", "hubspot_owner_id": "513215050",
                       "slack_user_id": "UKATH"},
              "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539",
                          "slack_user_id": "UYO"}},
}


def _deal(did, tutored="Yes", sched="Tuesdays 2 pm", owner="86868539"):
    return {"id": did, "properties": {
        "dealname": f"Parent - Kid - iLead {did}", "pipeline": "907748",
        "dealstage": "907749", "createdate": "2026-08-29T12:00:00Z",
        "schedule_preferences": sched, "hubspot_owner_id": owner,
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


def test_tutored_yes_sends_now(wired):
    wired["deals"].append(_deal("D1"))
    sms.run_sweep()
    assert wired["sent"] == [("+15551234567", "Hi Maria, schedule: Tuesdays 2 pm")]
    assert any(r["action_taken"] == "sms_sent" and r["deal_id"] == "D1"
               for r in wired["recorded"])


def test_tutored_no_alerts_then_sends_next_cycle(wired):
    wired["deals"].append(_deal("D2", tutored="No"))
    sms.run_sweep()
    assert wired["sent"] == []                       # cycle 1: alert only
    assert wired["dms"] and wired["dms"][0][0] == "UYO"   # the deal's owner
    sms.run_sweep()
    assert len(wired["sent"]) == 1                   # cycle 2: text goes
    sms.run_sweep()
    assert len(wired["sent"]) == 1                   # never again for this deal


def test_tutored_unset_skips_once(wired):
    wired["deals"].append(_deal("D3", tutored=""))
    sms.run_sweep()
    sms.run_sweep()
    assert wired["sent"] == []
    skips = [r for r in wired["recorded"] if r["action_taken"] == "sms_skipped_unverified"]
    assert len(skips) == 1


def test_family_deduped_across_sibling_deals(wired):
    # a 4-PO email creates 4 deals for ONE family → exactly one text
    wired["deals"] += [_deal("D4"), _deal("D5"), _deal("D6"), _deal("D7")]
    sms.run_sweep()
    assert len(wired["sent"]) == 1
    deduped = [r for r in wired["recorded"]
               if r.get("deduped_with_recent_family_text")]
    assert len(deduped) == 3


def test_blank_schedule_uses_ask_fallback(wired):
    wired["deals"].append(_deal("D8", sched=""))
    sms.run_sweep()
    assert "no schedule on file" in wired["sent"][0][1]


def test_missing_start_date_disables_sweep(wired, monkeypatch):
    bad = {**BASE_CFG, "sms": {**BASE_CFG["sms"]}}
    bad["sms"].pop("start_date")
    monkeypatch.setattr(sms, "cfg", lambda: bad)
    wired["deals"].append(_deal("D9"))
    sms.run_sweep()
    assert wired["sent"] == []


def test_quiet_hours_defers(wired, monkeypatch):
    quiet = {**BASE_CFG, "sms": {**BASE_CFG["sms"],
                                 "send_hour_start_pt": 0, "send_hour_end_pt": 0}}
    monkeypatch.setattr(sms, "cfg", lambda: quiet)
    wired["deals"].append(_deal("D10"))
    sms.run_sweep()
    assert wired["sent"] == [] and wired["recorded"] == []   # deferred, not skipped


def test_no_phone_skips(wired, monkeypatch):
    monkeypatch.setattr(sms.hs, "_get", lambda p, params=None: {
        "id": "C1", "properties": {"firstname": "Maria"}})
    wired["deals"].append(_deal("D11"))
    sms.run_sweep()
    assert wired["sent"] == []
    assert any(r.get("reason") == "no family phone" for r in wired["recorded"])


def test_send_failure_three_strikes_flags_staff(wired, monkeypatch):
    def boom(to, body):
        raise RuntimeError("jc down")
    monkeypatch.setattr(sms, "_jc_send", boom)
    wired["deals"].append(_deal("D12"))
    sms.run_sweep()
    sms.run_sweep()
    sms.run_sweep()
    sms.run_sweep()                                   # 4th cycle: capped, no retry
    errs = [r for r in wired["recorded"] if r["action_taken"] == "sms_error"]
    assert len(errs) == 3
    assert any("manually" in t for _, t in wired["dms"])


def test_em_dash_scrubbed_from_body(wired, monkeypatch):
    dashed = {**BASE_CFG, "sms": {**BASE_CFG["sms"], "templates":
              {"charter_po": "Hi {first_name} — schedule: {schedule_preferences}"}}}
    monkeypatch.setattr(sms, "cfg", lambda: dashed)
    wired["deals"].append(_deal("D13"))
    sms.run_sweep()
    assert "—" not in wired["sent"][0][1]
