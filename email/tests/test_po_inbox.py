"""PO-inbox deal handling: advance Waiting-for-PO, create when none, surface on multi."""
import base64

import pytest

from src import deal_sync as dsy_mod, gmail_client as gmc, po_inbox as po


@pytest.fixture(autouse=True)
def _stub_immediate_tw_sync(monkeypatch):
    # _handle_deal chains straight into the Teachworks sync — stub it so these
    # tests stay unit-scoped (deal_sync has its own suite).
    monkeypatch.setattr(dsy_mod, "sync_deal",
                        lambda d, **k: {"action_taken": "sync_pilot_logged"})


def _mock_po_prop(monkeypatch, result=None):
    po.hs.find_deals_by_po_number  # ensure attr exists
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: result or [])


def _po(**kw):
    base = {"is_po": True, "school": "iLEAD", "student_first": "Ana", "student_last": "Diaz",
            "po_number": "4471", "amount": "1500", "hours": "10", "summary": "s",
            "draft_reply": "ok", "confidence": 0.95}
    base.update(kw)
    return base


def _cfg_with_waiting(monkeypatch):
    # the advance path stays available if a waiting stage is ever re-added
    c = {"po_inbox": {"deal_pipeline_id": "907748", "waiting_for_po_stage": "W1",
                      "advance_to_stage": "907749"}}
    monkeypatch.setattr(po, "cfg", lambda: c)


def test_single_waiting_deal_advances(monkeypatch):
    _cfg_with_waiting(monkeypatch)
    moved = []
    # stage-scoped search (s set) finds the waiting deal; the PO-dedupe search (no s) finds nothing
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: ([{"id": "D1", "properties": {"dealname": "iLEAD - Ana Diaz"}}]
                                                   if s else []))
    monkeypatch.setattr(po.hs, "move_deal_stage", lambda d, s: moved.append((d, s)))
    notes = []
    po._handle_deal(_po(), notes)
    assert moved == [("D1", "907749")]
    assert any("advanced" in n for n in notes)


def test_retired_waiting_stage_always_creates(monkeypatch):
    # waiting stage retired → never stage-searches; PO has no number (dedupe skipped);
    # prior-deal lookup by student token returns history → Existing Business create.
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: (_ for _ in ()).throw(AssertionError("must not search waiting stage")) if s else [{"id": "old", "properties": {"dealname": "x"}}])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created.append((name, dealtype)) or {"id": "D2"})
    notes = []
    po._handle_deal(_po(po_number=""), notes)
    assert created and created[0][1] == "existingbusiness"   # prior deal found → existing
    assert "Created deal" in notes[0]


def test_no_match_creates_deal(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created.append((name, pl, st, amt, dealtype)) or {"id": "D9"})
    notes = []
    po._handle_deal(_po(), notes)
    assert created and created[0][1] == "907748" and created[0][3] == "1500"
    assert created[0][4] == "newbusiness"   # no prior deals for this student
    assert "Created deal" in notes[0]


def test_multi_match_surfaces(monkeypatch):
    _cfg_with_waiting(monkeypatch)   # advance path needs a waiting stage configured
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: ([{"id": "1", "properties": {"dealname": "a"}},
                                                    {"id": "2", "properties": {"dealname": "b"}}]
                                                   if s else []))
    moved = []
    monkeypatch.setattr(po.hs, "move_deal_stage", lambda d, s: moved.append(d))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create")))
    notes = []
    po._handle_deal(_po(), notes)
    assert moved == [] and "advance manually" in notes[0]


def test_po_number_dedupe_blocks_second_deal(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: [{"id": "X", "properties": {"dealname": "PCA - Carson - PO 53779"}}])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create dup")))
    notes = []
    dms = []
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    po._handle_deal(_po(po_number="53779"), notes)
    assert "DUPLICATE PO" in notes[0]
    assert dms and "URGENT" in dms[0][1] and "53779" in dms[0][1]


