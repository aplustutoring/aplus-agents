#!/usr/bin/env python3
"""
Fleet retry sweeper — failed runs get retried before anyone gets bothered.

Every ~20 minutes: any workflow run that completed as failure/timed_out gets
its failed jobs re-run, up to MAX_ATTEMPTS total tries (original + 3
retries, per Roman 2026-08-06). Only when the final attempt has also failed
does one Slack alert go to #agent-feedback, pinging the approvers
(ops/feedback-agent/config.yml slack.alerts_to).

Why cron instead of a workflow_run trigger: the 20-minute cadence naturally
spaces retries out (a platform outage like 2026-08-06's gets ~an hour of
runway before anyone is pinged), and a cron sweeper needs no recursion
tricks — re-runs it causes are just future rows in its own query.

GitHub's own per-failure notification emails are separate account-level
noise — turn them off at github.com/settings/notifications (Actions ->
uncheck Email); this sweeper is the fleet's alerting now.
"""

import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("fleet-retry")

REPO = os.getenv("GITHUB_REPOSITORY", "aplustutoring/aplus-agents")
GH_TOKEN = os.getenv("GH_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

MAX_ATTEMPTS = 4          # original run + 3 retries
LOOKBACK_HOURS = 24       # runs older than this are history, not incidents
ALERT_WINDOW_MIN = 25     # alert only for runs whose final failure is fresher
                          # than one sweep interval (so each exhaustion alerts once)
RETRYABLE = {"failure", "timed_out", "startup_failure"}

# Two failure shapes a rerun can only make WORSE, so they are alerted, never
# retried (2026-09-10, the day the call relay went live and queued runs):
#
#  - the run did its work and only the state commit-back lost a race with
#    another run's commit. rerun-failed-jobs re-executes the whole job, so
#    the agent step runs again on top of whatever state is on main and
#    re-does the work (16 duplicate HubSpot tickets/tasks/notes that day,
#    four rounds of them per failed run). Steps named in STATE_COMMIT_STEPS
#    are that commit-back step in every state-writing workflow.
#  - a 4xx from an upstream API (Teachworks 400 on deal 64842808888, retried
#    four times, identical each time). 429 is the one 4xx that IS transient.
STATE_COMMIT_STEPS = {"Commit state changes", "Persist state"}
DETERMINISTIC_4XX = re.compile(r"\b4(?!29\b)\d\d Client Error\b")

# Never auto-retried:
#   - this sweeper itself (a failing watchdog retrying itself is a siren loop)
#   - the approved-fix executor (a paid coding-agent run that half-completed
#     could open duplicate PRs — its thread already reports failures)
EXCLUDE_WORKFLOWS = {
    "Fleet retry sweeper (every 20 min)",
    "Feedback agent — execute approved fix",
}


def gh(method, path, params=None, ok404=False):
    r = requests.request(
        method, f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {GH_TOKEN}",
                 "Accept": "application/vnd.github+json"},
        params=params if method == "GET" else None,
        json=None, timeout=30,
    )
    if ok404 and r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def alert_targets():
    """Channel + mention string from the feedback agent's config — one
    routing source of truth for the whole fleet."""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "feedback-agent", "config.yml")
        cfg = yaml.safe_load(open(cfg_path))["slack"]
        people = cfg.get("people") or {}
        mentions = " ".join(
            f"<@{people[p]}>" for p in (cfg.get("alerts_to") or []) if str(people.get(p, "")).startswith("U")
        )
        return cfg.get("channel", ""), mentions
    except Exception as e:
        log.warning(f"could not read feedback-agent config ({e}); alerts disabled this run")
        return "", ""


def post_slack(channel, text):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                 "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": text, "unfurl_links": False},
        timeout=15,
    )
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Slack error: {r.json().get('error')}")


def failed_steps(run_id):
    """[(job_id, step name)] for every failed step of a run."""
    jobs = (gh("GET", f"/repos/{REPO}/actions/runs/{run_id}/jobs") or {}).get("jobs") or []
    return [(j["id"], s["name"]) for j in jobs
            for s in (j.get("steps") or []) if s.get("conclusion") == "failure"]


def only_state_commit_failed(step_names):
    """True when the run's work finished and only the state commit-back failed."""
    return bool(step_names) and all(n in STATE_COMMIT_STEPS for n in step_names)


