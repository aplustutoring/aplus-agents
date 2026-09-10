#!/usr/bin/env python3
"""
Cron-starvation watchdog — GitHub's schedule trigger is best-effort and some
days it barely fires (2026-08-27: the PO inbox's 9 AM PT window opened and NO
scheduled run fired for 8.5 hours; a Lake View PO sat unread all morning).

Piggybacks on the fleet retry sweeper's cadence (fleet-retry.yml runs this
right after sweep.py): for each watched scheduled workflow, if its newest run
is older than its staleness threshold DURING PT BUSINESS HOURS, the watchdog

  1. DISPATCHES a catch-up run (workflow_dispatch — dispatches fire
     immediately even when the schedule trigger is starving), carrying the
     per-workflow inputs in DISPATCH_INPUTS so the run is a REAL run (a bare
     dispatch takes every input's default, and a default of dry_run=true
     turns the catch-up into a no-op — see DISPATCH_INPUTS), and
  2. posts ONE Slack alert per stale episode to the feedback channel,
     pinging the approvers (same targets as the retry sweeper).

Before dispatching, dispatch_trap() reads the workflow file from the checkout
and refuses any dispatch that would silently do nothing (a no-op switch
defaulting to true with no override here, an input GitHub would reject, no
workflow_dispatch trigger at all). ops/fleet-health/tests pins the same check
so a new WATCHED entry with the trap fails in review, not in production.

Known limit: this rides the same scheduler it watches — a TOTAL cron outage
starves it too. The local heartbeat (scripts/po-inbox-heartbeat.sh, launchd
on Roman's Mac) covers that layer for the PO inbox.

Env: GH_TOKEN (actions:write), SLACK_BOT_TOKEN. --dry-run prints only.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "retry"))
from sweep import alert_targets, gh, post_slack  # noqa: E402 — shared helpers

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("cron-watchdog")

REPO = os.getenv("GITHUB_REPOSITORY", "aplustutoring/aplus-agents")
WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "..", ".github", "workflows")

# workflow file → minutes of business-hours silence that counts as stale.
# Thresholds are ~4x the intended cadence, so normal GitHub cron jitter
# (which is chronic) never alerts — only real starvation does.
WATCHED = {
    "email-po-inbox.yml": 60,     # 15-min cadence; a PO sitting an hour is real money
    "email-triage.yml": 90,
    "email-deal-sync.yml": 60,
    # Since #146 (2026-09-04) the call agent has NO business-hours cron: the
    # JustCall webhook relay is meant to dispatch it per call and the 00:30
    # UTC digest is the backstop. Its age at the first business-hours sweep is
    # therefore ~15 h, always past the once-window, so this entry never posts
    # a "starvation" alert — it silently dispatches a live poll about hourly
    # (Roman 2026-09-04: cron stays only for digests/sweeps + demoted
    # safety-net polls). Alerts fire only if that dispatch fails.
    "call-agent.yml": 60,
}

# Inputs the catch-up dispatch carries, per workflow. A dispatch with no
# inputs takes every workflow_dispatch input's DEFAULT, and call-agent.yml
# defaults dry_run to true (a human clicking "Run workflow" should get a safe
# run). From 2026-09-04 (#146 removed its poll crons) to 2026-09-09 every
# catch-up this watchdog dispatched for the call agent was therefore a DRY
# RUN — fetched, summarized, persisted nothing — while the log said "catch-up
# dispatch ok" (runs 34409712823, 34265433047, 34150770451). These inputs are
# exactly what the JustCall webhook relay sends
# (ops/call_agent/webhook-relay/worker.js): live run, digest entries held for
# the 00:30 UTC flush. CALL_AGENT_LIVE still gates real writes inside the
# workflow. Values are strings — the dispatch API takes booleans as "true"/"false".
DISPATCH_INPUTS = {
    "call-agent.yml": {"dry_run": "false", "no_digest": "true"},
}

# workflow_dispatch inputs that, defaulting to true, make a bare dispatch a no-op.
NOOP_SWITCHES = {"dry_run", "dry-run", "check_only", "check-only"}

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


def declared_dispatch_inputs(workflow_file: str, workflows_dir: str = WORKFLOWS_DIR):
    """{input name: spec} under on.workflow_dispatch.inputs, or None when the
    workflow has no workflow_dispatch trigger."""
    with open(os.path.join(workflows_dir, workflow_file)) as f:
        doc = yaml.safe_load(f) or {}
    # PyYAML reads the bare key `on` as boolean True.
    triggers = doc.get("on", doc.get(True)) or {}
    if "workflow_dispatch" not in triggers:
        return None
    return (triggers.get("workflow_dispatch") or {}).get("inputs") or {}


def dispatch_trap(workflow_file: str, workflows_dir: str = WORKFLOWS_DIR):
    """Why a catch-up dispatch of this workflow would silently do nothing, or
    None when it is safe. Read from the workflow file in the checkout."""
    try:
        inputs = declared_dispatch_inputs(workflow_file, workflows_dir)
    except FileNotFoundError:
        return f"{workflow_file} is not in the checkout"
    if inputs is None:
        return "no workflow_dispatch trigger — GitHub rejects the dispatch"
    sent = DISPATCH_INPUTS.get(workflow_file, {})
    for name, spec in inputs.items():
        default = (spec or {}).get("default")
        if name in NOOP_SWITCHES and str(default).lower() == "true" and name not in sent:
            return (f"`{name}` defaults to true and DISPATCH_INPUTS sends no override "
                    f"— the catch-up would be a no-op")
    undeclared = sorted(set(sent) - set(inputs))
    if undeclared:
        return (f"DISPATCH_INPUTS sends {undeclared}, not declared by the workflow "
                f"— GitHub rejects the dispatch (422)")
    return None


def dispatch_body(workflow_file: str) -> dict:
    body = {"ref": "main"}
    inputs = DISPATCH_INPUTS.get(workflow_file)
    if inputs:
        body["inputs"] = dict(inputs)
    return body


def describe_inputs(workflow_file: str) -> str:
    inputs = DISPATCH_INPUTS.get(workflow_file)
    if not inputs:
        return ""
    return " with inputs " + ", ".join(f"{k}={v}" for k, v in inputs.items())


def dispatch(workflow_file: str) -> bool:
    """POST the catch-up workflow_dispatch. True on 204."""
    trap = dispatch_trap(workflow_file)
    if trap:
        log.error(f"{workflow_file}: catch-up dispatch REFUSED — {trap}")
        return False
    try:
        # sweep.gh() never sends a JSON body; dispatch requires {"ref"} — go direct
        r = requests.post(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow_file}/dispatches",
            headers={"Authorization": f"Bearer {os.getenv('GH_TOKEN', '') or os.getenv('GITHUB_TOKEN', '')}",
                     "Accept": "application/vnd.github+json"},
            json=dispatch_body(workflow_file), timeout=30)
    except Exception as e:  # noqa: BLE001
        log.warning(f"{workflow_file}: dispatch failed: {e}")
        return False
    ok = r.status_code == 204
    log.info(f"{workflow_file}: catch-up dispatch{describe_inputs(workflow_file)} "
             f"{'ok' if ok else f'FAILED ({r.status_code}: {r.text[:200]})'}")
    return ok


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
            trap = dispatch_trap(wf)
            log.info(f"{wf}: would dispatch {dispatch_body(wf)}"
                     + (f" — but REFUSED: {trap}" if trap else ""))
            continue
        dispatched = dispatch(wf)
        if fresh_cross or not dispatched:
            text = (f"⏰ Cron starvation: `{wf}` hadn't run in {age:.0f} min during "
                    f"business hours (threshold {threshold}). "
                    + (f"A catch-up run was dispatched{describe_inputs(wf)}." if dispatched
                       else "Catch-up dispatch FAILED (see the sweeper log) — run it manually.")
                    + (f" {mentions}" if mentions else ""))
            try:
                post_slack(channel, text)
            except Exception as e:  # noqa: BLE001
                log.warning(f"slack alert failed: {e}")


if __name__ == "__main__":
    main()
