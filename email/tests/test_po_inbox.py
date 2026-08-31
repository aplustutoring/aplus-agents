"""PO-inbox deal handling: advance Waiting-for-PO, create when none, surface on multi."""
import base64

import pytest

from src import deal_sync as dsy_mod, gmail_client as gmc, po_inbox as po


@pytest.fixture(autouse=True)
def _reset_run_seq():
    # 'School N' numbering is RUN-scoped (module-level _RUN_SEQ) — clear it so
    # each test counts from its own mocked search results.
    po._RUN_SEQ.clear()
    yield
    po._RUN_SEQ.clear()


@pytest.fixture(autouse=True)
def _default_student_search(monkeypatch):
    # _next_school_seq now searches by student NAME PROPERTIES; default to no
    # history so legacy tests keep N=1. Seq tests override with real rows.
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda first, last=None: [], raising=False)


@pytest.fixture(autouse=True)
def _stub_immediate_tw_sync(monkeypatch):
    # _handle_deal chains straight into the Teachworks sync — stub it so these
    # tests stay unit-scoped (deal_sync has its own suite).
    monkeypatch.setattr(dsy_mod, "sync_deal",
                        lambda d, **k: {"action_taken": "sync_pilot_logged"})


@pytest.fixture(autouse=True)
def _stub_contact_associations(monkeypatch):
    # #AP031 family→TOR sync reads/writes contact associations — inert by
    # default so unrelated tests never touch the network; the sync tests
    # override these with recorders.
    monkeypatch.setattr(po.hs, "get_contact_to_contact_associations", lambda cid: [])
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda f, t, type_id=15, category="USER_DEFINED": {"id": "A1"})
    monkeypatch.setattr(po.hs, "find_contact_by_secondary_email", lambda e: None)
    monkeypatch.setattr(po.hs, "get_deal_contacts", lambda did: [])


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
    # stage_label fetches /crm/v3/pipelines/deals LIVE — unstubbed it 401s in CI
    # and would hit the real portal on any machine with a token in env.
    monkeypatch.setattr(po.hs, "stage_label", lambda pipeline, stage: "presented")
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
    # only a processed REAL PO closes a thread…
    monkeypatch.setattr(po.audit, "_iter_records",
                        lambda: iter([{"source": "po_inbox", "thread_id": "TH1",
                                       "category": "new_po"}]))
    assert po._thread_already_handled("TH1") is True
    assert po._thread_already_handled("TH2") is False


def test_review_thread_stays_open(monkeypatch):
    # …a review-only record (order agreement, "THIS IS NOT A PO") does NOT —
    # the actual POs often arrive as replies on that same thread.
    monkeypatch.setattr(po.audit, "_iter_records",
                        lambda: iter([{"source": "po_inbox", "thread_id": "TH1",
                                       "category": "po_inbox_other"}]))
    assert po._thread_already_handled("TH1") is False


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
                        lambda e, f=None, l=None, phone=None, extra_props=None:
                        created_contact.append((e, f, l, phone)) or {"id": "C9"})
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
                        lambda e, f=None, l=None, phone=None, extra_props=None:
                        created_contacts.append(e) or {"id": f"C-{e}"})
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
    assert po._po_month_end("2026-13") is None
    # prose formats extractors actually return (caught by the Milo dry run):
    assert po._po_month_end("August 2026").strftime("%Y-%m-%d") == "2026-08-31"
    assert po._po_month_end("Aug 2026").strftime("%Y-%m-%d") == "2026-08-31"
    assert po._po_month_end("8/2026").strftime("%Y-%m-%d") == "2026-08-31"
    assert po._po_month_end("2026-8").strftime("%Y-%m-%d") == "2026-08-31"


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
    due_patch = [p_ for p_ in patches if p_[0] == "/crm/v3/objects/deals/D44"
                 and "invoice_due_date" in (p_[1] or {}).get("properties", {})]
    assert due_patch and due_patch[0][1]["properties"]["invoice_due_date"] == "2026-08-31"
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


def test_levelup_configured_in_real_config():
    # the live config carries the verified Level Up A ids
    pc = po.cfg()["po_inbox"]
    assert pc["levelup_pipeline_id"] == "88841552"
    assert pc["levelup_stage_id"] == "164922249"


def test_levelup_unconfigured_warns(monkeypatch):
    created = []
    base = dict(po.cfg())
    base["po_inbox"] = {**base["po_inbox"], "levelup_pipeline_id": "", "levelup_stage_id": ""}
    monkeypatch.setattr(po, "cfg", lambda: base)
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
    assert any("not resolvable from records: grade" in n for n in notes)


def test_no_upcoming_lessons_posts_to_channel(monkeypatch):
    posts = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.slack_client, "post_message", lambda ch, t: posts.append((ch, t)))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert posts and "nothing on the calendar" in posts[0][1] and "Ana Diaz" in posts[0][1]
    assert any("scheduling alert posted" in n for n in notes)


def test_upcoming_lessons_no_channel_post(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 1, "upcoming": 2})
    monkeypatch.setattr(po.slack_client, "post_message",
                        lambda *a: (_ for _ in ()).throw(AssertionError("must not post")))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert any("2 upcoming lesson(s) already on the calendar" in n for n in notes)


def test_no_names_no_action(monkeypatch):
    notes = []
    po._handle_deal(_po(school="", student_first="", student_last=""), notes)
    assert "review manually" in notes[0]


# ── #AP031: family→TOR association sync + persona stamping ──────────────────

def _tor_link(to_id, type_id=15, category="USER_DEFINED"):
    return {"toObjectId": to_id,
            "associationTypes": [{"category": category, "typeId": type_id,
                                  "label": "Teacher of Record"}]}


def test_family_tor_already_linked_noop(monkeypatch):
    # (a) family already linked to THIS TOR → no association write, no flag.
    monkeypatch.setattr(po.hs, "get_contact_to_contact_associations",
                        lambda cid: [_tor_link("T1")])
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not re-link")))
    notes = []
    po._sync_family_tor("F1", "T1", "Terri Tor", notes)
    assert notes == []


def test_family_tor_link_created_when_missing(monkeypatch):
    # (b) no typeId-15 link (unlabeled/other associations don't count) → create.
    linked = []
    monkeypatch.setattr(po.hs, "get_contact_to_contact_associations",
                        lambda cid: [_tor_link("X9", type_id=449, category="HUBSPOT_DEFINED")])
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda f, t, type_id=15, category="USER_DEFINED":
                        linked.append((f, t, type_id, category)) or {"id": "A1"})
    notes = []
    po._sync_family_tor("F1", "T1", "Terri Tor", notes)
    assert linked == [("F1", "T1", 15, "USER_DEFINED")]
    assert any("Family → TOR association created" in n for n in notes)


def test_family_tor_different_tor_adds_and_flags(monkeypatch):
    # (c) family linked to a DIFFERENT TOR → ADD the new link, flag the change,
    # never remove the old one (multi-kid families have multiple TORs).
    linked = []
    monkeypatch.setattr(po.hs, "get_contact_to_contact_associations",
                        lambda cid: [_tor_link("OLD-TOR")])
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda f, t, type_id=15, category="USER_DEFINED":
                        linked.append((f, t)) or {"id": "A2"})
    notes = []
    po._sync_family_tor("F1", "NEW-TOR", "Terri Tor", notes)
    assert linked == [("F1", "NEW-TOR")]          # added, nothing removed
    flag = next(n for n in notes if "TOR CHANGE" in n)
    assert "OLD-TOR" in flag and "existing links kept" in flag


def test_sync_runs_from_create_path_with_family(monkeypatch):
    # End-to-end through _handle_deal: parent created from PO + TOR created →
    # the family→TOR link lands with the created ids.
    linked = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None: {"id": f"C-{e}"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda f, t, type_id=15, category="USER_DEFINED":
                        linked.append((f, t)) or {"id": "A3"})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="terri@school.org",
                        tor_first="Terri", tor_last="Tor"), notes)
    assert linked == [("C-mom@x.com", "C-terri@school.org")]


def test_persona_stamped_on_created_tor_and_parent(monkeypatch):
    # (d) contacts CREATED by this agent carry personas; TOR also gets lead status.
    created = {}
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None:
                        created.update({e: extra_props}) or {"id": f"C-{e}"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="terri@school.org"), notes)
    assert created["mom@x.com"] == {"a_persona": "Family"}
    assert created["terri@school.org"] == {"hs_lead_status": "Charter School Teacher TOR/EF",
                                           "a_persona": "Teacher of Record/EF/ES"}


def test_existing_contacts_never_persona_patched(monkeypatch):
    # Existing parent + TOR found by email → no create, no property writes at all.
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": f"C-{e}"})
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create")))
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="terri@school.org"), notes)
    assert not any("CREATED" in n for n in notes)


def test_tor_matched_via_secondary_email(monkeypatch):
    # Primary-email miss but secondary hit (the Kristy Doyal case) → the
    # existing contact is used, flagged, and NO duplicate is created.
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C-mom"} if e == "mom@x.com" else None)
    monkeypatch.setattr(po.hs, "find_contact_by_secondary_email",
                        lambda e: {"id": "C-kristy"})
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no duplicate TOR")))
    assoc = []
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: assoc.append(c))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com",
                        tor_email="kristy.doyal@heartlandcharterschool.com"), notes)
    assert assoc == ["C-kristy"]
    assert any("SECONDARY email" in n for n in notes)


# ── multi-PO emails: one deal per PO number ──────────────────────────────────

