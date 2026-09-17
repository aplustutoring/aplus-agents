"""Monday.com client: a refused call must never look like a write that landed.

Monday answers a refusal (no access to the item, bad column, complexity budget)
with HTTP 200 and the reason in the body, so the old client, which returned
r.json() unread, reported success for writes the board threw away. The weekly
L10 scorecard sync ran green for two weeks that way (2026-09-16).
"""
import pytest

from src import monday_client as mon


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _posts(monkeypatch, bodies):
    """Answer each POST with the next body; records the calls made."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _Resp(bodies[min(len(calls) - 1, len(bodies) - 1)])

    monkeypatch.setattr(mon.requests, "post", fake_post)
    monkeypatch.setattr(mon.time, "sleep", lambda s: None)
    return calls


def test_a_refused_write_raises_instead_of_returning(monkeypatch):
    _posts(monkeypatch, [{"errors": [{"message": "User unauthorized to perform action"}]}])
    with pytest.raises(mon.MondayError) as e:
        mon.update_item("18402267902", "12005709448", {"numeric_x": 4})
    assert "unauthorized" in str(e.value).lower()


def test_a_clean_response_comes_back_untouched(monkeypatch):
    _posts(monkeypatch, [{"data": {"change_multiple_column_values": {"id": "1"}}}])
    assert mon.monday_query("query {}")["data"]["change_multiple_column_values"]["id"] == "1"


def test_top_level_error_message_counts_too(monkeypatch):
    # not every Monday failure arrives as a GraphQL `errors` array
    _posts(monkeypatch, [{"error_message": "Not Authenticated", "status_code": 401}])
    with pytest.raises(mon.MondayError):
        mon.monday_query("query {}")


def test_a_throttle_is_retried_then_succeeds(monkeypatch):
    calls = _posts(monkeypatch, [
        {"errors": [{"message": "Complexity budget exhausted"}]},
        {"data": {"boards": []}},
    ])
    assert mon.monday_query("query {}") == {"data": {"boards": []}}
    assert len(calls) == 2                      # retried once, no exception

def test_a_throttle_that_never_clears_still_raises(monkeypatch):
    calls = _posts(monkeypatch, [{"errors": [{"message": "Rate limit exceeded"}]}])
    with pytest.raises(mon.MondayError):
        mon.monday_query("query {}")
    assert len(calls) == 3                      # the three attempts, then loud


def test_monday_errors_reads_both_shapes():
    assert mon.monday_errors({"data": {"x": 1}}) == []
    assert mon.monday_errors({"errors": [{"message": "a"}, {"message": "b"}]}) == ["a", "b"]
    assert mon.monday_errors({"errors": ["plain string"]}) == ["plain string"]
