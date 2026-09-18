"""Case engine: owner rules, stages, idempotent open, moves and closes."""
from src import case_engine as ce

STAFF = {"paola": {"name": "Paola", "hubspot_owner_id": "81494333", "slack_user_id": "UPAO"},
         "janelle": {"name": "Janelle", "hubspot_owner_id": "80047202", "slack_user_id": "UJA"},
         "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539", "slack_user_id": "UYO"},
         "mandy": {"name": "Mandy", "hubspot_owner_id": "80047201", "slack_user_id": "UMA"},
         "kath": {"name": "Kath", "hubspot_owner_id": "513215050", "slack_user_id": "UKA"}}
ROLES = {"charter_sales": "paola", "scheduler_a_l": "janelle", "scheduler_m_z": "yolanda",
         "operations": "mandy", "charter_admin": "kath"}
CFG = {"staff": STAFF, "roles": ROLES,
       "case_engine": {
           "pipelines": {"renewals": {"id": "935649887",
                                      "stages": {"waiting_on_family": "R1", "needs_scheduler": "R2", "needs_invoice": "R3",
                                                 "renewed": "R4", "not_renewing": "R5", "no_response": "R6"},
                                      "closed": ["renewed", "not_renewing", "no_response"]},
                         "support": {"id": "0", "stages": {"new": "1378066770", "waiting_on_us": "131537027", "resolved": "4",
                                                          "wont_fix": "W"}, "closed": ["resolved", "wont_fix"]},
                         "tutor": {"id": "935648438", "stages": {"new": "T1", "debrief": "T2", "resolved": "T5"}, "closed": ["resolved"]}},
           "owner_rules": {"renewals": {"trial": "charter_sales", "hsa_pipelines": ["5119061"],
                                        "hsa_parity": {"odd": "scheduler_a_l", "even": "scheduler_m_z"},
                                        "split": {"a_l": "scheduler_a_l", "m_z": "scheduler_m_z"}},
                           "support": {"po_watch": "charter_admin", "billing": "charter_admin", "scheduling": "split",
                                       "default": "operations"},
                           "tutor": "operations"},
           "service_levels": {"renewals": {"waiting_on_family": 3, "needs_scheduler": 1}}}}


def _wire(monkeypatch, search_hits=None):
    calls = {"write": [], "notes": [], "dms": [], "audit": []}
    monkeypatch.setattr(ce, "cfg", lambda: CFG)
    monkeypatch.setattr(ce, "staff", lambda k: STAFF.get(ROLES.get(k, k), {}))
    monkeypatch.setattr(ce, "DRY_RUN", False)

    def fake_write(method, path, payload=None):
        calls["write"].append((method, path, payload))
        if path.endswith("/tickets/search"):
            return {"results": list(search_hits or []), "total": len(search_hits or [])}
        if method == "POST" and path.endswith("/objects/tickets"):
            return {"id": "NEW1", "properties": (payload or {}).get("properties", {})}
        return {"id": "X"}
    monkeypatch.setattr(ce.hs, "_write", fake_write)
    monkeypatch.setattr(ce.hs, "add_ticket_note", lambda t, b: calls["notes"].append((t, b)))
    monkeypatch.setattr(ce.hs, "ticket_url", lambda t: f"https://hs/t/{t}")
    monkeypatch.setattr(ce.slack_client, "dm", lambda u, t: calls["dms"].append((u, t)) or {"ok": True})
    monkeypatch.setattr(ce.audit, "append", lambda r: calls["audit"].append(r))
    return calls


def test_owner_rules_for_renewals(monkeypatch):
    _wire(monkeypatch)
    assert ce.owner_for_renewals("charter", "Lujan")[0] == "scheduler_a_l"
    assert ce.owner_for_renewals("private_pay", "Seeley")[0] == "scheduler_m_z"
    assert ce.owner_for_renewals("charter", "")[0] == "scheduler_a_l" and "CHECK" in ce.owner_for_renewals("charter", "")[1]
    assert ce.owner_for_renewals("trial", "Zimmerman")[0] == "charter_sales"       # the only override
    # IEM HSA: group parity from the deal, odd A-L, even M-Z, whatever the surname
    assert ce.owner_for_renewals("charter", "Aguilar", {"pipeline": "5119061", "hsa_group": "C1-G4"})[0] == "scheduler_m_z"
    assert ce.owner_for_renewals("charter", "Zimmerman", {"pipeline": "5119061", "hsa_group": "C2-G3"})[0] == "scheduler_a_l"
    assert ce.owner_for_renewals("charter", "Zimmerman", {"pipeline": "5119061"})[0] == "scheduler_m_z"   # no group: split