def test_multi_po_email_creates_deal_per_po(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None,
                        owner_id=None, closedate_ms=None, extra_props=None:
                        created.append((extra_props.get("po_number"), amt)) or
                        {"id": f"D-{extra_props.get('po_number')}"})
    tasks = []
    monkeypatch.setattr(po.hs, "create_task",
                        lambda subj, body, owner, due, priority="MEDIUM", contact_id=None:
                        tasks.append(subj) or {"id": "T"})
    notes = []
    po._handle_deal(_po(po_number="", pos=[
        {"po_number": "3114047368", "amount": "150", "po_month": "2026-08"},
        {"po_number": "3114047369", "amount": "300", "po_month": "2026-09"},
        {"po_number": "3114047370", "amount": "300", "po_month": "2026-10"},
    ]), notes)
    assert created == [("3114047368", "150"), ("3114047369", "300"), ("3114047370", "300")]
    assert len(tasks) == 3                       # one invoice task per PO month
    assert any("Multi-PO email: 3 POs" in n for n in notes)


def test_comma_jammed_po_numbers_split_with_flag(monkeypatch):
    # extractor fallback: numbers mashed into po_number → one deal each,
    # amounts flagged for manual fill (never one mashed deal).
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None,
                        owner_id=None, closedate_ms=None, extra_props=None:
                        created.append((extra_props.get("po_number"), amt)) or {"id": "D"})
    notes = []
    po._handle_deal(_po(po_number="3114047368, 3114047369"), notes)
    assert [c[0] for c in created] == ["3114047368", "3114047369"]
    assert all(c[1] is None for c in created)
    assert any("fill on the deal manually" in n for n in notes)


def test_multi_po_scheduling_alert_fires_once(monkeypatch):
    posts = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: None)   # scheduler DM is separate
    monkeypatch.setattr(po.slack_client, "post_message", lambda ch, t: posts.append(t))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", po_number="", pos=[
        {"po_number": "A1", "amount": "100"}, {"po_number": "A2", "amount": "100"}]), notes)
    assert len(posts) == 1                       # per email, not per PO


def test_single_po_unchanged_by_split():
    assert po._split_pos(_po()) == [_po()]
    assert po._split_pos(_po(po_number="4471"))[0]["po_number"] == "4471"


# ── parent resolution via the student's prior deal (Kath's manual lookup) ────

def _deal(did, name):
    return {"id": did, "properties": {"dealname": name}}


def _contact(cid, email, first, last, persona=""):
    return {"id": cid, "properties": {"email": email, "firstname": first,
                                      "lastname": last, "a_persona": persona}}


def test_parent_resolved_from_prior_deal(monkeypatch):
    # PO has NO parent info; student has a prior deal → parent read off it.
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda f, l=None: [_deal("D-old", "Maria Diaz - Ana - iLead (Jul) 25/26")])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "get_deal_contacts",
                        lambda did: [_contact("C-mom", "maria@x.com", "Maria", "Diaz", "Family"),
                                     _contact("C-tor", "tor@school.org", "Terri", "Tor",
                                              "Teacher of Record/EF/ES")])
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: (_ for _ in ()).throw(AssertionError("deal lookup must win")))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, dealtype=None,
                        owner_id=None, closedate_ms=None, extra_props=None:
                        created.append(contact_id) or {"id": "D-new"})
    notes = []
    po._handle_deal(_po(parent_email="", tor_email="tor@school.org", po_number=""), notes)
    assert created == ["C-mom"]
    assert any("resolved from the student's prior deal" in n for n in notes)


def test_prior_deal_tor_never_picked_as_parent(monkeypatch):
    # The only non-TOR-filterable signal is persona/email — a deal whose only
    # contacts are TORs must NOT resolve, falling through to last-name search.
    fell_through = []
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda f, l=None: [_deal("D-old", "Ana deal")])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "get_deal_contacts",
                        lambda did: [_contact("C-tor", "tor@school.org", "Terri", "Tor",
                                              "Teacher of Record/EF/ES")])
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: fell_through.append(1) or [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D-new"})
    notes = []
    po._handle_deal(_po(parent_email="", tor_email="tor@school.org", po_number=""), notes)
    assert fell_through == [1]


def test_ambiguous_prior_deals_fall_through(monkeypatch):
    # Two different parents across matching deals → ambiguous → last-name path.
    fell_through = []
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda f, l=None: [_deal("D1", "P1 - Ana"), _deal("D2", "P2 - Ana")])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "get_deal_contacts",
                        lambda did: [_contact(f"C-{did}", f"{did}@x.com", "P", did)])
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: fell_through.append(1) or [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D-new"})
    notes = []
    po._handle_deal(_po(parent_email="", po_number=""), notes)
    assert fell_through == [1]


def test_prior_deal_narrowed_by_student_lastname(monkeypatch):
    # Common first name over-matches; the EXACT first+last property search only
    # ever sees this student's own deals (post-Mateo-incident contract).
    searched = []
    def by_student(first, last=None):
        searched.append((first, last))
        return [_deal("D-right", "Maria Diaz - Ana Diaz - iLead")] if last == "Diaz" else []
    monkeypatch.setattr(po.hs, "search_deals_by_student", by_student)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    calls = []
    monkeypatch.setattr(po.hs, "get_deal_contacts",
                        lambda did: calls.append(did) or [_contact("C-mom", "m@x.com", "Maria", "Diaz")])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D-new"})
    notes = []
    po._handle_deal(_po(parent_email="", po_number=""), notes)
    assert ("Ana", "Diaz") in searched
    assert calls == ["D-right"]          # only this student's own deal is consulted


# ── deal naming: "Parent - Student - School N - YY/YY" (Roman, 2026-08-10) ───

def test_school_year_tag():
    assert po._school_year_tag({"po_month": "2026-08"}) == "26/27"
    assert po._school_year_tag({"po_month": "2027-01"}) == "26/27"
    assert po._school_year_tag({"po_month": "2027-07"}) == "26/27"
    assert po._school_year_tag({"po_month": "2027-09"}) == "27/28"


def test_deal_name_parent_student_school_seq_year(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None: {"id": "C9"})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", parent_first="Maria", parent_last="Diaz",
                        po_number="", po_month="2026-08"), notes)
    assert created == ["Maria Diaz - Ana Diaz - iLead 1 - 26/27"]


def test_deal_name_seq_counts_existing_school_year_deals(monkeypatch):
    # student already has "iLead 1" this school year → the new deal is "iLead 2"
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda first, last=None: [_deal("D0", "Maria Diaz - Ana Diaz - iLead 1 - 26/27")])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D"})
    notes = []
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", po_month="2026-09"), notes)
    assert created == ["Maria Diaz - Ana Diaz - iLead 2 - 26/27"]


def test_multi_po_email_seq_staggers(monkeypatch):
    # 3 POs in one email → iLead 1 / 2 / 3 (search can't see sibling deals yet)
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D"})
    notes = []
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "A1", "amount": "100", "po_month": "2026-08"},
        {"po_number": "A2", "amount": "100", "po_month": "2026-09"},
        {"po_number": "A3", "amount": "100", "po_month": "2026-10"}]), notes)
    assert created == ["Maria Diaz - Ana Diaz - iLead 1 - 26/27",
                       "Maria Diaz - Ana Diaz - iLead 2 - 26/27",
                       "Maria Diaz - Ana Diaz - iLead 3 - 26/27"]


def test_unmapped_school_used_asis_and_flagged(monkeypatch):
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D"})
    notes = []
    po._handle_deal(_po(school="Zeta Academy", po_number="", parent_email="mom@x.com",
                        po_month="2026-09"), notes)
    assert created == ["Maria Diaz - Ana Diaz - Zeta Academy 1 - 26/27"]
    assert any("no shorthand" in n for n in notes)


# ── parent chase: missing parent info → draft to TOR → reply auto-resolves ───

def test_missing_parent_names_deal_and_opens_chase(monkeypatch):
    created, drafts, appended = [], [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D9"})
    monkeypatch.setattr(po.gm, "create_draft_reply",
                        lambda tid, to, subj, body, irt="", **kw: drafts.append((tid, to, body)) or {"id": "DR1"})
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    msg = {"threadId": "TH9", "sender": "Terri Tor <terri@school.org>",
           "subject": "PO for Ana", "message_id_header": "<m1>"}
    notes = []
    po._handle_deal(_po(po_number="", po_month="2026-08",
                        tor_email="terri@school.org", tor_first="Terri"), notes, msg=msg)
    assert created and created[0] == "NEEDS PARENT - Ana Diaz - iLead 1 - 26/27"
    assert drafts and drafts[0][0] == "TH9" and drafts[0][1] == "terri@school.org"
    assert "full name" in drafts[0][2] and "Phone number" in drafts[0][2]
    chases = [r for r in appended if r.get("action_taken") == "parent_chase_opened"]
    assert chases and chases[0]["deal_id"] == "D9" and chases[0]["thread_id"] == "TH9"
    assert chases[0]["pipeline"] == "907748"
    assert any("DRAFTED" in n for n in notes)


def test_no_chase_without_msg_context(monkeypatch):
    # unit-scoped calls (no Gmail message) must not attempt a draft
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D9"})
    monkeypatch.setattr(po.gm, "create_draft_reply",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no draft without msg")))
    notes = []
    po._handle_deal(_po(po_number=""), notes)
    assert not any("DRAFTED" in n for n in notes)


def test_parent_reply_resolves_chase(monkeypatch):
    assoc, patches, synced, appended = [], [], [], []
    chase = {"deal_id": "D9", "deal_name": "NEEDS PARENT - Ana Diaz - iLead 1 - 26/27",
             "pipeline": "907748", "po_number": "4471", "thread_id": "TH9",
             "tor_email": "terri@school.org"}
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: None if e == "mom@x.com" else {"id": "C-tor"})
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: assoc.append((d, c)))
    monkeypatch.setattr(po.hs, "_write",
                        lambda m_, p_, payload=None: patches.append((p_, payload)) or {})
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(dsy_mod, "sync_deal",
                        lambda d, **k: synced.append(d) or {"action_taken": "tw_synced"})
    notes = []
    po._resolve_parent_chase(chase, {"parent_email": "Mom@X.com", "parent_first": "Maria",
                                     "parent_last": "Diaz", "parent_phone": "555-2"}, notes)
    assert assoc == [("D9", "C-mom")]
    renames = [p for p in patches if (p[1] or {}).get("properties", {}).get("dealname")]
    assert renames and renames[0][1]["properties"]["dealname"] == \
        "Maria Diaz - Ana Diaz - iLead 1 - 26/27"
    assert synced and synced[0]["id"] == "D9" and synced[0]["properties"]["po_number"] == "4471"
    assert any(r.get("action_taken") == "parent_chase_resolved" for r in appended)
    assert any("PARENT RESOLVED" in n for n in notes)
    assert any("Family → TOR association created" in n for n in notes)  # #AP031 rides along


