#!/usr/bin/env python3
"""
ops/lead_agent — the reasoning lead engine.

Not a workflow with templated emails. For each active lead it assembles a
dossier of everything we know, asks Claude what the ONE next right thing is,
and writes the message for THAT family. Then Python decides whether it is
allowed to happen.

    Claude DECIDES.  presend GATES.  this code EXECUTES.

Claude never holds the send button. It returns a decision object; the
guardrails in `enforce()` run where no prompt can talk past them; the pre-send
gate (email/src/presend.py) runs after that; only then does anything leave.

Why this shape, and not a smarter prompt with tools: the failure we are
replacing (HubSpot flow 50818589, seven defects in
docs/investigations/2026-09-14-online-lead-intake.md) was a machine making
claims about reality it had no evidence for. It emailed families "we could not
leave a voicemail" from a branch default with no call placed, and stamped
ATTEMPTED_TO_CONTACT on a timer. A model with a send tool can make the same
class of mistake more fluently. So every status the agent writes must have its
evidence present in the dossier (`status_evidence` in config.yml), checked in
Python, and a decision it cannot prove is downgraded to a task for a human.

Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.
Before contacting a family, teacher, or tutor, read knowledge/journey/README.md
and pass knowledge/journey/00-pre-send-checklist.md. Act only on stages marked
REVIEWED.

Usage:
  python3 lead_agent.py [--live] [--contact ID] [--since ISO] [--report-json P]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "email"))

PT = ZoneInfo("America/Los_Angeles")
STATE = HERE / "state"
CURSOR = STATE / "cursor.json"

ACTIONS = ("send_sms", "send_email", "set_status", "create_task", "wait", "handoff", "nothing")

DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["read", "signal", "action", "why", "confidence"],
    "properties": {
        "read": {"type": "string", "description": "What is true about this lead right now."},
        "signal": {"type": "string", "description": "What changed since our last touch. 'nothing' is a valid answer."},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "sms_body": {"type": "string"},
        "email_subject": {"type": "string"},
        "email_body": {"type": "string"},
        "new_status": {"type": "string"},
        "status_evidence": {"type": "string", "description": "What in the dossier proves the new status."},
        "task_subject": {"type": "string"},
        "task_body": {"type": "string"},
        "handoff_seat": {"type": "string"},
        "wait_hours": {"type": "number"},
        "why": {"type": "string", "description": "One line a human will read in an audit."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}


def cfg() -> dict:
    return yaml.safe_load((HERE / "config.yml").read_text()) or {}


# ── pure core (unit-tested, no network) ────────────────────────────
def scrub(text: str) -> str:
    """The outbound style rule, applied in code because a prompt is a request
    and this is a rule (CLAUDE.md, Roman 2026-08-24, locked)."""
    return (text or "").replace("—", ", ").replace("–", ", ").replace("--", ", ")


def in_window(when, c: dict) -> bool:
    w = c.get("work_window") or {}
    local = when.astimezone(PT)
    return int(w.get("open_hour") or 8) <= local.hour < int(w.get("close_hour") or 18)


def evidence_ok(status: str, dossier: dict, c: dict) -> tuple[bool, str]:
    """Does the dossier actually prove this status? The whole point of the
    engine. Returns (ok, why_not)."""
    if status in (c.get("status_forbidden") or []):
        return False, f"{status} is never an agent decision"
    need = (c.get("status_evidence") or {}).get(status)
    if need is None:
        return True, ""                       # not an evidence-gated status
    if need == "human_only":
        return False, f"{status} is human only"
    have = dossier.get("evidence") or {}
    if int(have.get(need) or 0) > 0:
        return True, ""
    return False, f"{status} needs {need} on the record and the dossier shows none"


def enforce(decision: dict, dossier: dict, c: dict, now=None) -> tuple[dict, list[str]]:
    """Guardrails Claude cannot argue with. Returns the (possibly downgraded)
    decision and the list of reasons it was changed.

    A blocked send never becomes silence: it is downgraded to a task so a human
    sees the lead and the drafted copy. Silence is how the old flow lost people.
    """
    now = now or datetime.now(timezone.utc)
    notes: list[str] = []
    d = dict(decision)
    action = d.get("action")

    if action not in ACTIONS:
        return {**d, "action": "create_task", "task_subject": "Lead needs a look",
                "task_body": f"Agent returned an unknown action {action!r}."}, [f"unknown action {action!r}"]

    outbound = action in ("send_sms", "send_email")

    # Confidence: anything short of `high` is a human's call, not a send.
    if outbound and d.get("confidence") != (c.get("min_confidence_to_send") or "high"):
        notes.append(f"confidence {d.get('confidence')!r} is below the send bar")
        action = "create_task"

    # Frequency, counted from the record rather than trusted from the prompt.
    if outbound:
        if int((dossier.get("touches") or {}).get("outbound_today") or 0) >= \
                int(c.get("max_outbound_per_lead_per_day") or 1):
            notes.append("already contacted today")
            action = "create_task"
        gap = float(c.get("min_hours_between_touches") or 12)
        last = (dossier.get("touches") or {}).get("hours_since_last_outbound")
        if last is not None and float(last) < gap:
            notes.append(f"last outbound was {float(last):.1f}h ago, inside the {gap:g}h gap")
            action = "create_task"
        if not in_window(now, c):
            notes.append("outside the seat's working window")
            action = "create_task"

    # Status: only what the dossier proves.
    if action == "set_status":
        ok, why = evidence_ok(d.get("new_status") or "", dossier, c)
        if not ok:
            notes.append(why)
            action = "create_task"

    # Copy rules, applied to the text itself.
    if action == "send_sms":
        body = scrub(d.get("sms_body") or "")
        if not body.strip():
            notes.append("empty sms body")
            action = "create_task"
        elif not dossier.get("in_thread") and "stop" not in body.lower():
            body = body.rstrip() + " Reply STOP to opt out."
            notes.append("added the missing STOP line")
        d["sms_body"] = body
    if action == "send_email":
        d["email_body"] = scrub(d.get("email_body") or "")
        d["email_subject"] = scrub(d.get("email_subject") or "")
        if not d["email_body"].strip():
            notes.append("empty email body")
            action = "create_task"

    # Draft mode: the journey stages are not signed, so nothing reaches a human
    # being. The decision still stands and becomes a draft on the seat's task.
    if outbound and not c.get("send") and action in ("send_sms", "send_email"):
        notes.append("send is off (knowledge/journey 00 + 01 not REVIEWED): drafted instead")
        d["drafted_channel"] = action
        action = "create_task"

    d["action"] = action
    return d, notes


def task_from(decision: dict, dossier: dict, notes: list[str]) -> tuple[str, str]:
    """The task a human opens. Everything needed to act, including the agent's
    reasoning and why it was not allowed to act itself."""
    p = dossier.get("contact") or {}
    name = " ".join(x for x in (p.get("firstname"), p.get("lastname")) if x) or p.get("email") or "?"
    subject = decision.get("task_subject") or f"Lead: {name}"
    lines = [f"WHY NOW: {decision.get('why', '')}", "",
             f"WHAT THE AGENT SEES: {decision.get('read', '')}",
             f"WHAT CHANGED: {decision.get('signal', '')}",
             f"CONFIDENCE: {decision.get('confidence', '?')}"]
    if dossier.get("returning"):
        lines += ["", dossier["returning"]]
    if decision.get("drafted_channel"):
        lines += ["", f"DRAFT {decision['drafted_channel'].replace('send_', '').upper()} "
                      f"(review, then send from the seat's own line):"]
        lines.append(decision.get("sms_body") or
                     f"Subject: {decision.get('email_subject','')}\n\n{decision.get('email_body','')}")
    if decision.get("new_status"):
        lines += ["", f"PROPOSED STATUS: {decision['new_status']} "
                      f"({decision.get('status_evidence', 'no evidence given')})"]
    if decision.get("task_body"):
        lines += ["", decision["task_body"]]
    if notes:
        lines += ["", "HELD BACK BY:"] + [f"  - {n}" for n in notes]
    gate = dossier.get("gate") or {}
    if gate:
        lines += ["", f"PRE-SEND: {gate.get('verdict', '?').upper()}"] + \
                 [f"  - {r}" for r in (gate.get("reasons") or ["all checks clear"])]
    return subject, "\n".join(lines)


# ── the model call ─────────────────────────────────────────────────
def decide(dossier: dict, c: dict) -> dict:
    """Ask Claude for the one next right thing. Structured output, so the
    answer is a decision object and never prose we have to parse."""
    import anthropic
    from src.config import model_for                 # the one model policy

    client = anthropic.Anthropic(max_retries=3)
    system = (HERE / "prompts" / "decide.md").read_text()
    care = (ROOT / "ops" / "values" / "care-values.md").read_text()

    resp = client.messages.create(
        model=model_for(c.get("model_tier") or "customer_copy"),
        max_tokens=int(c.get("max_tokens") or 8000),
        thinking={"type": "adaptive"},
        output_config={"effort": c.get("effort") or "high",
                       "format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
        # Stable prefix first so it caches across every lead in the run; the
        # dossier is the only part that varies.
        system=[{"type": "text", "text": system + "\n\n# A+ CARE core values\n\n" + care,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(dossier, indent=1, default=str)}],
    )
    if resp.stop_reason == "refusal":
        return {"action": "create_task", "confidence": "low",
                "read": "model declined to decide", "signal": "",
                "task_subject": "Lead needs a human look",
                "why": f"model refusal: {getattr(resp.stop_details, 'category', '?')}"}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="write to HubSpot (default: plan only)")
    ap.add_argument("--contact", default="", help="one contact id")
    ap.add_argument("--since", default="", help="ISO cursor override")
    ap.add_argument("--report-json", default="")
    a = ap.parse_args()
    from runner import run  # noqa: E402  network half, kept out of the tested core
    run(live=a.live, only_contact=a.contact, since=a.since, report_path=a.report_json)


if __name__ == "__main__":
    main()