def test_owner_rules_for_support_and_tutor(monkeypatch):
    _wire(monkeypatch)
    assert ce.owner_for_support("po_watch")[0] == "charter_admin"
    assert ce.owner_for_support("scheduling", "Motiwalla")[0] == "scheduler_m_z"
    assert ce.owner_for_support("cancellation")[0] == "operations"
    assert ce.owner_for_tutor()[0] == "operations"


def test_stages_and_closed_sets(monkeypatch):
    _wire(monkeypatch)
    assert ce.stage_id("renewals", "needs_invoice") == "R3"
    assert ce.closed_stage_ids("renewals") == {"R4", "R5", "R6"}
    assert ce.is_closed_stage("4") and ce.is_closed_stage("W") and not ce.is_closed_stage("R1")


def test_open_case_creates_once_and_returns_the_open_one_after(monkeypatch):
    calls = _wire(monkeypatch)
    t = ce.open_case("low_balance", "low-balance:26/27:zie-rojas:charter-ilead", "renewals", "waiting_on_family",
                     "Low balance: Zie Rojas (iLead), 4 hours left", "desc", "scheduler_m_z",
                     contact_ids=["C1"], deal_id="D1", props={"funding_type": "charter"}, priority="MEDIUM")
    assert t["id"] == "NEW1"
    post = next(p for m, path, p in calls["write"] if m == "POST" and path.endswith("/objects/tickets"))
    props = post["properties"]
    assert props["hs_pipeline"] == "935649887" and props["hs_pipeline_stage"] == "R1"
    assert props["hubspot_owner_id"] == "86868539" and props["funding_type"] == "charter"
    assert props["case_key"].startswith("low-balance:") and props["case_client"] == "low_balance"
    assert props["sla_due_at"] > 0                                 # waiting_on_family has a 3-day clock
    assert {a["to"]["id"] for a in post["associations"]} == {"C1", "D1"}
    assert calls["audit"][0]["action_taken"] == "case_opened"
    # same key again: the open ticket comes back, no second POST
    calls2 = _wire(monkeypatch, search_hits=[{"id": "NEW1", "properties": {"hs_pipeline_stage": "R1"}}])
    t2 = ce.open_case("low_balance", "low-balance:26/27:zie-rojas:charter-ilead", "renewals", "waiting_on_family",
                      "x", "y", "scheduler_m_z")
    assert t2["id"] == "NEW1" and not any(m == "POST" and p.endswith("/objects/tickets") for m, p, _b in calls2["write"])
    assert calls2["notes"] and "repeat trigger" in calls2["notes"][0][1]
    # a CLOSED ticket with the key does not count as open
    calls3 = _wire(monkeypatch, search_hits=[{"id": "OLD", "properties": {"hs_pipeline_stage": "R4"}}])
    t3 = ce.open_case("low_balance", "k", "renewals", "waiting_on_family", "x", "y", "scheduler_a_l")
    assert t3["id"] == "NEW1"


def test_move_close_and_risk(monkeypatch):
    calls = _wire(monkeypatch)
    ce.move("T9", "renewals", "needs_scheduler", note="family replied")
    m, path, p = calls["write"][-1]
    assert path.endswith("/tickets/T9") and p["properties"]["hs_pipeline_stage"] == "R2" and p["properties"]["sla_due_at"]
    assert calls["notes"][-1] == ("T9", "family replied")
    ce.close("T9", "renewals", "renewed", "PO in")
    assert calls["write"][-1][2]["properties"]["hs_pipeline_stage"] == "R4"
    try:
        ce.close("T9", "renewals", "needs_scheduler")
        assert False, "needs_scheduler is not an outcome"
    except ValueError:
        pass
    ce.mark_risk("T9", "day 7, 0.5 h left")
    assert calls["write"][-1][2]["properties"] == {"hs_ticket_priority": "HIGH", "retention_risk": "true"}
    ce.dm_role("scheduler_a_l", "hi")
    assert calls["dms"] == [("UJA", "hi")]