def test_resolved_chase_thread_no_longer_open(monkeypatch):
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9"},
            {"action_taken": "parent_chase_resolved", "thread_id": "TH9", "deal_id": "D9"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    assert po._open_chases() == {}


def test_parent_chase_escalates_after_window(monkeypatch):
    dms, appended = [], []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "NEEDS PARENT - Ana Diaz - iLead 1 - 26/27",
             "chase_to": "terri@school.org", "sla_due": "2026-08-01T10:00:00-07:00",
             "timestamp": "2026-07-31T10:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append(t))
    po._sweep_parent_chases()
    # legacy chase (no draft_id) past both windows → Paola ping + escalation
    assert any("NO parent info" in t and "terri@school.org" in t for t in dms)
    assert any("STILL MISSING" in t for t in dms)
    acts = [a.get("action_taken") for a in appended]
    assert "parent_chase_escalated" in acts and "parent_chase_sales_notified" in acts
    # second sweep: already escalated + pinged → silent
    recs.extend(appended)
    dms.clear()
    po._sweep_parent_chases()
    assert dms == []


def test_norm_po_number():
    # Roman 2026-08-10: the number only, never a PO prefix
    assert po._norm_po_number("PO7514044381") == "7514044381"
    assert po._norm_po_number("PO 7514044381") == "7514044381"
    assert po._norm_po_number("P.O. #7514044381") == "7514044381"
    assert po._norm_po_number("po#7514044381") == "7514044381"
    assert po._norm_po_number("7514044381") == "7514044381"
    assert po._norm_po_number("PF593736") == "PF593736"   # letters IN the number stay
    assert po._norm_po_number("") == ""
    assert po._norm_po_number(None) == ""


def test_po_prefix_stripped_before_dedupe_and_deal(monkeypatch):
    searched, created = [], []
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: searched.append(n) or [])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        created.append(extra_props.get("po_number")) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(po_number="PO7514044381"), notes)
    assert searched == ["7514044381"]      # dedupe uses the bare number
    assert created == ["7514044381"]       # property stamped without the prefix


# ── "THIS IS NOT A PO" order agreements ARE POs (Roman, 2026-08-10) ──────────

def test_prompt_treats_order_agreements_as_pos():
    from src.po_inbox import PO_SYSTEM
    assert "THIS IS" in PO_SYSTEM and "NOT A PO" in PO_SYSTEM
    assert "pending_approval" in PO_SYSTEM


def test_pending_approval_flagged_on_deal_and_task(monkeypatch):
    created, tasks = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D"})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda subj, body, owner, due, priority="MEDIUM", contact_id=None:
                        tasks.append(body) or {"id": "T"})
    notes = []
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pending_approval=True, pos=[
        {"po_number": "3114047368", "amount": "150", "po_month": "2026-08"},
        {"po_number": "3114047369", "amount": "300", "po_month": "2026-09"}]), notes)
    assert len(created) == 2                          # one deal per pending PO
    assert any("PENDING school approval" in n for n in notes)
    assert all("PENDING school approval" in b for b in tasks)


# ── thread guard vs parent chase: the TOR's reply must get through ───────────

def test_closed_thread_detection(monkeypatch):
    # closed threads are LABELED now, never skipped (the Zie Rojas amount
    # correction was silently dropped by the old skip, 2026-08-12)
    monkeypatch.setattr(po, "_thread_already_handled", lambda t: True)
    monkeypatch.setattr(po, "_open_chases",
                        lambda: {"TH-open": {"deal_id": "D9"}})
    assert po._closed_thread("TH-open") is False       # chase waiting
    assert po._closed_thread("TH-closed") is True      # closed → gets labeled


def test_tor_first_name_variant_unique_lastname_matches(monkeypatch):
    # PO says 'Christina', portal has 'Christine' — unique last-name match
    # within the TOR pool wins anyway (the Mondolo case)
    assoc = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "find_tor_contacts_by_lastname",
                        lambda ln: [{"id": "C-tor", "properties":
                                     {"firstname": "Christine", "lastname": "Mondolo",
                                      "email": "christina.mondolo@ileadexploration.org"}}])
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: assoc.append(c))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com",
                        tor_first="Christina", tor_last="Mondolo"), notes)
    assert assoc == ["C-tor"]
    assert any("matched by NAME" in n for n in notes)


def test_gross_po_value_in_prompt():
    from src.po_inbox import PO_SYSTEM
    assert "NEVER the net payout" in PO_SYSTEM


# ── Slack routing flag + direct scheduler DM (Roman, 2026-08-10) ─────────────

def test_slack_routing_flag_set_on_created_deal(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(), [])
    # the HubSpot workflow behind this checkbox posts the deal to the
    # pipeline's Slack channel
    assert captured[0]["should_this_deal_be_posted_to_a_slack_channel_"] == "true"


def test_scheduler_dm_once_per_email_with_pending_flag(monkeypatch):
    dms = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D"})
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    notes = []
    po._handle_deal(_po(po_number="", pending_approval=True, pos=[
        {"po_number": "A1", "amount": "100", "po_month": "2026-08"},
        {"po_number": "A2", "amount": "100", "po_month": "2026-09"}]), notes)
    # Diaz → A-L scheduler (Janelle); ONE DM for the whole email, not per deal
    assert len(dms) == 1
    assert dms[0][0] == po.cfg()["staff"]["janelle"]["slack_user_id"]
    assert "2 new PO deal(s)" in dms[0][1] and "Post-Lesson" in dms[0][1]
    assert "PENDING school approval" in dms[0][1]
    assert any("Scheduler Janelle DM'd" in n for n in notes)


def test_no_scheduler_dm_when_nothing_created(monkeypatch):
    # stage_label fetches /crm/v3/pipelines/deals LIVE — unstubbed it 401s in CI
    # and would hit the real portal on any machine with a token in env.
    monkeypatch.setattr(po.hs, "stage_label", lambda pipeline, stage: "presented")
    # duplicate PO → no deal → no scheduler DM (only the duplicate alert to Kath)
    dms = []
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: [{"id": "X", "properties": {"dealname": "dup"}}])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create")))
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    po._handle_deal(_po(po_number="53779"), [])
    assert len(dms) == 1 and "duplicate po" in dms[0][1].lower()


# ── TOR name-only fallback (Roman, 2026-08-10): OPS PDFs omit the email ──────

def test_fold_name_accent_insensitive():
    assert po._fold_name("Véronique") == po._fold_name("Veronique")
    assert po._fold_name("  MARY ") == "mary"


def test_tor_name_only_unique_match_associates(monkeypatch):
    assoc, linked = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C-mom", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    monkeypatch.setattr(po.hs, "find_tor_contacts_by_lastname",
                        lambda ln: [{"id": "C-tor", "properties":
                                     {"firstname": "Véronique", "lastname": "Fabre",
                                      "email": "veronique.gaeta@ileadexploration.org"}}])
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: assoc.append((d, c)))
    monkeypatch.setattr(po.hs, "associate_contacts",
                        lambda f, t, type_id=15, category="USER_DEFINED":
                        linked.append((f, t)) or {"id": "A1"})
    notes = []
    # extractor gives the unaccented spelling from the PDF; portal stores Véronique
    po._handle_deal(_po(parent_email="mom@x.com",
                        tor_first="Veronique", tor_last="Fabre"), notes)
    assert assoc == [("D66", "C-tor")]
    assert linked == [("C-mom", "C-tor")]          # #AP031 family→TOR rides along
    assert any("matched by NAME" in n for n in notes)


def test_tor_name_only_no_match_flagged_not_silent(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "find_tor_contacts_by_lastname", lambda ln: [])
    monkeypatch.setattr(po.hs, "associate_contact_to_deal",
                        lambda *a: (_ for _ in ()).throw(AssertionError("must not associate")))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_first="Mary", tor_last="Nieves"), notes)
    assert any("associate manually" in n and "Mary Nieves" in n for n in notes)


def test_tor_name_only_ambiguous_flagged(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "find_tor_contacts_by_lastname",
                        lambda ln: [{"id": "T1", "properties": {"firstname": "Mary"}},
                                    {"id": "T2", "properties": {"firstname": "Mary"}}])
    monkeypatch.setattr(po.hs, "associate_contact_to_deal",
                        lambda *a: (_ for _ in ()).throw(AssertionError("ambiguous must not associate")))
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_first="Mary", tor_last="Smith"), notes)
    assert any("multiple matching TOR" in n for n in notes)


# ── missing info → direct DM to Kath AND Roman (Roman, 2026-08-11) ───────────

