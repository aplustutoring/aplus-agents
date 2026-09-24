"""Creation contract on the call agent: owner seat + lifecycle at birth, persona
stamped from the caller type the summary names (never from telco caller-ID)."""

import call_agent as ca

CFG = {"hubspot": {"created_contact_lead_status": "NEW", "created_contact_owner": "paola",
                   "default_task_owner": "paola", "auto_create_contacts": True,
                   "owners": {"paola": 81494333, "janelle": 80047202}},
       "justcall": {"line_names": {}}}


def test_created_contact_carries_owner_lifecycle_and_lead_status(monkeypatch):
    sent = {}
    monkeypatch.setattr(ca, "hs_post", lambda ep, payload: sent.update(payload) or {"id": "C7"})
    ca.create_contact_from_call({"contact_number": "+18185550100", "justcall_number": "x"}, CFG, False)
    p = sent["properties"]
    assert p["hubspot_owner_id"] == "81494333"
    assert p["lifecyclestage"] == "lead"
    assert p["hs_lead_status"] == "NEW"
    assert "a_persona" not in p, "persona comes from the transcript, not the phone number"


def test_persona_from_caller_type():
    assert ca.persona_for_caller_type("parent") == "Family"
    assert ca.persona_for_caller_type("school/charter contact") == "Teacher of Record/EF/ES"
    assert ca.persona_for_caller_type("tutor applicant") == "Tutors"
    for t in ("vendor", "spam", "other", None):
        assert ca.persona_for_caller_type(t) is None