def test_thread_dedupe(monkeypatch):
    monkeypatch.setattr(po.audit, "_iter_records",
                        lambda: iter([{"source": "po_inbox", "thread_id": "TH1"}]))
    assert po._thread_already_handled("TH1") is True
    assert po._thread_already_handled("TH2") is False


def test_created_deal_gets_parent_contact(monkeypatch):
    # Unique family-contact match → the deal is created WITH the parent associated
    # (that's what lets the Teachworks sync key the family by email downstream).
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: [{"id": "C7", "properties": {"firstname": "Maria", "lastname": "Diaz"}}])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created.append(contact_id) or {"id": "D3"})
    notes = []
    po._handle_deal(_po(), notes)
    assert created == ["C7"]
    assert "linked to family contact Maria Diaz" in notes[0]


def test_created_deal_ambiguous_contact_flagged(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: [{"id": "C1", "properties": {}}, {"id": "C2", "properties": {}}])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created.append(contact_id) or {"id": "D4"})
    notes = []
    po._handle_deal(_po(), notes)
    assert created == [None]
    assert "no unique family match" in notes[0]


def test_parent_from_po_creates_contact(monkeypatch):
    # Parent info extracted from the PO attachment → HubSpot contact created + on the deal.
    created_deal, created_contact = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None: created_contact.append((e, f, l, phone)) or {"id": "C9"})
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: (_ for _ in ()).throw(AssertionError("must not fall back")))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created_deal.append(contact_id) or {"id": "D8"})
    notes = []
    po._handle_deal(_po(parent_email="Kenna@Gmail.com", parent_first="Mckenna",
                        parent_last="Tschumperlin", parent_phone="555-1"), notes)
    assert created_contact == [("kenna@gmail.com", "Mckenna", "Tschumperlin", "555-1")]
    assert created_deal == ["C9"]
    assert "CREATED HubSpot contact" in notes[0]


def test_parent_email_existing_contact_linked(monkeypatch):
    created_deal = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C5"})
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create")))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None, owner_id=None, closedate_ms=None, extra_props=None:
                        created_deal.append(contact_id) or {"id": "D8"})
    notes = []
    po._handle_deal(_po(parent_email="kenna@gmail.com"), notes)
    assert created_deal == ["C5"]
    assert "linked to existing contact" in notes[0]


def test_content_blocks_attachments():
    blocks = po._content_blocks("body", "subj", "from", [
        {"filename": "po.pdf", "mime": "application/pdf", "data_b64": "QUJD"},
        {"filename": "scan.png", "mime": "image/png", "data_b64": "REVG"}])
    assert blocks[1]["type"] == "document"
    assert blocks[1]["source"]["media_type"] == "application/pdf"
    assert blocks[2]["type"] == "image"
    assert blocks[-1]["type"] == "text"


def test_get_attachments_filters_and_converts(monkeypatch):
    payload = {"payload": {"parts": [
        {"filename": "po.pdf", "mimeType": "application/pdf",
         "body": {"data": base64.urlsafe_b64encode(b"PDFDATA").decode()}},
        {"filename": "notes.docx",
         "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "body": {"data": "eHg="}},
        {"filename": "", "mimeType": "text/plain", "body": {"data": "eHg="}},
    ]}}
    monkeypatch.setattr(gmc, "_get", lambda p, params=None: payload)
    atts = gmc.get_attachments("M1")
    assert [a["filename"] for a in atts] == ["po.pdf"]
    assert base64.b64decode(atts[0]["data_b64"]) == b"PDFDATA"


def test_tor_associated_to_created_deal(monkeypatch):
    created_contacts, assoc = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None: created_contacts.append(e) or {"id": f"C-{e}"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: assoc.append((d, c)))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", parent_first="Lara", parent_last="Perkins",
                        tor_email="Terri@School.org", tor_first="Terri", tor_last="Tor"), notes)
    assert created_contacts == ["mom@x.com", "terri@school.org"]   # parent + TOR created
    assert assoc == [("D66", "C-terri@school.org")]                # TOR associated post-create
    assert any("TOR Terri Tor" in n for n in notes)


