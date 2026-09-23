"""Duplicate-PO guard: firm, and failing closed.

Roman, 2026-09-12: "Let's get rid of the approval checks, we will work on Kath
verifying in ops later. For now I just want the no duplicate po option being
firm as possible."

Five holes were closed, one test class each below:
  1. the lookup itself was blind in DRY_RUN (it went through `_write`);
  2. a PO with no readable number skipped the check entirely;
  3. EQ on the bare number missed "PO"-prefixed and case-differing spellings;
  4. HubSpot's search index lags, so two copies of one PO both passed;
  5. a failed lookup fell through to creation.
Every path must end with NO deal and a human alerted.
"""
import pytest

from src import deal_sync as dsy_mod, hubspot_client as hs, po_inbox as po

# Captured before the autouse fixture below stubs them out on the module: the
# client-level tests exercise the REAL lookups.
REAL_FIND_BY_PO = hs.find_deals_by_po_number
REAL_SEARCH_BY_NAME = hs.search_deals_by_name


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    po._RUN_SEQ.clear()
    # audit ledger: empty unless a test supplies rows (the real 8 MB
    # state/audit_log.jsonl must never decide a test)
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter(()))
    monkeypatch.setattr(po.hs, "search_deals_by_student", lambda first, last=None: [],
                        raising=False)
    monkeypatch.setattr(dsy_mod, "sync_deal", lambda d, **k: {"action_taken": "skipped"})
    monkeypatch.setattr(po.hs, "get_contact_to_contact_associations", lambda cid: [])
    monkeypatch.setattr(po.hs, "get_deal_contacts", lambda did: [])
    monkeypatch.setattr(po.hs, "find_contact_by_secondary_email", lambda e: None)
    monkeypatch.setattr(po.hs, "search_deals_by_name", lambda t, p=None, s=None: [])
    monkeypatch.setattr(po.hs, "find_deals_by_po_number", lambda n, raw="": [],
                        raising=False)
    monkeypatch.setattr(po.hs, "stage_label", lambda pipeline, stage: "presented")
    monkeypatch.setattr(po.hs, "create_task", lambda *a, **k: {"id": "T1"})
    yield
    po._RUN_SEQ.clear()


def _po(**kw):
    base = {"is_po": True, "school": "iLEAD", "student_first": "Ana", "student_last": "Diaz",
            "po_number": "4471", "amount": "1500", "hours": "10", "summary": "s",
            "confidence": 0.95}
    base.update(kw)
    return base


class Recorder:
    """create_deal / audit.append / slack.dm recorders wired in one place."""

    def __init__(self, monkeypatch, *, allow_create=True):
        self.created, self.audits, self.dms = [], [], []
        if allow_create:
            monkeypatch.setattr(po.hs, "create_deal", self._create)
        else:
            monkeypatch.setattr(po.hs, "create_deal", self._forbidden)
        monkeypatch.setattr(po.audit, "append", lambda r: self.audits.append(r))
        monkeypatch.setattr(po.slack_client, "dm", lambda u, t: self.dms.append((u, t)))

    def _create(self, name, pl, st, amt=None, **k):
        self.created.append(name)
        return {"id": f"D{len(self.created)}"}

    def _forbidden(self, *a, **k):
        raise AssertionError("create_deal must never be called on a refused PO")

    @property
    def actions(self):
        return [r.get("action_taken") for r in self.audits]


def _cfg(monkeypatch, **over):
    real = po.cfg()
    merged = {**real, "po_inbox": {**real["po_inbox"], **over}}
    monkeypatch.setattr(po, "cfg", lambda: merged)


# ── Hole 1: the lookup was blind in DRY_RUN ─────────────────────────────────

