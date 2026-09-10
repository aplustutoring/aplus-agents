"""
The transcript-retry marker must land where the workflow looks for it:
ops/call_agent/state/retry_wanted, regardless of the process CWD. Actions
runs the agent with working-directory ops/call_agent; on 2026-09-10 the
first relay-driven grace retry crashed with FileNotFoundError because the
marker path was resolved against the CWD (run 34540444397).
"""

import os

import call_agent as ca

CFG = {"state": {"path": "ops/call_agent/state/state.json"}}


def test_marker_resolves_from_repo_root_not_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "REPO_ROOT", tmp_path)
    workdir = tmp_path / "ops" / "call_agent"
    workdir.mkdir(parents=True)
    monkeypatch.chdir(workdir)              # what the Actions step does
    marker = ca.write_retry_marker(CFG, 2)
    assert marker == tmp_path / "ops" / "call_agent" / "state" / "retry_wanted"
    assert marker.read_text() == "2"
    # the workflow's own check, relative to its working directory
    assert os.path.isfile("state/retry_wanted")


def test_marker_cleared_when_nothing_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "REPO_ROOT", tmp_path)
    ca.write_retry_marker(CFG, 1)
    assert ca.retry_marker_path(CFG).exists()
    ca.write_retry_marker(CFG, 0)
    assert not ca.retry_marker_path(CFG).exists()


def test_clearing_a_missing_marker_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "REPO_ROOT", tmp_path)
    ca.write_retry_marker(CFG, 0)
