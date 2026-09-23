"""The audit log is redacted (FERPA pass, 2026-09-16) and it is also the
low-balance case store. open_cases() must hand the sweep a real address and
phone, never 'm…@gmail.com' / '…6225' (five days of Resend 422s, 2026-09-17
to 09-22)."""
from src import low_balance as lb


def _recs(**over):
    base = {"message_id": "low-balance:26/27:alexzander-gonzalez:charter-ilead",
            "action_taken": "low_balance_opened", "contact_id": "C1",
            "to_email": "m…@gmail.com", "parent_email": "m…@gmail.com", "phone": "…6225",
            "opened_at": "2026-09-17T02:53:00+00:00", "email_pending": True}
    base.update(over)
    return [base]


def test_open_cases_rehydrates_redacted_email_and_phone(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        return {"properties": {"email": "mary112yram@gmail.com", "mobilephone": "(818) 721-6225", "phone": ""}}

    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(_recs()))
    monkeypatch.setattr(lb.hs, "_get", fake_get)
    case = lb.open_cases()["low-balance:26/27:alexzander-gonzalez:charter-ilead"]
    assert case["to_email"] == "mary112yram@gmail.com"
    assert case["parent_email"] == "mary112yram@gmail.com"
    assert case["phone"] == "+18187216225"
    assert calls == ["/crm/v3/objects/contacts/C1"]


def test_open_cases_leaves_clean_values_alone(monkeypatch):
    monkeypatch.setattr(lb.audit, "_iter_records",
                        lambda: iter(_recs(to_email="anita@gmail.com", parent_email="anita@gmail.com", phone="+15412374755")))
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: (_ for _ in ()).throw(AssertionError("no lookup expected")))
    case = lb.open_cases()["low-balance:26/27:alexzander-gonzalez:charter-ilead"]
    assert case["to_email"] == "anita@gmail.com" and case["phone"] == "+15412374755"


def test_rehydrate_refuses_a_different_mailbox_or_phone(monkeypatch):
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(_recs()))
    monkeypatch.setattr(lb.hs, "_get",
                        lambda p, q=None: {"properties": {"email": "someone@yahoo.com", "mobilephone": "(818) 555-0000"}})
    case = lb.open_cases()["low-balance:26/27:alexzander-gonzalez:charter-ilead"]
    assert case["to_email"] == "m…@gmail.com" and case["phone"] == "…6225"   # masked stays masked, send fails loudly


def test_rehydrate_survives_a_hubspot_error(monkeypatch):
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(_recs()))
    monkeypatch.setattr(lb.hs, "_get", lambda p, q=None: (_ for _ in ()).throw(RuntimeError("503")))
    assert lb.open_cases()["low-balance:26/27:alexzander-gonzalez:charter-ilead"]["to_email"] == "m…@gmail.com"


def test_open_cases_folds_the_last_hold_reason(monkeypatch):
    recs = _recs(to_email="a@b.com", parent_email="a@b.com", phone="+15550000000") + [
        {"message_id": "low-balance:26/27:alexzander-gonzalez:charter-ilead:email",
         "action_taken": "low_balance_email_held", "reason": "⏸ Not armed: would email a@b.com: X"},
        {"message_id": "low-balance:26/27:alexzander-gonzalez:charter-ilead:email",
         "action_taken": "low_balance_email_held", "reason": "⚠️ Family email to a@b.com FAILED (422)"},
    ]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    case = lb.open_cases()["low-balance:26/27:alexzander-gonzalez:charter-ilead"]
    assert case["hold_reason"] == "⚠️ Family email to a@b.com FAILED (422)"
