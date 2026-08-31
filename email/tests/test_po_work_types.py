"""Non-PO charter mail is routed by what it IS (Roman approved 2026-08-27).

Every charter@ ticket used to be stamped hs_ticket_category=new_deal_po,
including the 42 of 93 open ones whose own description read "Not a PO:". No
routing rule matched a constant, so no owner was derived, nothing had an SLA and
nothing had a done-state. Measured over 845 tickets since 2026-06-01: a real
category closed in a median of 0.25 days at 92%; the catch-all took 2.15 days at
80%. Fixtures below are the actual open tickets behind that.
"""
import pytest

from src import po_inbox as po


@pytest.fixture
def captured(monkeypatch):
    """Run one message through and hand back the created ticket's arguments."""
    seen = {}

    def fake_create_ticket(subject, owner_id, stage, desc, contact_id,
                           priority=None, category=None, source=None, extra_props=None):
        seen.update(subject=subject, owner_id=owner_id, priority=priority,
                    category=category, extra_props=extra_props or {}, desc=desc)
        return {"id": "T1"}

    monkeypatch.setattr(po.hs, "create_ticket", fake_create_ticket)
    monkeypatch.setattr(po.hs, "add_ticket_note", lambda *a, **k: None)
    monkeypatch.setattr(po.gm, "apply_labels", lambda *a, **k: None)
    monkeypatch.setattr(po.gm, "ensure_label", lambda n: "L")
    monkeypatch.setattr(po.audit, "append", lambda r: None)
    monkeypatch.setattr(po.slack_client, "dm", lambda *a, **k: None)
    monkeypatch.setattr(po.slack_client, "post_message", lambda *a, **k: None)
    monkeypatch.setattr(po, "_open_chases", lambda: {})
    monkeypatch.setattr(po, "_thread_already_handled", lambda t: False)
    return seen


