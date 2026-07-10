"""Deal-stage automation on cancellations — the safeguards."""
from src import main


def _result(ctype="stop", conf=0.95, student="Layla"):
    return {"cancellation_type": ctype, "confidence": conf, "student_first_name": student}


def _setup(monkeypatch, deals):
    moved = []
    monkeypatch.setattr(main.hs, "get_contact_deals", lambda cid: deals)
    monkeypatch.setattr(main.hs, "stage_label", lambda pl, st: st)          # stage value is the label
    monkeypatch.setattr(main.hs, "find_stop_stage", lambda pl, pats: ("S", "Stopped"))
    monkeypatch.setattr(main.hs, "move_deal_stage", lambda d, s: moved.append((d, s)))
    return moved


def _deal(stage="Pre-Lesson", name="Michelle Schnider - Layla", did="D1"):
    return {"id": did, "name": name, "pipeline": "P", "stage": stage}


def test_auto_move_on_stop(monkeypatch):
    moved = _setup(monkeypatch, [_deal()])
    line, rec = main._cancellation_deal_action("C1", _result("stop"))
    assert moved == [("D1", "S")]
    assert rec and rec["moves"][0]["to"] == "Stopped" and rec["moves"][0]["from"] == "Pre-Lesson"
    assert "Auto-moved" in line


def test_all_active_student_deals_move(monkeypatch):
    # Old data: two active Layla deals — a confident stop closes BOTH.
    moved = _setup(monkeypatch, [_deal(did="D1"), _deal(stage="Post-Lesson", did="D2")])
    line, rec = main._cancellation_deal_action("C1", _result("stop"))
    assert set(moved) == {("D1", "S"), ("D2", "S")}
    assert rec and len(rec["moves"]) == 2


def test_no_student_name_never_auto_moves(monkeypatch):
    # No student name → can't scope → must NOT touch deals (could hit a sibling's).
    moved = _setup(monkeypatch, [_deal(name="Michelle Schnider - Tali")])
    line, rec = main._cancellation_deal_action("C1", _result("stop", student=""))
    assert moved == [] and rec is None and "Review" in line


def test_pause_also_moves_deal(monkeypatch):
    # A pause closes the current deal too — a returning family gets a NEW renewal deal.
    moved = _setup(monkeypatch, [_deal()])
    line, rec = main._cancellation_deal_action("C1", _result("pause"))
    assert moved == [("D1", "S")]
    assert rec and rec["moves"][0]["to"] == "Stopped"


def test_low_confidence_surfaces(monkeypatch):
    moved = _setup(monkeypatch, [_deal()])
    line, rec = main._cancellation_deal_action("C1", _result("stop", conf=0.6))
    assert moved == [] and rec is None and "Review" in line


def test_inactive_deal_ignored(monkeypatch):
    moved = _setup(monkeypatch, [_deal(stage="Stopped")])    # already stopped → not active
    line, rec = main._cancellation_deal_action("C1", _result("stop"))
    assert moved == [] and rec is None and line == ""


def test_one_time_skips_deals(monkeypatch):
    _setup(monkeypatch, [_deal()])   # active deal present, but a one-time skip never touches deals
    line, rec = main._cancellation_deal_action("C1", _result("one_time"))
    assert line == "" and rec is None


def test_no_deals_noop(monkeypatch):
    _setup(monkeypatch, [])
    assert main._cancellation_deal_action("C1", _result("stop")) == ("", None)
