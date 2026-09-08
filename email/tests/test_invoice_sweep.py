"""Smart invoice prompt: hours-exhausted or due-date → one DM to Kath per deal."""
from src import deal_sync as dsy, invoice_sweep as isw


def test_dealname_month_end():
    assert isw._dealname_month_end("Nikita Brixey - Londyn - Heartland 1 (Aug) 26/27") \
        .strftime("%Y-%m-%d") == "2026-08-31"
    assert isw._dealname_month_end("X - Y (Feb) 26/27").strftime("%Y-%m-%d") == "2027-02-28"
    assert isw._dealname_month_end("Ana Tzubery - Maksim - iLead") is None


def _cfg():
    return {"deal_sync": {"enabled": True, "charter_pipelines": ["907748"],
                          "invoice_sweep": {"enabled": True, "hour_pt": 9, "owner": "kath"}},
            "po_inbox": {"invoice_task": {}},
            "deal_automation": {"active_stage_patterns": ["pre-lesson"]},
            "notify": {},
            "staff": {"kath": {"name": "Kath", "slack_user_id": "UKATH"}}}


def _deal(did="D1", name="Lara Perkins - Nomi (Jan) 25/26", hours="10"):
    return {"id": did, "properties": {"dealname": name, "pipeline": "907748",
                                      "dealstage": "S1", "createdate": "2026-01-05T00:00:00Z",
                                      "po_number": "77", "amount": "1500",
                                      "number_of_hours_in_this_po": hours}}


def _wire(monkeypatch, deals, used, processed=False):
    dms = []
    monkeypatch.setattr(isw, "cfg", _cfg)
    # role-aware resolver reads the real config; route it through the fake too
    monkeypatch.setattr(isw, "staff",
                        lambda k: _cfg().get("staff", {}).get(
                            k, _cfg().get("staff", {}).get(
                                (_cfg().get("roles") or {}).get(k, ""), {})))
    monkeypatch.setattr(isw.audit, "already_processed", lambda k: processed)
    monkeypatch.setattr(isw.audit, "append", lambda r: None)
    monkeypatch.setattr(isw, "_find_po_deals", lambda p, d: deals)
    monkeypatch.setattr(isw, "_hours_used", lambda e, s, since, t: used)
    monkeypatch.setattr(isw.hs, "stage_label", lambda p, s: "Pre-Lesson")
    monkeypatch.setattr(isw.tw, "accounts", lambda: {"online": "tok"})
    monkeypatch.setattr(dsy, "_deal_contact",
                        lambda d, n="": {"properties": {"email": "mom@x.com"}})
    monkeypatch.setattr(isw.slack_client, "dm", lambda u, t: dms.append((u, t)))
    return dms


def test_hours_exhausted_prompts_now(monkeypatch):
    # future due date, but the 10 PO hours are used → prompt immediately
    dms = _wire(monkeypatch, [_deal(name="Lara Perkins - Nomi (Aug) 99/00")], used=10.5)
    isw.run_sweep(force=True)
    assert dms and "PO hours used up (10.5 of 10)" in dms[0][1] and dms[0][0] == "UKATH"


def test_due_date_reached_prompts(monkeypatch):
    dms = _wire(monkeypatch, [_deal()], used=3.0)  # (Jan) 25/26 → 2026-01-31, long past
    isw.run_sweep(force=True)
    assert dms and "invoice due date reached (Jan 31)" in dms[0][1]


def test_neither_condition_no_prompt(monkeypatch):
    dms = _wire(monkeypatch, [_deal(name="Lara Perkins - Nomi (Aug) 99/00")], used=3.0)
    isw.run_sweep(force=True)
    assert dms == []


def test_prompts_only_once(monkeypatch):
    dms = _wire(monkeypatch, [_deal()], used=99.0, processed=True)
    isw.run_sweep(force=True)
    assert dms == []


def test_tw_family_missing_falls_back_to_date(monkeypatch):
    # student not in TW yet (pilot) → hours unknown → date logic still works
    dms = _wire(monkeypatch, [_deal()], used=None)
    isw.run_sweep(force=True)
    assert dms and "due date reached" in dms[0][1]


def test_daily_gate(monkeypatch):
    monkeypatch.setattr(isw, "cfg", _cfg)
    monkeypatch.setattr(isw, "_find_po_deals",
                        lambda p, d: (_ for _ in ()).throw(AssertionError("gated")))
    class _T:
        hour = 3
        minute = 0
    monkeypatch.setattr(isw, "now_la", lambda: _T())
    isw.run_sweep()  # 3 AM PT ≠ hour_pt 9 → returns before searching


# ── overdue-submission nag ───────────────────────────────────────────────────
from datetime import datetime  # noqa: E402

from src.business_hours import LA  # noqa: E402


def _nag_cfg(**over):
    c = _cfg()
    c["deal_sync"]["invoice_sweep"].update({"invoice_due_property": "lessons_fulfilled_date",
                                            "overdue_grace_days": 1, "escalate_after_days": 3,
                                            "escalate_to": "roman"})
    c["deal_sync"]["invoice_sweep"].update(over)
    c["staff"]["roman"] = {"name": "Roman", "slack_user_id": "UROMAN"}
    c["notify"] = {"cc_owner_dms_to": "roman"}
    return c


