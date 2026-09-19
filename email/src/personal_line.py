"""Tutoring texts that land on the visionary's personal line, handed to a scheduler.

Why this exists. On 2026-09-17 Inna Volodinsky was told, in writing, that the
support line was the best number and the team there could help her right away.
On 2026-09-18 at 8:30 AM she replied on Roman's personal line anyway, because
that is where the conversation already was. She wrote that she was afraid her
son would be overwhelmed and crack. Nobody saw it for eight and a half hours,
because that line has no team behind it and Roman was out of office.

A redirect does not move a conversation. People reply where they are. So the
line needs a watcher rather than another instruction to the family.

WHAT THIS AGENT MAY SEE AND WHAT IT MAY SAY

This reads a personal phone. That is the whole design constraint, and every
other decision follows from it.

  - It classifies each inbound message as tutoring-related or not.
  - Tutoring-related: the message text goes to the right scheduler.
  - Anything else: the text is never logged, never summarised, never DMed,
    never written to HubSpot, and never stored in the audit trail. The audit
    row for a personal message records its id and the single word "personal".
  - When the classifier is unsure, the message is treated as PERSONAL. Silence
    about a tutoring text costs an hour of response time. Relaying a private
    message cannot be undone.

WHAT IT NEVER DOES

Reply, on any channel. Roman's rule from 2026-09-09: watch means read and
report. Relaying, posting and texting each need a go, and this agent has a go
for exactly one thing, telling a scheduler.

WHEN IT SPEAKS

Not immediately. Roman answers his own phone, and a scheduler DM thirty seconds
after he has already replied is noise. A message is surfaced only when nothing
has gone OUT from that line after it and it is older than `grace_minutes`.
Outbound means text or call, so picking up the phone counts as handling it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, justcall_client as jc, slack_client
from .business_hours import now_la
from .config import ANTHROPIC_API_KEY, DRY_RUN, cfg, staff
from .router import scheduler_for_last_name

SYSTEM = """You read a single inbound SMS sent to the personal mobile of the owner of a
tutoring company. Your only job is to decide whether it concerns the tutoring business.

TUTORING-RELATED means the message is about: a student's lessons, schedule, tutor,
homework or progress; a payment, invoice or purchase order for tutoring; a complaint or
praise about tutoring; a request to start, pause or stop tutoring; a referral of another
family; a school, teacher of record or education facilitator writing about a student.

NOT TUTORING-RELATED means anything else, including messages from friends and family,
personal appointments, deliveries, banks, politics, health, social plans, marketing,
one-time passcodes, and any message you cannot confidently place.

You are reading a private phone. A wrong "yes" shows a private message to an employee
and cannot be undone. A wrong "no" delays a reply. When the message is ambiguous, short,
context-free, or you are less than confident, answer no.

Return ONLY this JSON object and nothing else:
{"tutoring": true|false, "confidence": 0.0-1.0, "student": "first name or empty",
 "family_last_name": "surname or empty", "urgency": "now"|"today"|"normal",
 "reason": "one short clause, naming NO personal detail"}"""


def _digits(p) -> str:
    return jc.norm_number(p)


def parse_verdict(text: str) -> dict:
    """The model's JSON, validated. Anything malformed is treated as personal."""
    if not text or not text.strip():
        return {"tutoring": False, "confidence": 0.0, "reason": "empty response"}
    cleaned = re.sub(r"^```(?:json)?", "", text.strip()).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    a, b = cleaned.find("{"), cleaned.rfind("}")
    if a == -1 or b <= a:
        return {"tutoring": False, "confidence": 0.0, "reason": "no JSON in response"}
    try:
        obj = json.loads(cleaned[a:b + 1])
    except json.JSONDecodeError:
        return {"tutoring": False, "confidence": 0.0, "reason": "invalid JSON"}
    if not isinstance(obj, dict) or "tutoring" not in obj:
        return {"tutoring": False, "confidence": 0.0, "reason": "missing keys"}
    try:
        obj["confidence"] = float(obj.get("confidence") or 0.0)
    except (TypeError, ValueError):
        obj["confidence"] = 0.0
    obj["tutoring"] = bool(obj["tutoring"])
    return obj


def classify(body: str, client=None) -> dict:
    """Tutoring or personal. Any failure answers personal.

    The message body is the ONLY thing sent. No contact name, no history, no
    account context: the model does not need them to answer this question, and
    sending them would widen what leaves the phone for no gain.
    """
    conf = cfg().get("personal_line") or {}
    try:
        from anthropic import Anthropic
        client = client or Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=conf.get("model", "claude-opus-4-7"),
            max_tokens=int(conf.get("max_tokens", 400)),
            system=SYSTEM,
            messages=[{"role": "user", "content": body[:2000]}])
        text = "".join(b.text for b in msg.content
                       if getattr(b, "type", None) == "text")
        return parse_verdict(text)
    except Exception as e:  # noqa: BLE001
        # A classifier that cannot answer must not leak. Personal by default.
        return {"tutoring": False, "confidence": 0.0, "reason": f"classifier error: {e}"}


def _thread(index: dict, number: str) -> dict:
    return index.get(number) or {"texts": [], "calls": []}


def unhandled_inbound(thread: dict, line: str, grace_minutes: float,
                      now: datetime | None = None) -> list[dict]:
    """Inbound texts on THIS line with nothing outbound after them, past grace.

    Outbound counts calls as well as texts. Roman picking up the phone is him
    handling it, and a checker that reads only the text log called three
    phoned-back families neglected on 2026-09-15.
    """
    now = now or datetime.now(timezone.utc)
    line_d = _digits(line)
    texts = [t for t in thread.get("texts", []) if _digits(t.get("line")) == line_d]
    outs = [t.get("at", "") for t in texts
            if not str(t.get("direction", "")).startswith("in")]
    outs += [c.get("at", "") for c in thread.get("calls", [])
             if str(c.get("direction", "")).startswith("out")]
    newest_out = max(outs) if outs else ""
    cutoff = (now - timedelta(minutes=grace_minutes)).strftime("%Y-%m-%dT%H:%M:%S")
    return [t for t in texts
            if str(t.get("direction", "")).startswith("in")
            and t.get("at", "") > newest_out
            and t.get("at", "")[:19] <= cutoff]


