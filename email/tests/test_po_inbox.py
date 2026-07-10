"""PO-inbox deal handling: advance Waiting-for-PO, create when none, surface on multi."""
from src import po_inbox as po


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


def test_no_names_no_action(monkeypatch):
    notes = []
    po._handle_deal(_po(school="", student_first="", student_last=""), notes)
    assert "review manually" in notes[0]
