"""Gold deals: amount from the family's most current Teachworks invoice."""
from src import deal_sync as dsy, teachworks_client as tw


def test_latest_invoice_picks_newest_nonzero(monkeypatch):
    monkeypatch.setattr(tw, "tw_get", lambda ep, p=None, token=None: [
        {"date": "2026-08-01", "total": "480.0", "number": "1001"},
        {"date": "2026-09-01", "total": "0", "number": "1003"},      # void/zero → skipped
        {"date": "2026-08-20", "total": "520.0", "number": "1002"}])
    inv = tw.latest_invoice(7)
    assert inv == {"total": 520.0, "number": "1002", "date": "2026-08-20"}


def test_latest_invoice_none_when_no_invoices(monkeypatch):
    monkeypatch.setattr(tw, "tw_get", lambda ep, p=None, token=None: [])
    assert tw.latest_invoice(7) is None


def _wire_gold(monkeypatch, calls):
    base = {"deal_sync": {"enabled": True, "dry_run_first": False,
                          "in_person_pipelines": [], "charter_pipelines": ["907748"],
                          "exclude_pipelines": [], "gold_amount_pipelines": ["default"],
                          "charter_student_billing": "Package",
                          "private_student_billing": "Service List Cost"},
            "internal": {"domain": "wetutorathome.com"}, "slack": {"digest_channel": "C"}}
    monkeypatch.setattr(dsy, "cfg", lambda: base)
    monkeypatch.setattr(dsy.audit, "already_processed", lambda k: False)
    monkeypatch.setattr(dsy.audit, "append", lambda r: None)
    monkeypatch.setattr(dsy.hs, "pipeline_label", lambda p: "Gold Tutoring")
    monkeypatch.setattr(dsy, "_deal_contact", lambda d, n="": {"properties": {
        "email": "mom@x.com", "firstname": "Lara", "lastname": "Perkins"}})
    monkeypatch.setattr(dsy.tw, "accounts", lambda: {"online": "tok"})
    monkeypatch.setattr(dsy.tw, "find_customer_by_email", lambda e, t: {"id": 42})
    monkeypatch.setattr(dsy.tw, "update_customer", lambda cid, f, t: None)
    monkeypatch.setattr(dsy.tw, "tw_get", lambda ep, p=None, token=None: [])
    monkeypatch.setattr(dsy.tw, "create_student", lambda f, t: None)
    monkeypatch.setattr(dsy.tw, "latest_invoice",
                        lambda cid, token=None: {"total": 640.0, "number": "88", "date": "2026-09-01"})
    monkeypatch.setattr(dsy.hs, "_write",
                        lambda m, path, payload=None: calls.append((m, path, payload)) or {})
    monkeypatch.setattr(dsy.slack_client, "post_message", lambda ch, t: None)


def test_gold_deal_amount_stamped_from_invoice(monkeypatch):
    calls = []
    _wire_gold(monkeypatch, calls)
    rec = dsy.sync_deal({"id": "D9", "properties": {"pipeline": "default",
                                                    "dealname": "Lara Perkins - Nomi",
                                                    "amount": ""}})
    patches = [c for c in calls if c[0] == "PATCH" and c[1].endswith("/deals/D9")]
    assert patches and patches[0][2]["properties"]["amount"] == "640.0"
    assert rec["amount_from_invoice"] == 640.0


def test_gold_deal_with_amount_untouched(monkeypatch):
    calls = []
    _wire_gold(monkeypatch, calls)
    dsy.sync_deal({"id": "D9", "properties": {"pipeline": "default",
                                              "dealname": "Lara Perkins - Nomi",
                                              "amount": "500"}})
    assert not [c for c in calls if c[0] == "PATCH"]
