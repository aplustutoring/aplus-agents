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


def _wire(monkeypatch, existing=None, pilot=False, contact=None):
    calls = {"created": [], "updated": [], "students": [], "slack": []}
    monkeypatch.setattr(dsy, "cfg", lambda: {**_cfg(pilot),
                                             "internal": {"domain": "wetutorathome.com"},
                                             "slack": {"digest_channel": "CTEST"}})
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(dsy.audit, "append", lambda r: None)
    monkeypatch.setattr(dsy, "_deal_contact", lambda d, n="": {"properties": contact or {
        "email": "mom@x.com", "firstname": "Lara", "lastname": "Perkins",
        "phone": "555", "city": "LA"}})
    monkeypatch.setattr(dsy.hs, "pipeline_label", lambda p: "")
    monkeypatch.setattr(dsy.tw, "accounts", lambda: {"online": "tok1", "in_person": "tok2"})
    monkeypatch.setattr(dsy.tw, "find_customer_by_email", lambda e, t: existing)
    monkeypatch.setattr(dsy.tw, "create_family", lambda f, t: calls["created"].append((f, t)) or {"id": 99})
    monkeypatch.setattr(dsy.tw, "update_customer", lambda cid, f, t: calls["updated"].append((cid, f)))
    monkeypatch.setattr(dsy.tw, "tw_get", lambda ep, p=None, token=None: [])
    monkeypatch.setattr(dsy.tw, "create_student", lambda f, t: calls["students"].append(f))
    monkeypatch.setattr(dsy.slack_client, "post_message", lambda ch, txt: calls["slack"].append((ch, txt)))
    return calls


def test_field_mapping():
    f = dsy._tw_fields({"firstname": "A", "lastname": "B", "email": "E@X.com",
                        "mobilephone": "1", "zip": "90210"})
    assert f == {"first_name": "A", "last_name": "B", "email": "e@x.com",
                 "mobile_phone": "1", "zip": "90210"}


def test_student_from_dealname():
    assert dsy._student_firsts_from_dealname("Lara Perkins - Nomi") == ["Nomi"]
    assert dsy._student_firsts_from_dealname("iLEAD - Ana Diaz - PO 4471") == ["Ana"]
    assert dsy._student_firsts_from_dealname("Solo Name") == []
    # observed in pilot logs 2026-07-27:
    assert dsy._student_firsts_from_dealname("Renewal - Christine Nakamura - Luke") == ["Luke"]
    assert dsy._student_firsts_from_dealname("Alexa Marcano- Kash and Kingston") == ["Kash", "Kingston"]
    assert dsy._student_firsts_from_dealname("Tasame Savathasuk- Daniel") == ["Daniel"]
    assert dsy._student_firsts_from_dealname("Ana Tzubery - Maksim - iLead  (Apr) 25/26") == ["Maksim"]
    assert dsy._student_firsts_from_dealname("Charter Private Pay — 6-Session Pack via Payment Link") == []
    assert dsy._student_firsts_from_dealname("Anna-Marie Smith-Jones - Kai") == ["Kai"]


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
    d = _deal(pid="907748", name="iLEAD - Ana Diaz - PO 9")
    d["properties"]["po_number"] = "9"   # PO-created → parent associated by po_inbox
    rec = dsy.sync_deal(d)
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


def test_pilot_logs_each_deal_once(monkeypatch):
    calls = _wire(monkeypatch, existing=None, pilot=True)
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: k == "pilot-deal:D1")
    assert dsy.sync_deal(_deal()) is None
    assert not calls["created"] and not calls["students"]


def test_deal_contact_prefers_dealname_parent(monkeypatch):
    # Deal carries TOR + parent: the family contact is the one matching the deal name.
    contacts = {"1": {"id": "1", "properties": {"firstname": "Terri", "lastname": "Tor",
                                                "email": "tor@school.org"}},
                "2": {"id": "2", "properties": {"firstname": "Lara", "lastname": "Perkins",
                                                "email": "mom@x.com"}}}
    def fake_get(path, params=None):
        if path.endswith("/associations/contacts"):
            return {"results": [{"toObjectId": "1"}, {"toObjectId": "2"}]}
        return contacts[path.rsplit("/", 1)[1]]
    monkeypatch.setattr(dsy.hs, "_get", fake_get)
    c = dsy._deal_contact("D1", "Lara Perkins - Nomi")
    assert c["properties"]["email"] == "mom@x.com"
    # no dealname match → falls back to the first associated contact
    assert dsy._deal_contact("D1", "Zzz Qqq - Kid")["id"] == "1"


def test_force_bypasses_pilot_and_audit(monkeypatch):
    calls = _wire(monkeypatch, existing=None, pilot=True)
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: True)  # even if marked
    rec = dsy.sync_deal(_deal(), force=True)
    assert rec["action_taken"] == "tw_synced" and calls["created"]


def test_force_still_respects_charter_guard(monkeypatch):
    calls = _wire(monkeypatch, existing=None, pilot=True, contact={
        "email": "es@school.org", "firstname": "Celine", "lastname": "Gaeta"})
    rec = dsy.sync_deal(_deal(pid="907748", name="Ana Tzubery - Maksim - iLead"), force=True)
    assert rec["action_taken"] == "sync_needs_review"
    assert not calls["created"] and not calls["updated"]


