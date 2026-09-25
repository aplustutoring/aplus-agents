"""Roman 2026-09-22: Teachworks' own family notice does the 4-hour nudge; the
family email and text fire together at 3 hours live (or after the fallback),
the teacher email one business day later if still no PO and no reply."""
import datetime as dt

from src import low_balance as lb
from test_low_balance import DEAL, Harness, NOW_LA, NOW_UTC, _active_deal, _case, _cfg


def _fire_cfg(**over):
    c = _cfg(armed=True)
    c["low_balance"].update({"fire_at_hours": 3, "fire_fallback_days": 5, "text_with_email": True,
                             "lesson_hours_default": 1.0, "family_text_after_days": 1})
    c["low_balance"].update(over)
    return c


# ── pure rules ──────────────────────────────────────────────────────────────

def test_lesson_hours_from_the_start_end_pair():
    assert lb._lesson_hours({"from_date": "2026-09-10 10:00:00", "to_date": "2026-09-10 10:45:00"}, 1.0) == 0.75
    assert lb._lesson_hours({"from_date": "2026-09-10T10:00:00", "to_date": "2026-09-10T11:00:00"}, 1.0) == 1.0
    assert lb._lesson_hours({"from_date": "2026-09-10"}, 1.0) == 1.0                       # no pair: the default
    assert lb._lesson_hours({"from_date": "2026-09-10 10:00:00", "to_date": "2026-09-12 10:00:00"}, 1.0) == 1.0


def test_student_key_reads_last_first_and_first_last():
    assert lb._student_key("DaVault, Kailyn Marie") == lb._student_key("Kailyn Marie DaVault") == "kailyn marie davault"


def test_fire_ready_at_three_hours_live_or_after_the_fallback():
    lbc = _fire_cfg()["low_balance"]
    now = NOW_UTC
    fresh = {"hours": 3.75, "opened_at": (now - dt.timedelta(hours=2)).isoformat()}
    assert not lb._fire_ready(fresh, lbc, now)
    assert lb._fire_ready({**fresh, "hours_live": 3.0}, lbc, now)                 # a lesson burned it to 3
    assert lb._fire_ready({**fresh, "hours": 2.25}, lbc, now)                     # the alert itself was below 3
    assert not lb._fire_ready({**fresh, "hours_live": 3.25}, lbc, now)
    # NOW is Friday 9/11: opened Thursday 9/3 = 6 business days ago → fallback; Tuesday 9/8 = 3 → not yet
    assert lb._fire_ready({**fresh, "opened_at": "2026-09-03T16:00:00+00:00"}, lbc, now)
    assert not lb._fire_ready({**fresh, "opened_at": "2026-09-08T16:00:00+00:00"}, lbc, now)


