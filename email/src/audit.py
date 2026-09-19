"""Append-only audit log + processing cursor + escalation bookkeeping.

state/audit_log.jsonl  — one JSON object per line, committed back by CI each run.
state/cursor.json      — last processed Conversations position.

Idempotency: a message_id already present in the audit log is never reprocessed,
even if the cursor is lost.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import DRY_RUN, ROOT

STATE_DIR = ROOT / "state"
AUDIT_LOG = STATE_DIR / "audit_log.jsonl"
CURSOR = STATE_DIR / "cursor.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Keys whose values are a person's phone or email. The log is committed to
# the repo and read by every collaborator; nothing in the fleet needs the raw
# value back out of it (dedupe keys on contact/deal ids), so it is masked at
# the one choke point every writer uses (Roman 2026-09-16, FERPA pass).
REDACT_KEYS = ("to", "welcome_email_to", "email", "phone", "mobilephone",
               "parent_email", "parent_phone", "to_email", "from_email")


def redact(value):
    """'+18183844845' → '…4845'; 'roman@wetutorathome.com' → 'r…@wetutorathome.com';
    lists element-wise; anything else unchanged. Idempotent."""
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str) or not value or value.startswith("…") or "…@" in value:
        return value
    s = value.strip()
    if "@" in s:
        local, _, domain = s.partition("@")
        return f"{local[:1]}…@{domain}"
    digits = "".join(ch for ch in s if ch.isdigit())
    if 10 <= len(digits) <= 15 and len(digits) >= len(s) * 0.5:   # a phone, not a date or an id
        return f"…{digits[-4:]}"
    return value


def append(record: dict) -> None:
    """Append one decision/action to the audit log (skipped in DRY_RUN)."""
    record.setdefault("timestamp", _now_iso())
    for k in REDACT_KEYS:
        if k in record:
            record[k] = redact(record[k])
    if DRY_RUN:
        print(f"[DRY_RUN] audit << {json.dumps(record, default=str)}")
        return
    STATE_DIR.mkdir(exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _iter_records():
    if not AUDIT_LOG.exists():
        return
    with open(AUDIT_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def processed_message_ids() -> set[str]:
    return {r["message_id"] for r in _iter_records() if r.get("message_id")}


def already_processed(message_id: str) -> bool:
    return message_id in processed_message_ids()


def last_reasoner_pester(ticket_id: str) -> str | None:
    """When the reasoning sweep last pestered about a ticket, so the ladder holds
    its cadence instead of re-DMing on every run."""
    latest = None
    for r in _iter_records():
        if r.get("ticket_id") == ticket_id and r.get("action_taken") == "reasoner_pester":
            ts = r.get("timestamp")
            if ts and (latest is None or str(ts) > str(latest)):
                latest = ts
    return latest


def last_aging_nag(ticket_id: str) -> str | None:
    """Timestamp of the most recent aging nag for a ticket, so the aging sweep
    can hold to its cadence instead of re-DMing on every hourly run."""
    latest = None
    for r in _iter_records():
        if r.get("ticket_id") == ticket_id and r.get("action_taken") == "aging_nag":
            ts = r.get("timestamp")
            if ts and (latest is None or str(ts) > str(latest)):
                latest = ts
    return latest


def last_task_nag(task_id: str) -> str | None:
    """Timestamp of the most recent overdue-task DM for a HubSpot task, so the
    task sweep holds its cadence instead of re-DMing the owner every morning."""
    latest = None
    for r in _iter_records():
        if r.get("task_id") == task_id and r.get("action_taken") == "task_nag":
            ts = r.get("timestamp")
            if ts and (latest is None or str(ts) > str(latest)):
                latest = ts
    return latest


def bulk_closed_task_ids() -> set[str]:
    """Task ids closed by backlog remediation (close_stale_tasks), so the weekly
    scoreboard never counts a bulk closure as a task someone completed late."""
    ids: set[str] = set()
    for r in _iter_records():
        if r.get("action_taken") == "task_bulk_closed":
            ids.update(str(t) for t in r.get("task_ids") or [])
    return ids


def escalation_levels_pinged(ticket_id: str) -> set[int]:
    """Breach levels already escalated for a ticket (so the sweep never re-pings)."""
    levels = set()
    for r in _iter_records():
        if r.get("ticket_id") == ticket_id and r.get("action_taken") == "escalation":
            lvl = r.get("breach_level")
            if lvl is not None:
                levels.add(int(lvl))
    return levels


# ── Cursor ────────────────────────────────────────────────────────
def read_cursor() -> dict:
    if CURSOR.exists():
        return json.loads(CURSOR.read_text())
    return {}


def write_cursor(data: dict) -> None:
    if DRY_RUN:
        print(f"[DRY_RUN] cursor << {json.dumps(data, default=str)}")
        return
    STATE_DIR.mkdir(exist_ok=True)
    CURSOR.write_text(json.dumps(data, indent=2, default=str))


def personal_line_seen() -> set[str]:
    """Message ids the personal-line watch has already judged, so a message is
    classified once and a scheduler is told about it once. Personal messages
    are in here too: that is the only trace they leave, and it is what stops
    them being re-read on every run."""
    ids: set[str] = set()
    for r in _iter_records():
        if r.get("source") == "personal_line" and r.get("message_id"):
            ids.add(str(r["message_id"])[3:])   # strip the "pl:" prefix
    return ids
