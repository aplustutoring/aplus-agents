"""HubSpot 429s are retried with backoff at the one choke point every call
uses (2026-09-16: a 37-deal sync starved the HSA late-add sweep, and a
cohort_intake dry run died the same way)."""
import pytest
import requests

from src import hubspot_client as hs


def _resp(status, body=b'{"results": []}', retry_after=None):
    r = requests.Response()
    r.status_code = status
    r._content = body
    if retry_after is not None:
        r.headers["Retry-After"] = str(retry_after)
    return r


def test_search_retries_429_then_returns(monkeypatch):
    calls, sleeps = [], []
    seq = iter([_resp(429, retry_after=0), _resp(429), _resp(200)])
    monkeypatch.setattr(hs.requests, "request", lambda m, u, **k: calls.append((m, u)) or next(seq))
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    assert hs._get_search("/crm/v3/objects/deals/search", {}) == {"results": []}
    assert len(calls) == 3 and sleeps == [0.0, 2.0]          # Retry-After, then 2**1


def test_get_and_write_share_the_retry(monkeypatch):
    seq = iter([_resp(429), _resp(200, b'{"id": "1"}'), _resp(429), _resp(200, b'{"id": "2"}')])
    monkeypatch.setattr(hs.requests, "request", lambda m, u, **k: next(seq))
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(hs, "DRY_RUN", False)
    assert hs._get("/crm/v3/objects/deals/1") == {"id": "1"}
    assert hs._write("PATCH", "/crm/v3/objects/deals/2", {"properties": {}}) == {"id": "2"}


def test_other_errors_raise_at_once(monkeypatch):
    calls = []
    monkeypatch.setattr(hs.requests, "request", lambda m, u, **k: calls.append(1) or _resp(400, b"bad"))
    with pytest.raises(requests.HTTPError):
        hs._get_search("/crm/v3/objects/deals/search", {})
    assert len(calls) == 1


def test_gives_up_after_the_last_try(monkeypatch):
    calls = []
    monkeypatch.setattr(hs.requests, "request", lambda m, u, **k: calls.append(1) or _resp(429))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        hs._get_search("/crm/v3/objects/deals/search", {})
    assert len(calls) == hs.RATE_LIMIT_TRIES