def test_force_overrides_contact_and_student(monkeypatch):
    # Trace-by-email: explicit contact + student override syncs a charter deal whose
    # name has neither (e.g. 'Ocean Grove Charter School - PO 1418959').
    calls = _wire(monkeypatch, existing=None, pilot=True)
    override = {"properties": {"email": "kennahunter41@gmail.com",
                               "firstname": "Kenna", "lastname": "Hunter"}}
    rec = dsy.sync_deal(_deal(pid="907748", name="Ocean Grove Charter School - PO 1418959"),
                        force=True, contact_override=override, students_override=["McKenna"])
    assert rec["action_taken"] == "tw_synced"
    assert calls["created"][0][0]["email"] == "kennahunter41@gmail.com"
    assert calls["students"][0]["first_name"] == "McKenna"
    assert calls["students"][0]["last_name"] == "Hunter"
    assert calls["students"][0]["billing_method"] == "Package"


def test_sibling_students_all_created(monkeypatch):
    calls = _wire(monkeypatch, existing=None)
    dsy.sync_deal(_deal(name="Alexa Marcano- Kash and Kingston"))
    assert [s["first_name"] for s in calls["students"]] == ["Kash", "Kingston"]


def test_charter_es_contact_flagged_not_written(monkeypatch):
    # iLead ES (Celine Gaeta) on a deal named for the parent → review, no TW write.
    calls = _wire(monkeypatch, existing=None, contact={
        "email": "celine.gaeta@ileadexploration.org", "firstname": "Celine", "lastname": "Gaeta"})
    rec = dsy.sync_deal(_deal(pid="907748", name="Ana Tzubery - Maksim - iLead (Apr) 25/26"))
    assert rec["action_taken"] == "sync_needs_review"
    assert not calls["created"] and not calls["updated"] and not calls["students"]
    assert calls["slack"] and calls["slack"][0][0] == "CTEST"


def test_charter_parent_contact_passes_guard(monkeypatch):
    calls = _wire(monkeypatch, existing=None, contact={
        "email": "nikita@gmail.com", "firstname": "Nikita", "lastname": "Brixey"})
    rec = dsy.sync_deal(_deal(pid="907748", name="Nikita Brixey - Londyn - Heartland 1 (Aug) 26/27"))
    assert rec["action_taken"] == "tw_synced" and calls["created"]
    assert calls["students"][0]["first_name"] == "Londyn"
    assert calls["students"][0]["billing_method"] == "Package"


def test_charter_po_deal_exempt_from_guard(monkeypatch):
    # PO-created deal: contact is the parent (associated by po_inbox) but their name
    # isn't in the 'School - Student - PO n' deal name — po_number exempts it.
    calls = _wire(monkeypatch, existing=None, contact={
        "email": "mom@x.com", "firstname": "Maria", "lastname": "Diaz"})
    d = _deal(pid="907748", name="iLEAD - Ana Diaz - PO 4471")
    d["properties"]["po_number"] = "4471"
    rec = dsy.sync_deal(d)
    assert rec["action_taken"] == "tw_synced" and calls["created"]


def test_pipeline_settings_override(monkeypatch):
    calls = _wire(monkeypatch, existing=None)
    base = _cfg(False)
    base["deal_sync"]["pipeline_settings"] = {"21277473": {
        "account": "in_person", "student_billing": "Flat Monthly",
        "customer_fields": {"welcome_email": "no"},
        "student_fields": {"default_service": "Subscription Tutoring"}}}
    monkeypatch.setattr(dsy, "cfg", lambda: {**base,
                                             "internal": {"domain": "wetutorathome.com"},
                                             "slack": {"digest_channel": "CTEST"}})
    rec = dsy.sync_deal(_deal(pid="21277473"))
    assert rec["tw_account"] == "in_person"                       # account override
    assert calls["created"][0][0]["welcome_email"] == "no"        # customer fields merged
    assert calls["students"][0]["billing_method"] == "Flat Monthly"
    assert calls["students"][0]["default_service"] == "Subscription Tutoring"


def test_unlisted_charter_named_pipeline_gets_package(monkeypatch):
    # a NEW charter pipeline not yet in config → still charter → Package billing
    calls = _wire(monkeypatch, existing=None)
    monkeypatch.setattr(dsy.hs, "pipeline_label", lambda p: "Charter - Brand New School")
    d = _deal(pid="999999", name="Lara Perkins - Nomi")
    d["properties"]["po_number"] = "5"   # PO-created → guard exempt
    rec = dsy.sync_deal(d)
    assert rec["charter"] is True
    assert calls["students"][0]["billing_method"] == "Package"


def test_internal_contact_skipped(monkeypatch):
    calls = _wire(monkeypatch, existing=None, contact={
        "email": "danielle+001@wetutorathome.com", "firstname": "Danielle", "lastname": "Brodetsky"})
    rec = dsy.sync_deal(_deal(name="Teacher Scholarship Family -  -"))
    assert rec["action_taken"] == "sync_skipped"
    assert not calls["created"] and not calls["slack"]
