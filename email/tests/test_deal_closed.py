"""deal_closed — when a deal stops, its future work stops with it.

Pinned from the Wolfstein cancellation of 2026-09-15: the family said no, the
deal went to Stopped with no reason written down, and three days later the
record still told a scheduler to find a tutor and text the father.
"""
import datetime as dt

import pytest

from src import deal_closed as dc

STOPPED_AT = dt.datetime(2026, 9, 15, 22, 30, tzinfo=dt.timezone.utc)

CFG = {
    "staff": {
        "yolanda": {"name": "Yolanda", "hubspot_owner_id": "86868539", "slack_user_id": "UY"},
        "paola":   {"name": "Paola",   "hubspot_owner_id": "81494333", "slack_user_id": "UP"},
    },
    "deal_closed": {
        "enabled": True, "lookback_days": 7, "max_deals_per_run": 25,
        "digest_channel": "C_DIGEST",
        "stop_stage_labels": ["stopped", "closed lost", "lost"],
    },
}

PIPELINES = {
    "inperson": {"3067400": "Pre-Lesson", "3067402": "Stopped"},
    "charter":  {"111": "Invoice Submitted", "222": "Closed Lost"},
    "renewals": {"333": "Active"},
}


def _task(tid, due, subject="a task", status="NOT_STARTED"):
    return {"id": tid, "properties": {"hs_task_subject": subject, "hs_task_status": status,
                                      "hs_timestamp": due.isoformat(),
                                      "hubspot_owner_id": "81494333"}}


def _deal(did="65027182155", stage="3067402", name="Nolan Pereau - Bradley Pereau",
          owner="86868539", reason="", closed=STOPPED_AT):
    return {"id": did, "properties": {
        "dealname": name, "dealstage": stage, "pipeline": "inperson",
        "hubspot_owner_id": owner, "closed_lost_reason": reason,
        "closedate": closed.isoformat(), "hs_lastmodifieddate": closed.isoformat()}}


@pytest.fixture
def wired(monkeypatch):
    """The whole sweep with HubSpot and Slack replaced by recorders."""
    state = {"completed": [], "dms": [], "posts": [], "notes": [], "audit": [],
             "tasks": [], "notes_on_record": []}
    monkeypatch.setattr(dc, "cfg", lambda: CFG)
    monkeypatch.setattr(dc, "DRY_RUN", False)
    monkeypatch.setattr(dc.hs, "_deal_pipelines", lambda: PIPELINES)
    monkeypatch.setattr(dc.hs, "pipeline_label", lambda pid: pid)
    monkeypatch.setattr(dc.hs, "batch_complete_tasks",
                        lambda ids: state["completed"].extend(ids))
    monkeypatch.setattr(dc.slack_client, "dm",
                        lambda uid, text: state["dms"].append((uid, text)))
    monkeypatch.setattr(dc.slack_client, "post_message",
                        lambda ch, text: state["posts"].append((ch, text)))
    monkeypatch.setattr(dc.audit, "append", lambda r: state["audit"].append(r))
    monkeypatch.setattr(dc.audit, "deals_closed_swept", lambda: set())

    def _get(path, params=None):
        if "/associations/contacts" in path:
            return {"results": [{"toObjectId": "157457839544"}]}
        if "/associations/tasks" in path:
            return {"results": [{"toObjectId": t["id"]} for t in state["tasks"]]}
        if "/associations/notes" in path:
            return {"results": [{"toObjectId": n["id"]} for n in state["notes_on_record"]]}
        return {"results": []}

    def _write(method, path, payload=None):
        if path.endswith("/tasks/batch/read"):
            keep = {i["id"] for i in payload["inputs"]}
            return {"results": [t for t in state["tasks"] if t["id"] in keep]}
        if path.endswith("/notes/batch/read"):
            keep = {i["id"] for i in payload["inputs"]}
            return {"results": [n for n in state["notes_on_record"] if n["id"] in keep]}
        if path.endswith("/objects/notes"):
            state["notes"].append(payload)
            return {"id": "n1"}
        return {}

    monkeypatch.setattr(dc.hs, "_get", _get)
    monkeypatch.setattr(dc.hs, "_write", _write)
    return state


