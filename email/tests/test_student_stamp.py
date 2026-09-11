"""Fill-only student/parent stamp — the agent that replaced workflow 34950163."""
from src import student_stamp as st

CFG = {"student_stamp": {"enabled": True, "pipelines": ["907748", "19120821"]}}


def _contact(first="Mayra", last="Aguilar", student="Mario", grade="9", cid="C1"):
    return {"id": cid, "properties": {"firstname": first, "lastname": last,
                                      "email": f"{first}@x.com".lower(), "a_persona": "Family",
                                      "student_last_name": student,
                                      "what_is_your_child_s_current_grade_level_": grade}}


def _wire(monkeypatch, live_props, seen=()):
    calls = {"patch": [], "audit": []}
    monkeypatch.setattr(st, "cfg", lambda: CFG)
    monkeypatch.setattr(st, "DRY_RUN", False)
    monkeypatch.setattr(st.audit, "already_processed", lambda k: k in seen)
    monkeypatch.setattr(st.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(st.hs, "_get", lambda p, params=None: {"properties": live_props})
    monkeypatch.setattr(st.hs, "_write",
                        lambda m, p, body=None: calls["patch"].append((m, p, body)) or {})
    return calls


def test_dealname_student_parsing():
    assert st.student_firsts_from_dealname("Lesly Elenes - Nathan") == ["Nathan"]
    assert st.student_firsts_from_dealname(
        "Mayra Aguilar - Ezekiel Melara - Sky Mountain Charter School 1 - 26/27") == ["Ezekiel"]
    assert st.student_firsts_from_dealname("Renewal - Ana Diaz - Mateo") == ["Mateo"]
    assert st.student_firsts_from_dealname("Jane Wong - Kash and Kingston") == ["Kash", "Kingston"]
    assert st.student_firsts_from_dealname("iLEAD - PO 4471") == []
    assert st.student_firsts_from_dealname("Nicole Pifco") == []


def test_sibling_deal_keeps_its_own_student_and_skips_contact_grade():
    # the Melara case: contact says Mario/9, this deal is Ezekiel's
    writes, notes = st.plan({"dealname": "Mayra Aguilar - Ezekiel Melara - Sky Mountain 1 - 26/27"},
                            _contact())
    assert writes == {"student_first_name": "Ezekiel", "first_name": "Mayra",
                      "last_name": "Aguilar", "contact_record_id": "C1"}
    assert "student_grade" not in writes and any("deal name wins" in n for n in notes)


def test_contact_student_and_grade_used_when_dealname_has_no_student():
    writes, notes = st.plan({"dealname": "Nicole Pifco"}, _contact("Nicole", "Pifco", "Whitney", "4"))
    assert writes["student_first_name"] == "Whitney" and writes["student_grade"] == "4"
    assert notes == []


def test_matching_student_copies_grade():
    writes, _ = st.plan({"dealname": "Mayra Aguilar - Mario Melara - Sky Mountain 1 - 26/27"},
                        _contact())
    assert writes["student_first_name"] == "Mario" and writes["student_grade"] == "9"


def test_fill_only_never_overwrites():
    writes, _ = st.plan({"dealname": "Mayra Aguilar - Ezekiel Melara - X 1 - 26/27",
                         "student_first_name": "Ezekiel", "student_grade": "6",
                         "first_name": "Mayra", "last_name": "Aguilar",
                         "contact_record_id": "C1"}, _contact())
    assert writes == {}


def test_two_students_in_dealname_leaves_student_fields_for_a_human():
    writes, notes = st.plan({"dealname": "Jane Wong - Kash and Kingston"}, _contact("Jane", "Wong", "Kash"))
    assert "student_first_name" not in writes and "student_grade" not in writes
    assert writes["first_name"] == "Jane" and any("several students" in n for n in notes)


def test_maybe_stamp_patches_blanks_and_audits_once(monkeypatch):
    calls = _wire(monkeypatch, {"dealname": "Lesly Elenes - Nathan", "pipeline": "19120821"})
    deal = {"id": "D1", "properties": {"pipeline": "19120821"}}
    rec = st.maybe_stamp(deal, _contact("Lesly", "Elenes", "Adrian", "8", "C9"))
    assert rec["action_taken"] == "student_stamped"
    assert calls["patch"] == [("PATCH", "/crm/v3/objects/deals/D1", {"properties": {
        "student_first_name": "Nathan", "first_name": "Lesly", "last_name": "Elenes",
        "contact_record_id": "C9"}})]
    assert calls["audit"][0]["message_id"] == "student_stamp:D1"


def test_maybe_stamp_skips_off_pipeline_seen_and_no_contact(monkeypatch):
    calls = _wire(monkeypatch, {"dealname": "X - Y", "pipeline": "19120821"}, seen={"student_stamp:D2"})
    assert st.maybe_stamp({"id": "D1", "properties": {"pipeline": "971802"}}, _contact()) is None
    assert st.maybe_stamp({"id": "D2", "properties": {"pipeline": "19120821"}}, _contact()) is None
    rec = st.maybe_stamp({"id": "D3", "properties": {"pipeline": "19120821"}}, None)
    assert rec["action_taken"] == "student_stamp_skipped" and calls["patch"] == []
    assert calls["audit"][-1]["message_id"] == "student_stamp-skip:D3"   # not marked done


def test_school_staff_contact_never_supplies_parent_fields():
    tor = {"id": "T1", "properties": {"firstname": "Kristy", "lastname": "Doyal",
                                      "email": "es@school.org",
                                      "a_persona": "Teacher of Record/EF/ES"}}
    writes, notes = st.plan({"dealname": "NEEDS PARENT - Cooper Doyal - Heartland 1 - 26/27"}, tor)
    assert writes == {"student_first_name": "Cooper"}
    assert any("school staff" in n for n in notes)


def test_stamp_failure_is_non_fatal(monkeypatch):
    calls = _wire(monkeypatch, {})
    monkeypatch.setattr(st.hs, "_get", lambda p, params=None: (_ for _ in ()).throw(RuntimeError("503")))
    assert st.maybe_stamp({"id": "D1", "properties": {"pipeline": "19120821"}}, _contact()) is None
    assert calls["patch"] == [] and calls["audit"] == []   # not marked done → backfill/FORCE retries


def test_run_loop_calls_student_stamp(monkeypatch, tmp_path):
    # the hook in deal_sync.run(): every new deal passes through maybe_stamp
    import json, sys, types
    from src import deal_sync as ds
    seen = []
    cur = tmp_path / "cur.json"
    cur.write_text(json.dumps({"last_createdate_ms": 1}))
    monkeypatch.setattr(ds, "CUR_PATH", cur)
    monkeypatch.setattr(ds.student_stamp, "maybe_stamp", lambda d, c: seen.append(d["id"]))
    monkeypatch.setattr(ds.owner_assign, "maybe_assign", lambda d, c: None)
    monkeypatch.setattr(ds, "sync_deal", lambda d, **k: None)
    monkeypatch.setattr(ds, "_deal_contact", lambda did, dn="": None)
    monkeypatch.setattr(ds, "cfg", lambda: {"deal_sync": {"enabled": True, "dry_run_first": False}})
    monkeypatch.setattr(ds, "DRY_RUN", True)
    monkeypatch.setattr(ds.hs, "_write", lambda m, p, body=None: {"results": [
        {"id": "D7", "properties": {"dealname": "A - B", "createdate": "2026-09-10T00:00:00Z"}}]})
    for name, fn in (("relay_watchdog", "check"), ("invoice_sweep", "run_sweep"),
                     ("sms", "run_sweep"), ("sibling_gaps", "run")):
        m = types.ModuleType(f"src.{name}"); setattr(m, fn, lambda *a, **k: None)
        monkeypatch.setitem(sys.modules, f"src.{name}", m)
    ds.run()
    assert seen == ["D7"]
