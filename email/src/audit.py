"""Append-only audit log + processing cursor + escalation bookkeeping.

state/audit_log.jsonl  — one JSON object per line, committed back by CI each run.
state/cursor.json      — last processed Conversations position.

Idempotency: a message_id already present in the audit log is never reprocessed,
even if the cursor is lost.
"""
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