# ── stop stages come from LABELS, across every pipeline ────────────────────
def test_stop_stages_matched_by_label_not_id(monkeypatch):
    monkeypatch.setattr(dc, "cfg", lambda: CFG)
    monkeypatch.setattr(dc.hs, "_deal_pipelines", lambda: PIPELINES)
    monkeypatch.setattr(dc.hs, "pipeline_label", lambda pid: pid)
    stages = dc.stop_stage_ids()
    assert set(stages) == {"3067402", "222"}          # Stopped and Closed Lost
    assert "3067400" not in stages                    # Pre-Lesson is live work


def test_no_matching_stage_label_refuses_to_act(monkeypatch, wired):
    monkeypatch.setattr(dc.hs, "_deal_pipelines",
                        lambda: {"inperson": {"3067400": "Pre-Lesson"}})
    monkeypatch.setattr(dc, "recently_stopped",
                        lambda *a, **k: pytest.fail("must not search with no stop stage"))
    dc.run()
    assert wired["completed"] == []


# ── the core rule: future work closes, prior work is reported ──────────────
def test_only_tasks_due_on_or_after_the_stop_are_closed():
    future, prior = dc.split_by_stop_date([
        _task("t_after", STOPPED_AT + dt.timedelta(days=1), "[Scheduling] Check tutor availability"),
        _task("t_same", STOPPED_AT, "Call back Annie"),
        _task("t_before", STOPPED_AT - dt.timedelta(days=18), "August follow-up"),
    ], STOPPED_AT)
    assert [t["id"] for t in future] == ["t_after", "t_same"]
    assert [t["id"] for t in prior] == ["t_before"]


def test_unknown_stop_date_closes_nothing():
    """No stop date means no basis to call anything 'future'. Report, do not close."""
    future, prior = dc.split_by_stop_date([_task("t", STOPPED_AT)], None)
    assert future == [] and len(prior) == 1


def test_the_wolfstein_case_end_to_end(monkeypatch, wired):
    """The two [Scheduling] tasks dated the day after the cancel are closed;
    the three August follow-ups are left for a human to judge."""
    wired["tasks"] = [
        _task("116958937357", STOPPED_AT + dt.timedelta(days=1),
              "[Scheduling] Text Nolan directly with tutor availability updates"),
        _task("116955406746", STOPPED_AT + dt.timedelta(days=1),
              "[Scheduling] Check tutor availability for Bradley"),
        _task("115917632020", dt.datetime(2026, 8, 28, tzinfo=dt.timezone.utc),
              "Book next step with Annie Wolfstein"),
    ]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert set(wired["completed"]) == {"116958937357", "116955406746"}
    assert "115917632020" not in wired["completed"]
    rec = wired["audit"][0]
    assert rec["action_taken"] == "deal_closed_swept"
    assert rec["tasks_left"] == ["115917632020"]


def test_completed_and_deferred_tasks_are_never_touched(monkeypatch, wired):
    wired["tasks"] = [
        _task("done", STOPPED_AT + dt.timedelta(days=1), status="COMPLETED"),
        _task("deferred", STOPPED_AT + dt.timedelta(days=1), status="DEFERRED"),
    ]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert wired["completed"] == []


# ── the reason ─────────────────────────────────────────────────────────────
def test_missing_reason_asks_the_owner_and_never_invents_one(monkeypatch, wired):
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert len(wired["dms"]) == 1 and wired["dms"][0][0] == "UY"   # the deal owner
    body = wired["notes"][0]["properties"]["hs_note_body"]
    assert "no closing reason recorded" in body
    # it states the absence, it does not guess at a cause
    assert "cancel" not in body.lower()


