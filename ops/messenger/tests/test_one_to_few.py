"""one_to_few: the small-send rail. Dry run by default, gate decides, only
ALLOW rows reach JustCall, every body is scrubbed."""
import json

import pytest

import one_to_few as otf
from src.presend import Decision


def _c(cid="C1", first="Mary", last="Gonzalez", phone="+18187216225", **more):
    c = {"id": cid, "firstname": first, "lastname": last, "email": f"{first.lower()}@x.com",
         "phone": phone, "mobilephone": "", "student_first_name": "Alex", "last_tutor_name": "Christa",
         "student_names": "Alex", "student_count": "1", "a_persona": "Family"}
    c.update(more)
    return c


def _check_factory(verdicts: dict):
    def check(cid, channel, from_line, purpose, **kw):
        v = verdicts.get(cid, "allow")
        owner = {"name": "Yolanda", "seat": "scheduler_m_z"} if v == "hold" else None
        return Decision(v, [f"{v} reason"], False, "lead", owner, {})
    return check


def test_build_rows_renders_scrubs_and_gates():
    rows = otf.build_rows([_c()], purpose="po_push", from_line="charter_sales",
                          template="Hi {{firstname}} — {{student_first_name}}'s tutor {{last_tutor_name}}",
                          confirmed=True, check=_check_factory({}))
    assert rows[0]["verdict"] == "allow"
    assert "—" not in rows[0]["body"] and "Alex" in rows[0]["body"]
    assert rows[0]["to"] == "+18187216225"


def test_missing_merge_field_skips_not_sends():
    rows = otf.build_rows([_c(last_tutor_name="")], purpose="po_push", from_line="charter_sales",
                          template="{{last_tutor_name}} is back", confirmed=True, check=_check_factory({}))
    assert rows[0]["verdict"] == "skip" and "missing merge field" in rows[0]["reasons"][0]


def test_bodies_path_for_hand_written_relays():
    rows = otf.build_rows([_c()], purpose="lead_relay", from_line="charter_sales",
                          bodies={"C1": "Jonathan can do Monday at 12 — ok?"}, confirmed=True,
                          check=_check_factory({}))
    assert rows[0]["body"] == "Jonathan can do Monday at 12, ok?" or "—" not in rows[0]["body"]


def test_only_allow_rows_reach_justcall(tmp_path, monkeypatch):
    monkeypatch.setattr(otf, "HERE", tmp_path)
    monkeypatch.setattr(otf, "_pc", lambda: {"lines": {"charter_sales": "+18185736644"}})
    monkeypatch.setitem(otf.m.CFG, "sms", {"per_send_delay_s": 0, "timezone": "America/Los_Angeles"})
    rows = otf.build_rows([_c("C1"), _c("C2", "Jeanie", "Salcedo", "+19164130385")],
                          purpose="po_push", from_line="charter_sales", template="Hi {{firstname}}",
                          confirmed=True, check=_check_factory({"C1": "hold"}))
    sent, recorded = [], []
    counts = otf.send_rows(rows, purpose="po_push", from_line="charter_sales",
                           sender=lambda f, t, b: sent.append((f, t, b)) or (True, "200 ok"),
                           record=lambda *a, **k: recorded.append(a), delay=0)
    assert counts == {"sent": 1, "failed": 0, "held": 1, "blocked": 0, "skipped": 0}
    assert sent[0][1] == "+19164130385" and sent[0][0] == "+18185736644"
    assert recorded[0][0] == "C2"
    log = list((tmp_path / "state" / "sends").glob("*-po_push.jsonl"))
    assert log and json.loads(log[0].read_text().splitlines()[0])["contact_id"] == "C2"


def test_live_requires_confirm_and_refuses_over_max_few(monkeypatch, capsys):
    monkeypatch.setattr(otf, "_pc", lambda: {"purposes": {"po_push": {}}, "lines": {"charter_sales": "+1"},
                                              "max_few": 2})
    monkeypatch.setattr(otf, "fetch_contacts", lambda ids: [_c(i) for i in ids])
    with pytest.raises(SystemExit) as e:
        otf.main(["--contacts", "1,2,3", "--purpose", "po_push", "--from", "charter_sales",
                  "--template", "x"])
    assert "max_few" in str(e.value)
    with pytest.raises(SystemExit) as e2:
        otf.main(["--contacts", "1", "--purpose", "po_push", "--from", "charter_sales",
                  "--bodies", "/dev/null", "--live"])
    assert "confirm SEND" in str(e2.value)


def test_missing_from_or_purpose_refuses():
    with pytest.raises(SystemExit):
        otf.main(["--contacts", "1", "--purpose", "po_push", "--template", "x"])
    with pytest.raises(SystemExit):
        otf.main(["--contacts", "1", "--from", "charter_sales", "--template", "x"])