def test_gap_notes_filter():
    notes = ["💼 Created deal 'X' in Charter pipeline",
             "⚠️ Not in the PO: grade — fill on the deal manually.",
             "📨 Parent-info request DRAFTED to tor@x.org — SEND it from Gmail Drafts",
             "🧑‍🏫 TOR 'Mary Nieves' named in the PO without an email; no matching "
             "TOR contacts in HubSpot — associate manually.",
             "🔄 Teachworks sync ran immediately: tw_synced."]
    gaps = po._gap_notes(notes)
    assert len(gaps) == 3
    assert not any("Created deal" in g or "Teachworks sync" in g for g in gaps)


def test_notify_gaps_dms_kath_and_roman(monkeypatch):
    dms = []
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    monkeypatch.setattr(po.hs, "ticket_url", lambda t: f"https://hs/{t}")
    po._notify_gaps("new_po — Taylion (PO 1)", ["⚠️ Not in the PO: grade"], "T1")
    ids = [d[0] for d in dms]
    assert po.cfg()["staff"]["kath"]["slack_user_id"] in ids
    assert po.cfg()["staff"]["roman"]["slack_user_id"] in ids
    assert all("MISSING INFO" in d[1] and "https://hs/T1" in d[1] for d in dms)


def test_notify_gaps_silent_when_clean(monkeypatch):
    monkeypatch.setattr(po.slack_client, "dm",
                        lambda u, t: (_ for _ in ()).throw(AssertionError("clean run must not DM")))
    po._notify_gaps("s", ["💼 Created deal 'X'", "🔄 Teachworks sync ran immediately."], "T1")


def test_chase_escalation_dms_both(monkeypatch):
    dms = []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "NEEDS PARENT - Ana Diaz - iLead 1 - 26/27",
             "chase_to": "terri@school.org", "sla_due": "2026-08-01T10:00:00-07:00",
             "timestamp": "2026-07-31T10:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: None)
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    po._sweep_parent_chases()
    ids = [d[0] for d in dms]
    assert po.cfg()["staff"]["kath"]["slack_user_id"] in ids
    assert po.cfg()["staff"]["roman"]["slack_user_id"] in ids


# ── is_the_family_currently_being_tutored_by_us_ (gates scheduling texts) ────

def test_currently_tutored_yes_when_upcoming_lessons(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 0, "upcoming": 1})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com"), [])
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "Yes"


def test_currently_tutored_calendar_only_recent_lessons_dont_count(monkeypatch):
    # Roman: nothing on the calendar, PERIOD → they need the text — lessons
    # taught last week don't excuse an empty calendar
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 3, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com"), [])
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "No"


def test_multi_po_email_every_deal_gets_true_value(monkeypatch):
    # SMS workflow 1603217415 is CONTACT-based (one enrollment per PO event),
    # so per-deal suppression is pointless — and it fetches ONE associated deal,
    # so a lying sibling could skip the staff alert. Every deal carries truth.
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": True, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props["is_the_family_currently_being_tutored_by_us_"])
                        or {"id": "D"})
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "A1", "amount": "100"}, {"po_number": "A2", "amount": "100"},
        {"po_number": "A3", "amount": "100"}]), [])
    assert captured == ["No", "No", "No"]


# ── schedule_preferences stamp: the SMS must never end in a blank ────────────

def test_schedule_stamped_from_upcoming_lessons(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        {"found": True, "recent": 0, "upcoming": 2,
                         "upcoming_dates": ["2026-08-12", "2026-08-19"],
                         "upcoming_lessons": [
                             {"date": "2026-08-12", "time": "15:30", "tutor": "Sarah Lee"},
                             {"date": "2026-08-19", "time": "15:30", "tutor": "Sarah Lee"}]})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com", po_month="2026-08"), [])
    assert captured[0]["schedule_preferences"] == "Wednesdays 3:30 PM with Sarah Lee"
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "Yes"


def test_schedule_falls_back_to_recent_pattern(monkeypatch):
    # nothing booked (new month) but the student's recent rhythm is known →
    # the SMS confirms THAT pattern instead of ending in a blank
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        {"found": True, "recent": 2, "upcoming": 0, "upcoming_dates": [],
                         "upcoming_lessons": [],
                         "recent_lessons": [
                             {"date": "2026-08-04", "time": "16:00", "tutor": "Olsjon"},
                             {"date": "2026-08-11", "time": "16:00", "tutor": "Olsjon"}]})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com", po_month="2026-09"), [])
    assert captured[0]["schedule_preferences"] == "Tuesdays 4:00 PM with Olsjon"
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "No"


def test_no_schedule_derivable_stamps_ask_fallback(monkeypatch):
    # Roman 2026-08-22: no schedule in the PO or TW → the SMS asks the family
    # for one (general phrase auto-texted) instead of ending blank + a manual
    # follow-up. Note is informational only — must NOT trip the 🚩 gap DM.
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": False, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert captured[0]["schedule_preferences"] == po.cfg()["po_inbox"]["schedule_ask_fallback"]
    assert "schedule" in captured[0]["schedule_preferences"].lower()
    info = [n for n in notes if "asks the family for their schedule" in n]
    assert info and info[0].startswith("ℹ️")
    assert info[0] not in po._gap_notes(notes)


def test_schedule_ask_fallback_default_without_config(monkeypatch):
    # Config key absent → the built-in default phrase still goes out.
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": False, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    base = po.cfg()
    trimmed = {**base, "po_inbox": {k: v for k, v in base["po_inbox"].items()
                                    if k != "schedule_ask_fallback"}}
    monkeypatch.setattr(po, "cfg", lambda: trimmed)
    po._handle_deal(_po(parent_email="mom@x.com"), [])
    assert "reply" in captured[0]["schedule_preferences"].lower()
    assert "schedule" in captured[0]["schedule_preferences"].lower()


def test_schedule_text_formatting():
    assert po._fmt_time("15:30") == "3:30 PM"
    assert po._fmt_time("09:05") == "9:05 AM"
    assert po._fmt_time("00:15") == "12:15 AM"
    assert po._fmt_time("12:00") == "12:00 PM"
    lessons = [{"date": "2026-08-12", "time": "15:30", "tutor": "Sarah"},
               {"date": "2026-08-19", "time": "15:30", "tutor": "Sarah"},
               {"date": "2026-08-14", "time": "10:00", "tutor": ""}]
    assert po._schedule_text(lessons) == "Wednesdays 3:30 PM with Sarah, Fridays 10:00 AM"
    assert po._schedule_text([]) == ""


def test_currently_tutored_no_when_inactive_or_unknown_student(monkeypatch):
    # zero recent + zero upcoming → No; a student not in Teachworks at all is a
    # CONFIDENT No too (they're definitely not being tutored)
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: {"found": False, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com"), [])
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "No"


def test_currently_tutored_unverifiable_flags_not_guesses(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw: (_ for _ in ()).throw(RuntimeError("TW down")))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com"), notes)
    assert "is_the_family_currently_being_tutored_by_us_" not in captured[0]
    gap = [n for n in notes if "Could not verify the Teachworks calendar" in n]
    assert gap and gap[0] in po._gap_notes(notes)   # rides the missing-info DM


def test_currently_tutored_uses_prior_deal_parent_email(monkeypatch):
    # parent resolved from a prior deal (no email in the PO) → THAT email drives
    # the calendar check and the property
    captured, checked = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda f, l=None: [_deal("D-old", "Maria Diaz - Ana Diaz - iLead")])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "get_deal_contacts",
                        lambda did: [_contact("C-mom", "maria@x.com", "Maria", "Diaz", "Family")])
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        checked.append(e) or {"found": True, "recent": 2, "upcoming": 1})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="", po_number=""), [])
    assert checked == ["maria@x.com"]
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "Yes"


def test_tw_calendar_checked_once_per_multi_po_email(monkeypatch):
    calls = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        calls.append(e) or {"found": True, "recent": 0, "upcoming": 0})
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D"})
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "A1", "amount": "100"}, {"po_number": "A2", "amount": "100"},
        {"po_number": "A3", "amount": "100"}]), [])
    assert len(calls) == 1                         # memoized across the 3 deals


# ── month-scoped texting (Roman, 2026-08-11): each month's PO re-asks ────────

def test_new_month_po_texts_despite_current_month_lessons(monkeypatch):
    # Sept PO arrives mid-Aug; student still has Aug lessons booked but NOTHING
    # in Sept → "No" → the scheduling text goes out for September
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        {"found": True, "recent": 2, "upcoming": 2,
                         "upcoming_dates": ["2026-08-20", "2026-08-27"]})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com", po_month="2026-09"), [])
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "No"


def test_po_month_already_booked_no_text(monkeypatch):
    # September PO and September lessons are already on the calendar → "Yes"
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.tw, "student_lesson_activity",
                        lambda e, sf, lookback_days=30, **kw:
                        {"found": True, "recent": 0, "upcoming": 3,
                         "upcoming_dates": ["2026-08-28", "2026-09-04", "2026-09-11"]})
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(parent_email="mom@x.com", po_month="2026-09"), [])
    assert captured[0]["is_the_family_currently_being_tutored_by_us_"] == "Yes"


# ── PO hours computed from amount ÷ rate (Roman, 2026-08-11) ─────────────────

def test_hours_computed_from_amount_and_rate(monkeypatch):
    captured, tasks = [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda subj, body, owner, due, priority="MEDIUM", contact_id=None:
                        tasks.append(body) or {"id": "T"})
    notes = []
    po._handle_deal(_po(hours="", rate="75", amount="150"), notes)
    assert captured[0]["number_of_hours_in_this_po"] == "2"
    assert any("Hours computed" in n and "$150 ÷ $75/hr = 2 hrs" in n for n in notes)
    assert tasks and "Hours: 2 @ $75/hr" in tasks[0]
    assert "Invoice #" in tasks[0] and "Expected Lessons Fulfilled Date" in tasks[0]


