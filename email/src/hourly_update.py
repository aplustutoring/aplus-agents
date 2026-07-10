"""Hourly launch-monitoring rollup, DM'd to a staffer during business hours.

Time-boxed: auto-stops after `hourly_update.until`. Shows what was triaged in the
last hour plus today's running totals. Scheduled hourly; a PT business-hours gate
keeps it to 9-6 PT Mon-Fri.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

from . import audit, slack_client
from .business_hours import LA, now_la
from .config import DRY_RUN, cfg
from .daily_summary import gather_today


def _window(now: datetime) -> tuple[datetime, str]:
    """At 9 AM, cover everything since the previous business-day close (overnight /
    weekend catch-up). Every other hour, just the last hour."""
    if now.hour == 9:
        d = now.date() - timedelta(days=1)
        while d.weekday() >= 5:          # walk back over the weekend to Friday
            d -= timedelta(days=1)
        return datetime.combine(d, time(18, 0), tzinfo=LA), "Since last close (overnight)"
    return now - timedelta(hours=1), "New this hour"


def recent_items(cutoff: datetime) -> list[str]:
    out = []
    for r in audit._iter_records():
        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LA)
        except ValueError:
            continue
        if d < cutoff:
            continue
        a = r.get("action_taken")
        if a == "ticket_created":
            out.append(f"{r.get('category')} → {r.get('owner') or 'unassigned'}")
            mv = (r.get("deal_moved") or {}).get("moves", [])
            if mv:
                out.append(f"   💸 {len(mv)} deal(s) auto-moved → Stopped")
        elif a == "junk_archived":
            out.append("junk → archived")
        elif a == "escalation":
            out.append(f"⚠️ escalation L{r.get('breach_level')} ({r.get('category')})")
    return out


def run() -> None:
    hu = cfg().get("hourly_update", {})
    if not hu.get("enabled"):
        return
    now = now_la()
    force = DRY_RUN or os.getenv("FORCE_RUN", "").lower() == "true"
    until = hu.get("until")
    if until and now.date() > date.fromisoformat(until) and not force:
        print(f"hourly update window ended ({until}); skipping")
        return
    if not force and hu.get("business_hours_only", True) and (now.weekday() >= 5 or not (9 <= now.hour < 18)):
        print(f"outside business hours (PT {now.hour}); skipping")
        return

    cutoff, label = _window(now)
    items = recent_items(cutoff)
    m = gather_today()
    lines = "\n".join(f"  • {x}" for x in items) if items else "  • (nothing new)"
    text = (
        f"*⏱ Check-in — {now.strftime('%-I %p')} PT*\n"
        f"{label}:\n{lines}\n"
        f"_Today so far: {m['total']} triaged · {m['junk']} junk · {m['escalations']} escalations_"
    )
    print(text)
    rid = cfg()["staff"].get(hu.get("recipient", "roman"), {}).get("slack_user_id")
    slack_client.dm(rid, text)
    print("=== hourly update sent ===")


if __name__ == "__main__":
    run()
