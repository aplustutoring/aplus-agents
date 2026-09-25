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


# ── quote characters vary by client, not only by language ──────────────────
OURS_RU = ["Hi Alina, no we don't until Stephanie confirms she's ready to start again."]


def test_a_straight_quote_tapback_is_caught():
    """2026-09-22: Alina's client used a straight quote and the whole rule
    missed, even though the quoted text was our own message word for word."""
    body = ('Реакция ❤️ на " Hi Alina, no we don\'t until Stephanie confirms '
            'she\'s ready to start again. "')
    assert w.echoes_our_message(body, OURS_RU)


def test_every_common_quote_character_opens_a_tapback():
    inner = OURS_RU[0]
    for o, c in (("“", "”"), ('"', '"'), ("«", "»"),
                 ("„", "“"), ("‘", "’")):
        assert w.echoes_our_message(f"Liked {o}{inner}{c}", OURS_RU), (o, c)


def test_mismatched_quote_characters_still_count():
    """Clients are not consistent about pairing them."""
    assert w.echoes_our_message(f'Liked "{OURS_RU[0]}”', OURS_RU)


def test_widening_the_quote_class_did_not_swallow_real_messages():
    assert not w.echoes_our_message('She told me "bring the workbook" but which one?', OURS_RU)
    assert not w.echoes_our_message('"My tutor never emailed the homework"', OURS_RU)

# ── a short read must say so, not look like a quiet line ───────────────────
class _Resp:
    def __init__(self, rows, total, nxt):
        self.status_code = 200
        self._j = {"data": rows, "total_count": total, "next_page_link": nxt}

    def json(self):
        return self._j


def _pager(pages, calls=None):
    """A fake JustCall that serves the given pages in order."""
    def _get(url, headers=None, timeout=None, params=None):
        if calls is not None:
            calls.append(params.get("page"))
        i = params.get("page", 0)
        return pages[i] if i < len(pages) else _Resp([], pages[0]._j["total_count"], "")
    return _get


def test_a_complete_read_returns_every_row(monkeypatch):
    rows = [{"n": i} for i in range(150)]
    monkeypatch.setattr(w.requests, "get", _pager([
        _Resp(rows[:100], 150, "next"), _Resp(rows[100:], 150, "")]))
    assert len(w.pull("texts", {}, "since")) == 150


def test_paging_starts_at_zero(monkeypatch):
    """page=1 skips the newest hundred rows. That broke the monitor for ten
    hours on 2026-09-12 while six families were writing in."""
    calls = []
    monkeypatch.setattr(w.requests, "get", _pager([_Resp([{"n": 1}], 1, "")], calls))
    w.pull("texts", {}, "since")
    assert calls[0] == 0


def test_a_truncated_walk_raises_rather_than_answering(monkeypatch):
    """A short page ends the walk with no error raised anywhere. A family
    missing from a truncated read looks like a family who is fine."""
    monkeypatch.setattr(w.requests, "get",
                        _pager([_Resp([{"n": i} for i in range(19)], 22, "")]))
    try:
        w.pull("texts", {}, "since")
    except w.ShortRead as e:
        assert "19 of 22" in str(e)
    else:
        raise AssertionError("a short read must not return quietly")


def test_a_short_read_is_retried_before_refusing(monkeypatch):
    state = {"attempt": 0}

    def _get(url, headers=None, timeout=None, params=None):
        if params.get("page", 0) == 0:
            state["attempt"] += 1
            if state["attempt"] == 1:
                return _Resp([{"n": i} for i in range(19)], 22, "")   # short
            return _Resp([{"n": i} for i in range(22)], 22, "")       # recovered
        return _Resp([], 22, "")
    monkeypatch.setattr(w.requests, "get", _get)
    assert len(w.pull("texts", {}, "since")) == 22
    assert state["attempt"] == 2


def test_more_rows_than_claimed_is_fine(monkeypatch):
    """The window keeps gaining rows while we page. Only UNDER-counting is a
    short read."""
    monkeypatch.setattr(w.requests, "get",
                        _pager([_Resp([{"n": i} for i in range(25)], 22, "")]))
    assert len(w.pull("texts", {}, "since")) == 25


def test_a_missing_total_is_trusted_rather_than_blocking(monkeypatch):
    """If the envelope stops carrying total_count, answer rather than refuse to
    run at all. Losing the check is bad; losing the monitor is worse."""
    monkeypatch.setattr(w.requests, "get", _pager([_Resp([{"n": 1}], None, "")]))
    assert len(w.pull("texts", {}, "since")) == 1