def test_hours_stated_never_overwritten(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(hours="10", rate="75", amount="150"), [])
    assert captured[0]["number_of_hours_in_this_po"] == "10"


def test_no_rate_unique_offering_fit_computes(monkeypatch):
    # no rate stated, $150 divides cleanly ONLY at $75/hr (2.5 sessions at
    # $60 isn't whole) → hours filled at the standard offering, noted as such
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(hours="", rate="", amount="150"), notes)
    assert captured[0]["number_of_hours_in_this_po"] == "2"
    assert any("standard" in n and "$75/hr" in n for n in notes)


def test_no_rate_ambiguous_amount_stays_blank(monkeypatch):
    # $300 = 4 hrs at $75/hr OR 5 sessions (3.75 hrs) at $60/session — both
    # fit, so hours stay BLANK and the ambiguity is flagged (never guessed)
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(hours="", rate="", amount="300"), notes)
    assert "number_of_hours_in_this_po" not in captured[0]
    assert any("fits more than one offering" in n for n in notes)


def test_no_rate_no_offering_fit_stays_blank(monkeypatch):
    # $158 matches neither offering → blank + flagged for manual fill
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(hours="", rate="", amount="158"), notes)
    assert "number_of_hours_in_this_po" not in captured[0]
    assert any("matches no standard offering" in n for n in notes)


def test_session_rate_converts_to_hours(monkeypatch):
    # $60 per 45-min SESSION: a $240 PO = 4 sessions = 3 HOURS on the deal
    # (Roman, 2026-08-26: hours is always hours — a 4-session PO stamps 3)
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(hours="", rate="60", rate_unit="session", amount="240"), notes)
    assert captured[0]["number_of_hours_in_this_po"] == "3"
    assert any("4 sessions" in n for n in notes)


def test_fractional_hours_computed(monkeypatch):
    captured = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, extra_props=None, **k:
                        captured.append(extra_props) or {"id": "D1"})
    po._handle_deal(_po(hours="", rate="75", amount="112.50"), [])
    assert captured[0]["number_of_hours_in_this_po"] == "1.5"


# ── TOR name + email stamped on the deal (Roman, 2026-08-12) ─────────────────

def test_tor_name_and_email_stamped_on_deal(monkeypatch):
    patches = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None: patches.append((path, payload)) or {})
    po._handle_deal(_po(tor_first="Mary", tor_last="Nieves",
                        tor_email="mary.nieves@ilead.org", parent_email="mom@x.com"), [])
    stamp = [x for x in patches if x[0] == "/crm/v3/objects/deals/D22"
             and "teacher_of_record_name" in (x[1] or {}).get("properties", {})]
    assert stamp
    props = stamp[0][1]["properties"]
    assert props["teacher_of_record_name"] == "Mary Nieves"
    assert props["teacher_of_record_email"] == "mary.nieves@ilead.org"


def test_name_matched_tor_email_backfills_deal_stamp(monkeypatch):
    # PO names the TOR without an email → the matched contact's email is
    # resolved and lands on teacher_of_record_email anyway
    patches = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.hs, "find_tor_contacts_by_lastname",
                        lambda ln: [{"id": "C-tor", "properties":
                                     {"firstname": "Mary", "lastname": "Nieves",
                                      "email": "mary.nieves@ileadexploration.org"}}])
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None: patches.append((path, payload)) or {})
    po._handle_deal(_po(tor_first="Mary", tor_last="Nieves", tor_email="",
                        parent_email="mom@x.com"), [])
    stamp = [x for x in patches if "teacher_of_record_email" in (x[1] or {}).get("properties", {})]
    assert stamp
    assert stamp[0][1]["properties"]["teacher_of_record_email"] == \
        "mary.nieves@ileadexploration.org"


def test_missing_tor_flagged_for_manual_fill(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D22"})
    notes = []
    po._handle_deal(_po(), notes)   # no TOR in the PO at all
    missing = [n for n in notes if "not resolvable from records" in n]
    assert missing and "tor_name" in missing[0] and "tor_email" in missing[0]


def test_multi_po_seq_base_counted_once(monkeypatch):
    # the Zackarias 1,2,4,7,9 bug: the search index catches up mid-run and
    # re-counting per sibling inflates N — the base is searched ONCE per
    # (student, school, year) run key; siblings never re-search. The index
    # 'grows' as deals are created, but only a re-search could see that.
    index: list = []
    searches = {"n": 0}
    def live_index(first, last=None):
        searches["n"] += 1
        return list(index) if first == "Zack" else []
    created = []
    def create(name, pl, st, amt=None, **k):
        created.append(name)
        index.append(_deal(f"D{len(index)}", name))   # index catches up mid-run
        return {"id": "D"}
    monkeypatch.setattr(po.hs, "search_deals_by_student", live_index)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Mari", "lastname": "Barajas"}})
    monkeypatch.setattr(po.hs, "create_deal", create)
    po._handle_deal(_po(student_first="Zack", student_last="Barajas",
                        po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "A1", "amount": "100", "po_month": "2026-08"},
        {"po_number": "A2", "amount": "100", "po_month": "2026-09"},
        {"po_number": "A3", "amount": "100", "po_month": "2026-10"}]), [])
    seqs = [n.split(" - ")[2] for n in created]
    assert seqs == ["iLead 1", "iLead 2", "iLead 3"]   # contiguous, no gaps
    assert searches["n"] <= 2   # one seed (+ the first-name-only fallback), never per sibling


# ── TOR self-healing (Mary Nieves SMS incident, 2026-08-13) ──────────────────

def test_tor_flipped_status_healed_on_touch(monkeypatch):
    patches = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None:
                        {"id": "C-mom"} if e == "mom@x.com" else
                        {"id": "C-tor", "properties": {"email": e, "firstname": "Mary",
                                                       "lastname": "Nieves",
                                                       "a_persona": "",
                                                       "hs_lead_status": "OPEN_DEAL"}})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None: patches.append((path, payload)) or {})
    notes = []
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="mary@ilead.org"), notes)
    heal = [x for x in patches if x[0] == "/crm/v3/objects/contacts/C-tor"]
    assert heal
    fixed = heal[0][1]["properties"]
    assert fixed["hs_lead_status"] == "Charter School Teacher TOR/EF"
    assert fixed["a_persona"] == "Teacher of Record/EF/ES"
    assert any("TOR contact healed" in n for n in notes)


def test_dual_role_tor_family_status_untouched(monkeypatch):
    # a TOR who is ALSO a Family customer keeps their customer lead status —
    # only the missing persona would be appended (here it's present → no PATCH)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None:
                        {"id": "C-mom"} if e == "mom@x.com" else
                        {"id": "C-tor", "properties": {"email": e,
                                                       "a_persona": "Family;Teacher of Record/EF/ES",
                                                       "hs_lead_status": "OPEN_DEAL"}})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None:
                        (_ for _ in ()).throw(AssertionError("dual-role must not be patched"))
                        if "contacts/C-tor" in path else {})
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="dual@x.org"), [])


def test_healthy_tor_not_patched(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D66"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None:
                        {"id": "C-mom"} if e == "mom@x.com" else
                        {"id": "C-tor", "properties": {"email": e,
                                                       "a_persona": "Teacher of Record/EF/ES",
                                                       "hs_lead_status": "Charter School Teacher TOR/EF"}})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, path, payload=None:
                        (_ for _ in ()).throw(AssertionError("healthy TOR must not be patched"))
                        if "contacts/C-tor" in path else {})
    po._handle_deal(_po(parent_email="mom@x.com", tor_email="ok@x.org"), [])


# ── 2026-08-14 batch: multi-student certs, chase batching, pending sweep ─────

def test_multi_student_certificate_per_student_deals(monkeypatch):
    created, drafts, appended = [], [], []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: [])
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k:
                        created.append(name) or {"id": f"D{len(created)}"})
    monkeypatch.setattr(po.gm, "create_draft_reply",
                        lambda tid, to, subj, body, irt="", **kw: drafts.append((to, body)) or {"id": "DR"})
    # TOR ≠ sender → the chase goes out as a FRESH email, not a reply
    monkeypatch.setattr(po.gm, "create_draft",
                        lambda to, subj, body, bcc="": drafts.append((to, body)) or
                        {"id": "DR-F", "message": {"id": "M1", "threadId": "TH-NEW"}})
    monkeypatch.setattr(po.gm, "apply_labels", lambda mid, names: None)
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    msg = {"threadId": "TH-H", "sender": "Procurify <no@procurify.com>",
           "subject": "CERTIFICATE", "message_id_header": "<h1>"}
    po._handle_deal(_po(student_first="", student_last="", po_number="",
                        tor_first="Kristy", tor_last="Doyal",
                        tor_email="kristydoyal@gmail.com", po_month="2026-09", pos=[
        {"po_number": "PF1-CooperDoyal", "amount": "300", "hours": "4",
         "student_first": "Cooper", "student_last": "Doyal"},
        {"po_number": "PF1-CharlotteCzaja", "amount": "300", "hours": "4",
         "student_first": "Charlotte", "student_last": "Czaja"},
        {"po_number": "PF1-RayvenHolloway", "amount": "600", "hours": "8",
         "student_first": "Rayven", "student_last": "Holloway"}]), [], msg=msg)
    # per-student naming + per-student seq (each kid starts at 1)
    assert created == ["NEEDS PARENT - Cooper Doyal - iLead 1 - 26/27",
                       "NEEDS PARENT - Charlotte Czaja - iLead 1 - 26/27",
                       "NEEDS PARENT - Rayven Holloway - iLead 1 - 26/27"]
    # ONE draft to the TOR listing every student — not three identical drafts
    assert len(drafts) == 1 and drafts[0][0] == "kristydoyal@gmail.com"
    assert all(s in drafts[0][1] for s in ("Cooper Doyal", "Charlotte Czaja",
                                           "Rayven Holloway"))
    chases = [r for r in appended if r.get("action_taken") == "parent_chase_opened"]
    assert len(chases) == 3                              # one chase record per deal


