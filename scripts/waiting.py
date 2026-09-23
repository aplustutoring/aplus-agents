"""Who is ACTUALLY waiting on us. Version 4.

This script measures Roman's one-hour rule (2026-09-17: "all of our texts need
to be acknowledged within 1 hour"). It has been wrong four times, each time in a
different direction, and the history is kept here because every version looked
obviously correct while it was lying.

Version 1 read only the text log, so three families who had been CALLED back
looked neglected. Annie Wolfstein was on the phone with Paola at the moment it
said she was waiting.

Version 2 read HubSpot's `notes_last_contacted`, which aggregates channels. That
was WORSE, silently: the property updates on INBOUND activity too. Amanda
Calof's read 04:29:51, the exact second of her own text to us. Every message
looked answered the instant it arrived, so the checker reported "nobody is
waiting" every single tick, by construction, for about fifteen hours.

Version 3 asks the only question that means anything: did something go OUT to
this person after their message? Three channels, newest wins.

  - outbound text   JustCall
  - outbound call   JustCall (the channel version 1 was blind to)
  - outbound email  HubSpot engagements

If none of them is newer than the message, they are waiting.

Version 4 (2026-09-18) fixed two ways the count lied UPWARD, which is the
failure mode that gets a monitor ignored rather than trusted:

  - iPhone tapbacks arrive translated into the SENDER's language, so a Chinese
    "liked" ("赞了") never matched the English courtesy list. Judy Xu's reaction
    aged past the one-hour bar twice, reported each time as a parent being
    ignored.
  - The conference booth texts a photo to whoever is working the stand. That
    staff copy counted as a family waiting on us. A number that resolves to a
    contact on our own domain is now excluded.

Version 4.1 (2026-09-18, two hours later) stopped enumerating languages. Hannah
Thorn's phone sent the Spanish tapback `Le gusta "..."`, and adding Spanish
would have left French, Portuguese, Hebrew and every other language our families
use. A tapback has one property no language changes: the quoted part is OUR OWN
message handed back to us. So it is matched against what we actually sent that
number, and a real reply cannot be swallowed because a real reply is not a
verbatim echo of our words.

Version 4.4 (2026-09-22) widened the quote class. A Russian tapback quoting our
own message went uncaught because the client used a straight quote and the
shape matcher only knew typographic ones. Not a language gap: the same text in
curly quotes matched. Clients differ on quote characters and on whether they
pair them, so any of them opens and any of them closes.

Version 4.3 (2026-09-20) made a truncated read say so. The pager stops on an
empty `next_page_link`, so a page that arrives short ends the walk and the
result LOOKS complete, with no error anywhere. Every page reports
`total_count`, so the walk now checks its own work, retries once, and raises
`ShortRead` rather than reporting a number it cannot stand behind. A family
missing from a truncated read looks like a family who is fine, which is the
dangerous direction to be wrong in. Prompted by two JustCall read timeouts that
morning; the walk had no way to tell a short page from a finished one.

Version 4.2 (2026-09-18, same evening) stopped starving the echo rule. It was
reading our own outbound from the same narrow window as the question, so on a
two hour look-back `Reacted 💖 to "..."` had nothing to match against and was
reported as a parent waiting two hours. Our side is now read over three days
whatever the question asks about. Same evening, a second gap: a pleasantry that
does not START the message ("Well! Thank you.") now counts when the whole
message is short and asks nothing.

Output splits three ways and the third matters: WAITING, answered, and CANNOT
TELL when a number does not resolve to a contact. An unresolved number is a
confident wrong answer, not a blank.

    python3 scripts/waiting.py [hours]      # default 14

Two open questions Roman has not settled, both of which change the count:
  - does a closing "thank you" need acknowledging? They are filtered out here.
  - overnight. On 2026-09-16 the line went quiet at 21:31 and reopened at
    08:50, so six people breached a flat one-hour rule by morning. The rule
    needs either stated hours or an after-hours auto-acknowledgement that buys
    the real reply until the morning.
"""
# Annotations as strings: this runs on the system python 3.9, where
# `int | None` in a signature is a TypeError at import time.
from __future__ import annotations

import datetime
import os
import re
import sys
import warnings
from pathlib import Path

import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# Walk up for the first .env. A worktree sits at <repo>/.claude/worktrees/<name>
# and carries no .env of its own, so stopping at the immediate parent would mean
# this only ever runs from the main checkout. Variables already in the
# environment win either way, which is what lets Actions run this from repo
# secrets with no .env file present at all.
for _parent in Path(__file__).resolve().parents:
    if (_parent / ".env").is_file():
        load_dotenv(_parent / ".env")
        break

# Roman 2026-09-17: every text gets acknowledged within ONE HOUR.
SLA_MIN = 60

