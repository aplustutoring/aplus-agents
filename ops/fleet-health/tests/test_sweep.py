"""
Retry sweeper: two failure shapes are alerted, never rerun (2026-09-10).

A state commit-back that lost a race means the work is done; rerunning the
job re-does it (16 duplicate HubSpot items that day). A non-429 4xx from an
upstream API fails identically on every attempt (Teachworks 400, 4 tries).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "retry"))
import sweep  # noqa: E402


def test_only_state_commit_failed():
    assert sweep.only_state_commit_failed(["Commit state changes"])
    assert sweep.only_state_commit_failed(["Persist state"])
    assert not sweep.only_state_commit_failed(["Run call agent", "Commit state changes"])
    assert not sweep.only_state_commit_failed([])


def test_deterministic_4xx_detection():
    assert sweep.looks_deterministic("sync error on deal 1: 400 Client Error: Bad Request for url: x")
    assert sweep.looks_deterministic("404 Client Error: Not Found")
    assert not sweep.looks_deterministic("429 Client Error: Too Many Requests")
    assert not sweep.looks_deterministic("502 Server Error: Bad Gateway")
    assert not sweep.looks_deterministic("")
    assert not sweep.looks_deterministic(None)


def _jobs(*steps):
    return {"jobs": [{"id": 7, "steps": [{"name": n, "conclusion": c} for n, c in steps]}]}


def test_state_commit_race_is_held(monkeypatch):
    monkeypatch.setattr(sweep, "gh", lambda *a, **k: _jobs(("Run call agent", "success"),
                                                          ("Commit state changes", "failure")))
    reason = sweep.no_retry_reason(1)
    assert reason and "lost a race" in reason


def test_deterministic_4xx_is_held(monkeypatch):
    monkeypatch.setattr(sweep, "gh", lambda *a, **k: _jobs(("Run deal sync", "failure")))
    monkeypatch.setattr(sweep, "job_log", lambda job_id: "400 Client Error: Bad Request for url: tw")
    reason = sweep.no_retry_reason(1)
    assert reason and "4xx" in reason and "Run deal sync" in reason


def test_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr(sweep, "gh", lambda *a, **k: _jobs(("Run deal sync", "failure")))
    monkeypatch.setattr(sweep, "job_log", lambda job_id: "502 Server Error: Bad Gateway")
    assert sweep.no_retry_reason(1) is None


def test_agent_step_and_commit_step_both_failed_is_retried(monkeypatch):
    monkeypatch.setattr(sweep, "gh", lambda *a, **k: _jobs(("Run call agent", "failure"),
                                                          ("Commit state changes", "failure")))
    monkeypatch.setattr(sweep, "job_log", lambda job_id: "Traceback ... FileNotFoundError")
    assert sweep.no_retry_reason(1) is None


def test_main_holds_instead_of_rerunning(monkeypatch):
    run = {"id": 1, "name": "Email — PO inbox", "conclusion": "failure", "run_attempt": 1,
           "updated_at": sweep.datetime.now(sweep.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "html_url": "u"}
    calls = []

    def fake_gh(method, path, params=None, ok404=False):
        calls.append((method, path))
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [run]}
        if path.endswith("/jobs"):
            return _jobs(("Run PO inbox", "success"), ("Commit state changes", "failure"))
        raise AssertionError(f"unexpected {method} {path}")

    posted = []
    monkeypatch.setattr(sweep, "gh", fake_gh)
    monkeypatch.setattr(sweep, "GH_TOKEN", "t")
    monkeypatch.setattr(sweep, "alert_targets", lambda: ("C1", "<@U1>"))
    monkeypatch.setattr(sweep, "post_slack", lambda ch, text: posted.append(text))
    monkeypatch.setattr(sys, "argv", ["sweep.py"])
    sweep.main()
    assert not any(p.endswith("rerun-failed-jobs") for _, p in calls)
    assert posted and "NOT retried" in posted[0] and "lost a race" in posted[0]