def _run(monkeypatch, captured, hint, summary, subject="Re: something"):
    msg = {"id": "m1", "threadId": "TH-9", "sender": "ap@school.org",
           "subject": subject, "body": "b", "date_ms": 0}
    monkeypatch.setattr(po.gm, "get_message", lambda i: msg)
    monkeypatch.setattr(po.gm, "get_attachments", lambda i: [])
    monkeypatch.setattr(po.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(po, "po_extract", lambda *a, **k: {
        "is_po": False, "is_cancellation": False, "category_hint": hint,
        "summary": summary, "school": "Suncoast", "po_number": "",
        "student_first": "", "student_last": "", "parent_email": ""})
    po.process_po_message("m1")
    return captured


# ── the three types the corpus demanded ────────────────────────────────────
def test_ar_followup_is_billing_not_a_new_deal(monkeypatch, captured):
    """7 open, median 14 days, previously split across four owners because
    nothing named this work."""
    c = _run(monkeypatch, captured, "ar_followup",
             "Blue Ridge AP says invoices 52531 and 52354 were paid via ACH on 2/5/26")
    assert c["extra_props"]["po_work_type"] == "ar_followup"
    assert c["category"] == "billing_refund"
    assert c["priority"] == "HIGH"
    assert c["subject"].startswith("AR — ")
    assert "Money we are OWED" in c["desc"]


def test_invoice_correction_is_its_own_thing(monkeypatch, captured):
    """Suncoast held $1,330 for 10 days over a Bill To name."""
    c = _run(monkeypatch, captured, "invoice_correction",
             "Suncoast needs invoice 51832 reissued under their new legal name")
    assert c["extra_props"]["po_work_type"] == "invoice_correction"
    assert c["category"] == "billing_refund"
    assert c["priority"] == "HIGH"
    assert c["subject"].startswith("INVOICE FIX — ")


def test_vendor_onboarding_is_not_compliance(monkeypatch, captured):
    """11 open. Logins and welcome packets are setup, not a signature request."""
    c = _run(monkeypatch, captured, "vendor_onboarding",
             "Granite Mountain sent OPS vendor login credentials for 2026-2027")
    assert c["extra_props"]["po_work_type"] == "vendor_onboarding"
    assert c["priority"] == "MEDIUM"
    assert c["subject"].startswith("VENDOR SETUP — ")


# ── the ones that already worked keep working ──────────────────────────────
def test_compliance_still_goes_to_sales(monkeypatch, captured):
    c = _run(monkeypatch, captured, "vendor_compliance", "W-9 requested before we can be paid")
    assert c["extra_props"]["po_work_type"] == "vendor_compliance"
    assert c["priority"] == "HIGH"
    assert c["owner_id"] == "227538487"      # sales → Danielle
    assert c["subject"].startswith("COMPLIANCE — ")


def test_scam_is_low_and_drops_the_sender(monkeypatch, captured):
    c = _run(monkeypatch, captured, "scam", "Advance-fee prepay request from a free-mail address")
    assert c["priority"] == "LOW" and c["subject"].startswith("SUSPECTED SCAM — ")


def test_marketing_junk_is_low(monkeypatch, captured):
    c = _run(monkeypatch, captured, "marketing_junk", "Vendor spotlight newsletter")
    assert c["priority"] == "LOW"
    assert c["extra_props"]["po_work_type"] == "marketing_junk"


def test_unknown_hint_falls_back_to_other(monkeypatch, captured):
    c = _run(monkeypatch, captured, "", "Forest Charter confirming we are all set")
    assert c["extra_props"]["po_work_type"] == "other"
    assert c["category"] == "GENERAL_INQUIRY"


# ── the properties that were declared and never written ────────────────────
def test_ap007_stamps_are_finally_written(monkeypatch, captured):
    """ticket_source and source_thread_id were declared for #AP007 and written on
    zero tickets, which is why dedup could only key on the PO number and the
    reasoner had to find the Gmail thread by searching the subject."""
    c = _run(monkeypatch, captured, "ar_followup", "AP chasing invoices")
    assert c["extra_props"]["ticket_source"] == "email_engine"
    assert c["extra_props"]["source_thread_id"] == "TH-9"


def test_empty_extra_props_are_never_sent(monkeypatch):
    """A blank must not overwrite a real value."""
    sent = {}
    monkeypatch.setattr(po.hs, "_write", lambda m, p, body=None: sent.update(body or {}) or {"id": "1"})
    monkeypatch.setattr(po.hs, "cfg", lambda: {"hubspot": {"ticket_pipeline_id": "0"}})
    po.hs.create_ticket("s", "1", "2", "d", None,
                        extra_props={"po_work_type": "ar_followup", "ticket_source": ""})
    props = sent["properties"]
    assert props["po_work_type"] == "ar_followup"
    assert "ticket_source" not in props


def test_unsynced_property_does_not_drop_the_ticket(monkeypatch):
    """properties.yml is declarative and the portal sync is a separate step, so
    code can run ahead of the schema. An unknown property must cost us the
    stamp, never the ticket."""
    import requests as rq
    calls = []

    class Resp:
        status_code = 400
        text = ('{"message":"Property \\"po_work_type\\" does not exist",'
                '"category":"PROPERTY_DOESNT_EXIST"}')

    def flaky(method, path, body=None):
        calls.append(dict(body["properties"]))
        if len(calls) == 1:
            err = rq.HTTPError("400")
            err.response = Resp()
            raise err
        return {"id": "T9"}

    monkeypatch.setattr(po.hs, "_write", flaky)
    monkeypatch.setattr(po.hs, "cfg", lambda: {"hubspot": {"ticket_pipeline_id": "0"}})
    out = po.hs.create_ticket("s", "1", "2", "d", None,
                              extra_props={"po_work_type": "ar_followup",
                                           "ticket_source": "email_engine"})
    assert out["id"] == "T9"
    assert "po_work_type" in calls[0]
    assert "po_work_type" not in calls[1] and "ticket_source" not in calls[1]
    assert calls[1]["subject"] == "s"


def test_every_work_type_has_a_config_entry():
    """A hint with no config entry silently falls back to MEDIUM/new_deal_po —
    the exact bucket this change exists to eliminate."""
    from src.config import cfg
    wt = cfg()["po_inbox"]["work_types"]
    emitted = {"purchase_order", "po_cancellation", "ar_followup", "invoice_correction",
               "vendor_compliance", "vendor_onboarding", "parent_info_reply",
               "family_inquiry", "marketing_junk", "scam", "other"}
    assert emitted <= set(wt), f"no routing for: {emitted - set(wt)}"
    for name, rule in wt.items():
        assert rule.get("owner"), f"{name} has no owner"
        assert rule.get("priority") in {"LOW", "MEDIUM", "HIGH", "URGENT"}, name
        assert rule.get("category"), f"{name} has no hs_ticket_category"


def test_categories_are_real_hubspot_options():
    """hs_ticket_category is a closed enumeration — inventing a value silently
    fails the write."""
    from src.config import cfg
    VALID = {"PRODUCT_ISSUE", "FEATURE_REQUEST", "Tutor Issue", "BILLING_ISSUE",
             "GENERAL_INQUIRY", "reschedule", "cancellation_onetime", "pause",
             "cancel_service", "complaint", "new_deal_po", "billing_refund", "Review"}
    for name, rule in cfg()["po_inbox"]["work_types"].items():
        assert rule["category"] in VALID, f"{name}: {rule['category']} is not an option"