def test_live_hours_subtracts_lessons_after_the_alert_only(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    opened = (NOW_UTC - dt.timedelta(days=3)).isoformat()
    case = _case(email_sent=None, hours=4.0, opened_at=opened)
    before = (NOW_LA - dt.timedelta(days=4)).replace(tzinfo=None).isoformat()[:19]
    after1 = (NOW_LA - dt.timedelta(days=2)).replace(tzinfo=None).isoformat()[:19]
    after2 = (NOW_LA - dt.timedelta(days=1)).replace(tzinfo=None).isoformat()[:19]
    h.attended = {"taylor rodriguez": [(before, 1.0), (after1, 0.75), (after2, 0.75)],
                  "someone else": [(after1, 1.0)]}
    cases = {case["message_id"]: case}
    lb._update_live_hours(cases, lb.cfg()["low_balance"])
    assert case["hours_live"] == 2.5 and case["lessons_since"] == 2
    recs = [r for r in h.recs if r["action_taken"] == "low_balance_balance"]
    assert len(recs) == 1 and recs[0]["hours_live"] == 2.5 and recs[0]["message_id"].endswith(":balance")
    assert h.notes and "Live balance 2.5 h: 2 attended lesson(s)" in h.notes[0][1]
    # unchanged next sweep: no second record, no second note
    lb._update_live_hours(cases, lb.cfg()["low_balance"])
    assert len([r for r in h.recs if r["action_taken"] == "low_balance_balance"]) == 1 and len(h.notes) == 1


def test_live_hours_left_alone_when_teachworks_is_down(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_attended_since", lambda s, l: (_ for _ in ()).throw(RuntimeError("TW 502")))
    case = _case(email_sent=None, hours=4.0, hours_live=3.25, lessons_since=1)
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert case["hours_live"] == 3.25 and not h.recs and not h.notes


# ── the sweep ───────────────────────────────────────────────────────────────

def test_email_and_text_go_together_once_the_balance_is_three(monkeypatch):
    case = _case(email_sent=None, hours=3.0, opened_at=(NOW_UTC - dt.timedelta(hours=2)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep()                                                    # hourly, not forced
    assert len(h.emails) == 1 and h.emails[0][0] == "jessicalujanbd@gmail.com"
    assert h.sms == [("+1 909-454-8581", "Hi Jessica, text body.")]
    assert not h.drafts and not h.tor_sent                            # the teacher waits a business day
    rec = next(r for r in h.recs if r["action_taken"] == "low_balance_family_contacted")
    assert rec["sms_sent"] and rec["tor_pending"] is True
    assert any("Day 0 text, with the email" in n for _t, n in h.notes)


def test_nothing_fires_above_three_hours_before_the_fallback(monkeypatch):
    case = _case(email_sent=None, hours=3.75, opened_at=(NOW_UTC - dt.timedelta(hours=2)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep()
    assert not h.emails and not h.sms and not h.drafts
    assert not any(r["action_taken"] in ("low_balance_email_sent", "low_balance_email_held") for r in h.recs)


def test_a_lesson_in_teachworks_trips_the_trigger(monkeypatch):
    case = _case(email_sent=None, hours=3.75, opened_at=(NOW_UTC - dt.timedelta(days=1)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    yesterday = (NOW_LA - dt.timedelta(hours=20)).replace(tzinfo=None).isoformat()[:19]
    h.attended = {"taylor rodriguez": [(yesterday, 0.75)]}          # 3.75 - 0.75 = 3.0
    lb.run_sweep()
    assert len(h.emails) == 1 and len(h.sms) == 1


def test_fifteen_minute_pass_texts_with_the_email_too(monkeypatch):
    case = _case(email_sent=None, hours=2.5, opened_at=(NOW_UTC - dt.timedelta(hours=2)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    monkeypatch.setattr(lb, "now_la", lambda: NOW_LA.replace(minute=33))        # the :15/:30/:45 pass
    lb.run_sweep()
    assert len(h.emails) == 1 and len(h.sms) == 1 and not h.drafts


def test_teacher_email_follows_one_business_day_after_the_text(monkeypatch):
    # NOW is Friday 9/11 09:03 PT; texted Thursday → teacher due today; texted today → not yet
    texted_thu = (NOW_UTC - dt.timedelta(days=1)).isoformat()
    case = _case(day1_done=True, tor_pending=True, day1_at=texted_thu,
                 opened_at=(NOW_UTC - dt.timedelta(days=6)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep()
    assert not h.sms and h.drafts and h.drafts[0][0] == "kylee@ileadexploration.org"
    today = (NOW_UTC - dt.timedelta(minutes=30)).isoformat()
    case2 = _case(day1_done=True, tor_pending=True, day1_at=today,
                  opened_at=(NOW_UTC - dt.timedelta(days=6)).isoformat())
    h2 = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case2["message_id"]: case2})
    _active_deal(monkeypatch)
    lb.run_sweep()
    assert not h2.sms and not h2.drafts


def test_risk_reads_the_live_balance(monkeypatch):
    # alert said 3.0 eight days ago; three lessons since → 0.75 live → day-7 risk fires
    case = _case(day1_done=True, hours=3.0, opened_at=(NOW_UTC - dt.timedelta(days=8)).isoformat())
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    h.attended = {"taylor rodriguez": [((NOW_LA - dt.timedelta(days=d)).replace(tzinfo=None).isoformat()[:19], 0.75)
                                       for d in (6, 4, 2)]}
    lb.run_sweep()
    assert any(r["action_taken"] == "low_balance_escalated" for r in h.recs)
    assert next(r for r in h.recs if r["action_taken"] == "low_balance_balance")["hours_live"] == 0.75
    # same alert, no lessons: 3.0 live, no risk
    h2 = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: dict(case)})
    _active_deal(monkeypatch)
    lb.run_sweep()
    assert not any(r["action_taken"] == "low_balance_escalated" for r in h2.recs)


# ── the title carries the balance; zero is High now (Roman 2026-09-23) ──────

def test_hours_label_and_subject_rewrite():
    assert lb._hours_label(1.75) == "1.75 h left" and lb._hours_label(0) == "0 h left" and lb._hours_label(2.6) == "2.5 h left"
    assert lb._subject_with_hours("Low balance: Ember Seeley (iLead), 2.5 hours left", 1.75) == "Low balance: Ember Seeley (iLead), 1.75 h left"
    assert lb._subject_with_hours("Low balance: Ember Seeley (iLead), 1.75 h left", 1.0) == "Low balance: Ember Seeley (iLead), 1 h left"
    assert lb._subject_with_hours("Abby Ulstrup (private pay), 0 lessons left", 0.0) == "Abby Ulstrup (private pay), 0 h left"


def test_balance_change_rewrites_the_title_and_stamps_hours_left(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    case = _case(email_sent=None, hours=4.0, subject="Low balance: Taylor Rodriguez (iLead), 4 hours left",
                 opened_at=(NOW_UTC - dt.timedelta(days=2)).isoformat())
    h.attended = {"taylor rodriguez": [((NOW_LA - dt.timedelta(days=1)).replace(tzinfo=None).isoformat()[:19], 0.75)]}
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    ticket_patch = next(p for m, path, p in h.patches if "/tickets/T1" in path)
    assert ticket_patch["properties"] == {"subject": "Low balance: Taylor Rodriguez (iLead), 3.25 h left", "hours_left": "3.25"}
    assert ("64250037589", {"retention_hours_left": "3.25"}) in h.stamps
    assert not h.dms                                                 # 3.25 h is not zero


def test_repeat_alert_resets_the_anchor_and_the_title(monkeypatch):
    # opened at 4.0 five days ago, two lessons since; Teachworks re-alerts at 3.0 yesterday:
    # the alert wins, and only lessons AFTER it subtract
    recs = [{"message_id": "k", "action_taken": "low_balance_opened", "hours": 4.0, "contact_id": "C",
             "to_email": "a@b.com", "parent_email": "a@b.com", "phone": "+15550000000",
             "opened_at": (NOW_UTC - dt.timedelta(days=5)).isoformat()},
            {"message_id": "k", "action_taken": "low_balance_repeat", "hours": 3.0,
             "timestamp": (NOW_UTC - dt.timedelta(days=1)).isoformat()}]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    case = lb.open_cases()["k"]
    assert case["hours"] == 3.0 and case["hours_at"] == recs[1]["timestamp"] and case["hours_live"] is None
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    case.update(student="Taylor Rodriguez", ticket_id="T1", deal_id="D1", subject="Low balance: Taylor Rodriguez (iLead), 4 hours left")
    h.attended = {"taylor rodriguez": [((NOW_LA - dt.timedelta(days=3)).replace(tzinfo=None).isoformat()[:19], 1.0),
                                       ((NOW_LA - dt.timedelta(hours=6)).replace(tzinfo=None).isoformat()[:19], 0.75)]}
    lb._update_live_hours({"k": case}, lb.cfg()["low_balance"])
    assert case["hours_live"] == 2.25 and case["lessons_since"] == 1


def test_package_growth_on_the_deal_adds_to_the_balance(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: 6.0)          # Kath bumped the PO from 4 to 6
    case = _case(email_sent=None, hours=1.0, po_hours="4", opened_at=(NOW_UTC - dt.timedelta(days=2)).isoformat())
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert case["hours_live"] == 3.0
    rec = next(r for r in h.recs if r["action_taken"] == "low_balance_balance")
    assert rec["po_hours_seen"] == 6.0
    assert any("package grew by 2 h" in n for _t, n in h.notes)


def test_zero_balance_is_high_priority_now_with_one_dm(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    case = _case(email_sent="x", day1_done=True, hours=0.75, owner="scheduler_a_l",
                 opened_at=(NOW_UTC - dt.timedelta(days=2)).isoformat())           # day 2, not day 7
    h.attended = {"taylor rodriguez": [((NOW_LA - dt.timedelta(hours=5)).replace(tzinfo=None).isoformat()[:19], 0.75)]}
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    risk = [p for m, path, p in h.patches if "/tickets/T1" in path and p["properties"].get("hs_ticket_priority") == "HIGH"]
    assert risk and risk[0]["properties"]["retention_risk"] == "true"
    assert case["escalated"] is True
    assert any(r["action_taken"] == "low_balance_escalated" and r["reason"] == "zero_balance" for r in h.recs)
    assert len(h.dms) == 1 and h.dms[0][0] == "UJA" and "0 HOURS LEFT" in h.dms[0][1]
    assert ("64250037589", {"retention_stage": "retention_risk"}) in h.stamps
    # next sweep, still zero: no second DM, no second flag
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert len(h.dms) == 1


def test_trial_at_zero_is_flagged_on_the_first_sweep(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    case = _case(email_sent=None, hours=0.0, funding_type="trial", owner="charter_sales", charter=False,
                 subject="Low balance: Abby Ulstrup (private pay), 0 hours left",
                 opened_at=(NOW_UTC - dt.timedelta(hours=1)).isoformat())
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert h.dms and h.dms[0][0] == "UPAO" and "trial" in h.dms[0][1]
    assert any("only deal on file" in n for _t, n in h.notes)


# ── 2026-09-24: cases recorded before the stamp existed still get stamped; zero still escalates ──

def test_unchanged_case_without_a_stamp_is_stamped_once(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    # balance already recorded by the pre-#283 code (no title, no property), nothing moved since
    case = _case(email_sent="x", hours=3.5, hours_live=3.5, lessons_since=0, hours_stamped=False,
                 subject="Low balance: Taylor Rodriguez (iLead), 3.5 hours left",
                 opened_at=(NOW_UTC - dt.timedelta(days=2)).isoformat())
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    patch = next(p for m, path, p in h.patches if "/tickets/T1" in path)
    assert patch["properties"] == {"subject": "Low balance: Taylor Rodriguez (iLead), 3.5 h left", "hours_left": "3.5"}
    assert not h.notes                                                # nothing moved: no note
    assert next(r for r in h.recs if r["action_taken"] == "low_balance_balance")["stamped"] is True
    # second sweep, still unchanged and now stamped: silent
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert sum(1 for r in h.recs if r["action_taken"] == "low_balance_balance") == 1


def test_case_already_at_zero_is_escalated_even_if_unchanged(monkeypatch):
    h = Harness(monkeypatch, _fire_cfg())
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    case = _case(email_sent="x", day1_done=True, hours=0.0, hours_live=0.0, lessons_since=0, hours_stamped=True,
                 funding_type="trial", owner="charter_sales", charter=False,
                 opened_at=(NOW_UTC - dt.timedelta(days=1)).isoformat())
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert h.dms and h.dms[0][0] == "UPAO" and "0 HOURS LEFT" in h.dms[0][1]
    assert case["escalated"] is True
    lb._update_live_hours({case["message_id"]: case}, lb.cfg()["low_balance"])
    assert len(h.dms) == 1


def test_open_cases_folds_the_stamped_flag(monkeypatch):
    recs = [{"message_id": "k", "action_taken": "low_balance_opened", "hours": 4.0, "contact_id": "C",
             "to_email": "a@b.com", "parent_email": "a@b.com", "phone": "+15550000000", "opened_at": NOW_UTC.isoformat()},
            {"message_id": "k:balance", "action_taken": "low_balance_balance", "hours_live": 3.0, "lessons_since": 1},
            {"message_id": "k:balance", "action_taken": "low_balance_balance", "hours_live": 3.0, "lessons_since": 1, "stamped": True}]
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs[:2]))
    assert lb.open_cases()["k"].get("hours_stamped") is False
    monkeypatch.setattr(lb.audit, "_iter_records", lambda: iter(recs))
    assert lb.open_cases()["k"]["hours_stamped"] is True


# ── 2026-09-24: the scheduled run always sweeps; a dispatch can force it ────

def test_scheduled_run_sweeps_whatever_the_minute(monkeypatch):
    calls = []
    monkeypatch.setattr(lb, "_sweep", lambda cases, now, force=False, texts_only=False: calls.append("sweep"))
    monkeypatch.setattr(lb, "_send_pending_emails", lambda *a, **k: calls.append("emails") or set())
    monkeypatch.setattr(lb, "_day0_texts", lambda *a, **k: None)
    monkeypatch.setattr(lb, "needs_invoice_sweep", lambda: 0)
    monkeypatch.setattr(lb, "_recheck_deferred", lambda now: None)
    monkeypatch.setattr(lb, "open_cases", lambda: {"k": _case()})
    monkeypatch.setattr(lb, "cfg", lambda: _fire_cfg())
    monkeypatch.setattr(lb, "staff", lambda k: {})
    late = NOW_LA.replace(minute=45)                                  # the :45 cron
    monkeypatch.setattr(lb, "now_la", lambda: late)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("LOW_BALANCE_FORCE_SWEEP", raising=False)
    lb.run_sweep()
    assert calls == ["emails"]                                        # a dispatch at :45: email pass only
    calls.clear()
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    lb.run_sweep()
    assert calls == ["sweep"]                                         # the scheduled run always sweeps
    calls.clear()
    monkeypatch.delenv("GITHUB_EVENT_NAME")
    monkeypatch.setenv("LOW_BALANCE_FORCE_SWEEP", "1")
    lb.run_sweep()
    assert calls == ["sweep"]                                         # force_sweep dispatch input


# ── 2026-09-24: a trial with real deals after it is converted, not at risk ──

def _trial_case(**over):
    return _case(funding_type="trial", charter=False, owner="charter_sales", hours=0.0, email_sent="x", day1_done=True,
                 deal_id="trial-1", po_created="2026-09-10", package="Promotion - First Trial Lesson",
                 subject="Low balance: Taylor Rodriguez (private pay), 0 hours left", **over)


def test_trial_with_charter_deals_after_it_closes_as_converted(monkeypatch):
    later = [{"id": "c1", "properties": {**DEAL["properties"], "createdate": "2026-09-17T00:00:00Z",
                                         "dealname": "Angela Topcu - Cody Topcu - Valley View 1 - 26/27"}},
             {"id": "c2", "properties": {**DEAL["properties"], "createdate": "2026-09-22T00:00:00Z",
                                         "dealname": "Angela Topcu - Cody Topcu - Valley View 2 - 26/27"}}]
    case = _trial_case()
    h = Harness(monkeypatch, _fire_cfg(), deals=later, open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    lb.run_sweep(force=True)
    assert h.stage_updates == [("T1", "R4")]                          # Renewed, closed outright: no invoice to wait for
    rec = next(r for r in h.recs if r["action_taken"] == "low_balance_resolved")
    assert rec["stage"] == "renewed" and "2 deal(s) on file after the free trial" in rec["reason"] \
        and "Valley View 1" in rec["reason"]
    assert not h.dms and not any((p or {}).get("properties", {}).get("hs_ticket_priority") for _m, path, p in h.patches)


def test_trial_with_only_the_trial_escalates_and_says_so(monkeypatch):
    case = _trial_case()
    h = Harness(monkeypatch, _fire_cfg(), deals=[], open_cases={case["message_id"]: case})
    _active_deal(monkeypatch)
    monkeypatch.setattr(lb, "_deal_po_hours", lambda c: None)
    lb.run_sweep(force=True)
    assert not h.stage_updates
    assert h.dms and h.dms[0][0] == "UPAO" and "free trial, the only deal on file" in h.dms[0][1]
    assert any("only deal on file" in n for _t, n in h.notes)


def test_trial_conversion_ignores_trial_tracking_and_earlier_deals(monkeypatch):
    monkeypatch.setattr(lb, "cfg", lambda: {**_fire_cfg(), "first_lesson": {"trial_pipelines": ["19120821"], "exclude_pipelines": ["917641511"]},
                                            "deal_sync": {"exclude_pipelines": ["971802"]}})
    deals = [{"id": "t2", "properties": {"pipeline": "19120821", "createdate": "2026-09-20T00:00:00Z", "dealname": "second trial"}},
             {"id": "tsp", "properties": {"pipeline": "917641511", "createdate": "2026-09-20T00:00:00Z", "dealname": "teacher tracking"}},
             {"id": "old", "properties": {"pipeline": "907748", "createdate": "2026-08-01T00:00:00Z", "dealname": "last season"}},
             {"id": "trial-1", "properties": {"pipeline": "19120821", "createdate": "2026-09-10T00:00:00Z", "dealname": "the trial"}}]
    monkeypatch.setattr(lb, "_student_deals", lambda f, l, after=None: deals)
    assert lb._trial_converted(_trial_case()) == []
    assert lb._trial_converted(_case(funding_type="charter")) == []       # charter cases never take this path
    deals.append({"id": "real", "properties": {"pipeline": "907748", "createdate": "2026-09-15T00:00:00Z", "dealname": "real PO"}})
    assert [d["id"] for d in lb._trial_converted(_trial_case())] == ["real"]
