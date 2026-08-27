#!/usr/bin/env python3
"""
Cron-starvation watchdog — GitHub's schedule trigger is best-effort and some
days it barely fires (2026-08-27: the PO inbox's 9 AM PT window opened and NO
scheduled run fired for 8.5 hours; a Lake View PO sat unread all morning).

Piggybacks on the fleet retry sweeper's cadence (fleet-retry.yml runs this
right after sweep.py): for each watched scheduled workflow, if its newest run
is older than its staleness threshold DURING PT BUSINESS HOURS, the watchdog

  1. DISPATCHES a catch-up run (workflow_dispatch — dispatches fire
     immediately even when the schedule trigger is starving), and
  2. posts ONE Slack alert per stale episode to the feedback channel,
     pinging the approvers (same targets as the retry sweeper).

Known limit: this rides the same scheduler it watches — a TOTAL cron outage
starves it too. The local heartbeat (scripts/po-inbox-heartbeat.sh, launchd
on Roman's Mac) covers that layer for the PO inbox.

Env: GH_TOKEN (actions:write), SLACK_BOT_TOKEN. --dry-run prints only.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "retry"))
from sweep import alert_targets, gh, post_slack  # noqa: E402 — shared helpers

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("cron-watchdog")

REPO = os.getenv("GITHUB_REPOSITORY", "aplustutoring/aplus-agents")

# workflow file → minutes of business-hours silence that counts as stale.
# Thresholds are ~4x the intended cadence, so normal GitHub cron jitter
# (which is chronic) never alerts — only real starvation does.
WATCHED = {
    "email-po-inbox.yml": 60,     # 15-min cadence; a PO sitting an hour is real money
    "email-triage.yml": 90,
    "email-deal-sync.yml": 60,
    "call-agent.yml": 60,
}
# One sweep interval (fleet-retry runs at :07/:27/:47) — alert only when the
# staleness FIRST crosses the threshold inside this window, so each episode
# pings roughly once instead of every 20 minutes forever.
ALERT_ONCE_WINDOW_MIN = 25

BUSINESS_TZ = ZoneInfo("America/Los_Angeles")
BUSINESS_START, BUSINESS_END = 9, 16   # PT hours; weekdays only


def in_business_hours(now_utc: datetime) -> bool:
    local = now_utc.astimezone(BUSINESS_TZ)
    return local.weekday() < 5 and BUSINESS_START <= local.hour < BUSINESS_END


def newest_run_age_min(workflow_file: str, now_utc: datetime):
    """Minutes since the newest run (any status/trigger), or None if none."""
    data = gh("GET", f"/repos/{REPO}/actions/workflows/{workflow_file}/runs",
              params={"per_page": 1})
    runs = (data or {}).get("workflow_runs") or []
    if not runs:
        return None
    created = datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))
    return (now_utc - created).total_seconds() / 60


def main():
    dry = "--dry-run" in sys.argv
    now = datetime.now(timezone.utc)
    if not in_business_hours(now):
        log.info("outside PT business hours — nothing to watch")
        return
    channel, mentions = alert_targets()
    for wf, threshold in WATCHED.items():
        age = newest_run_age_min(wf, now)
        if age is None:
            log.info(f"{wf}: no runs found — skipping")
            continue
        if age <= threshold:
            log.info(f"{wf}: last run {age:.0f} min ago (ok, threshold {threshold})")
            continue
        fresh_cross = age <= threshold + ALERT_ONCE_WINDOW_MIN
        log.info(f"{wf}: STALE — {age:.0f} min since last run (threshold {threshold})"
                 f"{' [first crossing: alerting]' if fresh_cross else ' [already alerted]'}")
        if dry:
            continue
        try:
            # sweep.gh() never sends a JSON body; dispatch requires {"ref"} — go direct
            import requests
            r = requests.post(
                f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches",
                headers={"Authorization": f"Bearer {os.getenv('GH_TOKEN', '') or os.getenv('GITHUB_TOKEN', '')}",
                         "Accept": "application/vnd.github+json"},
                json={"ref": "main"}, timeout=30)
            dispatched = r.status_code == 204
            log.info(f"{wf}: catch-up dispatch {'ok' if dispatched else f'FAILED ({r.status_code})'}")
        except Exception as e:  # noqa: BLE001
            dispatched = False
            log.warning(f"{wf}: dispatch failed: {e}")
        if fresh_cross or not dispatched:
            text = (f"⏰ Cron starvation: `{wf}` hadn't run in {age:.0f} min during "
                    f"business hours (threshold {threshold}). "
                    + ("A catch-up run was dispatched." if dispatched
                       else "Catch-up dispatch FAILED — run it manually.")
                    + (f" {mentions}" if mentions else ""))
            try:
                post_slack(channel, text)
            except Exception as e:  # noqa: BLE001
                log.warning(f"slack alert failed: {e}")


if __name__ == "__main__":
    main()
