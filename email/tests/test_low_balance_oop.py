"""Roman 2026-09-24: 'CHARTER - Out of Pocket' is its own funding type, not
private pay. Scheduler split owns it, no PO ask, no teacher of record; the
ask is the charter family packs (HubSpot payment links), email and text
together, held until the rail is armed."""
from src import low_balance as lb
from test_low_balance import ALERT, DEAL, MSG, RECENT, Harness, _cfg

OOP = {"armed": True, "package_token": "out of pocket",
       "subject": "{student}'s prepaid tutoring sessions are running low",
       "template": "templates/low_balance_out_of_pocket.html",
       "sms_template": "Hi {first_name}, this is A+ Tutoring. {student} has {hours} left of prepaid sessions. "
                       "To keep going, the charter family packs are here: {pack_link}. Reply here with any questions.",
       "packs": [{"name": "6-Session Pack", "detail": "six 45-minute sessions", "price": 300, "url": "https://x/6"},
                 {"name": "12-Session Pack", "detail": "twelve 45-minute sessions", "price": 550, "url": "https://x/12"}]}
OOP_DEAL = {"id": "9", "properties": {**DEAL["properties"], "pipeline": "default", "po_number": ""}}
OOP_ALERT = ALERT.replace("Charter - iLEAD", "CHARTER - Out of Pocket")


def _open(monkeypatch, armed_rail=True):
    h = Harness(monkeypatch, _cfg(armed=True, charter_only=False, out_of_pocket={**OOP, "armed": armed_rail}),
                deals=[OOP_DEAL], recent=RECENT)
    monkeypatch.setattr(lb.hs, "pipeline_label", lambda p: "Gold Tutoring")
    rec = lb.handle_alert("thr1", {**MSG, "text": OOP_ALERT}, lb.parse_alert(OOP_ALERT))
    return h, rec


def test_funding_type_is_charter_out_of_pocket():
    lbc = {"trial_packages": ["trial"], "out_of_pocket": {"package_token": "out of pocket"}}
    assert lb._funding_type({"package": "CHARTER - Out of Pocket"}, False, lbc) == "charter_out_of_pocket"
    assert lb._funding_type({"package": "Charter - iLEAD"}, True, lbc) == "charter"
    assert lb._funding_type({"package": "2026 - Prep Package"}, False, lbc) == "private_pay"
    assert lb._funding_type({"package": "Promotion - First Trial Lesson"}, False, lbc) == "trial"


def test_out_of_pocket_case_scheduler_owned_no_po_no_teacher(monkeypatch):
    h, rec = _open(monkeypatch)
    assert rec["action_taken"] == "low_balance_opened"
    assert rec["funding_type"] == "charter_out_of_pocket" and rec["out_of_pocket"] is True and rec["private_pay"] is False
    assert rec["charter"] is False and rec["owner"] == "scheduler_a_l"          # Lujan: A-L, the split, not Paola
    assert h.tickets[0][1]["funding_type"] == "charter_out_of_pocket"
    assert h.tickets[0][0][0].startswith("Low balance: Taylor Rodriguez (iLead)")   # school tag, like charter
    assert rec["email_subject"] == "Taylor's prepaid tutoring sessions are running low"
    assert "https://x/12" in rec["sms_body"] and "PO" not in rec["sms_body"] and "prepaid sessions" in rec["sms_body"]
    assert rec["tor_body"] == "" and rec["email_pending"]
    assert "—" not in rec["sms_body"] and "--" not in rec["sms_body"]
    assert any("no teacher of record" in ln for ln in h.dms[0][1].splitlines())


def test_out_of_pocket_email_carries_every_pack_link(monkeypatch):
    h, rec = _open(monkeypatch)
    h.send_pending({rec["message_id"]: rec})
    assert len(h.emails) == 1
    to, subj, tpl, ctx = h.emails[0]
    assert to == "jessicalujanbd@gmail.com" and subj == "Taylor's prepaid tutoring sessions are running low"
    assert tpl.endswith("low_balance_out_of_pocket.html")
    assert "https://x/6" in ctx["pack_lines"] and "https://x/12" in ctx["pack_lines"] and "$550" in ctx["pack_lines"]
    assert ctx["sender_email"] == "janelle@wetutorathome.com"                  # reply-to the case owner
    assert any(r["action_taken"] == "low_balance_email_sent" for r in h.recs)
    import re
    html = re.sub(r"<!--.*?-->", "", lb._render((lb.ROOT / "templates/low_balance_out_of_pocket.html").read_text(), ctx), flags=re.S)
    assert "PO" not in html and "teacher" not in html.lower() and "—" not in html


def test_out_of_pocket_rail_holds_until_armed(monkeypatch):
    h, rec = _open(monkeypatch, armed_rail=False)
    h.send_pending({rec["message_id"]: rec})
    assert not h.emails
    held = next(r for r in h.recs if r["action_taken"] == "low_balance_email_held")
    assert "Out-of-pocket rail not armed" in held["reason"]