def test_po_lookups_read_through_get_search_not_write():
    """`_write` short-circuits in DRY_RUN and returns {"id": "DRYRUN"}, so both
    dedupe lookups answered "no deals" on every dry run and the guard behind
    them never fired. A search is a READ: it goes through `_get_search`."""
    import inspect
    for fn in (REAL_FIND_BY_PO, REAL_SEARCH_BY_NAME):
        body = inspect.getsource(fn)
        assert "_get_search(" in body
        assert "_write(" not in body


def test_dry_run_still_performs_a_real_duplicate_lookup(monkeypatch):
    assert hs.DRY_RUN is True                      # conftest forces it
    monkeypatch.setattr(hs, "_write",
                        lambda *a, **k: pytest.fail("a search must not go through _write"))
    monkeypatch.setattr(hs, "_get_search",
                        lambda path, body: {"results": [{"id": "D1", "properties":
                                                         {"po_number": "4471"}}]})
    assert REAL_FIND_BY_PO("4471")[0]["id"] == "D1"
    assert REAL_SEARCH_BY_NAME("4471")[0]["id"] == "D1"


# ── Hole 2: a missing PO number disabled dedupe ─────────────────────────────

def test_missing_po_number_refuses_to_create(monkeypatch):
    _cfg(monkeypatch, require_po_number=True)
    rec = Recorder(monkeypatch, allow_create=False)
    notes = []
    po._handle_deal(_po(po_number=""), notes)
    assert rec.created == []
    assert "po_refused_no_number" in rec.actions
    assert any(n.startswith("⛔") and "NO readable PO number" in n for n in notes)
    assert rec.dms and "no readable" in rec.dms[0][1].lower()


def test_missing_po_number_refusal_reaches_the_gap_dm(monkeypatch):
    _cfg(monkeypatch, require_po_number=True)
    Recorder(monkeypatch, allow_create=False)
    notes = []
    po._handle_deal(_po(po_number=""), notes)
    # ⛔ notes are MISSING-INFO notes, so the ticket's gap DM carries the refusal
    assert po._gap_notes(notes)


def test_missing_po_number_keeps_old_behaviour_when_flag_is_off(monkeypatch):
    _cfg(monkeypatch, require_po_number=False)
    rec = Recorder(monkeypatch)
    po._handle_deal(_po(po_number=""), [])
    assert len(rec.created) == 1
    assert "po_refused_no_number" not in rec.actions


# ── Hole 3: EQ on the bare number missed real variants ──────────────────────

def test_lookup_tries_prefixed_and_case_variants_in_order(monkeypatch):
    tried = []

    def fake_search(path, body):
        value = body["filterGroups"][0]["filters"][0]["value"]
        tried.append(value)
        if value == "PO3114181734":                # how the old deal is stored
            return {"results": [{"id": "D-old", "properties":
                                 {"po_number": "PO3114181734", "dealname": "Old"}}]}
        return {"results": []}

    monkeypatch.setattr(hs, "_get_search", fake_search)
    hits = REAL_FIND_BY_PO("3114181734")
    assert [h["id"] for h in hits] == ["D-old"]
    assert tried[0] == "3114181734"                # normalized first
    assert "PO3114181734" in tried


def test_case_differing_alphanumeric_number_is_found(monkeypatch):
    stored = "pf252648-ezekielgarcia"

    def fake_search(path, body):
        value = body["filterGroups"][0]["filters"][0]["value"]
        return ({"results": [{"id": "D-case", "properties": {"po_number": stored}}]}
                if value == stored else {"results": []})

    monkeypatch.setattr(hs, "_get_search", fake_search)
    assert REAL_FIND_BY_PO("PF252648-EzekielGarcia")[0]["id"] == "D-case"


def test_prefixed_duplicate_blocks_the_deal(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.hs, "find_deals_by_po_number",
                        lambda n, raw="": [{"id": "D-old", "properties": {
                            "po_number": "PO3114181734", "dealname": "Parent - Kid - iLead 1"}}])
    notes = []
    po._handle_deal(_po(po_number="3114181734"), notes)
    assert rec.created == []
    assert "po_refused_duplicate" in rec.actions
    assert any("DUPLICATE PO 3114181734" in n for n in notes)
    assert rec.dms and "URGENT" in rec.dms[0][1]


