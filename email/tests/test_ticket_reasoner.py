"""The reasoning sweep: evidence, verdicts, the close gate and the pester ladder."""
import datetime as dt

from src import ticket_reasoner as tr

NOW = dt.datetime.now(dt.timezone.utc)

CFG = {
    "staff": {"kath": {"hubspot_owner_id": "513215050", "slack_user_id": "UK"},
              "mandy": {"hubspot_owner_id": "80047201", "slack_user_id": "UM"},
              "emily": {"hubspot_owner_id": "39191217", "slack_user_id": "UE"}},
    "escalation": {"level2": "mandy", "level3": "emily"},
    "reasoner": {"enabled": True, "allow_close": True, "close_min_confidence": 0.85,
                 "owner_after_hours": 24, "supervisor_after_hours": 48,
                 "last_resort_after_hours": 96, "repeat_every_hours": 24},
    "hubspot": {"ticket_stages": {"closed": "4"}, "portal_id": "1"},
    "classifier": {"model": "m", "max_tokens": 100},
}


def _iso(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).isoformat()


def _ticket(tid="T1", subject="Something", hours=48, owner="513215050"):
    return {"id": tid, "properties": {
        "subject": subject, "hubspot_owner_id": owner, "content": "body",
        "createdate": _iso(hours), "hs_lastmodifieddate": _iso(hours),
        "hs_pipeline_stage": "2"}}


class FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeClient:
    def __init__(self, text):
        self._t = text
        self.messages = self

    def create(self, **k):
        return FakeMsg(self._t)