def looks_deterministic(log_text):
    """A non-429 4xx from an upstream API — the same request fails the same way."""
    return bool(DETERMINISTIC_4XX.search(log_text or ""))


def job_log(job_id):
    r = requests.get(f"https://api.github.com/repos/{REPO}/actions/jobs/{job_id}/logs",
                     headers={"Authorization": f"Bearer {GH_TOKEN}",
                              "Accept": "application/vnd.github+json"},
                     timeout=30, allow_redirects=True)
    return r.text if r.ok else ""


def no_retry_reason(run_id):
    """Why this failed run must NOT be rerun, or None if a retry is fine."""
    steps = failed_steps(run_id)
    names = [n for _, n in steps]
    if only_state_commit_failed(names):
        return ("state commit-back lost a race with another run — the work is done; "
                "a rerun would re-do it and duplicate tickets/tasks")
    for job_id, name in steps:
        if name not in STATE_COMMIT_STEPS and looks_deterministic(job_log(job_id)):
            return f"4xx client error in `{name}` — deterministic, a rerun repeats it"
    return None


def main():
    dry_run = "--dry-run" in sys.argv
    if not GH_TOKEN:
        log.error("GH_TOKEN/GITHUB_TOKEN not set")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M")
    runs = []
    for page in (1, 2):
        batch = gh("GET", f"/repos/{REPO}/actions/runs",
                   {"created": f">={since}", "status": "completed",
                    "per_page": 100, "page": page}).get("workflow_runs", [])
        runs += batch
        if len(batch) < 100:
            break

    retried, exhausted, held = [], [], []
    for r in runs:
        if r["conclusion"] not in RETRYABLE or r["name"] in EXCLUDE_WORKFLOWS:
            continue
        attempt = r.get("run_attempt", 1)
        if attempt < MAX_ATTEMPTS:
            label = f"{r['name']} (run {r['id']}, attempt {attempt})"
            try:
                reason = no_retry_reason(r["id"])
            except Exception as e:  # noqa: BLE001 — classification is best-effort
                log.warning(f"could not classify {label}: {e}; treating as retryable")
                reason = None
            if reason:
                log.info(f"NOT retried: {label} — {reason}")
                updated = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                if now - updated <= timedelta(minutes=ALERT_WINDOW_MIN):
                    held.append((r, reason))
                continue
            if dry_run:
                log.info(f"[dry-run] would retry: {label}")
            else:
                res = gh("POST", f"/repos/{REPO}/actions/runs/{r['id']}/rerun-failed-jobs", ok404=True)
                if res is None:
                    log.info(f"retry unavailable (too old / in progress): {label}")
                    continue
                log.info(f"retried: {label} -> attempt {attempt + 1}")
            retried.append(label)
        else:
            updated = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
            if now - updated <= timedelta(minutes=ALERT_WINDOW_MIN):
                exhausted.append(r)

    if exhausted:
        channel, mentions = alert_targets()
        lines = [f"{mentions} — fleet alert: {len(exhausted)} run(s) failed all "
                 f"{MAX_ATTEMPTS} attempts (original + {MAX_ATTEMPTS - 1} retries):".strip()]
        for r in exhausted:
            lines.append(f"• *{r['name']}* — <{r['html_url']}|last attempt log>")
        lines.append("This is a real failure, not a platform blip — it needs eyes.")
        text = "\n".join(lines)
        if dry_run or not channel:
            log.info(f"[dry-run/no-channel] alert would be:\n{text}")
        else:
            post_slack(channel, text)
            log.info(f"alerted on {len(exhausted)} exhausted run(s)")

    if held:
        channel, mentions = alert_targets()
        lines = [f"{mentions} — fleet alert: {len(held)} failed run(s) deliberately NOT retried:".strip()]
        for r, reason in held:
            lines.append(f"• *{r['name']}* — {reason} — <{r['html_url']}|log>")
        lines.append("Needs eyes, not a rerun.")
        text = "\n".join(lines)
        if dry_run or not channel:
            log.info(f"[dry-run/no-channel] alert would be:\n{text}")
        else:
            post_slack(channel, text)
            log.info(f"alerted on {len(held)} held run(s)")

    log.info(f"sweep done: {len(retried)} retried, {len(held)} held, {len(exhausted)} exhausted, "
             f"{len(runs)} completed runs scanned")


if __name__ == "__main__":
    main()