def test_a_returned_deal_with_a_different_number_is_not_a_duplicate(monkeypatch):
    # normalized equality decides, not the filter: a row carrying some OTHER
    # number is discarded rather than blocking a genuinely new PO
    rec = Recorder(monkeypatch)
    monkeypatch.setattr(po.hs, "find_deals_by_po_number",
                        lambda n, raw="": [{"id": "D-other", "properties": {
                            "po_number": "9999999", "dealname": "Someone else"}}])
    po._handle_deal(_po(po_number="4471"), [])
    assert len(rec.created) == 1


def test_exact_duplicate_blocks_and_audits(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.hs, "find_deals_by_po_number",
                        lambda n, raw="": [{"id": "X", "properties": {
                            "po_number": "53779", "dealname": "PCA - Carson - PO 53779"}}])
    notes = []
    po._handle_deal(_po(po_number="53779"), notes)
    assert rec.created == []
    assert "po_refused_duplicate" in rec.actions
    assert any("DUPLICATE PO 53779" in n for n in notes)


def test_stopped_deal_is_reported_as_a_reissue_and_still_creates_nothing(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.hs, "stage_label", lambda pipeline, stage: "Stopped")
    monkeypatch.setattr(po.hs, "find_deals_by_po_number",
                        lambda n, raw="": [{"id": "X", "properties": {
                            "po_number": "53779", "dealname": "PCA - Carson"}}])
    notes = []
    po._handle_deal(_po(po_number="53779"), notes)
    assert rec.created == []
    assert any("re-issued" in n for n in notes)
    assert "po_reissue_flagged" in rec.actions


def test_deal_name_backstop_still_blocks_deals_without_the_property(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: [{"id": "L", "properties": {
                            "dealname": "Parent - Kid - PCA 1 - 25/26 - PO 53779"}}])
    notes = []
    po._handle_deal(_po(po_number="53779"), notes)
    assert rec.created == []
    assert any("DUPLICATE PO 53779" in n for n in notes)


# ── Hole 4: HubSpot's search index lags ─────────────────────────────────────

def test_ledger_duplicate_blocks_when_hubspot_search_is_empty(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter([
        {"action_taken": "po_deal_created", "po_number": "4471", "deal_id": "D-earlier"}]))
    notes = []
    po._handle_deal(_po(po_number="4471"), notes)
    assert rec.created == []
    assert "po_refused_ledger_duplicate" in rec.actions
    assert any("DUPLICATE PO 4471" in n and "HubSpot search" in n for n in notes)


def test_legacy_po_processed_rows_count_as_a_created_deal(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter([
        {"action_taken": "po_processed", "category": "new_po", "po_number": "PO 4471"}]))
    po._handle_deal(_po(po_number="4471"), [])
    assert rec.created == []
    assert "po_refused_ledger_duplicate" in rec.actions


def test_unrelated_ledger_rows_do_not_block(monkeypatch):
    rec = Recorder(monkeypatch)
    monkeypatch.setattr(po.audit, "_iter_records", lambda: iter([
        {"action_taken": "po_processed", "category": "po_inbox_other", "po_number": "4471"},
        {"action_taken": "po_cancelled", "po_number": "4471"}]))
    po._handle_deal(_po(po_number="4471"), [])
    assert len(rec.created) == 1


def test_one_email_carrying_the_same_number_twice_creates_one_deal(monkeypatch):
    rec = Recorder(monkeypatch)
    notes = []
    po._handle_deal(_po(po_number="", pos=[
        {"po_number": "3114047368", "amount": "150", "po_month": "2026-08"},
        {"po_number": "3114047368", "amount": "150", "po_month": "2026-08"}]), notes)
    assert len(rec.created) == 1
    assert "po_refused_ledger_duplicate" in rec.actions