def test_reply_resolves_only_named_students_chases(monkeypatch):
    resolved = []
    monkeypatch.setattr(po, "_resolve_parent_chase",
                        lambda chase, p_, notes: resolved.append(chase.get("student")))
    chases = [{"student": "Cooper Doyal"}, {"student": "Charlotte Czaja"},
              {"student": "Emmalyn Czaja"}]
    po._resolve_parent_chases(chases, {"student_first": "Charlotte"}, [])
    assert resolved == ["Charlotte Czaja"]
    resolved.clear()
    po._resolve_parent_chases(chases, {"student_first": ""}, [])   # no student named
    assert len(resolved) == 3                                      # resolve all


def test_chase_resolution_arms_parent_sms(monkeypatch):
    patches = []
    chase = {"deal_id": "D9", "deal_name": "NEEDS PARENT - Ana Diaz - iLead 1 - 26/27",
             "pipeline": "907748", "po_number": "4471", "thread_id": "TH9"}
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m_, p_, payload=None: patches.append((p_, payload)) or {})
    monkeypatch.setattr(po.audit, "append", lambda r: None)
    monkeypatch.setattr(dsy_mod, "sync_deal", lambda d, **k: {"action_taken": "tw_synced"})
    notes = []
    po._resolve_parent_chase(chase, {"parent_email": "mom@x.com", "parent_first": "Maria",
                                     "parent_last": "Diaz"}, notes)
    arm = [x for x in patches if x[0] == "/crm/v3/objects/contacts/C-mom"
           and "contact_level_deal_stage" in (x[1] or {}).get("properties", {})]
    assert arm and arm[0][1]["properties"]["contact_level_deal_stage"] == \
        "Pre-Lesson (Charter Traditional)"
    assert any("Scheduling-text workflow armed" in n for n in notes)


def test_pending_sweep_nags_then_stays_quiet(monkeypatch):
    dms, appended = [], []
    recs = [{"action_taken": "pending_po_opened", "deal_id": "D1",
             "deal_name": "X - Y - iLead 1 - 26/27", "po_number": "111",
             "sla_due": "2026-08-01T10:00:00-07:00",
             "timestamp": "2026-07-31T10:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    po._sweep_pending_pos()
    assert len(dms) == 2                       # kath + roman
    assert all("PENDING school approval" in t for _u, t in dms)
    assert appended and appended[0]["action_taken"] == "pending_po_reminded"
    # already reminded → silent
    recs.append(appended[0]); dms.clear()
    po._sweep_pending_pos()
    assert dms == []


def test_pending_sweep_confirmed_by_duplicate_is_silent(monkeypatch):
    recs = [{"action_taken": "pending_po_opened", "deal_id": "D1",
             "deal_name": "X", "po_number": "111",
             "sla_due": "2026-08-01T10:00:00-07:00"},
            {"action_taken": "pending_po_confirmed", "po_number": "111"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.slack_client, "dm",
                        lambda u, t: (_ for _ in ()).throw(AssertionError("confirmed → no nag")))
    po._sweep_pending_pos()


def test_sla_sweep_sees_po_tickets(monkeypatch):
    from src import sla_sweep as sw
    monkeypatch.setattr(sw.audit, "_iter_records",
                        lambda: iter([{"action_taken": "po_processed", "ticket_id": "T1",
                                       "sla_due": "2026-08-07T16:36:59-07:00",
                                       "owner": "kath", "category": "new_po"}]))
    tickets = sw._latest_tickets()
    assert "T1" in tickets                     # PO tickets now enter the escalation chain


# ── draft guidelines (Roman, 2026-08-14): humans only, tracked, context-aware ─

def test_noreply_addresses_never_get_chase_drafts(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D9"})
    monkeypatch.setattr(po.gm, "create_draft",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no draft to robots")))
    monkeypatch.setattr(po.gm, "create_draft_reply",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no draft to robots")))
    msg = {"threadId": "TH-R", "sender": "OPS <noreply@ops-online.com>",
           "subject": "PO", "message_id_header": "<m>"}
    notes = []
    po._handle_deal(_po(po_number="", tor_email=""), notes, msg=msg)
    assert any("No HUMAN recipient" in n for n in notes)
    assert any(n in po._gap_notes(notes) for n in notes if "No HUMAN recipient" in n)


def test_human_addr_guard():
    assert po._human_addr("karen.mercer@ileadexploration.org") is True
    assert po._human_addr("noreply@ops-online.com") is False
    assert po._human_addr("no-reply@x.com") is False
    assert po._human_addr("notifications@mailer.procurify.com") is False
    assert po._human_addr("donotreply@school.org") is False
    assert po._human_addr("") is False


def test_chase_call_context_flags_ticket(monkeypatch):
    drafts = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D9"})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C-tor"})
    monkeypatch.setattr(po.hs, "recent_calls_for_contact",
                        lambda cid, since, limit=3:
                        [{"properties": {"hs_call_title": "Inbound call — school partnership",
                                         "hs_call_body": "[Call Agent] Karen mentioned parent August",
                                         "hs_timestamp": "2026-08-13T22:23:24Z"}}])
    monkeypatch.setattr(po.gm, "create_draft",
                        lambda to, subj, body, bcc="": drafts.append(body) or
                        {"id": "DR", "message": {"id": "M1", "threadId": "TH-N"}})
    monkeypatch.setattr(po.gm, "apply_labels", lambda mid, names: None)
    msg = {"threadId": "TH-C", "sender": "OPS <noreply@ops-online.com>",
           "subject": "PO", "message_id_header": "<m>"}
    notes = []
    po._handle_deal(_po(po_number="", tor_email="karen.mercer@ileadexploration.org",
                        tor_first="Karen", tor_last="Mercer"), notes, msg=msg)
    assert any("recent call may ALREADY have this info" in n for n in notes)
    assert drafts and "may already have come up on a recent call" in drafts[0]


def test_chase_self_resolve_sweep(monkeypatch):
    resolved = []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "student": "Kruz Vouniozos", "pipeline": "907748",
             "sla_due": "2026-09-01T10:00:00-07:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.hs, "_get",       # deal still genuinely NEEDS PARENT
                        lambda path, params=None: {"properties": {"dealname":
                                                   "NEEDS PARENT - Kruz Vouniozos - iLead 1 - 26/27"}})
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: [{"id": "C-aug", "properties":
                                         {"email": "august12v@gmail.com",
                                          "firstname": "August", "lastname": "Vouniozos"}}])
    monkeypatch.setattr(po, "_resolve_parent_chase",
                        lambda chase, p_, notes: resolved.append(p_["parent_email"]))
    po._sweep_chase_self_resolve()
    assert resolved == ["august12v@gmail.com"]


def test_unsent_draft_nags_and_sent_starts_clock(monkeypatch):
    dms, appended = [], []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "NEEDS PARENT - X - iLead 1 - 26/27", "student": "X Y",
             "chase_to": "tor@x.org", "draft_id": "DR9",
             "sla_due": "2026-09-01T10:00:00-07:00",
             "timestamp": "2026-08-01T10:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append(t))
    # draft still sitting there → nag
    monkeypatch.setattr(po.gm, "get_draft", lambda did: {"id": did})
    po._sweep_chase_drafts()
    assert dms and "STILL SITTING in Gmail Drafts" in dms[0]
    assert appended[-1]["action_taken"] == "parent_chase_draft_nag"
    # draft gone → sent record with a fresh reply clock
    dms.clear(); appended.clear()
    monkeypatch.setattr(po.gm, "get_draft", lambda did: None)
    po._sweep_chase_drafts()
    assert appended and appended[0]["action_taken"] == "parent_chase_sent"
    assert appended[0]["deal_id"] == "D9" and appended[0]["sla_due"]


def test_unsent_chase_never_escalates_tor(monkeypatch):
    # chase has a draft_id but no sent record → the TOR never got the email;
    # the escalation sweep must stay silent (draft nag handles it)
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "X", "chase_to": "tor@x.org", "draft_id": "DR9",
             "sla_due": "2026-08-01T10:00:00-07:00",
             "timestamp": "2026-07-31T10:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.slack_client, "dm",
                        lambda u, t: (_ for _ in ()).throw(AssertionError("unsent must not escalate")))
    po._sweep_parent_chases()


def test_charter_sales_notified_24h_after_sent_email(monkeypatch):
    dms, appended = [], []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "NEEDS PARENT - Kruz Vouniozos - iLead 1 - 26/27",
             "student": "Kruz Vouniozos", "chase_to": "karen@ilead.org",
             "draft_id": "DR9", "sla_due": "2026-09-20T10:00:00-07:00",
             "timestamp": "2026-08-01T10:00:00+00:00"},
            {"action_taken": "parent_chase_sent", "deal_id": "D9", "thread_id": "TH9",
             "draft_id": "DR9", "sla_due": "2026-09-20T10:00:00-07:00",
             "timestamp": "2026-08-01T12:00:00+00:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)))
    po._sweep_parent_chases()
    # >24h since send, escalation window (Sep) not yet reached → ONLY Paola
    assert len(dms) == 1
    assert dms[0][0] == po.cfg()["staff"][po.cfg()["roles"]["charter_sales"]]["slack_user_id"]
    assert "STILL MISSING 24h" in dms[0][1] and "Kruz Vouniozos" in dms[0][1]
    assert appended[-1]["action_taken"] == "parent_chase_sales_notified"
    # second sweep: already pinged → silent
    recs.append(appended[-1]); dms.clear()
    po._sweep_parent_chases()
    assert dms == []


def test_charter_sales_not_notified_before_send(monkeypatch):
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH9", "deal_id": "D9",
             "deal_name": "X", "student": "S T", "chase_to": "t@x.org",
             "draft_id": "DR9", "sla_due": "2026-09-20T10:00:00-07:00",
             "timestamp": "2026-08-01T10:00:00+00:00"}]   # opened long ago, never sent
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.slack_client, "dm",
                        lambda u, t: (_ for _ in ()).throw(AssertionError("unsent → no Paola ping")))
    po._sweep_parent_chases()


