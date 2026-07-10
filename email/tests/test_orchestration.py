"""End-to-end wiring test for process_message with all clients mocked.

Validates routing → ticket → draft-comment (or suppression) → junk archive →
tutor-doc receipt send path, without touching any real API.
"""
import pytest

from src import main


@pytest.fixture
def calls(monkeypatch):
    rec = {"tickets": [], "comments": [], "archived": [], "sent": [], "dms": [], "audit": [], "tasks": []}

    monkeypatch.setattr(main.audit, "already_processed", lambda mid: False)
    monkeypatch.setattr(main.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(main.hs, "sender_email", lambda m: "parent@example.com")
    monkeypatch.setattr(main.hs, "find_contact_by_email",
                        lambda e: {"id": "C1", "properties": {"lastname": "Adams"}})
    monkeypatch.setattr(main.hs, "create_contact", lambda *a, **k: {"id": "C1"})
    monkeypatch.setattr(main.hs, "contact_enrichment", lambda cid: {"properties": {}, "associated_deals": 0})
    monkeypatch.setattr(main.tw, "enrichment_for_email", lambda e: {"teachworks_match": False})
    monkeypatch.setattr(main.tw, "upcoming_lessons_for_family", lambda em, sf=None: [])
    monkeypatch.setattr(main.hs, "create_ticket",
                        lambda *a, **k: (rec["tickets"].append((a, k)) or {"id": "T1"}))
    monkeypatch.setattr(main.hs, "link_thread_to_ticket",
                        lambda th, tk: rec.setdefault("links", []).append((th, tk)))
    monkeypatch.setattr(main.hs, "add_ticket_note", lambda *a, **k: {"id": "N1"})
    monkeypatch.setattr(main.hs, "create_task", lambda *a, **k: rec["tasks"].append((a, k)) or {"id": "TASK1"})
    monkeypatch.setattr(main.hs, "find_contacts_by_lastname", lambda ln: [])
    monkeypatch.setattr(main.hs, "find_family_contact", lambda f, l: [])
    monkeypatch.setattr(main.hs, "get_contact_deals", lambda cid: [])
    monkeypatch.setattr(main.hs, "ticket_url", lambda tid: f"http://t/{tid}")
    monkeypatch.setattr(main.hs, "post_comment", lambda tid, text: rec["comments"].append(text))
    monkeypatch.setattr(main.hs, "archive_thread", lambda tid: rec["archived"].append(tid))
    monkeypatch.setattr(main.hs, "send_message",
                        lambda tid, text, **kw: rec["sent"].append(text))
    monkeypatch.setattr(main.slack_client, "dm", lambda uid, text: rec["dms"].append((uid, text)))
    # Hermetic by default: no prior tickets on any thread, so the dedup guard is a no-op
    # and every test below exercises the fresh-ticket path. Dedup tests override these.
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [])
    monkeypatch.setattr(main.hs, "get_ticket", lambda tid: {"properties": {}})
    monkeypatch.setattr(main.hs, "update_ticket_stage",
                        lambda tid, sid: rec.setdefault("stage", []).append((tid, sid)))
    return rec


def _classify_stub(category, confidence=0.95, draft="We can help with that. A+ Tutoring Team", risk="low"):
    def _c(body, summary):
        return {
            "category": category, "risk": risk, "confidence": confidence,
            "routing_target": category, "sla_tier": "24h", "draft_reply": draft,
            "reason": "stub",
        }
    return _c


def _msg():
    return {"id": "m1", "text": "hello", "channelId": "1", "channelAccountId": "2",
            "senders": [{"deliveryIdentifier": {"type": "HS_EMAIL_ADDRESS", "value": "p@x.com"}}]}


