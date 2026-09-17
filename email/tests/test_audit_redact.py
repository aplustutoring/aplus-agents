"""The committed audit log never carries a raw phone or email (FERPA pass,
Roman 2026-09-16): audit.append masks the known contact keys at the choke
point every writer uses."""
from src import audit


def test_redact_masks_phones_and_emails_and_leaves_the_rest():
    assert audit.redact("+18183844845") == "…4845"
    assert audit.redact("(818) 384-4845") == "…4845"
    assert audit.redact("roman@wetutorathome.com") == "r…@wetutorathome.com"
    assert audit.redact(["a@b.com", "+15550001111"]) == ["a…@b.com", "…1111"]
    assert audit.redact("Diego") == "Diego" and audit.redact("") == "" and audit.redact(None) is None
    assert audit.redact("2026-09-16") == "2026-09-16"          # a date is not a phone
    assert audit.redact(audit.redact("+18183844845")) == "…4845"   # idempotent


def test_append_masks_contact_keys(monkeypatch, tmp_path):
    written = []
    monkeypatch.setattr(audit, "DRY_RUN", False)
    monkeypatch.setattr(audit, "STATE_DIR", tmp_path)
    monkeypatch.setattr(audit, "AUDIT_LOG", tmp_path / "audit_log.jsonl")
    audit.append({"message_id": "sms-sent:D1", "action_taken": "sms_sent", "deal_id": "D1",
                  "to": "+18183844845", "welcome_email_to": "mom@gmail.com", "body": "Hi Reyna"})
    import json
    rec = json.loads((tmp_path / "audit_log.jsonl").read_text().splitlines()[0])
    assert rec["to"] == "…4845" and rec["welcome_email_to"] == "m…@gmail.com"
    assert rec["deal_id"] == "D1" and rec["body"] == "Hi Reyna"