# ── Pilibos incident (2026-08-14): self-resolve guards ───────────────────────

def test_self_resolve_skips_placeholder_student(monkeypatch):
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH", "deal_id": "D1",
             "student": "the student", "sla_due": "2026-09-01T10:00:00-07:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: (_ for _ in ()).throw(AssertionError("must not search 'the student'")))
    po._sweep_chase_self_resolve()


def test_self_resolve_respects_live_deal_name(monkeypatch):
    # deal already fixed by Kath (no longer NEEDS PARENT) → close the chase,
    # touch nothing on the deal
    appended = []
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH", "deal_id": "D1",
             "student": "Cooper Doyal", "sla_due": "2026-09-01T10:00:00-07:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.audit, "append", lambda r: appended.append(r))
    monkeypatch.setattr(po.hs, "_get",
                        lambda path, params=None: {"properties": {"dealname":
                                                   "Kristy Doyal - Cooper Doyal - Heartland 1 - 26/27"}})
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: (_ for _ in ()).throw(AssertionError("fixed deal must not be searched")))
    monkeypatch.setattr(po, "_resolve_parent_chase",
                        lambda *a: (_ for _ in ()).throw(AssertionError("must not resolve")))
    po._sweep_chase_self_resolve()
    assert appended and appended[0]["action_taken"] == "parent_chase_resolved"
    assert "human fixed" in appended[0]["resolved_via"]


def test_self_resolve_never_attaches_internal_contact(monkeypatch):
    recs = [{"action_taken": "parent_chase_opened", "thread_id": "TH", "deal_id": "D1",
             "student": "Cooper Doyal", "sla_due": "2026-09-01T10:00:00-07:00"}]
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(recs))
    monkeypatch.setattr(po.hs, "_get",
                        lambda path, params=None: {"properties": {"dealname": "NEEDS PARENT - Cooper Doyal - Heartland 1 - 26/27"}})
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: [{"id": "C-test", "properties":
                                         {"email": "roman+001@wetutorathome.com",
                                          "firstname": "Pilibos", "lastname": "Student"}}])
    monkeypatch.setattr(po, "_resolve_parent_chase",
                        lambda *a: (_ for _ in ()).throw(AssertionError("test contact must not attach")))
    po._sweep_chase_self_resolve()


def test_resolve_renames_from_live_deal_not_stale_audit(monkeypatch):
    patches = []
    chase = {"deal_id": "D9", "deal_name": "NEEDS PARENT - Heartland 2 - 26/27",   # stale
             "pipeline": "907748", "po_number": "X", "thread_id": "TH"}
    monkeypatch.setattr(po.hs, "_get",
                        lambda path, params=None: {"properties": {"dealname":
                                                   "NEEDS PARENT - Charlotte Czaja - Heartland 1 - 26/27"}})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: None)
    monkeypatch.setattr(po.hs, "create_contact",
                        lambda e, f=None, l=None, phone=None, extra_props=None: {"id": "C-mom"})
    monkeypatch.setattr(po.hs, "associate_contact_to_deal", lambda d, c: {})
    monkeypatch.setattr(po.hs, "_write",
                        lambda m_, p_, payload=None: patches.append((p_, payload)) or {})
    monkeypatch.setattr(po.audit, "append", lambda r: None)
    monkeypatch.setattr(dsy_mod, "sync_deal", lambda d, **k: {"action_taken": "tw_synced"})
    po._resolve_parent_chase(chase, {"parent_email": "angela@x.com", "parent_first": "Angela",
                                     "parent_last": "Czaja"}, [])
    renames = [p for p in patches if (p[1] or {}).get("properties", {}).get("dealname")]
    assert renames[0][1]["properties"]["dealname"] == \
        "Angela Czaja - Charlotte Czaja - Heartland 1 - 26/27"   # live name, student kept


# ── surname-only parent match rejected (Matthew Rose / Dina Rose, 2026-08-18) ─

def test_lone_surname_match_without_student_evidence_is_rejected(monkeypatch):
    from src import hubspot_client as hsc
    monkeypatch.setattr(hsc, "_write",
                        lambda m, path, body=None:
                        {"results": [{"id": "C-dina", "properties":
                                      {"email": "dinah.pham@gmail.com", "firstname": "Dina",
                                       "lastname": "Rose", "student_last_name": ""}}]}
                        if "contacts/search" in path else {"results": []})
    monkeypatch.setattr(hsc, "contact_deal_names", lambda cid: [])
    monkeypatch.setattr(hsc, "cfg", lambda: {"teachworks": {"student_name_properties": ["student_last_name"]}})
    assert hsc.find_family_contact("Matthew", "Rose") == []


def test_lone_surname_match_with_student_deal_is_accepted(monkeypatch):
    from src import hubspot_client as hsc
    def _write(m, path, body=None):
        if "contacts/search" in path:
            return {"results": [{"id": "C-mom", "properties":
                                 {"email": "mom@x.com", "firstname": "Marcela",
                                  "lastname": "Shea", "student_last_name": ""}}]}
        if "deals/batch/read" in path:
            return {"results": [{"properties": {"dealname": "Marcela Shea - Matthew - iLead 6"}}]}
        return {"results": []}
    monkeypatch.setattr(hsc, "_write", _write)
    monkeypatch.setattr(hsc, "contact_deal_names", lambda cid: ["Marcela Shea - Matthew - iLead 6"])
    monkeypatch.setattr(hsc, "cfg", lambda: {"teachworks": {"student_name_properties": ["student_last_name"]}})
    assert [c["id"] for c in hsc.find_family_contact("Matthew", "Shea")] == ["C-mom"]


# ── TW student-name lookup as parent-resolution step 2 (Matthew Rose, 2026-08-18)

@pytest.fixture
def _no_tw_family(monkeypatch):
    monkeypatch.setattr(po.tw, "find_family_by_student", lambda f, l, tutor_hint="": None)


def test_tw_student_lookup_resolves_parent_before_surname_search(monkeypatch):
    # PO: Matthew Rose, tutor Jacquelyn Lemerond, no parent info. Teachworks
    # knows Megan Miller's Matthew (104 lessons, same tutor). The surname
    # search (which would find Dina Rose) must never even run.
    created = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.tw, "find_family_by_student",
                        lambda f, l, tutor_hint="": {"parent_first": "Megan", "parent_last": "Miller",
                                                     "email": "missmegan1230@yahoo.com",
                                                     "phone": "661-886-9677",
                                                     "tutor": "Lemerond, Jacquelyn", "lessons": 104,
                                                     "last_lesson": "2026-05-20", "tutor_match": True})
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C-megan", "properties":
                                                    {"firstname": "Megan", "lastname": "Miller"}})
    monkeypatch.setattr(po.hs, "find_family_contact",
                        lambda sf, ln: (_ for _ in ()).throw(AssertionError("surname search must not run")))
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, contact_id=None, **k:
                        created.append((name, contact_id)) or {"id": "D1"})
    notes = []
    po._handle_deal(_po(student_first="Matthew", student_last="Rose", po_number="",
                        tutor_name="Jacquelyn Lemerond", po_month="2026-09"), notes)
    assert created == [("Megan Miller - Matthew Rose - iLead 1 - 26/27", "C-megan")]
    assert any("found IN TEACHWORKS" in n and "Lemerond" in n for n in notes)


def test_tw_student_lookup_tutor_mismatch_flags(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.tw, "find_family_by_student",
                        lambda f, l, tutor_hint="": {"parent_first": "Megan", "parent_last": "Miller",
                                                     "email": "m@x.com", "phone": "",
                                                     "tutor": "Someone Else", "lessons": 12,
                                                     "last_lesson": "2026-03-01", "tutor_match": False})
    monkeypatch.setattr(po.hs, "find_contact_by_email", lambda e, properties=None: {"id": "C1"})
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D1"})
    notes = []
    po._handle_deal(_po(po_number="", tutor_name="Jacquelyn Lemerond"), notes)
    assert any("verify it's the same student" in n for n in notes)


def test_tw_student_lookup_internal_family_ignored(monkeypatch):
    fell_through = []
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.tw, "find_family_by_student",
                        lambda f, l, tutor_hint="": {"parent_first": "Pilibos", "parent_last": "Student",
                                                     "email": "roman+001@wetutorathome.com",
                                                     "phone": "", "tutor": "", "lessons": 3,
                                                     "last_lesson": "", "tutor_match": False})
    monkeypatch.setattr(po.hs, "find_family_contact", lambda sf, ln: fell_through.append(1) or [])
    monkeypatch.setattr(po.hs, "create_deal", lambda *a, **k: {"id": "D1"})
    po._handle_deal(_po(po_number=""), [])
    assert fell_through == [1]        # test family skipped → normal ladder continues


