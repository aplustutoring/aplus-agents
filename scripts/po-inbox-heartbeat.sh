#!/bin/bash
# PO-inbox heartbeat — runs every 15 min from launchd on Roman's Mac
# (~/Library/LaunchAgents/com.aplus.po-inbox-heartbeat.plist, template in
# scripts/launchd/). GitHub's schedule trigger is best-effort and starves some
# days (2026-08-27: no scheduled run for 8.5 business hours while a PO sat
# unread); workflow_dispatch fires immediately, so this pings it from outside.
#
# Layered with ops/fleet-health/watchdog/cron_watchdog.py (in-repo, rides the
# retry sweeper): the watchdog self-heals most gaps, this covers TOTAL cron
# starvation — and it self-reports: a failed dispatch DMs the visionary role.
#
# Guards: weekday 07:45-19:15 PT only; skips when a run already happened in
# the last 12 min (no doubling when GitHub cron behaves).
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

REPO_DIR="$HOME/code/aplus-agents"
WORKFLOW="email-po-inbox.yml"
LOG="$HOME/Library/Logs/aplus-po-heartbeat.log"

note() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

# Business window (PT — launchd runs in local time; Roman's Mac is PT)
dow=$(date +%u)   # 1-7, Mon=1
hm=$(date +%H%M)
if [ "$dow" -gt 5 ] || [ "$hm" -lt 0745 ] || [ "$hm" -gt 1915 ]; then
    exit 0
fi

alert_roman() {
    # Slack DM to the visionary role on heartbeat failure — token from the
    # repo .env, role→person from email/config.yaml (roles, not names).
    python3 - "$1" <<'PY' 2>> "$LOG" || true
import os, sys, yaml, requests
repo = os.path.expanduser("~/code/aplus-agents")
tok = ""
for line in open(f"{repo}/.env"):
    if line.startswith("SLACK_BOT_TOKEN="):
        tok = line.split("=", 1)[1].strip()
c = yaml.safe_load(open(f"{repo}/email/config.yaml"))
who = c["staff"][c["roles"]["visionary"]]["slack_user_id"]
requests.post("https://slack.com/api/chat.postMessage",
              headers={"Authorization": f"Bearer {tok}"},
              json={"channel": who, "text": sys.argv[1]}, timeout=15)
PY
}

cd "$REPO_DIR" || { note "repo dir missing"; exit 1; }

# Skip if a run already happened recently (GitHub cron did its job)
last=$(gh run list --workflow="$WORKFLOW" --limit 1 --json createdAt \
         -q '.[0].createdAt' 2>> "$LOG")
if [ -n "${last:-}" ]; then
    last_epoch=$(date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "$last" +%s 2>/dev/null || echo 0)
    age=$(( $(date +%s) - last_epoch ))
    if [ "$age" -lt 720 ]; then
        exit 0   # a run within 12 min — nothing to do
    fi
fi

if gh workflow run "$WORKFLOW" 2>> "$LOG"; then
    note "dispatched $WORKFLOW (last run ${age:-?}s ago)"
else
    note "DISPATCH FAILED for $WORKFLOW"
    alert_roman "🫀 PO-inbox heartbeat on your Mac FAILED to dispatch $WORKFLOW. Check gh auth / network, or run: gh workflow run $WORKFLOW"
fi