def test_two_different_numbers_in_one_email_still_create_two_deals(monkeypatch):
    rec = Recorder(monkeypatch)
    po._handle_deal(_po(po_number="", pos=[
        {"po_number": "3114047368", "amount": "150", "po_month": "2026-08"},
        {"po_number": "3114047369", "amount": "300", "po_month": "2026-09"}]), [])
    assert len(rec.created) == 2


# ── Hole 5: a failed lookup fell through to creation ────────────────────────

def test_lookup_failure_refuses_to_create(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)

    def boom(n, raw=""):
        raise RuntimeError("HubSpot 502")

    monkeypatch.setattr(po.hs, "find_deals_by_po_number", boom)
    notes = []
    po._handle_deal(_po(po_number="4471"), notes)
    assert rec.created == []                       # create_deal raises if called
    assert "po_refused_dedupe_unavailable" in rec.actions
    assert any("Could not check PO 4471" in n for n in notes)
    assert rec.dms and "duplicate lookup failed" in rec.dms[0][1]


def test_name_backstop_failure_also_refuses(monkeypatch):
    rec = Recorder(monkeypatch, allow_create=False)
    monkeypatch.setattr(po.hs, "search_deals_by_name",
                        lambda t, p=None, s=None: (_ for _ in ()).throw(RuntimeError("429")))
    po._handle_deal(_po(po_number="4471"), [])
    assert rec.created == []
    assert "po_refused_dedupe_unavailable" in rec.actions


def test_fail_closed_can_be_turned_off(monkeypatch):
    _cfg(monkeypatch, dedupe_fail_closed=False)
    rec = Recorder(monkeypatch)

    def boom(n, raw=""):
        raise RuntimeError("HubSpot 502")

    monkeypatch.setattr(po.hs, "find_deals_by_po_number", boom)
    po._handle_deal(_po(po_number="4471"), [])
    assert len(rec.created) == 1                   # explicit opt-out only


def test_defaults_are_safe_when_the_config_keys_are_absent(monkeypatch):
    # an older config.yaml (no require_po_number / dedupe_fail_closed) must get
    # the SAFE behaviour, not the old permissive one
    real = po.cfg()
    stripped = {k: v for k, v in real["po_inbox"].items()
                if k not in ("require_po_number", "dedupe_fail_closed")}
    monkeypatch.setattr(po, "cfg", lambda: {**real, "po_inbox": stripped})
    rec = Recorder(monkeypatch, allow_create=False)
    po._handle_deal(_po(po_number=""), [])
    assert "po_refused_no_number" in rec.actions


# ── the happy path must survive all of it ───────────────────────────────────

def test_a_genuinely_new_po_still_creates_exactly_one_deal(monkeypatch):
    rec = Recorder(monkeypatch)
    notes = []
    po._handle_deal(_po(po_number="7514044381"), notes)
    assert len(rec.created) == 1
    assert any("Created deal" in n for n in notes)
    assert "po_deal_created" in rec.actions
    created_row = next(r for r in rec.audits if r["action_taken"] == "po_deal_created")
    assert created_row["po_number"] == "7514044381"
    assert not [a for a in rec.actions if str(a).startswith("po_refused")]


def test_config_ships_both_flags_on():
    pc = po.cfg()["po_inbox"]
    assert pc["require_po_number"] is True
    assert pc["dedupe_fail_closed"] is True


# ── the removed pending-approval follow-up ──────────────────────────────────

def test_no_module_emits_the_pending_approval_follow_up_actions():
    import pathlib
    root = pathlib.Path(po.__file__).resolve().parent
    for path in root.glob("*.py"):
        text = path.read_text()
        for gone in ("_sweep_pending_pos", "pending_po_opened", "pending_po_confirmed",
                     "pending_po_reminded"):
            assert gone not in text, f"{gone} still in {path.name}"