def _contact_for(number: str) -> dict:
    """Whoever this number belongs to, via the calculated phone index.

    That index holds normalised digits. Guessing formatting variants of the raw
    `phone` property misses people, which is how a family went unmatched on
    2026-09-16.
    """
    for prop in ("hs_searchable_calculated_phone_number",
                 "hs_searchable_calculated_mobile_number"):
        try:
            res = hs._write("POST", "/crm/v3/objects/contacts/search", {
                "filterGroups": [{"filters": [
                    {"propertyName": prop, "operator": "EQ", "value": number}]}],
                "properties": ["firstname", "lastname", "student_last_name_if_diff_from_parent",
                               "a_persona"],
                "limit": 1})
        except Exception:  # noqa: BLE001
            continue
        hits = (res.get("results") or []) if isinstance(res, dict) else []
        if hits:
            return hits[0]
    return {}


def target_scheduler(verdict: dict, contact: dict) -> tuple[str, str]:
    """(role key, why). The student's surname picks the scheduler, same A-L /
    M-Z split every other engine uses. No surname means the fallback seat and
    the reason says so, rather than defaulting silently."""
    conf = cfg().get("personal_line") or {}
    p = (contact.get("properties") or {})
    last = (verdict.get("family_last_name")
            or p.get("student_last_name_if_diff_from_parent")
            or p.get("lastname") or "").strip()
    if not last:
        return conf.get("fallback_role", "charter_sales"), "no surname to split on"
    role, notes = scheduler_for_last_name(last)
    return role or conf.get("fallback_role", "charter_sales"), "; ".join(notes) or f"surname {last}"


def run(now: datetime | None = None) -> None:
    """`now` is injectable so the age a scheduler is told ("8.5h ago") can be
    asserted in a test rather than drifting with the clock."""
    conf = cfg().get("personal_line") or {}
    if not conf.get("enabled"):
        print("=== personal_line: disabled in config ===")
        return
    line = conf.get("line") or ""
    if not line:
        print("  no line configured — refusing to run")
        return
    print(f"=== personal line watch ({now_la().isoformat()}) "
          f"{'DRY RUN ' if DRY_RUN else ''}===")

    try:
        index = jc.index_by_number(int(conf.get("lookback_days", 2)))
    except jc.JustCallUnavailable as e:
        # An empty index makes every phone look silent, and silence is what
        # this agent acts on.
        print(f"  ⚠️  JustCall unavailable ({e}) — refusing to run blind")
        return

    grace = float(conf.get("grace_minutes", 20))
    cap = int(conf.get("max_relays_per_run", 8))
    seen = audit.personal_line_seen()
    now = now or datetime.now(timezone.utc)

    tutoring, personal, relayed = 0, 0, 0
    for number, thread in index.items():
        for msg in unhandled_inbound(thread, line, grace, now):
            mid = f"{number}:{msg.get('at', '')}"
            if mid in seen:
                continue
            body = (msg.get("text") or "").strip()
            if not body:
                continue
            verdict = classify(body)
            min_conf = float(conf.get("min_confidence", 0.7))
            if not verdict.get("tutoring") or verdict["confidence"] < min_conf:
                personal += 1
                # The ONLY thing recorded about a personal message is that one
                # existed and was left alone. No text, no number, no sender.
                if not DRY_RUN:
                    audit.append({"message_id": f"pl:{mid}", "source": "personal_line",
                                  "action_taken": "personal_line_ignored"})
                continue

            tutoring += 1
            if relayed >= cap:
                print(f"  cap of {cap} reached; the rest wait for the next run")
                break
            contact = _contact_for(number)
            role, why = target_scheduler(verdict, contact)
            cp = contact.get("properties") or {}
            who = f"{cp.get('firstname') or ''} {cp.get('lastname') or ''}".strip()
            sid = (staff(role) or {}).get("slack_user_id")
            waited = ""
            try:
                sent_at = datetime.strptime(msg["at"][:19], "%Y-%m-%dT%H:%M:%S")
                waited = f"{(now.replace(tzinfo=None) - sent_at).total_seconds() / 3600:.1f}h ago"
            except (KeyError, ValueError):
                waited = "time unknown"

            student = (verdict.get("student") or "").strip()
            header = f"*From:* {who or number}"
            if student:
                header += f" · student {student}"
            text = (f"📱 Tutoring text on Roman's personal line, {waited}, no reply yet.\n"
                    f"{header}\n"
                    f"*They said:* {body[:600]}\n"
                    f"_Routed to you because: {why}. He has not replied. "
                    f"Answer from the support line._")
            if sid and not DRY_RUN:
                slack_client.dm(sid, text)
            elif not sid:
                print(f"  ⚠️  role {role} has no slack_user_id — nothing sent")
            if not DRY_RUN:
                audit.append({"message_id": f"pl:{mid}", "source": "personal_line",
                              "action_taken": "personal_line_relayed",
                              "owner": role, "confidence": verdict.get("confidence"),
                              "urgency": verdict.get("urgency"),
                              "contact": who or None})
            relayed += 1
            print(f"  → {role}: {who or number} ({waited})")

    print(f"=== {tutoring} tutoring, {personal} personal (left alone), "
          f"{relayed} relayed ===")


if __name__ == "__main__":
    run()
