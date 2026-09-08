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


def append(record: dict) -> None:
    """Append one decision/action to the audit log (skipped in DRY_RUN)."""
    record.setdefault("timestamp", _now_iso())
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