def test_closed_lost_reason_property_counts_as_a_reason(monkeypatch, wired):
    monkeypatch.setattr(dc, "recently_stopped",
                        lambda *a, **k: [_deal(reason="Found a tutor at school")])
    dc.run()
    assert wired["dms"] == [] and wired["notes"] == []


def test_a_note_written_after_the_stop_counts_as_a_reason(monkeypatch, wired):
    wired["notes_on_record"] = [{"id": "n9", "properties": {
        "hs_timestamp": (STOPPED_AT + dt.timedelta(hours=2)).isoformat(),
        "hs_note_body": "Annie called back, Bradley has a tutor at his school now."}}]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert wired["dms"] == []


def test_a_note_written_before_the_stop_is_not_a_reason(monkeypatch, wired):
    wired["notes_on_record"] = [{"id": "n1", "properties": {
        "hs_timestamp": (STOPPED_AT - dt.timedelta(days=3)).isoformat(),
        "hs_note_body": "Scheduling note: prefers a male tutor, Wednesday evenings."}}]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert len(wired["dms"]) == 1


def test_our_own_nag_is_not_mistaken_for_a_reason(monkeypatch, wired):
    """Otherwise the second run reads the first run's note and goes quiet."""
    wired["notes_on_record"] = [{"id": "n1", "properties": {
        "hs_timestamp": (STOPPED_AT + dt.timedelta(days=1)).isoformat(),
        "hs_note_body": "[Agent] no closing reason recorded — written by "
                        "email/src/deal_closed.py\n\nThis deal was moved to Stopped"}}]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert len(wired["dms"]) == 1


# ── guards ─────────────────────────────────────────────────────────────────
def test_disabled_config_does_nothing(monkeypatch, wired):
    monkeypatch.setattr(dc, "cfg", lambda: {**CFG, "deal_closed": {"enabled": False}})
    monkeypatch.setattr(dc, "recently_stopped",
                        lambda *a, **k: pytest.fail("must not run while disabled"))
    dc.run()


def test_dry_run_writes_nothing(monkeypatch, wired):
    monkeypatch.setattr(dc, "DRY_RUN", True)
    wired["tasks"] = [_task("t1", STOPPED_AT + dt.timedelta(days=1))]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert wired["completed"] == [] and wired["dms"] == [] and wired["posts"] == []
    assert wired["audit"] == [] and wired["notes"] == []


def test_already_swept_deal_is_not_re_nagged(monkeypatch, wired):
    monkeypatch.setattr(dc.audit, "deals_closed_swept", lambda: {"65027182155"})
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal()])
    dc.run()
    assert wired["dms"] == [] and wired["completed"] == []


def test_run_is_capped_and_takes_the_most_recent(monkeypatch, wired):
    monkeypatch.setattr(dc, "cfg", lambda: {**CFG, "deal_closed": {
        **CFG["deal_closed"], "max_deals_per_run": 2}})
    deals = [_deal(did=str(i), closed=STOPPED_AT - dt.timedelta(days=i)) for i in range(5)]
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: deals)
    dc.run()
    assert [r["deal_id"] for r in wired["audit"]] == ["0", "1"]


def test_one_digest_per_run_not_one_message_per_deal(monkeypatch, wired):
    monkeypatch.setattr(dc, "recently_stopped",
                        lambda *a, **k: [_deal(did="1", reason="r"), _deal(did="2", reason="r")])
    dc.run()
    assert len(wired["posts"]) == 1
    assert wired["posts"][0][0] == "C_DIGEST"


def test_empty_digest_channel_posts_nowhere(monkeypatch, wired):
    monkeypatch.setattr(dc, "cfg", lambda: {**CFG, "deal_closed": {
        **CFG["deal_closed"], "digest_channel": ""}})
    monkeypatch.setattr(dc, "recently_stopped", lambda *a, **k: [_deal(reason="r")])
    dc.run()
    assert wired["posts"] == []
