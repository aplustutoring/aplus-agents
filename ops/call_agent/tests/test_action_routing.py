"""
Action-item routing + name-correction propagation (Paola's 2026-09-01
correction: trial logistics landed in the call agent's own task output, and a
child's name corrected to "Autumn" on the call still went out under the old
name in the next-step language).

The four scheduling examples are the ones from her report.
"""

from datetime import datetime, timezone

import call_agent


def _cfg(scheduling_owner=""):
    return {
        "justcall": {"require_recording": True, "min_transcript_chars": 200,
                     "ai_fetch_pause_seconds": 0},
        "claude": {"model": "x", "max_tokens": 100, "max_transcript_chars": 50000},
        "hubspot": {
            "owners": {"roman": 1, "paola": 2, "janelle": 3, "yolanda": 4,
                       "scheduling": 99},
            "default_task_owner": "paola",
            "scheduling_task_owner": scheduling_owner,
            "task_due_business_days": 1,
            "ticket": {"pipeline": "0", "stage": "1", "priority": "HIGH",
                       "owner": "paola", "check_in_business_days": 2},
        },
        "slack": {"channel": "#calls", "alert_channel": ""},
        "coaching": {"enabled": False},
    }


def _item(text, route="follow_up", owner_hint=None):
    return {"item": text, "owner_hint": owner_hint, "route": route}


def _summary(**over):
    d = {
        "summary": "Parent called about tutoring for her daughter.",
        "caller_type": "parent",
        "intent": "scheduling",
        "sentiment": "neutral",
        "action_items": [],
        "name_corrections": [],
        "follow_up_needed": True,
        "next_step_scheduled": True,
        "handoff_note": None,
        "lead_status": "no_change",
        "lead_status_reason": "",
        "student_or_school_names_mentioned": [],
        "record_updates": {f: None for f in call_agent.RECORD_FIELD_MAP},
    }
    d.update(over)
    return d


# ─── Task subject prefixing ───────────────────────────────────────────────────

def test_scheduling_items_are_subject_prefixed():
    assert call_agent.task_subject(_item("Text the family to confirm the trial",
                                         "scheduling")) == \
        "[Scheduling] Text the family to confirm the trial"


def test_follow_up_items_are_not_prefixed():
    assert call_agent.task_subject(_item("Call back with pricing")) == \
        "Call back with pricing"


def test_subject_stays_within_hubspot_250_char_cap():
    subject = call_agent.task_subject(_item("x" * 400, "scheduling"))
    assert len(subject) == 250
    assert subject.startswith(call_agent.SCHEDULING_TASK_PREFIX)


# ─── Owner resolution ─────────────────────────────────────────────────────────

def test_scheduling_route_goes_to_scheduling_owner_when_configured():
    cfg = _cfg(scheduling_owner="scheduling")
    assert call_agent._resolve_owner(None, cfg, "Paola", "scheduling") == 99


def test_scheduling_route_beats_the_roman_handoff_rule():
    # Roman-answered calls hand follow-up to Paola, but scheduling work is not
    # follow-up — it still belongs to the scheduling queue.
    cfg = _cfg(scheduling_owner="scheduling")
    assert call_agent._resolve_owner("Janelle", cfg, "Roman Vasquez", "scheduling") == 99


def test_scheduling_route_falls_back_to_default_owner_until_roman_confirms():
    # scheduling_task_owner is empty in the shipped config; the prefix is what
    # marks the item until the real owner id is wired.
    assert call_agent._resolve_owner(None, _cfg(), "Paola", "scheduling") == 2


def test_unknown_scheduling_owner_key_does_not_crash_the_call():
    assert call_agent._resolve_owner(None, _cfg(scheduling_owner="nobody"),
                                     "Paola", "scheduling") == 2


def test_follow_up_routing_is_unchanged():
    cfg = _cfg(scheduling_owner="scheduling")
    assert call_agent._resolve_owner("have Janelle call them", cfg, "Paola") == 3
    assert call_agent._resolve_owner("have Janelle call them", cfg, "Roman") == 2


# ─── Route validation ─────────────────────────────────────────────────────────

