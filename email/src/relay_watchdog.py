"""Relay watchdog — the doorbell must never die silently again.

The path is: HubSpot deal created / stage changed → `[Agent] Doorbell`
workflow → deal-sync-relay worker → workflow_dispatch → this run, about a
minute after the deal exists. The Zapier zap that used to own new deals died
on 2026-09-04 and nobody knew for five days; the private-app webhook that was
supposed to feed the relay was never configured and nobody knew for a week.
Both failures look identical from inside deal_sync: a CRON run finds a new
deal that is already old.

So that is the tripwire. On a scheduled (cron) run, any new deal whose
createdate is more than `max_lag_minutes` old means no event-driven run
handled it → one DM to `notify` naming the deals, once per deal (audit
`relay-miss:{id}`). Dispatch-triggered runs never fire it (they ARE the
relay working). Local runs (no GITHUB_EVENT_NAME) never fire it either.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from . import audit, slack_client
from .config import cfg, staff


def _age_minutes(createdate_iso: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    cd = datetime.fromisoformat(createdate_iso.replace("Z", "+00:00"))
    return (now - cd).total_seconds() / 60


def check(deals: list[dict], event_name: str | None = None,
          now: datetime | None = None) -> list[dict]:
    """Return the deals the relay missed (and DM about them). Pure enough to test:
    `event_name` defaults to GITHUB_EVENT_NAME; only 'schedule' runs count."""
    rw = cfg().get("relay_watchdog") or {}
    if not rw.get("enabled"):
        return []
    event = event_name if event_name is not None else os.environ.get("GITHUB_EVENT_NAME", "")
    if event != "schedule":
        return []
    max_lag = float(rw.get("max_lag_minutes", 10))
    # A deal deal_sync already touched (synced, deferred, errored) was handled by
    # SOME run; it is only in this window because the cursor is held behind an
    # error. Hazel Barnett, 2026-09-10: the doorbell was fine, the DM was false.
    handled = set()
    for r in audit._iter_records():
        if r.get("source") != "deal_sync":
            continue
        mid = str(r.get("message_id") or "")
        if r.get("deal_id"):
            handled.add(str(r["deal_id"]))
        if ":deal:" in mid:
            handled.add(mid.rsplit(":", 1)[1])
    missed = []
    for d in deals:
        cd = (d.get("properties") or {}).get("createdate")
        if not cd:
            continue
        key = f"relay-miss:{d['id']}"
        if audit.already_processed(key) or str(d["id"]) in handled:
            continue
        age = _age_minutes(cd, now)
        if age < max_lag:
            continue
        missed.append({**d, "_age_min": round(age)})
    if not missed:
        return []
    target = staff(rw.get("notify", "visionary"))
    lines = [f"• {m['properties'].get('dealname', m['id'])} — created {m['_age_min']} min ago"
             for m in missed]
    text = ("🔕 *deal-sync relay watchdog*: the cron backstop just picked up "
            f"{len(missed)} new deal(s) no event-driven run had handled. The doorbell "
            "(HubSpot workflow → deal-sync-relay → workflow_dispatch) is not ringing.\n"
            + "\n".join(lines)
            + "\nCheck: HubSpot workflow \"[Agent] Doorbell\" enabled; "
              "`wrangler tail deal-sync-relay`; the worker's GITHUB_TOKEN secret.")
    slack_client.dm(target["slack_user_id"], text)
    for m in missed:
        audit.append({"message_id": f"relay-miss:{m['id']}", "source": "relay_watchdog",
                      "deal_id": m["id"], "deal_name": m["properties"].get("dealname"),
                      "age_minutes": m["_age_min"], "action_taken": "relay_miss_flagged"})
    return missed
