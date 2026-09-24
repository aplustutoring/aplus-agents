"""
The reasoner reads the contact record before any message (Roman 2026-09-24).
A parked lead status closes the ticket with no model call; missing persona or
lead status on a lead shows up in the pester as a one-line ask.
"""

from src import hubspot_client as hs
from src import ticket_reasoner as tr

CFG = {"reasoner": {"parked_lead_statuses": ["Check Back Quarterly",
                                             "Dead Opportunity/Unqualified"],
                    "pester_as": "visionary"}}


def test_parked_label_closes_without_the_model(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    ev = {"subject": "Stein, Daniella — Scheduling", "contact": "Daniella Stein",
          "contact_record": {"persona": "Family", "lifecycle": "lead",
                             "lead_status": "Check Back Quarterly"}}
    v = tr.reason(ev)
    assert v["verdict"] == "PARKED" and v["confidence"] >= 0.85
    assert "Check Back Quarterly" in v["reason"]
    assert "PARKED" in tr.CLOSEABLE


def test_label_match_is_case_insensitive_and_value_never_matches(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    assert tr.parked_reason({"contact_record": {"lead_status": "check back quarterly"}})
    assert tr.parked_reason({"contact_record": {"lead_status": "Using Someone Else"}}) is None
    assert tr.parked_reason({"contact_record": {"lead_status": "Open deal"}}) is None
    assert tr.parked_reason({}) is None


def test_gather_carries_the_record_and_names_gaps(monkeypatch):
    monkeypatch.setattr(tr.hs, "get_ticket_emails", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_notes", lambda t: [])
    monkeypatch.setattr(tr.hs, "lead_status_label", lambda v: {"Using Someone Else": "Check Back Quarterly"}.get(v, v or ""))
    monkeypatch.setattr(tr.hs, "get_ticket_contacts", lambda t: [
        {"properties": {"firstname": "Amanda", "lastname": "W", "lifecyclestage": "lead"}}])
    ev = tr.gather({"id": "T1", "properties": {"subject": "x", "createdate": "2026-09-20T00:00:00Z"}}, {})
    assert ev["contact_record"] == {"persona": "", "lifecycle": "lead", "lead_status": ""}
    assert ev["contact_gaps"] == ["persona", "lead_status"]

    monkeypatch.setattr(tr.hs, "get_ticket_contacts", lambda t: [
        {"properties": {"firstname": "Judy", "lastname": "G", "lifecyclestage": "customer",
                        "a_persona": "Family", "hs_lead_status": "Using Someone Else"}}])
    ev = tr.gather({"id": "T2", "properties": {"subject": "x", "createdate": "2026-09-20T00:00:00Z"}}, {})
    assert ev["contact_record"]["lead_status"] == "Check Back Quarterly"
    assert ev["contact_gaps"] == []          # a customer is not asked for lead status


def test_pester_asks_for_the_missing_fields():
    ev = {"ticket_id": "1", "age_hours": 50, "subject": "Wolgemuth, Amanda — Scheduling",
          "contact_gaps": ["persona", "lead_status"]}
    text = tr.pester_text("Paola", ev, {"verdict": "WAITING", "reason": "no reply"}, "u")
    assert "Also set the A+ Persona and lead status on the contact." in text
    ev["contact_gaps"] = []
    assert "Also set" not in tr.pester_text("Paola", ev, {"verdict": "WAITING", "reason": ""}, "u")


def test_lead_status_label_reads_labels_not_values(monkeypatch):
    monkeypatch.setattr(hs, "_get", lambda path, params=None: {"options": [
        {"value": "Using Someone Else", "label": "Check Back Quarterly"},
        {"value": "UNQUALIFIED", "label": "Dead Opportunity/Unqualified"}]})
    hs._lead_status_labels.cache_clear()
    assert hs.lead_status_label("Using Someone Else") == "Check Back Quarterly"
    assert hs.lead_status_label("UNQUALIFIED") == "Dead Opportunity/Unqualified"
    assert hs.lead_status_label("NEW") == "NEW"
    assert hs.lead_status_label(None) == ""