# A TAPBACK quotes our own message back at us, so whatever follows the prefix is
# OUR text and its length says nothing. These arrive translated into the
# sender's language, which is why the Chinese forms are here: leaving them out
# put Judy Xu's "liked" reaction on the breach list twice on 2026-09-18.
TAPBACK = re.compile(
    r"^\s*(liked|loved|laughed at|emphasi[sz]ed|questioned|disliked)\s*[“\"']"
    r"|^\s*(赞了|喜欢了|大笑了?|强调了|质疑了|不喜欢)", re.IGNORECASE)

# A CLOSING pleasantry only counts when the message STOPS there. "Thanks, but
# can we move Wednesday to 5?" opens with thanks and is a real request; an
# earlier version swallowed it, which is the direction of error that hides a
# family instead of inventing one.
_CLOSING_WORDS = (r"(thank you|thanks|thx|ty|ok(ay)?|got it|great|perfect|"
                  r"wonderful|excellent|awesome|sounds good|will do|no problem|"
                  r"yes|yep|yup|you too|👍|😊|❤️|​👍​|​❤️​)")
CLOSING = re.compile(r"^\s*" + _CLOSING_WORDS, re.IGNORECASE)
# The same vocabulary, unanchored, for the short-message rule below. CLOSING
# itself is anchored, so .search() on it would still only match the start.
CLOSING_ANY = re.compile(_CLOSING_WORDS, re.IGNORECASE)

# A message this short that contains a pleasantry and asks nothing is a
# pleasantry wherever the words sit in it.
_SHORT = 40

# What may trail a pleasantry and still leave it a pleasantry.
_TRAILING = " \t.!,…~-–—:;)\u200b👍😊❤️🙏😀🙂"

# The language-proof form: a few words, then OUR message in typographic quotes,
# and nothing after it. Hannah Thorn's phone sent the Spanish tapback
# `Le gusta “Okay thank you, I offered Angelo 2:30 pm today...”` two hours after
# the Chinese one was fixed by adding Chinese. Enumerating languages loses.
# Quote characters vary by client, not just by language. Alina's phone used a
# straight quote on 2026-09-22 and the whole rule missed, even though the
# quoted text was our own message word for word. Curly, straight, angled and
# low-9 all count, and the closing quote is any of them rather than the
# matching pair: clients are not consistent about pairing them.
_Q = "“”\"«»„‟‘’"
TAPBACK_SHAPE = re.compile(
    r"^\s*\S{1,18}(?:\s+\S{1,18}){0,3}\s*[:：]?\s*[" + _Q + r"](.+)[" + _Q + r"]\s*$",
    re.DOTALL)

_ECHO_KEEP = 60          # characters of our message to compare; tapbacks truncate

# How far back to read OUR OWN messages, whatever window the question asks
# about. A tapback quotes something we said, and on 2026-09-18 a two hour
# look-back could not recognise `Reacted 💖 to "..."` because the message being
# quoted had been sent earlier that afternoon and was not in the index. The
# echo rule was right and starved. Reading our side wide costs one more page of
# JustCall and makes the rule work at any window size.
ECHO_LOOKBACK_HOURS = 72

INTERNAL_DOMAIN = "@wetutorathome.com"

# number -> the bodies we sent it inside the window, filled by newest_each_way
OUR_WORDS: dict = {}


def _headers() -> tuple[dict, dict]:
    """Built at call time, not import time, so the pure helpers below can be
    unit tested with no credentials present."""
    k, s = os.environ["JUSTCALL_API_KEY"], os.environ["JUSTCALL_API_SECRET"]
    return ({"Authorization": f"{k}:{s}", "Accept": "application/json"},
            {"Authorization": f"Bearer {os.environ['HUBSPOT_PRIVATE_APP_TOKEN']}",
             "Content-Type": "application/json"})


def digits(p) -> str:
    """Last ten digits, the only phone shape that compares reliably."""
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""


def is_courtesy(body: str) -> bool:
    """A closing thank-you or a tapback, not a question waiting on an answer."""
    b = (body or "").strip()
    if not b:
        return False
    if TAPBACK.match(b):
        return True
    m = CLOSING.match(b)
    if not m:
        # "Well! Thank you." is a closing pleasantry that does not open the
        # message. Allowed only when the whole message is short and asks
        # nothing, so "The tutor never showed up. Thanks for nothing." and
        # "Thanks, but can we move Wednesday to 5?" both survive.
        if "?" not in b and len(b) <= _SHORT and CLOSING_ANY.search(b):
            return True
        return False
    rest = b[m.end():].strip(_TRAILING)
    if "?" in rest:
        return False
    # "Thank you" and "Thank you so much" close a thread. "Thanks, but can we
    # move Wednesday" does not, and the difference is that the message keeps
    # going.
    return len(rest) <= 25


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def quoted_part(body: str) -> str:
    """The quoted payload of a tapback-shaped message, else ""."""
    m = TAPBACK_SHAPE.match((body or "").strip())
    return m.group(1) if m else ""