def test_scheduling_creates_ticket_and_draft(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling"))
    rec = main.process_message("thread1", _msg())
    assert rec["action_taken"] == "ticket_created"
    assert rec["owner"] == "janelle"            # Adams → A-L
    assert len(calls["tickets"]) == 1
    assert calls["tickets"][0][0][2] == "1378066770"   # enters at "Working on it"
    tk = calls["tickets"][0][1]                       # kwargs: priority/category/source
    assert tk["source"] == "EMAIL"
    assert tk["priority"] == "MEDIUM"                 # scheduling = normal priority
    assert tk["category"] == "GENERAL_INQUIRY"   # scheduling (new booking) → General
    assert len(calls["comments"]) == 1          # draft posted as COMMENT
    assert rec["draft_posted"] is True
    assert calls["dms"]                         # owner DM'd
    copies = [t for u, t in calls["dms"] if "[copy →" in t]
    assert copies and "Janelle" in copies[0]    # CC shows the owner's NAME, not the id
    assert calls["tasks"] and calls["tasks"][0][0][2] == "80047202"  # task assigned to Janelle
    assert calls.get("links") == [("thread1", "T1")]   # email thread attached to the ticket


def test_hubspot_parent_last_name_drives_split(monkeypatch, calls):
    # Split keys off the HubSpot contact (parent) last name = Wilson (M-Z → Yolanda),
    # NOT the Teachworks student last name (Adams, A-L).
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling"))
    monkeypatch.setattr(main.hs, "find_contact_by_email",
                        lambda e: {"id": "C1", "properties": {"lastname": "Wilson"}})
    monkeypatch.setattr(main.tw, "enrichment_for_email",
                        lambda e: {"teachworks_match": True, "student_last_name": "Adams"})
    rec = main.process_message("thread7", _msg())
    assert rec["owner"] == "yolanda"


def test_complaint_suppresses_draft(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("complaint"))
    rec = main.process_message("thread2", _msg())
    assert rec["owner"] == "mandy"
    assert rec["draft_posted"] is False
    assert calls["comments"] == []              # no draft for complaints
    assert len(calls["tickets"]) == 1
    assert calls["tickets"][0][1]["category"] == "complaint"   # complaint → Complaint
    assert calls["tickets"][0][1]["priority"] == "HIGH"   # complaint=high; risk low so not URGENT


def test_high_risk_bumps_priority_to_urgent(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("payment_dispute", risk="high"))
    main.process_message("thread6", _msg())
    assert calls["tickets"][0][1]["priority"] == "URGENT"
    assert calls["tickets"][0][1]["category"] == "billing_refund"


def test_internal_email_routes_to_named_teammate(monkeypatch, calls):
    def _c(body, summary):
        return {"category": "unknown", "risk": "low", "confidence": 0.5, "routing_target": "x",
                "sla_tier": "24h", "draft_reply": "", "reason": "r", "internal_recipient": "Kath"}
    monkeypatch.setattr(main, "classify", _c)
    monkeypatch.setattr(main.hs, "sender_email", lambda m: "leo@wetutorathome.com")
    rec = main.process_message("threadI", _msg())
    assert rec["owner"] == "kath"                       # routed to the addressed teammate
    assert calls["tickets"][0][0][2] == "1378066770"     # normal queue, NOT Stuck


def test_junk_archives_no_ticket(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("junk", draft=""))
    rec = main.process_message("thread3", _msg())
    assert rec["action_taken"] == "junk_archived"
    assert calls["archived"] == ["thread3"]
    assert calls["tickets"] == []


def test_low_confidence_downgraded_no_draft(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("school_partner", confidence=0.5))
    rec = main.process_message("thread4", _msg())
    assert rec["category"] == "unknown"
    assert rec["draft_posted"] is False
    assert len(calls["tickets"]) == 1
    assert calls["tickets"][0][0][2] == "131537028"   # unknown enters at "Stuck"


def test_returning_family_scheduling_creates_existing_business_deal(monkeypatch, calls):
    created = []
    def _c(body, summary):
        return {"category": "scheduling", "risk": "low", "confidence": 0.92,
                "routing_target": "x", "sla_tier": "24h", "draft_reply": "ok",
                "reason": "returning family", "student_first_name": "Nomi"}
    monkeypatch.setattr(main, "classify", _c)
    monkeypatch.setattr(main.tw, "enrichment_for_email",
                        lambda e: {"teachworks_match": True, "recent_lessons": 28})
    monkeypatch.setattr(main.hs, "create_deal",
                        lambda name, pl, st, amount=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created.append((name, pl, st, dealtype)) or {"id": "D5"})
    # family's most recent B2C deal is In-Person → deal follows that pipeline
    monkeypatch.setattr(main.hs, "get_contact_deals",
                        lambda cid: [{"id": "100", "pipeline": "default", "stage": "x"},
                                     {"id": "200", "pipeline": "3067397", "stage": "y"}])
    rec = main.process_message("threadR", _msg())
    assert rec.get("deal_created") == "D5"
    assert created == [("Adams - Nomi", "3067397", "3067398", "existingbusiness")]


def test_new_inquiry_no_deal(monkeypatch, calls):
    # No existing-customer signals → no deal creation
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling", confidence=0.95))
    monkeypatch.setattr(main.hs, "create_deal",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create")))
    rec = main.process_message("threadN", _msg())
    assert "deal_created" not in rec


def test_parent_name_from_content_routes(monkeypatch, calls):
    # Teachworks-style notice: sender contact is "Adams" (A-L) but the family named in
    # the CONTENT is Schnider (M-Z) → must route to Yolanda via content extraction.
    def _c(body, summary):
        return {"category": "cancellation", "risk": "low", "confidence": 0.9,
                "routing_target": "x", "sla_tier": "24h", "draft_reply": "",
                "reason": "r", "cancellation_reason": "summer break", "parent_last_name": "Schnider"}
    monkeypatch.setattr(main, "classify", _c)
    rec = main.process_message("threadS", _msg())
    assert rec["owner"] == "yolanda"


def test_pause_reports_leftover_tw_lessons(monkeypatch, calls):
    def _c(body, summary):
        return {"category": "cancellation", "risk": "low", "confidence": 0.95,
                "routing_target": "x", "sla_tier": "24h", "draft_reply": "",
                "reason": "r", "cancellation_reason": "summer", "cancellation_type": "pause",
                "student_first_name": "Layla", "parent_last_name": "Schnider"}
    monkeypatch.setattr(main, "classify", _c)
    monkeypatch.setattr(main.tw, "upcoming_lessons_for_family", lambda em, sf=None: [
        {"account": "in_person", "student": "Layla Schnider", "lesson_id": 1,
         "date": "2026-06-18", "time": "16:45", "status": "Scheduled", "tutor": "KC, Shiwani"}])
    rec = main.process_message("threadTW", _msg())
    assert rec["tw_lessons_left"] == 1
    dm_texts = " ".join(t for _, t in calls["dms"])
    assert "1 TW lesson(s) to remove" in dm_texts


def test_cancellation_reason_captured(monkeypatch, calls):
    def _c(body, summary):
        return {"category": "cancellation", "risk": "low", "confidence": 0.9,
                "routing_target": "x", "sla_tier": "24h", "draft_reply": "ok",
                "reason": "r", "cancellation_reason": "family vacation"}
    monkeypatch.setattr(main, "classify", _c)
    rec = main.process_message("threadC", _msg())
    assert rec["cancellation_reason"] == "family vacation"
    desc = calls["tickets"][0][0][3]            # 4th positional arg to create_ticket
    assert "Cancellation reason: family vacation" in desc


def test_tutor_document_sends_receipt(monkeypatch, calls):
    monkeypatch.setattr(main, "classify", _classify_stub("tutor_document"))
    rec = main.process_message("thread5", _msg())
    assert rec.get("receipt_sent") is True
    assert len(calls["sent"]) == 1              # the only outbound MESSAGE
    assert "A+ Tutoring Team" in calls["sent"][0]
    assert rec["owner"] == "kath"


# ── Ticket naming (Option A: "Lastname, Firstname — Category") ──

def test_subject_lastname_firstname_category(monkeypatch, calls):
    def _c(body, summary):
        return {"category": "cancellation", "risk": "low", "confidence": 0.9,
                "routing_target": "x", "sla_tier": "24h", "draft_reply": "", "reason": "r",
                "cancellation_reason": "moving", "student_first_name": "Layla",
                "parent_last_name": "Schnider"}
    monkeypatch.setattr(main, "classify", _c)
    main.process_message("threadName", _msg())
    assert calls["tickets"][0][0][0] == "Schnider, Layla — Cancellation"


def test_subject_falls_back_to_email_local_part(monkeypatch, calls):
    # Brand-new sender, no CRM match and no student name → use the email local-part.
    monkeypatch.setattr(main.hs, "find_contact_by_email", lambda e: None)
    monkeypatch.setattr(main.hs, "create_contact", lambda *a, **k: {"id": "C9"})
    monkeypatch.setattr(main.hs, "sender_email", lambda m: "newlead@example.com")
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling"))
    main.process_message("threadFB", _msg())
    assert calls["tickets"][0][0][0] == "newlead — Scheduling"


# ── Thread dedup: one conversation = one ticket ──

def _prior(thread_id="threadX", ticket_id="T9", owner="janelle", category="scheduling"):
    return {"thread_id": thread_id, "ticket_id": ticket_id, "owner": owner,
            "category": category, "action_taken": "ticket_created", "sla_due": "2026-06-01T10:00:00"}


def test_reply_on_open_thread_reuses_ticket(monkeypatch, calls):
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [_prior(thread_id="threadX")])
    monkeypatch.setattr(main.hs, "get_ticket", lambda tid: {"properties": {"hs_pipeline_stage": "1378066770"}})  # Needs Approval = open
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling"))
    rec = main.process_message("threadX", _msg())
    assert calls["tickets"] == []                  # no second ticket
    assert rec["action_taken"] == "ticket_followup"
    assert rec["ticket_id"] == "T9"
    assert rec["owner"] == "janelle"               # keeps the ORIGINAL owner, not the reply's route
    assert "stage" not in calls                    # already open → not re-opened
    assert calls["dms"]                            # owner pinged that the customer replied


def test_reply_reopens_waiting_ticket_with_fresh_sla(monkeypatch, calls):
    monkeypatch.setattr(main.audit, "_iter_records",
                        lambda: [_prior(thread_id="threadY", ticket_id="T10", owner="mandy", category="complaint")])
    monkeypatch.setattr(main.hs, "get_ticket", lambda tid: {"properties": {"hs_pipeline_stage": "2"}})  # Waiting on Family
    monkeypatch.setattr(main, "classify", _classify_stub("complaint", draft=""))
    rec = main.process_message("threadY", _msg())
    assert calls["tickets"] == []
    assert rec["action_taken"] == "ticket_reopened"
    assert rec["reopened"] is True
    assert calls["stage"] == [("T10", "1378066770")]   # moved back to Needs Approval
    assert rec.get("sla_due")                           # fresh SLA window, not the stale one


def test_reply_on_closed_thread_creates_new_ticket(monkeypatch, calls):
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [_prior(thread_id="threadZ", ticket_id="T11")])
    monkeypatch.setattr(main.hs, "get_ticket", lambda tid: {"properties": {"hs_pipeline_stage": "4"}})  # Done = closed
    monkeypatch.setattr(main, "classify", _classify_stub("scheduling"))
    rec = main.process_message("threadZ", _msg())
    assert rec["action_taken"] == "ticket_created"     # closed → genuinely fresh ticket
    assert len(calls["tickets"]) == 1
