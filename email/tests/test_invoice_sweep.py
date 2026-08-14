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
