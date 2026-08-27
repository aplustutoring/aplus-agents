"""
A run where every call fails must exit 1 so the Actions retry sweeper fires.

Before the 2026-08-20 correction, process_call exceptions were caught per call
(one bad call must never kill the run) but never counted, so a 100%-failure run
looked exactly like a quiet day: exit 0, sweeper silent.

Quiet days (no calls) and all-skips days (hang-ups) stay at exit 0 — those are
healthy runs, not broken ones.
"""

import pytest

import call_agent


def _call(cid, number="310-555-0100"):
    return {
        "id": cid,
        "contact_number": number,
        "justcall_number": "+13105550199",   # in monitored_numbers below
        "call_date": "2026-08-20",
        "call_time": "14:05:00",
        "call_info": {"direction": "Incoming", "type": "answered"},
    }


CFG = {
    "justcall": {
        "monitored_numbers": ["+13105550199"],
        "process_call_types": ["answered"],
        "overlap_minutes": 10,
        "initial_lookback_days": 1,
        "transcript_grace_minutes": 45,
        "require_recording": True,
        "ai_fetch_pause_seconds": 0,
    },
    "missed_calls": {"enabled": False, "alert_types": []},
    "slack": {"channel": "#calls", "alert_channel": "#calls"},
    "state": {"path": "ops/call_agent/state/state.json", "max_processed_ids": 100},
}


@pytest.fixture
def harness(monkeypatch):
    """main() with every outbound edge stubbed; returns the Slack posts made."""
    posts = []
    monkeypatch.setattr(call_agent, "load_config", lambda: CFG)
    monkeypatch.setattr(call_agent, "load_state", lambda path: {
        "last_run_utc": None, "processed_call_ids": [],
        "pending_digest": [], "pending_skipped": [], "pending_failures": [],
    })
    monkeypatch.setattr(call_agent, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(call_agent, "fetch_daily_activity", lambda cfg, now: [])
    monkeypatch.setattr(call_agent, "build_activity_brief", lambda *a: None)
    monkeypatch.setattr(call_agent, "post_to_slack",
                        lambda text, channel: posts.append((channel, text)))
    for name in ("JUSTCALL_API_KEY", "JUSTCALL_API_SECRET",
                 "HUBSPOT_API_KEY", "ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN"):
        monkeypatch.setattr(call_agent, name, "x")
    monkeypatch.setattr(call_agent, "CHECK_ONLY", False)
    monkeypatch.setattr(call_agent.sys, "argv", ["call_agent.py"])
    return posts


def _entry(call):
    return {
        "call_id": call["id"],
        "number": call["contact_number"],
        "time_pt": "2:05 PM",
        "matched": True,
        "contact_label": "Katie Alexander",
        "summary": {"summary": "Asked about SAT prep.", "intent": "new inquiry",
                    "caller_type": "parent", "sentiment": "neutral",
                    "follow_up_needed": False},
    }


def _run(monkeypatch, calls, process):
    """Run main() and return its exit code (0 when it returns normally)."""
    monkeypatch.setattr(call_agent, "fetch_inbound_calls", lambda cfg, since: calls)
    monkeypatch.setattr(call_agent, "process_call", process)
    try:
        call_agent.main()
    except SystemExit as e:
        return e.code or 0
    return 0


def test_all_calls_fail_exits_1(monkeypatch, harness):
    def boom(call, cfg, dry_run, now_utc):
        raise RuntimeError("HubSpot 500")
    assert _run(monkeypatch, [_call("1"), _call("2"), _call("3")], boom) == 1


def test_all_calls_fail_alerts_slack(monkeypatch, harness):
    def boom(call, cfg, dry_run, now_utc):
        raise RuntimeError("HubSpot 500")
    _run(monkeypatch, [_call("1"), _call("2")], boom)
    alerts = [t for _, t in harness if "0/2 calls succeeded" in t]
    assert len(alerts) == 1, harness


def test_dry_run_still_exits_1_without_posting(monkeypatch, harness):
    # --dry-run is how the exit code gets verified before a live merge.
    monkeypatch.setattr(call_agent.sys, "argv", ["call_agent.py", "--dry-run"])

    def boom(call, cfg, dry_run, now_utc):
        raise RuntimeError("HubSpot 500")
    assert _run(monkeypatch, [_call("1")], boom) == 1
    assert harness == []


def test_no_calls_exits_0(monkeypatch, harness):
    def never(call, cfg, dry_run, now_utc):
        raise AssertionError("should not be called")
    assert _run(monkeypatch, [], never) == 0


def test_all_hangups_exits_0(monkeypatch, harness):
    # Skips are normal outcomes — an all-hang-ups day is not a broken run.
    def hangup(call, cfg, dry_run, now_utc):
        return "skipped", {"number": call["contact_number"],
                           "time_pt": "2:05 PM", "reason": "hang-up"}
    assert _run(monkeypatch, [_call("1"), _call("2")], hangup) == 0


def test_one_success_among_failures_exits_0(monkeypatch, harness):
    # Partial failure is the digest's job to report, not the sweeper's.
    def mixed(call, cfg, dry_run, now_utc):
        if call["id"] != "1":
            raise RuntimeError("HubSpot 500")
        return "entry", _entry(call)
    assert _run(monkeypatch, [_call("1"), _call("2"), _call("3")], mixed) == 0
