"""The agent's own append-only state (agents/cohort_intake/state/audit.jsonl).

Why not the shared email/state/audit_log.jsonl: writing there forced this
workflow into the `aplus-email-state` concurrency group, and on 2026-09-16
GitHub cancelled the group-3 execute while it waited behind two relay-fired
deal-sync runs (a newer pending run in a group evicts the older one). Own
file, own group, no queue. The shared log is still READ (refresh: deal_sync
and sms markers) and, for idempotency keys written before this change, also
consulted by already_processed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ._bootstrap import DRY_RUN, audit as shared_audit

STATE_DIR = Path(__file__).resolve().parent / "state"
LOG = STATE_DIR / "audit.jsonl"


def append(record: dict) -> None:
    rec = dict(record)
    rec.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    rec.setdefault("source", "cohort_intake")
    if DRY_RUN:
        print(f"[DRY_RUN] cohort state << {json.dumps(rec)[:300]}")
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def _iter_records():
    if not LOG.exists():
        return
    with open(LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def already_processed(key: str) -> bool:
    for r in _iter_records():
        if r.get("message_id") == key:
            return True
    return shared_audit.already_processed(key)   # keys written before the split
