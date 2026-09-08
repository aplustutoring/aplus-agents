"""One-off backlog remediation (Roman 2026-08-28): close every open HubSpot
Task created before a cutoff date.

Context: when the task-completion sweep first read tasks back, the portal held
1,745 open tasks, most of them months-to-years old — dead backlog nobody will
ever action, drowning the live signal. Roman: "Let's close all tasks created
before 8/1/2026."

Marks them COMPLETED via the batch API (reversible: every closed id lands in
the audit log as `task_bulk_closed`, batched 100 ids per record). The weekly
scoreboard in task_sweep.py excludes these ids so ~1,500 bulk closures do not
read as "completed late" on the next Monday digest.

Usage (from email/):  DRY_RUN=true python -m src.close_stale_tasks 2026-08-01
"""
from __future__ import annotations

import sys
from datetime import datetime

from . import audit, hubspot_client as hs
from .business_hours import LA


def run(cutoff_date: str) -> None:
    cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d").replace(tzinfo=LA)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    print(f"=== Closing open tasks created before {cutoff.date()} PT ===")
    tasks = hs.search_open_tasks_created_before(cutoff_ms)
    print(f"  found {len(tasks)} open task(s) created before the cutoff")
    if not tasks:
        return
    by_owner: dict[str, int] = {}
    for t in tasks:
        oid = (t.get("properties") or {}).get("hubspot_owner_id") or "unassigned"
        by_owner[oid] = by_owner.get(oid, 0) + 1
    for oid, n in sorted(by_owner.items(), key=lambda kv: -kv[1]):
        print(f"    owner {oid}: {n}")
    ids = [t["id"] for t in tasks]
    hs.batch_complete_tasks(ids)
    for i in range(0, len(ids), 100):
        audit.append({"action_taken": "task_bulk_closed",
                      "cutoff": cutoff_date, "task_ids": ids[i:i + 100]})
    print(f"=== closed {len(ids)} task(s) ===")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "2026-08-01")
