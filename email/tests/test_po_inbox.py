"""PO-inbox deal handling: advance Waiting-for-PO, create when none, surface on multi."""
import base64

from src import gmail_client as gmc, po_inbox as po


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
    po._handle_deal(_po(po_number="53779"), notes)
    assert "already exists" in notes[0]


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


def test_no_names_no_action(monkeypatch):
    notes = []
    po._handle_deal(_po(school="", student_first="", student_last=""), notes)
    assert "review manually" in notes[0]
