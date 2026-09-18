"""The agent's HubSpot reads are real even in a dry run: the plan must say
update, not create, for a contact that already exists."""
from agents.cohort_intake import _bootstrap as B


def test_dry_run_searches_pass_through():
    assert B.hs.SEARCH_PASSTHROUGH is True


def test_hubspot_429_is_retried_then_succeeds(monkeypatch):
    import requests
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            r = requests.Response()
            r.status_code = 429
            r.headers["Retry-After"] = "0"
            raise requests.HTTPError("429", response=r)
        return {"ok": True}

    assert B._retry_429(flaky)() == {"ok": True} and calls["n"] == 3


def test_other_http_errors_are_not_retried():
    import pytest
    import requests

    def bad():
        r = requests.Response()
        r.status_code = 400
        raise requests.HTTPError("400", response=r)

    with pytest.raises(requests.HTTPError):
        B._retry_429(bad)()
