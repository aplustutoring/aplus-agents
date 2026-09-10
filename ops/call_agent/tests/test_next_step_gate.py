"""No-next-step guard hygiene (2026-09-10 task audit).

Between 9/1 and 9/9 the guard raised 42 "Book next step" tasks on the sales
seat; 19 were outbound voicemails or screening services where nobody could
have booked anything, and four families got a second task while the first
was still open. Two gates fix that: the summary now says whether a live
person took part (reached_live), and an identical open task short-circuits
the create.
"""

import call_agent


def _summary(**over):
    d = {
        "summary": "Paola called the family back about tutoring.",
        "caller_type": "parent",
        "intent": "new inquiry",
        "sentiment": "neutral",
        "action_items": [],
        "name_corrections": [],
        "follow_up_needed": True,
        "next_step_scheduled": False,
        "reached_live": True,
        "handoff_note": None,
        "lead_status": "no_change",
        "lead_status_reason": "",
        "student_or_school_names_mentioned": [],
        "record_updates": {f: None for f in call_agent.RECORD_FIELD_MAP},
    }
    d.update(over)
    return d


# ─── reached_live gate ────────────────────────────────────────────────────────

def test_live_new_inquiry_with_no_next_step_needs_a_task():
    assert call_agent.needs_next_step_task(_summary()) is True


def test_voicemail_never_needs_a_next_step_task():
    assert call_agent.needs_next_step_task(_summary(reached_live=False)) is False


def test_booked_next_step_needs_no_task():
    assert call_agent.needs_next_step_task(_summary(next_step_scheduled=True)) is False


def test_existing_customer_call_needs_no_task():
    assert call_agent.needs_next_step_task(_summary(intent="scheduling")) is False


def test_validator_defaults_reached_live_true_for_older_payloads():
    d = _summary()
    d.pop("reached_live")
    out = call_agent._validate_summary(d)
    assert out["reached_live"] is True


def test_validator_keeps_reached_live_false():
    out = call_agent._validate_summary(_summary(reached_live=False))
    assert out["reached_live"] is False


# ─── open-task dedupe ─────────────────────────────────────────────────────────

SUBJ = "Book next step with Neta ((818) 430-4241) — none set on call"


def test_find_open_task_returns_the_exact_open_match(monkeypatch):
    seen = {}

    def fake_post(endpoint, payload):
        seen["endpoint"] = endpoint
        seen["payload"] = payload
        return {"results": [{"id": "T77", "properties": {"hs_task_subject": SUBJ}}]}

    monkeypatch.setattr(call_agent, "hs_post", fake_post)
    assert call_agent.find_open_task(SUBJ) == "T77"
    assert seen["endpoint"] == "crm/v3/objects/tasks/search"
    filters = seen["payload"]["filterGroups"][0]["filters"]
    assert {"propertyName": "hs_task_subject", "operator": "EQ", "value": SUBJ} in filters
    status = [f for f in filters if f["propertyName"] == "hs_task_status"][0]
    assert status["operator"] == "NOT_IN" and "COMPLETED" in status["values"]


def test_find_open_task_ignores_near_matches():
    def fake_post(endpoint, payload):
        return {"results": [{"id": "T1", "properties": {"hs_task_subject": SUBJ + " (old)"}}]}

    call_agent.hs_post, orig = fake_post, call_agent.hs_post
    try:
        assert call_agent.find_open_task(SUBJ) is None
    finally:
        call_agent.hs_post = orig


def test_find_open_task_never_suppresses_on_lookup_error(monkeypatch):
    def boom(endpoint, payload):
        raise RuntimeError("HubSpot 500")

    monkeypatch.setattr(call_agent, "hs_post", boom)
    assert call_agent.find_open_task(SUBJ) is None
