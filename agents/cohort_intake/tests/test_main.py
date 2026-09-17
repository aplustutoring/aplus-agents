"""End to end through the CLI with the sheet, HubSpot, Slack and the send
rail faked: dry run writes nothing; execute writes deals, sends ONE ES email
per ES per group, DMs the scheduler once, stamps the sheet, appends the Log."""
from agents.cohort_intake import __main__ as CLI, messages as M, sheet as S, stop_window as SW, writer as W
from agents.cohort_intake import _bootstrap as B
from agents.cohort_intake.tests import fixtures as F, hsmock as H


class FakeSheet:
    instances = []

    def __init__(self, sid, dry_run=True):
        self.id, self.dry_run = sid, dry_run
        self.outputs, self.logs = [], []
        self.rows = [(i + 2, cells) for i, cells in enumerate(F.GROUP1)]
        FakeSheet.instances.append(self)

    def read_intake(self):
        return list(F.HEADERS), self.rows

    def ensure_output_columns(self, headers):
        return headers

    def write_outputs(self, headers, row, values):
        self.outputs.append((row, values))

    def append_log(self, mode, rows, did, refused, by):
        self.logs.append((mode, rows, did, refused))


def _wire(monkeypatch, fake_hs):
    FakeSheet.instances.clear()
    monkeypatch.setattr(S, "Sheet", FakeSheet)
    H.wire(monkeypatch, fake_hs)
    dms, sends = [], []
    monkeypatch.setattr(B.slack_client, "dm", lambda u, t: dms.append((u, t)) or {"ok": True})
    monkeypatch.setattr(CLI, "date", type("D", (), {"today": staticmethod(lambda: __import__("datetime").date(2026, 9, 15))}))
    monkeypatch.setattr(SW, "hold", lambda summary, minutes: (True, "test"))
    monkeypatch.setattr(B.otf, "fetch_contacts",
                        lambda ids: [{"id": ids[0], "email": "kortiz@ieminc.org", "firstname": "Karen",
                                      "lastname": "Ortiz", "phone": "", "mobilephone": ""}])
    from src.presend import Decision
    monkeypatch.setattr(B.otf.presend, "check", lambda *a, **k: Decision("allow", [], False, "tor", None, {}))

    def send_rows(rows, **kw):
        sends.append((rows, kw))
        return {"sent": len(rows), "failed": 0, "held": 0, "blocked": 0, "skipped": 0}
    monkeypatch.setattr(B.otf, "send_rows", send_rows)
    monkeypatch.setattr(B, "staff", lambda k: H.STAFF.get(k, {}))
    return dms, sends


def test_dry_run_plans_and_writes_nothing(monkeypatch):
    fake = H.FakeHS()
    dms, sends = _wire(monkeypatch, fake)
    assert CLI.main([]) == 0
    assert fake.created_deals == [] and fake.created_contacts == []
    assert sends == [] and FakeSheet.instances[0].outputs == []
    assert FakeSheet.instances[0].logs[0][0] == "dry-run"
    # plan DM to Roman + Danielle
    assert {u for u, _ in dms} == {"UR", "UD"} and "$1,250.00 → deal create" in dms[0][1]


def test_list_prints_every_row_with_status_and_writes_nothing(monkeypatch, capsys):
    fake = H.FakeHS()
    dms, sends = _wire(monkeypatch, fake)
    assert CLI.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "IEM-1001" in out and "Diego R." in out and "Ready" in out
    assert "Diego Reyna" not in out                               # last initial only in logs
    assert "reyna.family@gmail.com" not in out                    # no parent contact details
    assert fake.created_deals == [] and dms == [] and sends == []


def test_only_row_narrows_to_one_student(monkeypatch):
    fake = H.FakeHS()
    dms, _ = _wire(monkeypatch, fake)
    assert CLI.main(["--only-row", "IEM-1002"]) == 0
    assert "1 student(s)" in dms[0][1] and "Maya C." in dms[0][1]     # dry run: redacted everywhere


def test_dry_run_log_never_carries_full_student_names(monkeypatch, capsys):
    fake = H.FakeHS()
    _wire(monkeypatch, fake)
    assert CLI.main([]) == 0
    out = capsys.readouterr().out
    assert "Diego R. (IEM-1001)" in out and "Diego Reyna" not in out
    assert CLI.main(["--only-row", "NOPE-1"]) == 1


def test_execute_writes_deals_one_es_email_per_group_and_one_handoff(monkeypatch):
    fake = H.FakeHS()
    dms, sends = _wire(monkeypatch, fake)
    assert CLI.main(["--execute", "--wait-minutes", "0"]) == 0
    assert len(fake.created_deals) == 3
    # ONE ES email for the group (one ES), on the email channel, cohort_welcome
    assert len(sends) == 1
    rows, kw = sends[0]
    assert len(rows) == 1 and rows[0]["channel"] == "email" and rows[0]["to"] == "kortiz@ieminc.org"
    assert kw["purpose"] == "cohort_welcome" and kw["channel"] == "email"
    assert rows[0]["subject"] == "Your HSA English 9 group starts Sep 21: A+ Tutoring"
    assert "—" not in rows[0]["subject"] and "—" not in rows[0]["body"]
    # ONE handoff DM to the owning scheduler (Janelle, odd group), summary DMs to Roman + Danielle
    handoffs = [t for u, t in dms if u == "UJ"]
    assert len(handoffs) == 1 and "Book *25 sessions*" in handoffs[0]
    assert any("cohort_intake done" in t for u, t in dms if u == "UR")
    # sheet: deal id + cohort + sessions on each row, ES Email Sent on each row, one Log line
    sheet = FakeSheet.instances[0]
    stamped = {row: vals for row, vals in sheet.outputs if "HubSpot Deal ID" in vals}
    assert set(stamped) == {2, 3, 4} and stamped[2]["Cohort"] == "1" and stamped[2]["Sessions"] == "25"
    assert sum(1 for _r, v in sheet.outputs if "ES Email Sent" in v) == 3
    assert sheet.logs[-1][0] == "execute" and "deal" in sheet.logs[-1][2]


def test_rerun_never_repeats_the_es_email_or_the_handoff(monkeypatch):
    fake = H.FakeHS()
    dms, sends = _wire(monkeypatch, fake)
    assert CLI.main(["--execute", "--wait-minutes", "0"]) == 0
    fake.deals = list(fake.created_deals)                  # the deals now exist
    fake.created_deals = []
    assert CLI.main(["--execute", "--wait-minutes", "0"]) == 0
    assert len(sends) == 1                                 # ES email once per roster
    assert len([t for u, t in dms if u == "UJ"]) == 1      # handoff once per roster
    assert fake.created_deals == [] and len(fake.patched_deals) == 3


def test_a_refused_row_never_blocks_the_valid_group(monkeypatch):
    fake = H.FakeHS()
    dms, _ = _wire(monkeypatch, fake)
    bad = list(F.LATE_ADD)
    bad[7] = ""                                            # blank parent email → hard-stop
    FakeSheet.instances.clear()
    orig_init = FakeSheet.__init__

    def init(self, sid, dry_run=True):
        orig_init(self, sid, dry_run)
        self.rows.append((5, bad))
    monkeypatch.setattr(FakeSheet, "__init__", init)
    assert CLI.main([]) == 0
    assert "Refused (fix the sheet, re-run)" in dms[0][1] and "IEM-1004" in dms[0][1]
    assert "3 student(s)" in dms[0][1]
