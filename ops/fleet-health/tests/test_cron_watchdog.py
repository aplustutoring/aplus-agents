"""
Cron-starvation watchdog: a catch-up dispatch must be a REAL run.

Born 2026-09-09: the watchdog POSTed {"ref": "main"} with no inputs, and
call-agent.yml defaults dry_run to true, so every catch-up of the call agent
since 2026-09-04 was a dry run that persisted nothing while the log said
"catch-up dispatch ok". These tests read the real workflow files so the trap
cannot come back through a new WATCHED entry, a changed default, or a
DISPATCH_INPUTS entry GitHub would reject.
"""

import os
import re
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "watchdog"))
import cron_watchdog as wd  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RELAY_WORKER = os.path.join(REPO_ROOT, "ops", "call_agent", "webhook-relay", "worker.js")


# --- against the real .github/workflows -----------------------------------

@pytest.mark.parametrize("wf", sorted(wd.WATCHED))
def test_every_watched_workflow_gets_a_real_catch_up(wf):
    assert wd.dispatch_trap(wf) is None, wd.dispatch_trap(wf)


def test_call_agent_catch_up_is_live_and_holds_digest():
    body = wd.dispatch_body("call-agent.yml")
    assert body == {"ref": "main", "inputs": {"dry_run": "false", "no_digest": "true"}}


def test_call_agent_inputs_match_the_webhook_relay():
    """The relay (worker.js) and the watchdog must dispatch the same run —
    if one changes its payload, the other has to follow on purpose."""
    with open(RELAY_WORKER) as f:
        src = f.read()
    m = re.search(r"inputs:\s*\{([^}]*)\}", src)
    assert m, "worker.js no longer sends workflow_dispatch inputs"
    relay_inputs = dict(re.findall(r'(\w+):\s*"([^"]*)"', m.group(1)))
    assert relay_inputs == wd.DISPATCH_INPUTS["call-agent.yml"]


def test_workflows_without_a_map_entry_dispatch_bare():
    for wf in wd.WATCHED:
        if wf not in wd.DISPATCH_INPUTS:
            assert wd.dispatch_body(wf) == {"ref": "main"}


def test_every_dispatch_inputs_entry_is_watched():
    assert set(wd.DISPATCH_INPUTS) <= set(wd.WATCHED)


# --- the guard itself, on synthetic workflow files -------------------------

def write_workflow(tmp_path, name, on_block):
    (tmp_path / name).write_text(textwrap.dedent(on_block))
    return str(tmp_path)


def test_dry_run_defaulting_true_is_a_trap(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          workflow_dispatch:
            inputs:
              dry_run:
                type: boolean
                default: true
        jobs: {}
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})
    trap = wd.dispatch_trap("x.yml", d)
    assert trap and "dry_run" in trap and "no-op" in trap


def test_override_in_map_clears_the_trap(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          workflow_dispatch:
            inputs:
              dry_run:
                type: boolean
                default: true
        jobs: {}
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {"x.yml": {"dry_run": "false"}})
    assert wd.dispatch_trap("x.yml", d) is None


def test_check_only_defaulting_true_is_a_trap(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          workflow_dispatch:
            inputs:
              check_only:
                type: boolean
                default: true
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})
    assert "check_only" in (wd.dispatch_trap("x.yml", d) or "")


def test_dry_run_defaulting_false_is_fine(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          schedule:
            - cron: "*/15 * * * *"
          workflow_dispatch:
            inputs:
              dry_run:
                type: boolean
                default: false
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})
    assert wd.dispatch_trap("x.yml", d) is None


def test_undeclared_input_is_a_trap(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          workflow_dispatch:
            inputs:
              dry_run:
                type: boolean
                default: false
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {"x.yml": {"dry_run": "false", "no_digest": "true"}})
    trap = wd.dispatch_trap("x.yml", d)
    assert trap and "no_digest" in trap and "422" in trap


def test_missing_workflow_dispatch_trigger_is_a_trap(tmp_path, monkeypatch):
    d = write_workflow(tmp_path, "x.yml", """
        on:
          schedule:
            - cron: "0 * * * *"
    """)
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})
    assert "workflow_dispatch" in (wd.dispatch_trap("x.yml", d) or "")


def test_missing_file_is_a_trap(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})
    assert "not in the checkout" in (wd.dispatch_trap("nope.yml", str(tmp_path)) or "")


# --- dispatch() sends the body and refuses traps ---------------------------

class FakeResp:
    def __init__(self, status):
        self.status_code = status
        self.text = ""


def test_dispatch_posts_inputs(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return FakeResp(204)

    monkeypatch.setattr(wd.requests, "post", fake_post)
    assert wd.dispatch("call-agent.yml") is True
    assert sent["url"].endswith("/actions/workflows/call-agent.yml/dispatches")
    assert sent["json"] == {"ref": "main", "inputs": {"dry_run": "false", "no_digest": "true"}}


def test_dispatch_refuses_a_trap_without_posting(monkeypatch):
    calls = []
    monkeypatch.setattr(wd.requests, "post", lambda *a, **k: calls.append(1) or FakeResp(204))
    monkeypatch.setattr(wd, "DISPATCH_INPUTS", {})   # re-creates the 2026-09-09 trap
    assert wd.dispatch("call-agent.yml") is False
    assert calls == []


def test_dispatch_reports_non_204(monkeypatch):
    monkeypatch.setattr(wd.requests, "post", lambda *a, **k: FakeResp(422))
    assert wd.dispatch("email-triage.yml") is False


def test_slack_line_names_the_inputs():
    assert wd.describe_inputs("call-agent.yml") == " with inputs dry_run=false, no_digest=true"
    assert wd.describe_inputs("email-triage.yml") == ""