def test_missing_or_bogus_route_defaults_to_follow_up():
    d = call_agent._validate_summary(_summary(action_items=[
        {"item": "Send pricing", "owner_hint": None},
        {"item": "Book the trial", "owner_hint": None, "route": "nonsense"},
        "Call the family back",
    ]))
    assert [it["route"] for it in d["action_items"]] == \
        ["follow_up", "follow_up", "follow_up"]


def test_scheduling_route_survives_validation():
    d = call_agent._validate_summary(_summary(action_items=[
        _item("Send the tutor's profile to the family", "scheduling")]))
    assert d["action_items"][0]["route"] == "scheduling"


# ─── Name-correction propagation ──────────────────────────────────────────────

def test_corrected_name_replaces_stale_name_everywhere():
    d = call_agent._validate_summary(_summary(
        summary="Mom called about Autum's reading. Autum is in 3rd grade.",
        handoff_note="Open with the trial time for Autum.",
        student_or_school_names_mentioned=["Autum"],
        action_items=[_item("Text mom to confirm Autum's trial", "scheduling")],
        name_corrections=[{"wrong": "Autum", "correct": "Autumn"}],
        record_updates={**{f: None for f in call_agent.RECORD_FIELD_MAP},
                        "whats_going_on": "Autum needs reading support.",
                        "student_first_name": "Autum"},
    ))
    assert "Autum'" not in d["summary"] and "Autumn's reading" in d["summary"]
    assert d["handoff_note"] == "Open with the trial time for Autumn."
    assert d["student_or_school_names_mentioned"] == ["Autumn"]
    assert d["action_items"][0]["item"] == "Text mom to confirm Autumn's trial"
    assert d["record_updates"]["whats_going_on"] == "Autumn needs reading support."
    assert d["record_updates"]["student_first_name"] == "Autumn"


def test_swap_is_whole_word_only():
    d = call_agent._validate_summary(_summary(
        summary="Ali called about Alison's math.",
        name_corrections=[{"wrong": "Ali", "correct": "Alice"}],
    ))
    assert d["summary"] == "Alice called about Alison's math."


def test_swap_skipped_when_corrected_name_contains_the_old_one():
    # "Autumn" -> "Autumn Rose" would stack on re-match; leave the model's text.
    d = call_agent._validate_summary(_summary(
        summary="Autumn starts Tuesday.",
        name_corrections=[{"wrong": "Autumn", "correct": "Autumn Rose"}],
    ))
    assert d["summary"] == "Autumn starts Tuesday."


def test_malformed_name_corrections_are_dropped_not_raised():
    d = call_agent._validate_summary(_summary(
        summary="Autumn starts Tuesday.",
        name_corrections=[{"wrong": "", "correct": "Autumn"},
                          {"wrong": "Autumn", "correct": "autumn"},
                          {"correct": "Autumn"}, "junk"],
    ))
    assert d["name_corrections"] == []
    assert d["summary"] == "Autumn starts Tuesday."


def test_no_corrections_leaves_output_untouched():
    d = call_agent._validate_summary(_summary(summary="Nothing to correct here."))
    assert d["summary"] == "Nothing to correct here."
    assert d["name_corrections"] == []


# ─── End to end: Paola's call ─────────────────────────────────────────────────

def _run_process_call(monkeypatch, cfg, summary, created):
    """process_call with JustCall/Claude/HubSpot stubbed; records create_task."""
    monkeypatch.setattr(call_agent, "fetch_transcript", lambda cid, pause: "t" * 500)
    monkeypatch.setattr(call_agent, "find_contact_by_phone",
                        lambda number: {"id": "77", "properties": {
                            "firstname": "Maria", "lastname": "Reyes"}})
    monkeypatch.setattr(call_agent, "summarize_call",
                        lambda tr, c, contact=None, call=None: summary)
    monkeypatch.setattr(call_agent, "log_call_to_hubspot",
                        lambda *a, **k: "call-1")
    monkeypatch.setattr(call_agent, "apply_record_updates",
                        lambda *a, **k: ([], []))

    def fake_create_task(contact_id, subject, body, owner_id, due_utc,
                         priority="MEDIUM"):
        created.append({"subject": subject, "body": body, "owner_id": owner_id})
        return f"task-{len(created)}"

    monkeypatch.setattr(call_agent, "create_task", fake_create_task)

    call = {"id": 1, "contact_number": "+13105550147", "agent_name": "Paola Ruiz",
            "call_date": "2026-09-01", "call_time": "14:05:00",
            "call_info": {"direction": "Incoming", "type": "answered",
                          "recording": "https://rec/1"}}
    return call_agent.process_call(call, cfg, dry_run=False,
                                   now_utc=datetime(2026, 9, 1, 21, 0,
                                                    tzinfo=timezone.utc))


