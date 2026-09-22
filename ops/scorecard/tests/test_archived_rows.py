"""
Archived L10 rows are skipped, never written, never fatal (2026-09-22).
Monday refuses writes to inactive items; five CSM rows archived by hand on
2026-08-31 failed the 2026-09-21 weekly sync four times.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import aplus_weekly_sync as ws  # noqa: E402

CSM = {"csm_meeting_requested", "csm_meeting_scheduled", "csm_proposal_out",
       "csm_active_proposals", "csm_program_won"}


def _board(states):
    """Fake Monday: every SCORECARD_ITEMS row active unless listed in states."""
    def fake(query, variables=None):
        items = []
        for key, iid in ws.SCORECARD_ITEMS.items():
            st = states.get(key, "active")
            if st == "deleted":
                continue
            items.append({"id": str(iid), "name": key, "state": st})
        return {"data": {"items": items}}
    return fake


def test_archived_rows_are_reported_by_id(monkeypatch):
    monkeypatch.setattr(ws, "monday_query", _board({k: "archived" for k in CSM}))
    dead = ws.archived_scorecard_items()
    assert set(dead) == {ws.SCORECARD_ITEMS[k] for k in CSM}
    assert all("[archived]" in v for v in dead.values())


def test_deleted_rows_count_as_dead(monkeypatch):
    monkeypatch.setattr(ws, "monday_query", _board({"nps_tutor": "deleted"}))
    dead = ws.archived_scorecard_items()
    assert dead == {ws.SCORECARD_ITEMS["nps_tutor"]: "(deleted)"}


def test_all_active_means_nothing_skipped(monkeypatch):
    monkeypatch.setattr(ws, "monday_query", _board({}))
    assert ws.archived_scorecard_items() == {}


def test_state_lookup_failure_never_blocks_the_sync(monkeypatch):
    def boom(query, variables=None):
        raise ws.MondayError("complexity budget exhausted")
    monkeypatch.setattr(ws, "monday_query", boom)
    assert ws.archived_scorecard_items() == {}
