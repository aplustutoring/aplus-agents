import pytest

from src.classifier import ClassificationError, parse_classification

VALID = {
    "category": "scheduling",
    "risk": "low",
    "confidence": 0.92,
    "routing_target": "Janelle",
    "sla_tier": "24h",
    "draft_reply": "Hi, we can help with that.",
    "reason": "Parent asking to move a lesson.",
}


def _json(d):
    import json
    return json.dumps(d)


def test_parses_plain_json():
    out = parse_classification(_json(VALID))
    assert out["category"] == "scheduling"
    assert out["confidence"] == 0.92


def test_parses_fenced_json():
    out = parse_classification("```json\n" + _json(VALID) + "\n```")
    assert out["category"] == "scheduling"


def test_parses_json_with_surrounding_prose():
    text = "Sure! Here is the classification:\n" + _json(VALID) + "\nLet me know."
    assert parse_classification(text)["risk"] == "low"


def test_missing_key_raises():
    bad = dict(VALID)
    del bad["reason"]
    with pytest.raises(ClassificationError):
        parse_classification(_json(bad))


def test_non_numeric_confidence_raises():
    bad = dict(VALID, confidence="high")
    with pytest.raises(ClassificationError):
        parse_classification(_json(bad))


def test_confidence_clamped():
    out = parse_classification(_json(dict(VALID, confidence=1.4)))
    assert out["confidence"] == 1.0


def test_unknown_category_coerced():
    out = parse_classification(_json(dict(VALID, category="banana")))
    assert out["category"] == "unknown"


def test_empty_raises():
    with pytest.raises(ClassificationError):
        parse_classification("   ")


def test_cancellation_reason_defaults_empty():
    assert parse_classification(_json(VALID))["cancellation_reason"] == ""


def test_cancellation_reason_preserved():
    out = parse_classification(_json(dict(VALID, category="cancellation",
                                          cancellation_reason="tutor sick")))
    assert out["cancellation_reason"] == "tutor sick"