def test_scheduling_follow_ups_and_a_name_correction_on_one_call(monkeypatch):
    summary = _summary(
        summary="Maria called about Autum's trial next week.",
        follow_up_needed=True,
        action_items=[
            _item("Send the tutor's profile to the family", "scheduling"),
            _item("Text the family to confirm the trial time", "scheduling"),
            _item("Call back about Autum's dropped transfer", "scheduling"),
            _item("Move Autum's trial to Thursday", "scheduling"),
            _item("Email Maria the charter pricing sheet"),
        ],
        name_corrections=[{"wrong": "Autum", "correct": "Autumn"}],
    )
    created = []
    kind, entry = _run_process_call(
        monkeypatch, _cfg(scheduling_owner="scheduling"),
        call_agent._validate_summary(summary), created)

    assert kind == "entry"
    sched = [t for t in created
             if t["subject"].startswith(call_agent.SCHEDULING_TASK_PREFIX)]
    assert len(sched) == 4
    assert all(t["owner_id"] == 99 for t in sched)

    follow_up = [t for t in created
                 if not t["subject"].startswith(call_agent.SCHEDULING_TASK_PREFIX)]
    assert len(follow_up) == 1
    assert follow_up[0]["subject"] == "Email Maria the charter pricing sheet"
    assert follow_up[0]["owner_id"] == 2          # Paola, unchanged

    # No task subject or body carries the stale name.
    assert not any("Autum'" in t["subject"] or "Autum'" in t["body"]
                   for t in created)
    assert any("Autumn's dropped transfer" in t["subject"] for t in created)
    assert [route for _, _, route in entry["tasks_created"]].count("scheduling") == 4


def test_scheduling_items_stay_on_paola_until_the_owner_is_configured(monkeypatch):
    summary = call_agent._validate_summary(_summary(action_items=[
        _item("Text the family to confirm the trial time", "scheduling")]))
    created = []
    _run_process_call(monkeypatch, _cfg(), summary, created)
    assert created[0]["owner_id"] == 2
    assert created[0]["subject"].startswith(call_agent.SCHEDULING_TASK_PREFIX)


# ─── Digest ───────────────────────────────────────────────────────────────────

def test_digest_counts_scheduling_tasks_separately():
    entry = {"call_id": 1, "number": "+13105550147", "time_pt": "2:05 PM",
             "matched": True, "contact_label": "Maria Reyes", "no_next_step": False,
             "summary": _summary(follow_up_needed=False),
             "record_applied": [], "record_skipped": [],
             "tasks_created": [("Confirm the trial", 99, "scheduling"),
                               ("Send pricing", 2, "follow_up")],
             "ticket_id": None, "coached": False, "direction": "incoming"}
    text = call_agent.build_digest([entry], [], [], "2026-09-01")
    assert "Tasks created: 2 (1 to scheduling)" in text


def test_digest_tolerates_pre_route_entries_held_in_state():
    # --no-digest runs persist entries; ones written before this change have
    # two-element tasks_created tuples.
    entry = {"call_id": 1, "number": "+13105550147", "time_pt": "2:05 PM",
             "matched": True, "contact_label": "Maria Reyes", "no_next_step": False,
             "summary": _summary(follow_up_needed=False),
             "record_applied": [], "record_skipped": [],
             "tasks_created": [["Send pricing", 2]],
             "ticket_id": None, "coached": False, "direction": "incoming"}
    text = call_agent.build_digest([entry], [], [], "2026-09-01")
    assert "Tasks created: 1 ·" in text
