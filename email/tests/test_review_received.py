"""review_received: platform notifications become family-tied Review tickets."""
from src import hubspot_client as hs
from src.classifier import VALID_CATEGORIES, parse_classification
from src.config import cfg
from src.router import resolve


def test_review_category_is_valid_and_routes_to_paola():
    assert "review_received" in VALID_CATEGORIES
    d = resolve("review_received", 0.9)
    assert d.owner_key == "paola"          # roles.quality -> paola
    assert d.should_draft is False         # reply happens ON the platform
    assert d.sla_hours == 8
    assert d.priority == "normal"


def test_review_category_maps_to_review_ticket_category():
    assert cfg()["ticket_fields"]["category_map"]["review_received"] == "Review"


def test_platform_domains_configured():
    domains = cfg()["review_platforms"]["sender_domains"]
    assert "google.com" in domains and "yelp.com" in domains


def test_parse_accepts_review_fields():
    r = parse_classification(
        '{"category": "review_received", "risk": "low", "confidence": 0.95,'
        ' "routing_target": "paola", "sla_tier": "8", "draft_reply": "",'
        ' "reason": "Google review alert", "review_platform": "google",'
        ' "review_rating": 5, "reviewer_name": "Maria Alvarez"}')
    assert r["category"] == "review_received"
    assert r["review_rating"] == 5 and r["reviewer_name"] == "Maria Alvarez"


def test_find_contact_by_name_exact_pair(monkeypatch):
    captured = {}

    def fake_write(method, path, body=None):
        captured["filters"] = body["filterGroups"][0]["filters"]
        return {"results": [{"id": "42", "properties": {"lastname": "Alvarez"}}]}

    monkeypatch.setattr(hs, "_write", fake_write)
    res = hs.find_contact_by_name("Maria", "Alvarez")
    assert [c["id"] for c in res] == ["42"]
    assert {f["propertyName"] for f in captured["filters"]} == {"firstname", "lastname"}


def test_find_contact_by_name_refuses_blank():
    assert hs.find_contact_by_name("", "Alvarez") == []
    assert hs.find_contact_by_name("Maria", "") == []


# ── end-to-end wiring (process_message, all clients mocked) ──────────────────

import pytest  # noqa: E402

from src import main  # noqa: E402


@pytest.fixture
def calls(monkeypatch):
    rec = {"tickets": [], "created_contacts": [], "audit": []}
    monkeypatch.setattr(main.audit, "already_processed", lambda mid: False)
    monkeypatch.setattr(main.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [])
    monkeypatch.setattr(main.hs, "sender_email",
                        lambda m: "googlebusinessprofile-noreply@google.com")
    monkeypatch.setattr(main.hs, "find_contact_by_email", lambda e: None)
    monkeypatch.setattr(main.hs, "create_contact",
                        lambda *a, **k: rec["created_contacts"].append(a) or {"id": "JUNK"})
    monkeypatch.setattr(main.hs, "contact_enrichment",
                        lambda cid: {"properties": {}, "associated_deals": 0})
    monkeypatch.setattr(main.tw, "enrichment_for_email", lambda e: {"teachworks_match": False})
    monkeypatch.setattr(main.hs, "create_ticket",
                        lambda *a, **k: (rec["tickets"].append((a, k)) or {"id": "T1"}))
    monkeypatch.setattr(main.hs, "link_thread_to_ticket", lambda th, tk: None)
    monkeypatch.setattr(main.hs, "add_ticket_note", lambda *a, **k: {"id": "N1"})
    monkeypatch.setattr(main.hs, "create_task", lambda *a, **k: {"id": "TASK1"})
    monkeypatch.setattr(main.hs, "get_ticket", lambda tid: {"properties": {}})
    monkeypatch.setattr(main.slack_client, "dm", lambda uid, text: None)
    return rec


def _review_classify(reviewer, rating=5, platform="google"):
    def _c(body, summary):
        return {"category": "review_received", "risk": "low", "confidence": 0.95,
                "routing_target": "paola", "sla_tier": "8", "draft_reply": "",
                "reason": "review alert stub", "reviewer_name": reviewer,
                "review_platform": platform, "review_rating": rating}
    return _c


def _msg():
    return {"id": "m-rev", "text": "Maria Alvarez left you a new review",
            "senders": [{"deliveryIdentifier": {
                "type": "HS_EMAIL_ADDRESS",
                "value": "googlebusinessprofile-noreply@google.com"}}]}


def test_review_ticket_ties_to_family_not_platform(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _review_classify("Maria Alvarez"))
    monkeypatch.setattr(main.hs, "find_contact_by_name",
                        lambda f, l: [{"id": "FAM1", "properties": {}}]
                        if (f, l) == ("Maria", "Alvarez") else [])
    rec = main.process_message("th-rev", _msg())
    assert rec["ticket_id"] == "T1" and rec["owner"] == "paola"
    assert calls["created_contacts"] == []          # no junk contact for the no-reply sender
    args, kwargs = calls["tickets"][0]
    assert args[4] == "FAM1"                        # associated to the FAMILY
    assert kwargs["category"] == "Review"
    assert kwargs["extra_props"]["review_platform"] == "google"
    assert kwargs["extra_props"]["review_rating"] == 5
    assert kwargs["extra_props"]["review_reviewer_name"] == "Maria Alvarez"


def test_partial_reviewer_name_leaves_ticket_unassociated(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _review_classify("Maria A.", rating=None))
    monkeypatch.setattr(main.hs, "find_contact_by_name",
                        lambda f, l: (_ for _ in ()).throw(AssertionError("must not search on partial name")))
    main.process_message("th-rev2", _msg())
    args, kwargs = calls["tickets"][0]
    assert args[4] is None                          # unassociated — a refusal, not a guess
    assert "review_rating" not in kwargs["extra_props"]
    assert "partial" in args[3]                     # reason lands in the ticket description


def test_ambiguous_reviewer_match_leaves_ticket_unassociated(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _review_classify("Maria Alvarez"))
    monkeypatch.setattr(main.hs, "find_contact_by_name",
                        lambda f, l: [{"id": "1"}, {"id": "2"}])
    main.process_message("th-rev3", _msg())
    args, _ = calls["tickets"][0]
    assert args[4] is None
    assert "matched 2 contacts" in args[3]
