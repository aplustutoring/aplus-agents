"""Inbound messages that bear on work already open.

Two things families do that our systems currently do not hear.

**They answer the question a task is waiting on.** On 2026-09-18 Ashley Clay
texted that her school was approving and would send the purchase order to us
directly. The task "PO request: Ashley Clay - Trace" was due that same day and
its body still read "Awaiting email confirmation from EF." The answer had
arrived; the task that was waiting for it never heard. Whoever opened it would
have seen a question the family had already answered.

**They chase us.** On 2026-09-13 Jeff Werner sent his daughter's practice test
results. The reply task was marked COMPLETED on 9/15 with no reply ever sent, and
the escalation ladder had already spent all three of its levels on the Monday,
two of them inside the same minute. Jeff wrote again on 9/15 and again on 9/17.
Triage read both, scored them 0.30 and 0.52 confidence, and did nothing, because
a message that says "just following up" carries no new information. That reading
is backwards. A customer repeating themselves is the highest-signal event we get:
it means we are late, and they can tell. Five days and two chases later Roman
answered it himself.

So this sweep asks one question of every inbound message: does it bear on
something already open?

  answers an open ask   → stamp it on the task, move the due date out
  repeats an old ask    → re-arm, because nothing else will

What it never does: reply, close a ticket, or judge whether the family is right.
It puts what they said where the work lives and makes sure a human sees it.

Both legs are separately switchable in config. Either can be turned off without
touching the other.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import audit, hubspot_client as hs, justcall_client as jc, slack_client
from . import ticket_reasoner as tr
from .business_hours import now_la
from .config import DRY_RUN, cfg, staff

# A promise that a purchase order is coming. Deliberately literal: these are
# phrases a parent actually types, and a false positive here pushes a real
# chase a week into the future, which is the expensive direction to be wrong in.
PO_PROMISE = [
    "waiting for it to be approved",
    "waiting on approval",
    "waiting for approval",
    "pending approval",
    "submitted the request",
    "submitted it to the school",
    "they will send you the purchase order",
    "they will send you the po",
    "school will send",
    "sent it to my es",
    "sent it to the school",
    "requested the po",
    "requested the purchase order",
    "asked my teacher",
    "asked the school",
    "it's been approved",
    "it has been approved",
    "approved through the school",
]


def _ts(v):
    return tr._ts(v)


def _norm(p: str) -> str:
    return tr._norm_phone(p)


# ── leg 1: a chase ──────────────────────────────────────────────────────────
def last_outbound_at(ev: dict) -> datetime | None:
    """Newest thing that went OUT to this person, any channel.

    Not `notes_last_contacted`: that property moves on INBOUND activity too, so
    a ticket looks answered the instant the customer writes to it (2026-09-17,
    the checker that reported nobody waiting for fifteen hours).
    """
    stamps = []
    for m in ev.get("emails") or []:
        if m.get("direction") == "outbound":
            stamps.append(_ts(m.get("at")))
    for m in ev.get("sms") or []:
        if str(m.get("direction", "")).startswith("out"):
            stamps.append(_ts(m.get("at")))
    for c in ev.get("calls") or []:
        if str(c.get("direction", "")).startswith("out"):
            stamps.append(_ts(c.get("at")))
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def unanswered_inbound(ev: dict) -> list[dict]:
    """Inbound messages with nothing from us after them, oldest first."""
    cut = last_outbound_at(ev)
    out = []
    for m in (ev.get("emails") or []):
        if m.get("direction") != "inbound":
            continue
        t = _ts(m.get("at"))
        if t and (cut is None or t > cut):
            out.append({"at": t, "text": (m.get("text") or "")[:200], "channel": "email"})
    for m in (ev.get("sms") or []):
        if not str(m.get("direction", "")).startswith("in"):
            continue
        t = _ts(m.get("at"))
        if t and (cut is None or t > cut):
            out.append({"at": t, "text": (m.get("text") or "")[:200], "channel": "text"})
    return sorted(out, key=lambda x: x["at"])


def is_chase(msgs: list[dict], min_messages: int, after_hours: float,
             now: datetime | None = None) -> bool:
    """Two or more unanswered messages, the oldest of them older than the bar.

    Two, not one: a single unanswered message is a normal queue, and the SLA
    ladder already owns that. Two is the customer telling us we are late.
    """
    if len(msgs) < min_messages:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - msgs[0]["at"]).total_seconds() / 3600.0 >= after_hours


def stale_reply_tasks(contact_ids: list[str], since: datetime | None) -> list[dict]:
    """COMPLETED reply tasks that were closed while the customer was still waiting.

    This is the Werner failure exactly: the task said "Reply: scheduling" and it
    was marked done on 2026-09-15 with no reply ever sent. A completed task is
    normally proof work happened; here it is the opposite, and nothing checked.
    """
    out = []
    for cid in contact_ids:
        for t in _contact_tasks(cid):
            p = t.get("properties") or {}
            subj = (p.get("hs_task_subject") or "")
            if not subj.lower().startswith("reply:"):
                continue
            if p.get("hs_task_status") != "COMPLETED":
                continue
            done = _ts(p.get("hs_task_completion_date"))
            if since and done and done >= since:
                out.append(t)
    return out


def _contact_tasks(contact_id: str) -> list[dict]:
    try:
        assoc = hs._get(f"/crm/v4/objects/contacts/{contact_id}/associations/tasks")
    except Exception:  # noqa: BLE001
        return []
    ids = [str(r.get("toObjectId") or r.get("id")) for r in assoc.get("results", [])][-40:]
    if not ids:
        return []
    try:
        res = hs._write("POST", "/crm/v3/objects/tasks/batch/read",
                        {"inputs": [{"id": i} for i in ids],
                         "properties": ["hs_task_subject", "hs_task_status", "hs_timestamp",
                                        "hs_createdate", "hs_task_completion_date",
                                        "hs_task_body", "hubspot_owner_id"]})
    except Exception:  # noqa: BLE001
        return []
    return (res.get("results") or []) if isinstance(res, dict) else []


# ── leg 2: an answer ────────────────────────────────────────────────────────
def promise_in(text: str) -> str | None:
    """The phrase that makes this message a purchase-order promise, or None."""
    low = (text or "").lower()
    for phrase in PO_PROMISE:
        if phrase in low:
            return phrase
    return None


def _append_body(existing: str, line: str) -> str:
    existing = (existing or "").rstrip()
    return (existing + "\n\n" if existing else "") + line


# ── the sweep ───────────────────────────────────────────────────────────────
def _owner_key(owner_id) -> str:
    for key, s in (cfg().get("staff") or {}).items():
        if str(s.get("hubspot_owner_id") or "") == str(owner_id or ""):
            return key
    return ""


def run() -> None:
    conf = cfg().get("inbound_watch") or {}
    if not conf.get("enabled"):
        print("=== inbound_watch: disabled in config ===")
        return
    print(f"=== inbound watch ({now_la().isoformat()}) {'DRY RUN ' if DRY_RUN else ''}===")

    try:
        sms_index = jc.index_by_number(int(conf.get("sms_lookback_days", 30)))
    except jc.JustCallUnavailable as e:
        # An empty index would make every phone look silent, and silence is the
        # thing this sweep acts on. Refuse rather than act on a broken read.
        print(f"  ⚠️  JustCall unavailable ({e}) — refusing to run on a blind index")
        return

    lines: list[str] = []
    if conf.get("chase", {}).get("enabled"):
        lines += _chase_leg(conf, sms_index)
    if conf.get("answers", {}).get("enabled"):
        lines += _answer_leg(conf, sms_index)

    print(f"=== {len(lines)} item(s) ===")
    for line in lines:
        print(f"  {line}")
    chan = conf.get("digest_channel")
    if chan and lines and not DRY_RUN:
        slack_client.post_message(chan, "📨 *Inbound that bears on open work*\n" + "\n".join(lines))


def _chase_leg(conf: dict, sms_index: dict) -> list[str]:
    c = conf.get("chase") or {}
    min_msgs = int(c.get("min_messages", 2))
    after_h = float(c.get("after_hours", 4))
    repeat_h = float(c.get("repeat_every_hours", 24))
    cap = int(c.get("max_per_run", 10))
    now = datetime.now(timezone.utc)
    lines, acted = [], 0

    for ticket in hs.search_open_tickets():
        if acted >= cap:
            lines.append(f"• cap of {cap} reached, the rest wait for the next run")
            break
        tid = ticket["id"]
        prior = audit.last_inbound_chase(tid)
        if prior:
            p = _ts(prior)
            if p and (now - p).total_seconds() / 3600.0 < repeat_h:
                continue
        try:
            ev = tr.gather(ticket, sms_index)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  could not gather ticket {tid}: {e}")
            continue
        msgs = unanswered_inbound(ev)
        if not is_chase(msgs, min_msgs, after_h, now):
            continue

        owner_key = _owner_key(ev.get("owner_id"))
        lead_key = (cfg().get("escalation") or {}).get("level3")
        waited = (now - msgs[0]["at"]).total_seconds() / 3600.0
        last_words = msgs[-1]["text"]

        contacts = hs.get_ticket_contacts(tid)
        cids = [str(x.get("id")) for x in contacts if x.get("id")]
        reopened = stale_reply_tasks(cids, msgs[0]["at"])
        if reopened and not DRY_RUN:
            for t in reopened:
                try:
                    hs._write("PATCH", f"/crm/v3/objects/tasks/{t['id']}",
                              {"properties": {
                                  "hs_task_status": "NOT_STARTED",
                                  "hs_timestamp": hs._now_ms(),
                                  "hs_task_body": _append_body(
                                      (t.get("properties") or {}).get("hs_task_body") or "",
                                      f"[Agent] Reopened {now:%Y-%m-%d}. This was marked done "
                                      f"while the customer was still waiting, and they have "
                                      f"written {len(msgs)} more times since. Their last "
                                      f"message: \"{last_words}\"")}})
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️  could not reopen task {t['id']}: {e}")

        note = (f"[Agent] Customer chase — written by email/src/inbound_watch.py\n\n"
                f"{len(msgs)} message(s) from them with nothing from us since, oldest "
                f"{waited:.0f}h ago. Their last words: \"{last_words}\"\n\n"
                f"Re-armed because the SLA ladder pings each level once and then goes "
                f"quiet forever, so a customer repeating themselves currently reaches "
                f"nobody.")
        if not DRY_RUN:
            try:
                hs.add_ticket_note(tid, note)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  could not note ticket {tid}: {e}")
            for key in [k for k in (owner_key, lead_key) if k]:
                sid = (staff(key) or {}).get("slack_user_id")
                if sid:
                    slack_client.dm(sid, (
                        f"📣 *{ev.get('contact') or 'A customer'}* has written {len(msgs)} times "
                        f"with no reply from us, oldest {waited:.0f}h ago. "
                        f"\"{last_words}\"\n{hs.ticket_url(tid)}"))
            audit.append({"ticket_id": tid, "action_taken": "inbound_chase",
                          "messages": len(msgs), "waited_hours": round(waited, 1),
                          "tasks_reopened": [str(t["id"]) for t in reopened],
                          "owner": owner_key})
        lines.append(f"• *{ev.get('contact') or ev.get('subject')}* — {len(msgs)} unanswered, "
                     f"oldest {waited:.0f}h"
                     f"{f', reopened {len(reopened)} reply task(s)' if reopened else ''}")
        acted += 1
    return lines


def _answer_leg(conf: dict, sms_index: dict) -> list[str]:
    a = conf.get("answers") or {}
    prefixes = tuple(p.lower() for p in a.get("task_prefixes") or ["po request:"])
    push_days = int(a.get("promise_pushes_due_days", 7))
    cap = int(a.get("max_per_run", 25))
    lines, acted = [], 0

    try:
        open_tasks = hs._search_all("/crm/v3/objects/tasks/search", [
            {"propertyName": "hs_task_status", "operator": "NOT_IN",
             "values": ["COMPLETED", "DEFERRED"]}],
            ["hs_task_subject", "hs_task_body", "hs_timestamp", "hs_createdate",
             "hubspot_owner_id"])
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  could not list open tasks: {e}")
        return lines

    stamped = audit.inbound_answers_stamped()
    for t in open_tasks:
        if acted >= cap:
            break
        p = t.get("properties") or {}
        subj = (p.get("hs_task_subject") or "")
        if not subj.lower().startswith(prefixes):
            continue
        created = _ts(p.get("hs_createdate"))
        cids = _task_contact_ids(t["id"])
        hit = None
        for cid in cids:
            for phone in _contact_phones(cid):
                for m in (sms_index.get(phone) or {}).get("texts", []):
                    if not str(m.get("direction", "")).startswith("in"):
                        continue
                    when = _ts(m.get("at"))
                    if created and when and when < created:
                        continue
                    phrase = promise_in(m.get("text") or "")
                    if phrase:
                        hit = {"at": when, "text": m.get("text") or "", "phrase": phrase}
        if not hit:
            continue
        key = f"{t['id']}:{hit['at'].isoformat() if hit['at'] else ''}"
        if key in stamped:
            continue

        stamp = (f"[Agent] {hit['at']:%Y-%m-%d} the family answered this by text: "
                 f"\"{hit['text'][:200]}\"")
        new_due = (hit["at"] or datetime.now(timezone.utc)) + timedelta(days=push_days)
        if not DRY_RUN:
            try:
                hs._write("PATCH", f"/crm/v3/objects/tasks/{t['id']}", {"properties": {
                    "hs_task_body": _append_body(p.get("hs_task_body") or "", stamp),
                    "hs_timestamp": str(int(new_due.timestamp() * 1000))}})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  could not stamp task {t['id']}: {e}")
                continue
            audit.append({"task_id": str(t["id"]), "action_taken": "inbound_answer_stamped",
                          "answer_key": key, "phrase": hit["phrase"],
                          "new_due": new_due.isoformat()})
        lines.append(f"• *{subj.strip()}* — family answered by text, due date moved to "
                     f"{new_due:%b %-d}")
        acted += 1
    return lines


def _task_contact_ids(task_id: str) -> list[str]:
    try:
        assoc = hs._get(f"/crm/v4/objects/tasks/{task_id}/associations/contacts")
    except Exception:  # noqa: BLE001
        return []
    return [str(r.get("toObjectId") or r.get("id")) for r in assoc.get("results", [])][:5]


def _contact_phones(contact_id: str) -> list[str]:
    try:
        c = hs._get(f"/crm/v3/objects/contacts/{contact_id}",
                    {"properties": "phone,mobilephone"})
    except Exception:  # noqa: BLE001
        return []
    p = c.get("properties") or {}
    return [n for n in {_norm(p.get("phone")), _norm(p.get("mobilephone"))} if n]


if __name__ == "__main__":
    run()
