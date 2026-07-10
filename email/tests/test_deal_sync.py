"""HubSpot→Teachworks deal sync: mapping, upsert, charter billing, pilot gate."""
from src import deal_sync as dsy


def _cfg(pilot=False):
    return {"deal_sync": {"enabled": True, "dry_run_first": pilot,
                          "in_person_pipelines": ["3067397"],
                          "charter_pipelines": ["907748"],
                          "exclude_pipelines": ["971802"],
                          "charter_student_billing": "Package",
                          "private_student_billing": "Service List Cost"}}


def _deal(pid="default", name="Lara Perkins - Nomi", did="D1"):
    return {"id": did, "properties": {"pipeline": pid, "dealname": name}}


def _wire(monkeypatch, existing=None, pilot=False):
    calls = {"created": [], "updated": [], "students": []}
    monkeypatch.setattr(dsy, "cfg", lambda: _cfg(pilot))
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(dsy.audit, "append", lambda r: None)
    monkeypatch.setattr(dsy, "_deal_contact", lambda d: {"properties": {
        "email": "mom@x.com", "firstname": "Lara", "lastname": "Perkins",
        "phone": "555", "city": "LA"}})
    monkeypatch.setattr(dsy.tw, "accounts", lambda: {"online": "tok1", "in_person": "tok2"})
    monkeypatch.setattr(dsy.tw, "find_customer_by_email", lambda e, t: existing)
    monkeypatch.setattr(dsy.tw, "create_family", lambda f, t: calls["created"].append((f, t)) or {"id": 99})
    monkeypatch.setattr(dsy.tw, "update_customer", lambda cid, f, t: calls["updated"].append((cid, f)))
    monkeypatch.setattr(dsy.tw, "tw_get", lambda ep, p=None, token=None: [])
    monkeypatch.setattr(dsy.tw, "create_student", lambda f, t: calls["students"].append(f))
    return calls


def test_field_mapping():
    f = dsy._tw_fields({"firstname": "A", "lastname": "B", "email": "E@X.com",
                        "mobilephone": "1", "zip": "90210"})
    assert f == {"first_name": "A", "last_name": "B", "email": "e@x.com",
                 "mobile_phone": "1", "zip": "90210"}


def test_student_from_dealname():
    assert dsy._student_first_from_dealname("Lara Perkins - Nomi") == "Nomi"
    assert dsy._student_first_from_dealname("iLEAD - Ana Diaz - PO 4471") == "Ana"
    assert dsy._student_first_from_dealname("Solo Name") == ""


def test_new_customer_created_with_student(monkeypatch):
    calls = _wire(monkeypatch, existing=None)
    rec = dsy.sync_deal(_deal())
    assert rec["tw_action"] == "created" and calls["created"]
    assert calls["students"][0]["first_name"] == "Nomi"
    assert calls["students"][0]["billing_method"] == "Service List Cost"
    assert rec["tw_account"] == "online"


def test_existing_customer_updated(monkeypatch):
    calls = _wire(monkeypatch, existing={"id": 42})
    rec = dsy.sync_deal(_deal())
    assert rec["tw_action"] == "updated" and calls["updated"][0][0] == 42
    assert not calls["created"]


def test_charter_deal_gets_package_billing_online_account(monkeypatch):
    calls = _wire(monkeypatch, existing=None)
    rec = dsy.sync_deal(_deal(pid="907748", name="iLEAD - Ana Diaz - PO 9"))
    assert rec["tw_account"] == "online" and rec["charter"] is True
    assert calls["students"][0]["billing_method"] == "Package"


def test_in_person_pipeline_uses_inperson_account(monkeypatch):
    _wire(monkeypatch, existing=None)
    rec = dsy.sync_deal(_deal(pid="3067397"))
    assert rec["tw_account"] == "in_person"


def test_excluded_pipeline_skipped(monkeypatch):
    _wire(monkeypatch)
    assert dsy.sync_deal(_deal(pid="971802")) is None


def test_pilot_mode_writes_nothing(monkeypatch):
    calls = _wire(monkeypatch, existing=None, pilot=True)
    rec = dsy.sync_deal(_deal())
    assert rec["action_taken"] == "sync_pilot_logged"
    assert not calls["created"] and not calls["students"]
