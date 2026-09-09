"""New-deal owner assignment: the A-L / M-Z scheduler split, audited once per deal."""
from src import owner_assign as oa
from src import router

STAFF = {"janelle": {"name": "Janelle", "hubspot_owner_id": "80047202"},
         "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539"},
         "danielle": {"name": "Danielle", "hubspot_owner_id": "227538487"}}
CFG = {"owner_assign": {"enabled": True, "pipelines": ["19120821", "default"]},
       "scheduler_split": {"a_to_l": "janelle", "m_to_z": "yolanda"}}


def _deal(name="Lesly Elenes - Adrian", owner="227538487", pid="19120821", did="D1"):
    return {"id": did, "properties": {"dealname": name, "pipeline": pid, "hubspot_owner_id": owner}}


def _wire(monkeypatch, cfg=None, seen=()):
    calls = {"patch": [], "audit": []}
    c = cfg or CFG
    monkeypatch.setattr(oa, "cfg", lambda: c)
    monkeypatch.setattr(router, "cfg", lambda: c)
    monkeypatch.setattr(oa, "staff", lambda k: STAFF[k])
    monkeypatch.setattr(oa.audit, "already_processed", lambda k: k in seen)
    monkeypatch.setattr(oa.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(oa.hs, "_write", lambda m, p, body=None: calls["patch"].append((m, p, body)) or {})
    return calls


def test_a_to_l_goes_to_janelle_from_contact(monkeypatch):
    calls = _wire(monkeypatch)
    rec = oa.maybe_assign(_deal(), contact={"properties": {"lastname": "Elenes"}})
    assert rec["action_taken"] == "owner_assigned" and rec["owner"] == "janelle"
    assert calls["patch"] == [("PATCH", "/crm/v3/objects/deals/D1",
                               {"properties": {"hubspot_owner_id": "80047202"}})]
    assert rec["last_name_source"] == "contact" and rec["previous_owner_id"] == "227538487"


def test_m_to_z_goes_to_yolanda(monkeypatch):
    calls = _wire(monkeypatch)
    rec = oa.maybe_assign(_deal("Alina Matiukhina - Sofiia", owner="81494333"),
                          contact={"properties": {"lastname": "Matiukhina"}})
    assert rec["owner"] == "yolanda"
    assert calls["patch"][0][2] == {"properties": {"hubspot_owner_id": "86868539"}}


def test_dealname_fallback_when_no_contact(monkeypatch):
    _wire(monkeypatch)
    rec = oa.maybe_assign(_deal("Kym Whitley - Joshua", owner="80047202"), contact=None)
    assert rec["last_name_source"] == "dealname" and rec["last_name"] == "Whitley"
    assert rec["owner"] == "yolanda" and rec["action_taken"] == "owner_assigned"


def test_charter_style_dealname_takes_parent_segment():
    assert oa._parent_last_from_dealname("Ana Diaz - Mateo - iLEAD 2 - 26/27") == "Diaz"
    assert oa._parent_last_from_dealname("Nicole Pifco") == "Pifco"
    assert oa._parent_last_from_dealname("Solo") is None


def test_already_correct_scheduler_no_write(monkeypatch):
    calls = _wire(monkeypatch)
    rec = oa.maybe_assign(_deal("Emma De La Cruz Ponce - Leia", owner="80047202"),
                          contact={"properties": {"lastname": "De La Cruz Ponce"}})
    assert rec["action_taken"] == "owner_kept" and calls["patch"] == []
    assert len(calls["audit"]) == 1


def test_wrong_scheduler_is_reowned(monkeypatch):
    # Janelle created Kym Whitley (W) on 2026-08-28; the zap moved it to Yolanda.
    calls = _wire(monkeypatch)
    rec = oa.maybe_assign(_deal("Kym Whitley - Joshua", owner="80047202", pid="default"),
                          contact={"properties": {"lastname": "Whitley"}})
    assert rec["owner"] == "yolanda" and len(calls["patch"]) == 1


def test_unknown_last_name_defaults_a_to_l_with_note(monkeypatch):
    _wire(monkeypatch)
    rec = oa.maybe_assign(_deal("Solo", owner="81494333"), contact={"properties": {}})
    assert rec["owner"] == "janelle" and rec["last_name_source"] == "none"
    assert any("needs review" in n for n in rec["notes"])


def test_skips_uncovered_pipeline_disabled_and_seen(monkeypatch):
    calls = _wire(monkeypatch, seen={"owner:D1"})
    assert oa.maybe_assign(_deal(pid="907748"), contact=None) is None
    assert oa.maybe_assign(_deal(did="D1"), contact={"properties": {"lastname": "Elenes"}}) is None
    off = {**CFG, "owner_assign": {"enabled": False, "pipelines": ["19120821"]}}
    _wire(monkeypatch, cfg=off)
    assert oa.maybe_assign(_deal(did="D2"), contact=None) is None
    assert calls["patch"] == []
