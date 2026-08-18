"""Draft feedback loop: registry, outcome classification, style rules."""
import json

from src import draft_feedback as df


def test_classify_sent_as_is():
    v, ratio, diff = df._classify("Hi Karen,\n\nThanks for the PO.\n\nA+ Team",
                                  "Hi Karen,\n\nThanks for the PO.\n\nA+ Team")
    assert v == "sent_as_is" and ratio >= 0.97 and diff == ""


def test_classify_edited_with_diff():
    v, ratio, diff = df._classify(
        "Hi Karen,\n\nThank you for the purchase order for Kruz. We'll take it from there.\n\nA+ Tutoring Team",
        "Hi Karen,\n\nThank you for the purchase order for Kruz. Happy to help from here!\n\nA+ Tutoring Team")
    assert v == "edited"
    assert "-" in diff and "+" in diff and "Happy to help" in diff


def test_classify_ignores_quoted_reply_tail():
    agent = "Hi Karen,\n\nThanks for the PO.\n\nA+ Team"
    sent = agent + "\n\nOn Wed, Aug 13, 2026 Karen wrote:\n> the original robot email"
    v, _r, _d = df._classify(agent, sent)
    assert v == "sent_as_is"


def test_classify_rewritten():
    v, ratio, _d = df._classify("Hi Karen, thanks for the PO, we need parent info.",
                                "Karen — quick one: who's Kruz's parent? Need email + phone. Thx")
    assert v == "rewritten"


def test_registry_and_open_drafts(monkeypatch, tmp_path):
    reg = tmp_path / "draft_registry.jsonl"
    monkeypatch.setattr(df, "REGISTRY", reg)
    monkeypatch.setattr(df, "DRY_RUN", False)
    df.register({"id": "DR1", "message": {"id": "M1", "threadId": "TH1"}},
                "parent_chase", "body text", "tor@x.org", "po_inbox")
    df.register({"id": "DR2", "message": {"id": "M2", "threadId": "TH2"}},
                "reply", "other", "h@x.org", "po_inbox")
    df._append({"event": "outcome", "draft_id": "DR2", "verdict": "sent_as_is"})
    opens = df._open_drafts()
    assert [o["draft_id"] for o in opens] == ["DR1"]
    assert opens[0]["body"] == "body text"


def test_sweep_settles_and_records_correction(monkeypatch, tmp_path):
    reg = tmp_path / "draft_registry.jsonl"
    corr = tmp_path / "corrections" / "email-drafts"
    monkeypatch.setattr(df, "REGISTRY", reg)
    monkeypatch.setattr(df, "CORR_DIR", corr)
    monkeypatch.setattr(df, "STYLE_RULES", corr / "STYLE-RULES.md")
    monkeypatch.setattr(df, "DRY_RUN", False)
    df.register({"id": "DR1", "message": {"id": "M1", "threadId": "TH1"}},
                "parent_chase", "Hi Karen,\n\nWe'll take it from there.\n\nA+ Tutoring Team",
                "tor@x.org", "po_inbox")
    monkeypatch.setattr(df.gm, "get_draft", lambda did: None)          # left Drafts
    monkeypatch.setattr(df, "_sent_on_thread",
                        lambda tid, since: {"ts": 1, "id": "S1",
                                            "body": "Hi Karen,\n\nHappy to help from here!\n\nA+ Tutoring Team"})
    labels = []
    monkeypatch.setattr(df.gm, "apply_labels", lambda mid, names: labels.append((mid, names)))
    df.sweep()
    outcomes = [json.loads(l) for l in reg.read_text().splitlines() if '"outcome"' in l]
    assert outcomes and outcomes[0]["verdict"] == "edited"
    assert labels == [("S1", ["A+ Agent/Sent"])]
    files = list(corr.glob("*.md"))
    assert any("edited" in f.name for f in files)
    rules = df.style_rules_prompt()
    assert "STYLE RULES" in rules and "Happy to help" in rules


def test_sweep_discarded(monkeypatch, tmp_path):
    reg = tmp_path / "draft_registry.jsonl"
    corr = tmp_path / "corrections" / "email-drafts"
    monkeypatch.setattr(df, "REGISTRY", reg)
    monkeypatch.setattr(df, "CORR_DIR", corr)
    monkeypatch.setattr(df, "STYLE_RULES", corr / "STYLE-RULES.md")
    monkeypatch.setattr(df, "DRY_RUN", False)
    df.register({"id": "DR1", "message": {"id": "M1", "threadId": "TH1"}},
                "reply", "text", "h@x.org", "po_inbox")
    monkeypatch.setattr(df.gm, "get_draft", lambda did: None)
    monkeypatch.setattr(df, "_sent_on_thread", lambda tid, since: None)
    df.sweep()
    outcomes = [json.loads(l) for l in reg.read_text().splitlines() if '"outcome"' in l]
    assert outcomes[0]["verdict"] == "discarded"
    assert list(corr.glob("*discarded*.md"))


def test_style_rules_empty_when_none(monkeypatch, tmp_path):
    monkeypatch.setattr(df, "STYLE_RULES", tmp_path / "none.md")
    assert df.style_rules_prompt() == ""
