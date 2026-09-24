"""one_to_few --channel email (added 2026-09-15 for the IEM HSA ES email):
recipient = contact email, subject AND body scrubbed, gate on the email
channel, Resend sender, record channel=email. Nothing new is built for SMS."""
import json

import pytest

import one_to_few as otf
from src.presend import Decision


def _es(cid="T1", email="kortiz@ieminc.org"):
    return {"id": cid, "firstname": "Karen", "lastname": "Ortiz", "email": email, "phone": "",
            "mobilephone": "", "a_persona": "Teacher of Record/EF/ES"}


def _allow(cid, channel, from_line, purpose, **kw):
    _allow.calls.append((cid, channel, from_line, purpose, kw))
    return Decision("allow", [], False, "tor", None, {})
_allow.calls = []


def test_email_rows_scrub_subject_and_body_and_gate_on_email_channel():
    _allow.calls.clear()
    rows = otf.build_rows([_es()], purpose="cohort_welcome", from_line="email",
                          bodies={"T1": "Your group starts Sep 21 — weekly through May 14."},
                          subjects={"T1": "Your HSA English 9 group starts Sep 21 — A+ Tutoring"},
                          channel="email", check=_allow)
    r = rows[0]
    assert r["verdict"] == "allow" and r["channel"] == "email" and r["to"] == "kortiz@ieminc.org"
    assert "—" not in r["subject"] and "—" not in r["body"]
    assert r["subject"] == "Your HSA English 9 group starts Sep 21, A+ Tutoring"
    assert _allow.calls[0][1] == "email" and _allow.calls[0][2] == "email"
    assert _allow.calls[0][4]["phone"] == ""


def test_email_without_address_or_subject_is_skipped():
    rows = otf.build_rows([_es(email="")], purpose="cohort_welcome", from_line="email",
                          bodies={"T1": "hi"}, subjects={"T1": "s"}, channel="email", check=_allow)
    assert rows[0]["verdict"] == "skip" and "unusable email" in rows[0]["reasons"][0]
    rows = otf.build_rows([_es()], purpose="cohort_welcome", from_line="email",
                          bodies={"T1": "hi"}, channel="email", check=_allow)
    assert rows[0]["verdict"] == "skip" and rows[0]["reasons"] == ["no subject"]


def test_email_rows_send_through_resend_identity_and_record_email_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(otf, "HERE", tmp_path)
    monkeypatch.setattr(otf, "_pc", lambda: {"email_from": "A+ <admin@wetutorathome.com>"})
    monkeypatch.setitem(otf.m.CFG, "sms", {"per_send_delay_s": 0, "timezone": "America/Los_Angeles"})
    rows = otf.build_rows([_es()], purpose="cohort_welcome", from_line="email",
                          bodies={"T1": "body"}, subjects={"T1": "subj"}, channel="email", check=_allow)
    sent, recorded = [], []
    counts = otf.send_rows(rows, purpose="cohort_welcome", from_line="email", channel="email",
                           sender=lambda f, t, b, s: sent.append((f, t, b, s)) or (True, "resend ok"),
                           record=lambda *a, **k: recorded.append(a), delay=0)
    assert counts["sent"] == 1
    assert sent == [("A+ <admin@wetutorathome.com>", "kortiz@ieminc.org", "body", "subj")]
    assert recorded[0][1] == "email" and recorded[0][3] == "cohort_welcome"
    log = list((tmp_path / "state" / "sends").glob("*-cohort_welcome.jsonl"))
    line = json.loads(log[0].read_text().splitlines()[0])
    assert line["channel"] == "email" and line["subject"] == "subj"


def test_send_email_dry_run_never_posts(monkeypatch):
    monkeypatch.setattr(otf, "DRY_RUN", True)
    assert otf.send_email("a@x", "b@y", "body", "subj") == (True, "dry run")


def test_cli_email_channel_requires_email_line_and_subject(monkeypatch):
    monkeypatch.setattr(otf, "_pc", lambda: {"purposes": {"cohort_welcome": {}}, "lines": {"support": "+1"}})
    with pytest.raises(SystemExit) as e:
        otf.main(["--contacts", "1", "--purpose", "cohort_welcome", "--from", "support",
                  "--bodies", "/dev/null", "--channel", "email", "--subject", "s"])
    assert "'email' line" in str(e.value)
    with pytest.raises(SystemExit) as e2:
        otf.main(["--contacts", "1", "--purpose", "cohort_welcome", "--from", "email",
                  "--bodies", "/dev/null", "--channel", "email"])
    assert "--subject" in str(e2.value)
