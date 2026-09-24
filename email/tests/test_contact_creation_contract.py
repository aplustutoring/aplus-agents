"""
Contact-creation contract (Roman 2026-09-24): every contact an agent creates
is born with persona, owner seat, lifecycle and (families) a lead status.
Email triage used to create senders with an email address and nothing else.
"""

import pytest

from src import hubspot_client as hs
from src import main
from src import po_inbox as po


# ── the helper itself ────────────────────────────────────────────────────────

def _staff(monkeypatch):
    table = {"charter_sales": {"hubspot_owner_id": "81494333"},
             "sales": {"hubspot_owner_id": "227538487"},
             "janelle": {"hubspot_owner_id": "80047202"},
             "visionary": {"hubspot_owner_id": "38681249"}}
    monkeypatch.setattr(hs, "staff", lambda k: table.get(k, {}))


def test_creation_props_carries_the_contract(monkeypatch):
    _staff(monkeypatch)
    p = hs.creation_props("Family", "charter_sales", lead_status="NEW")
    assert p == {"hubspot_owner_id": "81494333", "a_persona": "Family",
                 "lifecyclestage": "lead", "hs_lead_status": "NEW"}


def test_persona_may_be_none_but_owner_may_not(monkeypatch):
    _staff(monkeypatch)
    assert "a_persona" not in hs.creation_props(None, "janelle")
    with pytest.raises(ValueError):
        hs.creation_props("Family", "")
    with pytest.raises(ValueError):
        hs.creation_props("Family", "nobody")


def test_unknown_persona_is_refused(monkeypatch):
    _staff(monkeypatch)
    with pytest.raises(ValueError):
        hs.creation_props("Parent", "janelle")


def test_create_contact_requires_the_contract(monkeypatch):
    _staff(monkeypatch)
    sent = {}
    monkeypatch.setattr(hs, "_write", lambda m, path, payload=None: sent.update(payload) or {"id": "C1"})
    with pytest.raises(TypeError):
        hs.create_contact("a@b.com")                       # persona/owner_role missing
    hs.create_contact("a@b.com", "Ann", persona="Family", owner_role="janelle",
                      extra_props={"a_persona": "Tutors"})  # extra_props cannot override
    assert sent["properties"]["a_persona"] == "Family"
    assert sent["properties"]["hubspot_owner_id"] == "80047202"
    assert sent["properties"]["lifecyclestage"] == "lead"


# ── PO intake ────────────────────────────────────────────────────────────────

def test_po_family_and_teacher_defaults():
    assert po.FAMILY_CREATE == {"persona": "Family", "owner_role": "charter_sales",
                                "lifecycle": "customer"}
    assert po.TOR_CREATE["persona"] == "Teacher of Record/EF/ES"
    assert po.TOR_CREATE["owner_role"] == "sales"
    assert po.TOR_CREATE["lifecycle"] is None


# ── the config maps every triage category the router knows ─────────────────

def test_persona_map_covers_every_routed_category_or_is_deliberately_blank():
    c = main.cfg()
    routed = set(c["routing"]) if "routing" in c else set(
        k for k in c.get("triage", {}).get("categories", {}))
    pm = c["contact_creation"]["persona_by_category"]
    for persona in set(pm.values()):
        assert persona in hs.PERSONAS
    # junk and unknown are the only categories allowed to have no persona
    blank = {k for k in routed if k not in pm}
    assert blank <= {"junk", "unknown"}, f"categories creating persona-less contacts: {sorted(blank)}"