def echoes_our_message(body: str, ours: list) -> bool:
    """Is this message quoting something WE sent to this number?

    That is what a tapback is, in every language. A real reply is not a verbatim
    echo of our own words, so this cannot swallow one.
    """
    quoted = _squash(quoted_part(body))
    if not quoted:
        return False
    quoted = quoted.rstrip("…....").strip()
    if len(quoted) < 8:          # too short to be distinctive
        return False
    head = quoted[:_ECHO_KEEP]
    return any(head in _squash(o) for o in ours if o)


def is_internal(email: str) -> bool:
    """Our own staff are not families waiting on us."""
    return str(email or "").lower().endswith(INTERNAL_DOMAIN)


def age_minutes(when: str, now: datetime.datetime) -> int:
    try:
        return int((now - datetime.datetime.strptime(when[:19], "%Y-%m-%d %H:%M:%S"))
                   .total_seconds() // 60)
    except ValueError:
        return -1


def fmt_age(minutes: int) -> str:
    h, m = divmod(max(minutes, 0), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


class ShortRead(Exception):
    """The walk ended with fewer rows than the API said exist."""


def _walk(kind: str, jh: dict, since_s: str) -> tuple[list, int | None]:
    """One pass. Returns (rows, total the API claims) so the caller can check.

    JustCall v2.1 paging starts at ZERO. `page=1` skips the newest hundred rows
    and makes a narrow window look empty; that broke the SMS monitor for about
    ten hours on 2026-09-12 while six families were writing in.
    """
    out, page, total = [], 0, None
    while page <= 60:
        r = requests.get(f"https://api.justcall.io/v2.1/{kind}", headers=jh, timeout=60,
                         params={"per_page": 100, "page": page, "from_datetime": since_s})
        if r.status_code >= 300:
            raise SystemExit(f"JustCall {kind} HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        if total is None:
            try:
                total = int(j.get("total_count"))
            except (TypeError, ValueError):
                total = None
        rows = j.get("data") or []
        out += rows
        if not rows or not j.get("next_page_link"):
            break
        page += 1
    return out, total


def pull(kind: str, jh: dict, since_s: str, attempts: int = 2) -> list:
    """Every row in the window, or an exception. Never a partial answer.

    The walk stops on an empty `next_page_link`, so a page that arrives short
    or link-less ends it early and the result LOOKS complete, with no error
    raised anywhere. A family missing from a truncated read looks like a family
    who is fine, which is the dangerous direction to be wrong in.

    Every page reports `total_count`, so the walk checks its own work. An
    over-count is fine (the window can gain rows while we page); an under-count
    is a short read, retried once and then refused.
    """
    last = 0
    for _ in range(max(1, attempts)):
        rows, total = _walk(kind, jh, since_s)
        if total is None or len(rows) >= total:
            return rows
        last = len(rows)
    raise ShortRead(f"{kind}: read {last} of {total} rows the API reports. "
                    f"Refusing to answer on a partial read.")


def newest_each_way(texts: list, calls: list) -> tuple[dict, dict]:
    """(newest inbound text per number, newest OUTBOUND touch per number).

    Calls count. Reading texts alone is what made three phoned-back families
    look neglected.

    The window is whatever the caller already asked JustCall for. Do NOT filter
    timestamps here: rows carry the account's clock and a local cutoff string
    compared against them silently widened a two hour check by the UTC offset
    on 2026-09-18.
    """
    newest_in, newest_out = {}, {}
    for t in texts:
        n = digits(t.get("contact_number"))
        if not n:
            continue
        info = t.get("sms_info") or {}
        w = (f"{t.get('sms_date') or info.get('sms_date')} "
             f"{t.get('sms_time') or info.get('sms_time')}")
        body = ((info.get("body")) or "").replace("\n", " ").strip()
        if str(t.get("direction", "")).lower().startswith("in"):
            if n not in newest_in or w > newest_in[n][0]:
                newest_in[n] = (w, body, t.get("contact_name") or "")
        else:
            if n not in newest_out or w > newest_out[n]:
                newest_out[n] = w
    for c in calls:
        info = c.get("call_info") or {}
        if str(info.get("direction") or "").lower() != "outgoing":
            continue
        n = digits(c.get("contact_number"))
        if not n:
            continue
        w = f"{c.get('call_date')} {c.get('call_time')}"
        if n not in newest_out or w > newest_out[n]:
            newest_out[n] = w
    return newest_in, newest_out


def load_our_words(texts: list) -> None:
    """Fill OUR_WORDS from a WIDE pull of the feed.

    Kept separate from the question's window on purpose. A tapback quotes
    something we said, and on a two hour check the message being quoted is
    usually older than that, so the echo rule starves and reports a reaction as
    a parent waiting.
    """
    OUR_WORDS.clear()
    for t in texts:
        if str(t.get("direction", "")).lower().startswith("in"):
            continue
        n = digits(t.get("contact_number"))
        if not n:
            continue
        info = t.get("sms_info") or {}
        OUR_WORDS.setdefault(n, []).append(
            ((info.get("body")) or "").replace("\n", " ").strip())


def outbound_email_after(number: str, when: str, h: dict):
    """(answered?, label). True means something went out on email after `when`,
    or the number belongs to our own staff. None means the number resolves to no
    contact at all, which the caller must report rather than silently drop.

    Matches on HubSpot's calculated phone index, which holds normalised digits.
    Guessing formatting variants of the raw `phone` property misses people.
    """
    r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/search", headers=h,
                      timeout=30, json={"filterGroups": [
                          {"filters": [{"propertyName": "hs_searchable_calculated_phone_number",
                                        "operator": "EQ", "value": number}]},
                          {"filters": [{"propertyName": "hs_searchable_calculated_mobile_number",
                                        "operator": "EQ", "value": number}]}],
                          "properties": ["firstname", "lastname", "email"], "limit": 1})
    hits = r.json().get("results") or []
    if not hits:
        return None, ""
    c = hits[0]
    p = c["properties"]
    label = f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip()
    if is_internal(p.get("email")):
        return True, label
    a = requests.get(
        f"https://api.hubapi.com/crm/v4/objects/contacts/{c['id']}/associations/emails",
        headers=h, timeout=30).json()
    ids = [str(x["toObjectId"]) for x in a.get("results", [])][-20:]
    if not ids:
        return False, label
    b = requests.post("https://api.hubapi.com/crm/v3/objects/emails/batch/read", headers=h,
                      timeout=30, json={"inputs": [{"id": i} for i in ids],
                                        "properties": ["hs_timestamp", "hs_email_direction"]}).json()
    for e in b.get("results", []):
        ep = e["properties"]
        # INCOMING_EMAIL is inbound. There is no OUTGOING value: outbound reads
        # as EMAIL, and treating that as inbound makes every thread look
        # unanswered.
        if ep.get("hs_email_direction") == "INCOMING_EMAIL":
            continue
        ts = (ep.get("hs_timestamp") or "")[:19].replace("T", " ")
        if ts >= when[:19]:
            return True, label
    return False, label


def main(hours: float = 14.0) -> int:
    """Prints the three buckets. Returns how many are past the one-hour bar."""
    jh, h = _headers()
    now = datetime.datetime.now()
    # A ShortRead here must reach the caller. Catching it and carrying on would
    # turn "I could not read the line" into "nobody is waiting", which is the
    # single failure this script keeps having.
    ask_from = (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    newest_in, newest_out = newest_each_way(pull("texts", jh, ask_from),
                                            pull("calls", jh, ask_from))
    # Our own side, read wider, so a tapback quoting something we said this
    # morning is still recognisable on a two hour check.
    wide_from = (now - datetime.timedelta(
        hours=max(hours, ECHO_LOOKBACK_HOURS))).strftime("%Y-%m-%d %H:%M:%S")
    load_our_words(pull("texts", jh, wide_from) if hours < ECHO_LOOKBACK_HOURS
                   else pull("texts", jh, ask_from))

    waiting, courtesy = [], 0
    for n, (when, body, name) in sorted(newest_in.items(), key=lambda x: x[1][0]):
        out = newest_out.get(n, "")
        if out and out[:19] >= when[:19]:
            continue                               # texted or called back
        if is_courtesy(body) or echoes_our_message(body, OUR_WORDS.get(n, [])):
            courtesy += 1
            continue
        answered, label = outbound_email_after(n, when, h)
        if answered:
            continue
        waiting.append((when, label or name or f"...{n[-4:]}", body,
                        "no contact record" if answered is None else ""))

    now = datetime.datetime.utcnow()
    print(f"{len(newest_in)} numbers wrote in over {hours}h "
          f"({courtesy} closing courtesies ignored)\n")
    rows = sorted(((age_minutes(w, now), w, lab, b, note)
                   for w, lab, b, note in waiting), reverse=True)
    over = [r for r in rows if r[0] >= SLA_MIN]
    print(f"WAITING: {len(rows)}   PAST THE 1-HOUR BAR: {len(over)}")
    for age, _when, label, body, note in rows:
        flag = "BREACH" if age >= SLA_MIN else "  ok  "
        print(f"  [{flag}] {fmt_age(age):>7s} | {label}{(' · ' + note) if note else ''}")
        print(f"             {body[:150]}")
    return len(over)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 14.0)
