"""scripts/waiting.py — the checker behind the one-hour rule.

Every test here is a bug this script actually shipped. The pure helpers are
tested; the two API pulls are not, because they are thin and the traps in them
(zero-indexed JustCall paging, INCOMING_EMAIL direction) are recorded in
comments at the call sites.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import waiting as w  # noqa: E402


# ── courtesies ──────────────────────────────────────────────────────────────
def test_english_closing_courtesies_are_not_people_waiting():
    for body in ("Thank you!", "thanks so much", "Ok", "Got it", "Perfect",
                 "Wonderful!", "Sounds good", "Will do", "You too"):
        assert w.is_courtesy(body), body


def test_tapbacks_in_the_senders_language_are_courtesies():
    """2026-09-18: Judy Xu's iPhone "liked" reaction came through as 赞了 and
    aged past the one-hour bar twice, reported both times as a parent being
    ignored."""
    assert w.is_courtesy("赞了：No worries at all. Thank you for the update.")
    assert w.is_courtesy('Liked “See you Wednesday”')
    assert w.is_courtesy('Laughed at “that works”')


def test_a_real_question_is_never_a_courtesy():
    assert not w.is_courtesy("Thanks, but can we move Wednesday to 5?")
    assert not w.is_courtesy("No one has logged in yet. I have to get going.")
    assert not w.is_courtesy("")


def test_courtesy_matches_only_at_the_start():
    """Otherwise any message containing 'thanks' anywhere vanishes."""
    assert not w.is_courtesy("The tutor never showed up. Thanks for nothing.")


# ── our own people ──────────────────────────────────────────────────────────
def test_staff_numbers_are_not_families():
    """The booth texts a photo to whoever is working the stand; that staff copy
    was counted as a family waiting on us."""
    assert w.is_internal("janelle@wetutorathome.com")
    assert w.is_internal("ROMAN@WeTutorAtHome.com")
    assert not w.is_internal("parent@gmail.com")
    assert not w.is_internal("")
    assert not w.is_internal(None)


# ── phones ──────────────────────────────────────────────────────────────────
def test_phone_shapes_all_reduce_to_ten_digits():
    for p in ("+1 (818) 573-6644", "8185736644", "1-818-573-6644", "818.573.6644"):
        assert w.digits(p) == "8185736644"


def test_a_short_or_missing_number_is_not_guessed_at():
    assert w.digits("911") == ""
    assert w.digits(None) == ""


# ── a call back counts as an answer ─────────────────────────────────────────
def _text(num, when, body, direction="inbound"):
    d, t = when.split(" ")
    return {"contact_number": num, "direction": direction, "contact_name": "A Parent",
            "sms_info": {"body": body, "sms_date": d, "sms_time": t}}


def _call(num, when, direction="outgoing"):
    d, t = when.split(" ")
    return {"contact_number": num, "call_date": d, "call_time": t,
            "call_info": {"direction": direction}}


def test_an_outbound_call_registers_as_a_touch():
    """Version 1 read only the text log and called three phoned-back families
    neglected. Annie Wolfstein was on the phone with Paola at the time."""
    _in, out = w.newest_each_way(
        [_text("8185551234", "2026-09-18 10:00:00", "are you there?")],
        [_call("8185551234", "2026-09-18 10:05:00")])
    assert out["8185551234"] == "2026-09-18 10:05:00"


def test_an_inbound_call_is_not_a_touch():
    _in, out = w.newest_each_way(
        [_text("8185551234", "2026-09-18 10:00:00", "hello")],
        [_call("8185551234", "2026-09-18 10:05:00", direction="incoming")])
    assert out == {}


def test_newest_wins_on_both_sides():
    texts = [_text("8185551234", "2026-09-18 09:00:00", "first"),
             _text("8185551234", "2026-09-18 11:00:00", "second"),
             _text("8185551234", "2026-09-18 10:00:00", "our reply", direction="outgoing")]
    inbound, out = w.newest_each_way(texts, [])
    assert inbound["8185551234"][1] == "second"
    assert out["8185551234"] == "2026-09-18 10:00:00"


# ── the bar ─────────────────────────────────────────────────────────────────
def test_the_bar_is_sixty_minutes():
    assert w.SLA_MIN == 60


def test_age_and_its_formatting():
    now = dt.datetime(2026, 9, 18, 12, 0, 0)
    assert w.age_minutes("2026-09-18 10:18:00", now) == 102
    assert w.fmt_age(102) == "1h 42m"
    assert w.fmt_age(7) == "7m"
    assert w.fmt_age(0) == "0m"


def test_an_unparseable_timestamp_does_not_crash_the_run():
    assert w.age_minutes("not a date", dt.datetime(2026, 9, 18)) == -1


# ── tapbacks, without enumerating languages ─────────────────────────────────
OURS = ["Okay thank you, I offered Angelo 2:30 pm today. Waiting on their "
        "confirmation. I'll be using slack to for future communication.",
        "Hi Misty, we have you down for Tuesdays at 10."]


def test_a_spanish_tapback_is_caught_by_the_echo_not_a_word_list():
    """2026-09-18, two hours after the Chinese fix shipped: Hannah Thorn's phone
    sent the Spanish form. Enumerating languages loses; the quoted part being
    OUR OWN message does not change between languages."""
    body = ('Le gusta “Okay thank you, I offered Angelo 2:30 pm today. Waiting on '
            'their confirmation. I\'ll be using slack to for future communication.”')
    assert w.echoes_our_message(body, OURS)


def test_any_language_works_because_the_prefix_is_never_read():
    for prefix in ("Aimé", "Gefällt mir", "いいね", "Понравилось", "Curtiu"):
        body = f'{prefix} “Hi Misty, we have you down for Tuesdays at 10.”'
        assert w.echoes_our_message(body, OURS), prefix


def test_a_quote_we_never_sent_is_not_a_tapback():
    body = '“My tutor said she would email me the homework” — did that happen?'
    assert not w.echoes_our_message(body, OURS)


def test_a_real_message_that_happens_to_quote_is_left_alone():
    body = 'She told me “bring the workbook” but which one?'
    assert not w.echoes_our_message(body, OURS)


def test_nothing_quoted_means_nothing_to_echo():
    assert not w.echoes_our_message("Can we move to 4pm?", OURS)
    assert not w.echoes_our_message("", OURS)
    assert not w.echoes_our_message('Liked “ok”', OURS)   # too short to be distinctive


def test_a_truncated_tapback_still_matches():
    """Tapbacks cut long messages off with an ellipsis."""
    body = 'Le gusta “Okay thank you, I offered Angelo 2:30 pm today. Waiting on…”'
    assert w.echoes_our_message(body, OURS)


def test_the_explicit_prefixes_still_cover_unquoted_forms():
    """The Chinese tapback carries no quotes at all, so the word list earns its
    keep alongside the echo check."""
    assert w.is_courtesy("赞了：No worries at all. Thank you for the update.")


# ── the echo rule must not be starved by the question's window ─────────────
def test_our_words_come_from_a_wider_pull_than_the_question():
    """2026-09-18: a two hour look-back could not recognise a tapback because
    the message it quoted had been sent earlier that afternoon. The rule was
    right and starved."""
    wide = [
        _text("8185551234", "2026-09-18 09:00:00",
              "Your words mean so much to me! Thank you for your kindness.",
              direction="outgoing"),
        _text("8185551234", "2026-09-18 16:45:00",
              'Reacted 💖 to “Your words mean so much to me! Thank you for your kindness.”'),
    ]
    w.load_our_words(wide)
    assert w.OUR_WORDS["8185551234"] == [
        "Your words mean so much to me! Thank you for your kindness."]
    reaction = wide[1]["sms_info"]["body"]
    assert w.echoes_our_message(reaction, w.OUR_WORDS["8185551234"])


def test_load_our_words_never_keeps_their_messages():
    """Echoing THEIR words back would make any repeated phrase look like a
    tapback."""
    w.load_our_words([_text("8185551234", "2026-09-18 09:00:00", "their question")])
    assert w.OUR_WORDS.get("8185551234", []) == []


def test_the_question_window_is_left_to_the_api():
    """A local cutoff string compared against the account's clock widened a two
    hour check by the UTC offset on 2026-09-18."""
    import inspect
    src = inspect.getsource(w.newest_each_way)
    assert "inbound_since" not in src


def test_the_outbound_lookback_is_wider_than_any_normal_window():
    assert w.ECHO_LOOKBACK_HOURS >= 48


# ── a pleasantry that does not open the message ────────────────────────────
def test_a_short_message_that_is_only_thanks_is_a_courtesy():
    assert w.is_courtesy("Well! Thank you.")
    assert w.is_courtesy("Oh wonderful, thank you")


def test_a_long_message_containing_thanks_is_still_a_message():
    assert not w.is_courtesy("The tutor never showed up. Thanks for nothing.")


def test_a_question_containing_thanks_is_still_a_question():
    assert not w.is_courtesy("Thanks, but can we move Wednesday to 5?")
    assert not w.is_courtesy("Ok thank you, can she do Tuesday?")