# ── evidence ────────────────────────────────────────────────────────────────
def test_email_direction_is_read_correctly(monkeypatch):
    """EMAIL is outbound, INCOMING_EMAIL is inbound. Reading it as 'OUTGOING'
    makes every ticket look unanswered — that bug inflated the dropped bucket
    from 13 to 30 on 2026-08-26."""
    monkeypatch.setattr(tr.hs, "get_ticket_emails", lambda t: [
        {"hs_email_direction": "INCOMING_EMAIL", "hs_timestamp": _iso(50), "hs_email_text": "hi"},
        {"hs_email_direction": "EMAIL", "hs_timestamp": _iso(49), "hs_email_text": "we replied"}])
    monkeypatch.setattr(tr.hs, "get_ticket_notes", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_contacts", lambda t: [])
    ev = tr.gather(_ticket())
    assert [e["direction"] for e in ev["emails"]] == ["inbound", "outbound"]


def test_sms_after_the_ticket_is_attached(monkeypatch):
    monkeypatch.setattr(tr.hs, "get_ticket_emails", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_notes", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_contacts", lambda t: [
        {"properties": {"firstname": "Inna", "lastname": "V", "mobilephone": "+1 626-437-1321"}}])
    idx = {"6264371321": {"texts": [{"at": _iso(2), "direction": "incoming", "text": "for physics"}],
                          "calls": []}}
    ev = tr.gather(_ticket(hours=100), idx)
    assert ev["sms"] and "physics" in ev["sms"][0]["text"]


# ── hard-evidence shortcuts (no model call) ────────────────────────────────
def test_invoice_proof_resolves_without_the_model():
    ev = {"subject": "new_po — iLEAD (PO 3114122494)", "invoice_proof": "PO ... has an Invoice #"}
    v = tr.reason(ev)
    assert v["verdict"] == "RESOLVED" and v["confidence"] >= 0.85


def test_duplicate_resolves_without_the_model():
    v = tr.reason({"subject": "x", "duplicate_of": "T9"})
    assert v["verdict"] == "DUPLICATE" and "T9" in v["reason"]


def test_enrich_only_marks_a_po_that_is_actually_invoiced():
    hit = tr.enrich_invoice_proof({"subject": "new_po — x (PO 111)"}, {"111"})
    miss = tr.enrich_invoice_proof({"subject": "new_po — x (PO 222)"}, {"111"})
    assert hit["invoice_proof"] and miss.get("invoice_proof") is None


def test_same_subject_is_not_a_duplicate(monkeypatch):
    """Caught by the 2026-08-26 dry run: two tickets both titled "Eddie Sumlin"
    from one referral partner are DIFFERENT students (CNA support vs a new
    intake for Kaliyah P). Closing on subject text would destroy a live
    referral, so only a shared PO number counts as identity."""
    evs = tr.mark_duplicates([
        {"ticket_id": "A", "subject": "Eddie Sumlin", "age_hours": 4000},
        {"ticket_id": "B", "subject": "Eddie Sumlin", "age_hours": 2600}])
    assert all(e["duplicate_of"] is None for e in evs)


def test_duplicates_keep_the_oldest_ticket(monkeypatch):
    evs = tr.mark_duplicates([
        {"ticket_id": "new", "subject": "new_po — x (PO 555)", "age_hours": 10},
        {"ticket_id": "old", "subject": "new_po — x (PO 555)", "age_hours": 99}])
    by = {e["ticket_id"]: e for e in evs}
    assert by["old"]["duplicate_of"] is None
    assert by["new"]["duplicate_of"] == "old"


# ── the model path ──────────────────────────────────────────────────────────
def test_model_verdict_is_parsed(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    c = FakeClient('{"verdict":"BALL_IN_COURT","confidence":0.7,'
                   '"reason":"tutor asked twice about sick pay","owed_to":"us"}')
    v = tr.reason({"subject": "Morelli", "description": "", "age_hours": 1,
                   "quiet_hours": 1, "emails": [], "notes": [], "sms": [],
                   "calls": [], "invoice_proof": None}, client=c)
    assert v["verdict"] == "BALL_IN_COURT" and "sick pay" in v["reason"]


def test_unknown_verdict_falls_back_to_unclear(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    c = FakeClient('{"verdict":"CLOSE_IT_NOW","confidence":0.99,"reason":"x","owed_to":"us"}')
    v = tr.reason({"subject": "x", "description": "", "age_hours": 1, "quiet_hours": 1,
                   "emails": [], "notes": [], "sms": [], "calls": [],
                   "invoice_proof": None}, client=c)
    assert v["verdict"] == "UNCLEAR"


def test_unparseable_model_output_never_closes(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    v = tr.reason({"subject": "x", "description": "", "age_hours": 1, "quiet_hours": 1,
                   "emails": [], "notes": [], "sms": [], "calls": [],
                   "invoice_proof": None}, client=FakeClient("sorry, no JSON here"))
    assert v["verdict"] == "UNCLEAR" and v["confidence"] == 0.0


# ── the pester ladder ───────────────────────────────────────────────────────
def test_ladder_climbs_with_age(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    assert tr.pester_targets(12, "kath") == []
    assert tr.pester_targets(25, "kath") == ["kath"]
    assert tr.pester_targets(49, "kath") == ["kath", "mandy"]
    assert tr.pester_targets(97, "kath") == ["kath", "mandy", "emily"]


def test_owner_who_is_also_the_supervisor_is_not_dmed_twice(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    assert tr.pester_targets(97, "mandy") == ["mandy", "emily"]


def test_cadence_holds_between_pesters(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    monkeypatch.setattr(tr.audit, "last_reasoner_pester", lambda t: _iso(3))
    assert tr._due_for_pester("T1", NOW) is False
    monkeypatch.setattr(tr.audit, "last_reasoner_pester", lambda t: _iso(30))
    assert tr._due_for_pester("T1", NOW) is True


def test_never_pestered_is_due(monkeypatch):
    monkeypatch.setattr(tr, "cfg", lambda: CFG)
    monkeypatch.setattr(tr.audit, "last_reasoner_pester", lambda t: None)
    assert tr._due_for_pester("T1", NOW) is True


# ── the close gate ──────────────────────────────────────────────────────────
def _run_one(monkeypatch, verdict_json, dry_run, cfg=None, hours=48):
    cfg = cfg or CFG
    closed, dms = [], []
    monkeypatch.setattr(tr, "cfg", lambda: cfg)
    monkeypatch.setattr(tr, "staff", lambda k: (cfg["staff"].get(k) or {}))
    monkeypatch.setattr(tr.hs, "search_open_tickets", lambda: [_ticket(hours=hours)])
    monkeypatch.setattr(tr.hs, "invoiced_po_numbers", lambda: set())
    monkeypatch.setattr(tr.hs, "get_ticket_emails", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_notes", lambda t: [])
    monkeypatch.setattr(tr.hs, "get_ticket_contacts", lambda t: [])
    monkeypatch.setattr(tr.hs, "ticket_url", lambda t: "u")
    monkeypatch.setattr(tr.hs, "update_ticket_stage", lambda t, s: closed.append((t, s)))
    monkeypatch.setattr(tr.hs, "add_ticket_note", lambda t, b: None)
    monkeypatch.setattr(tr.jc, "index_by_number", lambda since_days=90: {})
    monkeypatch.setattr(tr.audit, "append", lambda r: None)
    monkeypatch.setattr(tr.audit, "last_reasoner_pester", lambda t: None)
    monkeypatch.setattr(tr.slack_client, "dm", lambda u, m: dms.append(u))
    monkeypatch.setattr(tr, "reason", lambda ev, client=None: verdict_json)
    out = tr.run(dry_run=dry_run)
    return out, closed, dms


HIGH = {"verdict": "RESOLVED", "confidence": 0.95, "reason": "invoice exists"}
LOW = {"verdict": "RESOLVED", "confidence": 0.6, "reason": "probably fine"}
BALL = {"verdict": "BALL_IN_COURT", "confidence": 0.8, "reason": "they asked twice"}


def test_dry_run_writes_nothing(monkeypatch):
    out, closed, dms = _run_one(monkeypatch, HIGH, dry_run=True)
    assert closed == [] and dms == []
    assert out["lines"][0]["action"] == "CLOSE"


def test_close_happens_when_allowed(monkeypatch):
    out, closed, _ = _run_one(monkeypatch, HIGH, dry_run=False)
    assert closed == [("T1", "4")] and out["closed"] == 1


def test_low_confidence_is_never_closed(monkeypatch):
    out, closed, dms = _run_one(monkeypatch, LOW, dry_run=False)
    assert closed == [] and dms == ["UK", "UM"]   # 48h -> owner + supervisor


def test_allow_close_off_means_no_writes(monkeypatch):
    cfg = {**CFG, "reasoner": {**CFG["reasoner"], "allow_close": False}}
    out, closed, _ = _run_one(monkeypatch, HIGH, dry_run=False, cfg=cfg)
    assert closed == [] and out["closed"] == 0


def test_ball_in_court_pesters_and_never_closes(monkeypatch):
    out, closed, dms = _run_one(monkeypatch, BALL, dry_run=False)
    assert closed == [] and dms == ["UK", "UM"]


def test_nothing_happens_before_24_hours(monkeypatch):
    out, closed, dms = _run_one(monkeypatch, BALL, dry_run=False, hours=6)
    assert closed == [] and dms == []
    assert out["lines"][0]["action"] == "none"


def test_waiting_still_pesters(monkeypatch):
    """Roman 2026-08-26: pester regardless of who owes the reply."""
    waiting = {"verdict": "WAITING", "confidence": 0.9, "reason": "family went quiet"}
    out, closed, dms = _run_one(monkeypatch, waiting, dry_run=False)
    assert closed == [] and dms == ["UK", "UM"]
