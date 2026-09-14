"""Unit tests for the pure core of ops/lead_intake. No network.

Every case is a real record from the 2026-09-14 trace
(docs/investigations/2026-09-14-online-lead-intake.md).
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import lead_intake as li  # noqa: E402

C = li.cfg()


def contact(cid, **props):
    return {"id": str(cid), "properties": props}


# ── selection: the F5 / F7 fixes ───────────────────────────────────
def test_intake_event_matches_any_landing_page():
    # Three different pages, one form. The old flow needed a GUID for each.
    for page in ("Book a Free Consultation: Main InTake Form - Request a Free Consultation",
                 "Woodland Hills Tutoring | In-Home & Online | A+ Tutoring: Main InTake Form - Request a Free Consultation",
                 "A+ Tutoring Service Area Locations: Main InTake Form - Request a Free Consultation"):
        assert li.is_intake_event(page, C), page


def test_not_a_lead_wins_over_intake_event():
    assert not li.is_intake_event("North Hollywood Tutor: Become a Tutor", C)
    assert not li.is_intake_event("Teacher Scholarship Program Form", C)
    assert not li.is_intake_event("Student Diagnostic Test Upload: student-diagnostic-test-upload", C)


def test_returning_customer_is_selected_not_locked_out():
    """F7. David Reich, contact 3495701: a 2023 customer whose 2026-09-10
    resubmit produced nothing at all under flow 50818589."""
    david = contact(3495701, recent_conversion_date="2026-09-10T14:36:39.213Z",
                    recent_conversion_event_name="Book a Free Consultation: Main InTake Form - Request a Free Consultation",
                    lifecyclestage="customer", hs_lead_status="QTL - Diagnostic Sent")
    got = li.select([david], "2026-09-09T00:00:00Z", set(), C)
    assert [r["id"] for r in got] == ["3495701"]


def test_cursor_and_processed_suppress_replays():
    row = contact(1, recent_conversion_date="2026-09-10T00:00:00Z",
                  recent_conversion_event_name="Main InTake Form")
    assert li.select([row], "2026-09-11T00:00:00Z", set(), C) == []      # older than cursor
    assert li.select([row], "2026-09-01T00:00:00Z",
                     {"1:2026-09-10T00:00:00Z"}, C) == []                 # already alerted


def test_select_is_oldest_first_so_the_cursor_advances_monotonically():
    rows = [contact(2, recent_conversion_date="2026-09-12T00:00:00Z",
                    recent_conversion_event_name="Main InTake Form"),
            contact(1, recent_conversion_date="2026-09-11T00:00:00Z",
                    recent_conversion_event_name="Main InTake Form")]
    assert [r["id"] for r in li.select(rows, "2026-09-01T00:00:00Z", set(), C)] == ["1", "2"]


# ── classification and routing ─────────────────────────────────────
def test_persona_wins_then_lead_status_carries_identity():
    assert li.classify({"a_persona": "Family"}) == "family"
    assert li.classify({"a_persona": "Teacher of Record/EF/ES;Family"}) == "tor"
    assert li.classify({"hs_lead_status": "Charter School Teacher TOR/EF"}) == "tor"
    assert li.classify({"hs_lead_status": "Teacher in a School"}) == "decision_maker"
    assert li.classify({}) == "family"       # no persona at all: the common case


def test_routing_follows_the_locked_sender_rule():
    fam = li.route("family", C)
    assert fam["seat"] == "charter_sales" and fam["line"] == "charter_sales"
    assert li.route("decision_maker", C)["seat"] == "sales"
    assert li.route("tutor", C)["line"] == "support"


def test_family_sla_is_ninety_minutes_not_the_next_afternoon():
    """F2. The old flow held the alert task until 15:30 PT, measured at up to
    23h20m (Lincoln Campbell)."""
    assert li.route("family", C)["sla_hours"] == 1.5


# ── phones and spam ────────────────────────────────────────────────
def test_norm_phone_handles_the_double_one_the_intake_form_writes():
    assert li.norm_phone("+118184048544") == "8184048544"   # Vishta Granados
    assert li.norm_phone("+12135247104") == "2135247104"    # Elia Palacios
    assert li.norm_phone("+1669-2556326") == "6692556326"   # Annalee Baroni


def test_spam_catches_the_repeated_non_us_number():
    """The +93 307 207 6448 fills: Charles Smith, Roli Roy, Mia Garcia."""
    assert li.is_spam({"phone": "+933072076448"}, Counter(), C)
    assert not li.is_spam({"phone": "+13232861087"}, Counter(), C)
    assert not li.is_spam({"phone": ""}, Counter(), C)


def test_spam_catches_one_phone_across_many_contacts():
    counts = Counter({"7077060205": 3})
    assert li.is_spam({"phone": "+17077060205"}, counts, C)


# ── copy ───────────────────────────────────────────────────────────
def test_render_strips_em_dashes_and_double_hyphens():
    """CLAUDE.md outbound style, Roman 2026-08-24, locked."""
    out = li.render("Hi {{firstname}} — welcome -- glad you wrote.", {"firstname": "Olga"})
    assert "—" not in out and "--" not in out and "Olga" in out


def test_render_leaves_no_unfilled_tokens_in_family_copy():
    """F4. The old SMS shipped '{{ enrolled_object.hubspot_owner_id }}' as a name."""
    tpl = (HERE.parent / "templates" / "first-touch-family.txt").read_text()
    out = li.render(tpl, {"firstname": "Olga", "seat_first": "Paola"})
    assert "{{" not in out and "Paola" in out and "STOP" in out


def test_returning_summary_leads_with_the_history():
    deals = [{"properties": {"dealname": "David Reich - Juliana",
                             "start_of_tutoring_for_this_deal": "2023-10-19"}}]
    s = li.returning_summary(deals)
    assert "RETURNING FAMILY" in s and "Juliana" in s
    assert li.returning_summary([]) == ""


# ── the alert ──────────────────────────────────────────────────────
class _Gate:
    verdict = "hold"
    reasons = ["active thread on the support line in the last 14 days (4 texts), owned by Yolanda"]
    owner = {"name": "Yolanda Rico", "seat": "scheduler_m_z"}


def test_alert_carries_the_gate_verdict_and_the_thread_owner():
    """The Gonzalez failure: nothing looked at the other line before sending."""
    c = contact(1, firstname="Mary", lastname="Gonzalez",
                recent_conversion_date="2026-09-14T00:00:00Z",
                recent_conversion_event_name="Main InTake Form")
    subj, body = li.alert_task(c, "family", "Paola Sarmiento", _Gate(), "", "Hi Mary...")
    assert "Mary Gonzalez" in subj
    assert "HOLD" in body and "Yolanda" in body
    assert "Talk to them before you reach out" in body
    assert "Has anyone at A+ already been in touch with you?" in body


# ── SLA clamp (found by replaying 2026-08-15..09-14) ───────────────
from datetime import datetime, timezone  # noqa: E402


def _at(h, m=0):
    return datetime(2026, 9, 10, h, m, tzinfo=timezone.utc)


def test_due_inside_the_window_is_just_now_plus_sla():
    assert li.due_at(_at(10), 1.5, C).hour == 11


def test_overnight_submit_is_not_due_at_two_in_the_morning():
    """Vaani Arora submitted 23:57; naive maths made it due 01:27."""
    due = li.due_at(_at(23, 57), 1.5, C)
    assert due.hour == 9 and due.day == 11        # next open (08:00) + 90 min


def test_before_open_waits_for_open():
    """Sarah Adams submitted 02:32; naive maths made it due 04:02."""
    due = li.due_at(_at(2, 32), 1.5, C)
    assert due.hour == 9 and due.day == 10


def test_evening_submit_rolls_to_the_next_morning():
    assert li.due_at(_at(18, 21), 1.5, C).day == 11
