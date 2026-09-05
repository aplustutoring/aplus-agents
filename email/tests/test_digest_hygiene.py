"""Weekly digest B2C deal-hygiene block."""
from datetime import date

from src import digest


def test_hygiene_flags_no_amount_and_junk_school(monkeypatch):
    rows = [{"properties": {"dealname": "Lara Perkins - Nomi", "amount": "", "student_school": "."}},
            {"properties": {"dealname": "Good Deal - Kid", "amount": "500", "student_school": "Colfax"}},
            {"properties": {"dealname": "Zero Amount - Kid", "amount": "0", "student_school": "Real School"}}]
    monkeypatch.setattr(digest.hs, "_write", lambda m, p, b=None: {"results": rows})
    block = digest._deal_hygiene_block(date(2026, 8, 24), date(2026, 8, 30))
    assert "Lara Perkins - Nomi" in block and "no amount, school blank/junk" in block
    assert "Zero Amount - Kid" in block and "Good Deal" not in block


def test_hygiene_silent_when_clean(monkeypatch):
    monkeypatch.setattr(digest.hs, "_write", lambda m, p, b=None: {"results": [
        {"properties": {"dealname": "Good Deal - Kid", "amount": "500", "student_school": "Colfax"}}]})
    assert digest._deal_hygiene_block(date(2026, 8, 24), date(2026, 8, 30)) == ""


def test_hygiene_never_breaks_digest(monkeypatch):
    monkeypatch.setattr(digest.hs, "_write",
                        lambda m, p, b=None: (_ for _ in ()).throw(RuntimeError("api down")))
    assert digest._deal_hygiene_block(date(2026, 8, 24), date(2026, 8, 30)) == ""
