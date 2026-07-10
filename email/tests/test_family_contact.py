"""Teachworks family-contact disambiguation (student props + deal names)."""
from src import hubspot_client as hs


def _no_deals(monkeypatch):
    monkeypatch.setattr(hs, "contact_deal_names", lambda cid: [])


def test_single_match_links(monkeypatch):
    _no_deals(monkeypatch)
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: {"results": [{"id": "9", "properties": {"lastname": "Smith"}}]})
    assert [c["id"] for c in hs.find_family_contact("Anyone", "Smith")] == ["9"]


def test_collision_resolved_by_student_property(monkeypatch):
    _no_deals(monkeypatch)
    two = {"results": [
        {"id": "1", "properties": {"lastname": "Schnider", "student_full_name_clone_": "Layla"}},
        {"id": "2", "properties": {"lastname": "Schnider", "student_last_name": "Marcus"}},
    ]}
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: two)
    res = hs.find_family_contact("Layla", "Schnider")
    assert len(res) == 1 and res[0]["id"] == "1"


def test_collision_resolved_by_deal_name(monkeypatch):
    # No student props at all — deal names break the tie.
    two = {"results": [{"id": "1", "properties": {"lastname": "Schnider"}},
                       {"id": "2", "properties": {"lastname": "Schnider"}}]}
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: two)
    monkeypatch.setattr(hs, "contact_deal_names",
                        lambda cid: ["Michelle Schnider - Layla"] if cid == "1" else ["Bob Schnider - Marcus"])
    res = hs.find_family_contact("Layla", "Schnider")
    assert len(res) == 1 and res[0]["id"] == "1"


def test_unresolved_returns_all(monkeypatch):
    _no_deals(monkeypatch)
    two = {"results": [{"id": "1", "properties": {"lastname": "Schnider"}},
                       {"id": "2", "properties": {"lastname": "Schnider"}}]}
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: two)
    assert len(hs.find_family_contact("Nobody", "Schnider")) == 2