# ── accepting what we already did ───────────────────────────────────────────
#
# Every message below is verbatim from the Maricris Tiu thread of 2026-09-18
# to 09-23, the thread this checker called a 90 hour breach and I repeated by
# name in #support-team. The direction of error that matters is the second
# block: a rule that hides a family is far worse than one that flags a
# thank-you, so most of these tests exist to prove it hides nobody.

OURS_SAID = [("2026-09-19 01:42:53",
              "Hi Maricris, I have added the lesson to 12:30 pm. "
              "Since Hannah has a student until 12:30.")]


def test_the_message_that_caused_the_false_accusation():
    """"Yes thats fine. We'll take it. Thank you!", three minutes after we told
    her the lesson was added. There was nothing waiting on us."""
    assert w.accepts_what_we_did(
        "Yes thats fine. We'll take it. Thank you!",
        "2026-09-19 01:45:45", OURS_SAID)


def test_a_plain_yes_to_a_question_we_asked():
    ours = [("2026-09-22 20:20:40",
             "Hi Maricris, hope all is well. Just wanted to check in and see "
             "if you received the lesson notes for the session")]
    assert w.accepts_what_we_did("Yes we did.", "2026-09-22 20:21:22", ours)


def test_accepting_the_time_we_ourselves_offered():
    assert w.accepts_what_we_did("Yes, 12:30 pm works. Thank you!",
                                 "2026-09-19 01:45:45", OURS_SAID)


# ── the ones it must never swallow ──────────────────────────────────────────

def test_a_yes_that_counter_offers_a_time_we_never_gave():
    """The whole reason rule 4 exists. It opens with a yes and is a live ask."""
    assert not w.accepts_what_we_did("Yes that's fine, can we do 5pm instead?",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_a_yes_carrying_a_day_we_never_proposed():
    assert not w.accepts_what_we_did("Ok. He can only do Saturday morning.",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_a_yes_that_still_asks():
    assert not w.accepts_what_we_did("Ok thank you. Please call me.",
                                     "2026-09-19 01:45:45", OURS_SAID)
    assert not w.accepts_what_we_did("Great, let me know when it is confirmed",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_a_complaint_is_never_an_acceptance():
    assert not w.accepts_what_we_did("The tutor never showed up. Thanks for nothing.",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_a_yes_with_a_but_stays_open():
    assert not w.accepts_what_we_did("Yes that works but he needs the workbook",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_nothing_of_ours_to_accept():
    """An affirmation out of nowhere is not an answer to us."""
    assert not w.accepts_what_we_did("Yes thats fine. We'll take it. Thank you!",
                                     "2026-09-19 01:45:45", [])


def test_too_long_after_us_to_be_a_reply_to_us():
    """Tomorrow morning's message is a new thread, whatever it opens with."""
    assert not w.accepts_what_we_did("Yes thats fine. We'll take it. Thank you!",
                                     "2026-09-20 09:00:00", OURS_SAID)


def test_only_counts_our_messages_sent_BEFORE_it():
    later = [("2026-09-19 02:00:00", "Hi Maricris, I have added the lesson to 12:30 pm")]
    assert not w.accepts_what_we_did("Yes thats fine. We'll take it. Thank you!",
                                     "2026-09-19 01:45:45", later)


def test_a_question_is_never_an_acceptance():
    assert not w.accepts_what_we_did("Yes. Does she have any open schedules today?",
                                     "2026-09-19 01:45:45", OURS_SAID)


def test_the_yes_must_open_the_message():
    """"...but yes" is not an acceptance, it is the tail of an argument."""
    assert not w.accepts_what_we_did(
        "We waited forty minutes and nobody came, yes we still want the lesson",
        "2026-09-19 01:45:45", OURS_SAID)


def test_load_our_words_fills_the_timestamped_twin():
    """OUR_WORDS and OUR_SAID come from one pass so they cannot drift."""
    w.load_our_words([_text("8185551234", "2026-09-18 09:00:00", "we said this", "outbound"),
                      _text("8185551234", "2026-09-18 10:00:00", "and this", "outbound")])
    assert w.OUR_WORDS["8185551234"] == ["we said this", "and this"]
    assert w.OUR_SAID["8185551234"] == [("2026-09-18 09:00:00", "we said this"),
                                        ("2026-09-18 10:00:00", "and this")]