def _inv_deal(did, name, due, inv="54421", submitted="", amount="300"):
    return {"id": did, "properties": {"dealname": name, "pipeline": "907748", "dealstage": "S1",
                                      "createdate": "2026-08-13T16:48:09Z", "po_number": "PF236244",
                                      "amount": amount, "invoice__": inv,
                                      "invoice_submitted_date": submitted,
                                      "lessons_fulfilled_date": due}}


def _wire_nag(monkeypatch, deals, today="2026-09-08", processed=False, **over):
    dms, audits = [], []
    cfgf = lambda: _nag_cfg(**over)  # noqa: E731
    monkeypatch.setattr(isw, "cfg", cfgf)
    monkeypatch.setattr(isw, "staff", lambda k: cfgf()["staff"].get(k, {}))
    monkeypatch.setattr(isw.audit, "already_processed", lambda k: processed)
    monkeypatch.setattr(isw.audit, "append", lambda r: audits.append(r))
    monkeypatch.setattr(isw.hs, "stage_label", lambda p, s: "Post-Lesson")
    monkeypatch.setattr(isw.slack_client, "dm", lambda u, t: dms.append((u, t)))
    now = datetime.fromisoformat(today + "T09:05:00").replace(tzinfo=LA)
    monkeypatch.setattr(isw, "now_la", lambda: now)
    return dms, audits, now


def test_overdue_nag_lists_every_late_invoice_daily(monkeypatch):
    deals = [_inv_deal("D1", "Angela Czaja - Charlotte Czaja - Heartland 1 - 26/27", "2026-08-14"),
             _inv_deal("D2", "Fresh - Kid - iLead 1 - 26/27", "2026-09-30"),           # not due yet
             _inv_deal("D3", "Done - Kid - iLead 2 - 26/27", "2026-08-31", submitted="2026-09-01")]
    dms, audits, now = _wire_nag(monkeypatch, deals)
    cfgv = isw.cfg()["deal_sync"]["invoice_sweep"]
    assert isw.run_overdue_nag(deals, now, cfgv, ["post-lesson"]) == 1
    kath = [t for u, t in dms if u == "UKATH"]
    assert len(kath) == 1 and "Charlotte Czaja" in kath[0] and "25 days late" in kath[0] \
        and "$300.00" in kath[0] and "Fresh" not in kath[0] and "Done" not in kath[0]
    # 25 days late ≥ 3 → escalation to Roman, and no separate CC copy
    roman = [t for u, t in dms if u == "UROMAN"]
    assert len(roman) == 1 and roman[0].startswith("🚩 ESCALATION") and "25 days overdue" in roman[0]
    assert audits[-1]["action_taken"] == "submission_nag" and audits[-1]["escalated"] is True \
        and audits[-1]["message_id"] == "submission-nag:2026-09-08"


def test_overdue_nag_under_escalation_threshold_copies_not_escalates(monkeypatch):
    deals = [_inv_deal("D1", "A - B - iLead 1 - 26/27", "2026-09-05")]   # 3 days → grace ok, 2 < 3? no: 3 days
    dms, audits, now = _wire_nag(monkeypatch, deals, escalate_after_days=5)
    isw.run_overdue_nag(deals, now, isw.cfg()["deal_sync"]["invoice_sweep"], ["post-lesson"])
    assert [u for u, _ in dms] == ["UKATH", "UROMAN"]
    assert dms[1][1].startswith("📋 [copy → Kath]") and audits[-1]["escalated"] is False


def test_overdue_nag_respects_grace_weekend_and_daily_dedupe(monkeypatch):
    deals = [_inv_deal("D1", "A - B - iLead 1 - 26/27", "2026-09-08")]     # due today → 0 days late
    dms, _, now = _wire_nag(monkeypatch, deals)
    assert isw.run_overdue_nag(deals, now, isw.cfg()["deal_sync"]["invoice_sweep"], ["post-lesson"]) == 0
    late = [_inv_deal("D1", "A - B - iLead 1 - 26/27", "2026-08-14")]
    dms, _, sat = _wire_nag(monkeypatch, late, today="2026-09-05")          # Saturday
    assert isw.run_overdue_nag(late, sat, isw.cfg()["deal_sync"]["invoice_sweep"], ["post-lesson"]) == 0
    dms, _, now = _wire_nag(monkeypatch, late, processed=True)               # already nagged today
    assert isw.run_overdue_nag(late, now, isw.cfg()["deal_sync"]["invoice_sweep"], ["post-lesson"]) == 0
    assert dms == []


def test_find_po_deals_pages_and_filters_unsubmitted(monkeypatch):
    calls = []

    def fake_write(method, path, body):
        calls.append(body)
        if body.get("after"):
            return {"results": [{"id": "old"}]}
        return {"results": [{"id": "new"}], "paging": {"next": {"after": "p2"}}}
    monkeypatch.setattr(isw, "cfg", _cfg)
    monkeypatch.setattr(isw.hs, "_write", fake_write)
    out = isw._find_po_deals(["907748"], "lessons_fulfilled_date")
    assert [d["id"] for d in out] == ["new", "old"]                     # both pages
    f = calls[0]["filterGroups"][0]["filters"]
    assert {"propertyName": "invoice_submitted_date", "operator": "NOT_HAS_PROPERTY"} in f
    assert calls[0]["limit"] == 200 and "invoice__" in calls[0]["properties"]