def test_tor_same_as_parent_not_duplicated(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal",
                        lambda *a: (_ for _ in ()).throw(AssertionError("no TOR assoc")))
    notes = []
    po._handle_deal(_po(parent_email="same@x.com", tor_email="same@x.com"), notes)
    assert not any("TOR" in n for n in notes)


def test_po_pdf_attached_to_created_deal(monkeypatch):
    uploads, notes_created = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D77"})
    monkeypatch.setattr(po.hs, "upload_file",
                        lambda fn, data, mime, folder_path="/po-inbox": uploads.append((fn, data, mime)) or "F1")
    monkeypatch.setattr(po.hs, "add_deal_note",
                        lambda did, body, att=None: notes_created.append((did, att)) or {"id": "N1"})
    notes = []
    atts = [{"filename": "po.pdf", "mime": "application/pdf",
             "data_b64": base64.b64encode(b"PDF").decode()}]
    po._handle_deal(_po(), notes, atts)
    assert uploads == [("po.pdf", b"PDF", "application/pdf")]
    assert notes_created == [("D77", ["F1"])]
    assert any("PO document attached" in n for n in notes)


def test_po_upload_failure_asks_manual(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D77"})
    monkeypatch.setattr(po.hs, "upload_file", lambda fn, data, mime, folder_path="/po-inbox": None)
    monkeypatch.setattr(po.hs, "add_deal_note",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no note without files")))
    notes = []
    atts = [{"filename": "po.pdf", "mime": "application/pdf",
             "data_b64": base64.b64encode(b"PDF").decode()}]
    po._handle_deal(_po(), notes, atts)
    assert any("attach the PDF to the deal manually" in n for n in notes)


def test_invoice_task_created_with_po_fields(monkeypatch):
    tasks = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D55"})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda subj, body, owner, due, priority="MEDIUM", contact_id=None:
                        tasks.append((subj, body, priority)) or {"id": "T1"})
    notes = []
    po._handle_deal(_po(), notes)
    assert tasks and "Convert PO to TW invoice" in tasks[0][0] and "$1500" in tasks[0][0]
    assert "PO #: 4471" in tasks[0][1] and tasks[0][2] == "HIGH"
    assert any("Convert-to-TW-invoice task created" in n for n in notes)


def test_po_month_end_parsing():
    assert po._po_month_end("2026-08").strftime("%Y-%m-%d") == "2026-08-31"
    assert po._po_month_end("2027-02").strftime("%Y-%m-%d") == "2027-02-28"
    assert po._po_month_end("") is None
    assert po._po_month_end("Aug 2026") is None
    assert po._po_month_end("2026-13") is None


def test_invoice_due_end_of_po_month_and_deal_stamped(monkeypatch):
    tasks, patches = [], []
    base = dict(po.cfg())
    base["po_inbox"] = {**base["po_inbox"],
                       "invoice_task": {"enabled": True, "owner": "kath",
                                        "invoice_due_property": "invoice_due_date"}}
    monkeypatch.setattr(po, "cfg", lambda: base)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D44"})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None: patches.append((path, payload)) or {})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda subj, body, owner, due, priority="MEDIUM", contact_id=None:
                        tasks.append((body, due)) or {"id": "T1"})
    notes = []
    po._handle_deal(_po(po_month="2026-08"), notes)
    deal_patch = [p_ for p_ in patches if p_[0] == "/crm/v3/objects/deals/D44"]
    assert deal_patch and deal_patch[0][1]["properties"]["invoice_due_date"] == "2026-08-31"
    assert tasks and "Submit to the school's ops system by: Aug 31, 2026" in tasks[0][0]
    assert any("Convert-to-TW-invoice task" in n for n in notes)