def test_find_family_by_student_prefers_lessons_and_tutor(monkeypatch):
    from src import teachworks_client as twc
    monkeypatch.setattr(twc, "accounts", lambda: {"online": "tok"})
    def _get(endpoint, params=None, token=None):
        if endpoint == "students":
            return [{"id": 1, "first_name": "Matthew", "last_name": "Rose", "customer_id": 10},
                    {"id": 2, "first_name": "Matthew", "last_name": "Rose", "customer_id": 20}]
        if endpoint == "lessons":
            sid = params["student_id"]
            return ([{"from_date": "2026-05-20", "employee_name": "Lemerond, Jacquelyn"}] * 3
                    if sid == 1 else [])           # student 2 = 0-lesson shell
        if endpoint == "customers":
            cid = params["id"]
            return [{"id": 10, "first_name": "Megan", "last_name": "Miller",
                     "email": "missmegan1230@yahoo.com", "mobile_phone": "661"}] if cid == 10 else \
                   [{"id": 20, "first_name": "Dina", "last_name": "Rose", "email": "d@x.com"}]
        return []
    monkeypatch.setattr(twc, "tw_get", _get)
    fam = twc.find_family_by_student("Matthew", "Rose", tutor_hint="Jacquelyn Lemerond")
    assert fam["email"] == "missmegan1230@yahoo.com" and fam["tutor_match"] is True
    assert fam["lessons"] == 3
    # no lesson history anywhere → None (never a shell)
    monkeypatch.setattr(twc, "tw_get",
                        lambda e, p=None, token=None:
                        [{"id": 2, "first_name": "Matthew", "last_name": "Rose", "customer_id": 20}]
                        if e == "students" else [])
    assert twc.find_family_by_student("Matthew", "Rose") is None


# ── 2026-08-26 refinements: run-scoped numbering, cancellations, scrub ──

def test_seq_continues_across_emails_same_run(monkeypatch):
    # the McGraw double-1,2,3 bug: two PO emails 30s apart in ONE run — the
    # search index can't see the first email's deals yet, but the run-scoped
    # counter must keep counting 3, 4 instead of restarting at 1
    monkeypatch.setattr(po.hs, "search_deals_by_student", lambda f, l=None: [])
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    monkeypatch.setattr(po.hs, "find_contact_by_email",
                        lambda e, properties=None: {"id": "C1", "properties":
                                                    {"firstname": "Maria", "lastname": "Diaz"}})
    created = []
    monkeypatch.setattr(po.hs, "create_deal",
                        lambda name, pl, st, amt=None, **k: created.append(name) or {"id": "D"})
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "B1", "amount": "150", "po_month": "2026-08"},
        {"po_number": "B2", "amount": "150", "po_month": "2026-09"}]), [])
    po._handle_deal(_po(po_number="", parent_email="mom@x.com", pos=[
        {"po_number": "B3", "amount": "150", "po_month": "2026-10"},
        {"po_number": "B4", "amount": "150", "po_month": "2026-11"}]), [])
    seqs = [n.split(" iLead ")[1].split(" ")[0] for n in created]
    assert seqs == ["1", "2", "3", "4"]


def _cancel_po(**kw):
    base = {"is_po": False, "is_cancellation": True, "po_number": "1433577",
            "billable_stated": "0", "school": "Ocean Grove",
            "summary": "Service PO Cancellation, 0 sessions billable"}
    base.update(kw)
    return base


def _stopped_pipeline(monkeypatch):
    monkeypatch.setattr(po.hs, "find_stop_stage",
                        lambda pl, pats: ("13267787", "Stopped"))


def test_cancellation_zeroes_and_stops_deal(monkeypatch):
    patched, notes_added, dms, tasks = [], [], [], []
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [
        {"id": "D9", "properties": {"dealname": "P - S - OG 1 - 26/27",
                                    "pipeline": "907748", "dealstage": "907749",
                                    "amount": "90", "hubspot_owner_id": "80047202",
                                    "invoice__": "54321"}}])
    _stopped_pipeline(monkeypatch)
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, p, b=None: patched.append((m, p, b)) or {"id": "X"})
    monkeypatch.setattr(po.hs, "add_deal_note", lambda d, b, **k: notes_added.append(b) or {})
    monkeypatch.setattr(po.hs, "create_task",
                        lambda s, b, o, due, priority=None: tasks.append((s, priority)) or {})
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append((u, t)) or {"ok": True})
    notes = []
    po._handle_cancellation(_cancel_po(), notes)
    deal_patch = next(b for m, p, b in patched if p.endswith("/deals/D9"))
    assert deal_patch["properties"]["amount"] == "0"
    assert deal_patch["properties"]["number_of_hours_in_this_po"] == "0"
    assert deal_patch["properties"]["dealstage"] == "13267787"
    assert notes_added and "CANCELLED" in notes_added[0]
    assert any("54321" in t for _, t in dms)          # invoice number in the alert
    assert tasks and tasks[0][1] == "HIGH"            # void-invoice task for Kath
    assert any("CANCELLED" in n for n in notes)


def test_partial_cancellation_touches_nothing(monkeypatch):
    patched, dms = [], []
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [
        {"id": "D9", "properties": {"dealname": "P - S - OG 1 - 26/27",
                                    "pipeline": "907748", "dealstage": "907749",
                                    "amount": "300", "hubspot_owner_id": ""}}])
    _stopped_pipeline(monkeypatch)
    monkeypatch.setattr(po.hs, "_write",
                        lambda m, p, b=None: patched.append((m, p)) or {"id": "X"})
    monkeypatch.setattr(po.slack_client, "dm", lambda u, t: dms.append(t) or {"ok": True})
    notes = []
    po._handle_cancellation(_cancel_po(billable_stated="3"), notes)
    assert not any(p.endswith("/deals/D9") for m, p in patched)   # no mutation
    assert any("PARTIAL" in n for n in notes)
    assert dms and all("manual" in t for t in dms)


def test_cancellation_without_matching_deal_flags(monkeypatch):
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n: [])
    notes = []
    po._handle_cancellation(_cancel_po(), notes)
    assert any(n.startswith("⚠️") and "NO deal" in n for n in notes)


def test_outbound_scrub_removes_em_dashes():
    from src import gmail_client as g
    out = g._scrub_outbound("Thanks — we will resubmit -- next week.")
    assert "—" not in out and "--" not in out
    assert "Thanks, we will resubmit" in out


# ── 2026-08-28: parent resolution — the Mateo Murray-Fiore incident ──

def test_tw_lookup_matches_compound_surname_part(monkeypatch):
    # PO says 'Murray-Fiore', Teachworks has 'Fiore' — the part retry must find
    # the real family (real lesson history still required)
    from src import teachworks_client as twc
    monkeypatch.setattr(twc, "accounts", lambda: {"online": "tok"})
    def _get(endpoint, params=None, token=None):
        if endpoint == "students":
            if params.get("last_name") == "Fiore":
                return [{"id": 5, "first_name": "Mateo", "last_name": "Fiore",
                         "customer_id": 50}]
            return []                       # exact 'Murray-Fiore' query misses
        if endpoint == "lessons":
            return [{"from_date": "2026-06-01", "employee_name": "Luckey, Emma"}] * 4
        if endpoint == "customers":
            return [{"id": 50, "first_name": "Sarah", "last_name": "Fiore",
                     "email": "sfiore1822@gmail.com"}]
        return []
    monkeypatch.setattr(twc, "tw_get", _get)
    fam = twc.find_family_by_student("Mateo", "Murray-Fiore", tutor_hint="Emma Luckey")
    assert fam and fam["email"] == "sfiore1822@gmail.com"
    assert fam["tutor_match"] is True


def test_prior_deal_lookup_never_guesses_on_first_name_alone(monkeypatch):
    # THE incident: 'Mateo Murray-Fiore' matched nothing by last name, and the
    # old first-name-only fallback resolved a DIFFERENT Mateo's parent (Luis
    # Ramirez). Property search finding nothing must return None — chase, not guess.
    monkeypatch.setattr(po.hs, "search_deals_by_student", lambda f, l=None: [])
    called = {"name_search": 0}
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: called.__setitem__("name_search", 1) or
                        [_deal("D1", "Luis Ramirez - Mateo")])
    assert po._find_parent_via_deals(
        {"student_first": "Mateo", "student_last": "Murray-Fiore"}) is None
    assert called["name_search"] == 0   # the token search is out of this path entirely


def test_prior_deal_lookup_retries_surname_parts(monkeypatch):
    # 'Murray-Fiore' misses on the exact property, hits on the 'Fiore' part →
    # unique parent resolves
    def by_student(first, last=None):
        if first == "Mateo" and last == "Fiore":
            return [_deal("D7", "Sarah Fiore - Mateo - iLead 1 (May) 25/26")]
        return []
    monkeypatch.setattr(po.hs, "search_deals_by_student", by_student)
    monkeypatch.setattr(po.hs, "get_deal_contacts", lambda did: [
        {"id": "C50", "properties": {"email": "sfiore1822@gmail.com",
                                     "firstname": "Sarah", "lastname": "Fiore",
                                     "a_persona": "Family"}}])
    got = po._find_parent_via_deals(
        {"student_first": "Mateo", "student_last": "Murray-Fiore"})
    assert got and got[0]["properties"]["email"] == "sfiore1822@gmail.com"


def test_prior_deal_lookup_requires_last_name(monkeypatch):
    monkeypatch.setattr(po.hs, "search_deals_by_student",
                        lambda f, l=None: [_deal("D1", "Luis Ramirez - Mateo")])
    assert po._find_parent_via_deals({"student_first": "Mateo",
                                      "student_last": ""}) is None