def test_no_amount_no_invoice_task(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D55"})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no task without amount")))
    notes = []
    po._handle_deal(_po(amount=""), notes)
    assert not any("invoice" in n.lower() for n in notes)


def test_levelup_po_routes_to_levelup_pipeline(monkeypatch):
    created = []
    base = dict(po.cfg())
    base["po_inbox"] = {**base["po_inbox"], "levelup_pipeline_id": "LU1",
                        "levelup_stage_id": "LU-pre"}
    monkeypatch.setattr(po, "cfg", lambda: base)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append((pl, st)) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(level_up=True), notes)
    assert created == [("LU1", "LU-pre")]
    assert any("LEVEL UP PO" in n for n in notes)


def test_levelup_unconfigured_warns(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(pl) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(level_up=True), notes)
    assert created == ["907748"]   # falls back to default charter pipeline
    assert any("MOVE IT" in n for n in notes)


def test_created_deal_syncs_to_tw_immediately(monkeypatch):
    synced = []
    monkeypatch.setattr(dsy_mod, "sync_deal",
                        lambda d, **k: synced.append(d) or {"action_taken": "tw_synced"})
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D33"})
    notes = []
    po._handle_deal(_po(), notes)
    assert synced and synced[0]["id"] == "D33" and synced[0]["properties"]["po_number"] == "4471"
    assert any("Teachworks sync ran immediately: tw_synced" in n for n in notes)


def test_po_never_gets_a_reply_draft():
    # belt & braces lives in process_po_message: is_po forces draft to ""
    assert ("" if {"is_po": True, "draft_reply": "thanks!"}.get("is_po") else "thanks!") == ""
    # and the extraction prompt itself forbids PO drafts
    from src.po_inbox import PO_SYSTEM
    assert "ALWAYS empty" in PO_SYSTEM and "never reply to purchase" in PO_SYSTEM


def test_student_properties_stamped_on_deal(monkeypatch):
    patches = []
    base = dict(po.cfg())
    base["po_inbox"] = {**base["po_inbox"], "deal_property_map": {
        "student_first": "student_first_name", "student_last": "student_last_name",
        "grade": "grade_level", "school": "school_name"}}
    monkeypatch.setattr(po, "cfg", lambda: base)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None: patches.append((path, payload)) or {})
    notes = []
    po._handle_deal(_po(grade="4"), notes)
    stamp = [x for x in patches if x[0] == "/crm/v3/objects/deals/D22"
             and "student_first_name" in (x[1] or {}).get("properties", {})]
    assert stamp and stamp[0][1]["properties"] == {
        "student_first_name": "Ana", "student_last_name": "Diaz",
        "grade_level": "4", "school_name": "iLEAD"}


def test_missing_grade_flagged_for_manual_fill(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    notes = []
    po._handle_deal(_po(), notes)   # no grade in the PO
    assert any("Not in the PO: grade" in n for n in notes)


def test_no_upcoming_lessons_posts_to_channel(monkeypatch):
    posts = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "upcoming_lessons_for_family", lambda e, sf: [])
    monkeypatch.setattr(po.slack_client, "post_message", lambda ch, t: posts.append((ch, t)))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert posts and "nothing on the calendar" in posts[0][1] and "Ana Diaz" in posts[0][1]
    assert any("scheduling alert posted" in n for n in notes)


def test_upcoming_lessons_no_channel_post(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "upcoming_lessons_for_family",
                        lambda e, sf: [{"lesson_id": 1}, {"lesson_id": 2}])
    monkeypatch.setattr(po.slack_client, "post_message",
                        lambda *a: (_ for _ in ()).throw(AssertionError("must not post")))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert any("2 upcoming lesson(s) already on the calendar" in n for n in notes)


def test_no_names_no_action(monkeypatch):
    notes = []
    po._handle_deal(_po(school="", student_first="", student_last=""), notes)
    assert "review manually" in notes[0]
