#!/usr/bin/env python3
"""
pr_merge_nudge.py — green-suite fix PRs should not rot in the queue.

The fleet's feedback loop produces [fix]/[correction] PRs faster than they get
merged: on 2026-08-26 ten PRs were open, six of them fixes with green CI, the
oldest six days old — while the bugs they fix kept firing. Approve+merge was
opened to four people on 2026-08-20 precisely so this would not bottleneck on
Roman, but nobody is prompted, so nobody merges.

This agent prompts. Every run it finds open PRs that are
    (a) older than --stale-days (default 3),
    (b) mergeable, with a GREEN check suite (nothing failing, nothing pending),
and posts ONE digest to #agent-feedback pinging the approvers, each PR with its
age, title, and a one-click link. PRs with failing or pending checks are listed
separately without a ping — those need work, not approval.

NEVER REMEDIATES. It does not merge, close, approve, or comment on any PR.
Merging stays a human click; this only makes the click findable. Silence means
a clean queue (no post at all).

Approver roster comes from ops/feedback-agent/config.yml (roles, not names —
the same list that may approve+merge feedback fixes). Exit codes per the fleet
rule: 0 = ran fine (digest or clean), 1 = could not do its job.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, SLACK_BOT_TOKEN.
    python3 ops/fleet-health/pr_merge_nudge.py            # post if warranted
    python3 ops/fleet-health/pr_merge_nudge.py --dry-run  # print, never post
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_CFG = REPO_ROOT / "ops" / "feedback-agent" / "config.yml"
FIX_MARKERS = ("[fix]", "[correction]")


def gh_api(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def approver_mentions():
    cfg = yaml.safe_load(FEEDBACK_CFG.read_text())
    slack = cfg.get("slack", {})
    people = slack.get("people", {})
    roster = slack.get("approvers") or slack.get("alerts_to") or []
    out = []
    for role in roster:
        uid = people.get(role, "")
        out.append(f"<@{uid}>" if uid else role)
    return " ".join(out), slack.get("channel", "")


def check_state(sha):
    """'green' | 'pending' | 'failing' for a head SHA (checks API + legacy statuses)."""
    runs = gh_api(f"/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
    concl = [c.get("conclusion") for c in runs]
    if any(c in ("failure", "timed_out", "cancelled", "action_required") for c in concl):
        return "failing"
    if any(c is None for c in concl):
        return "pending"
    status = gh_api(f"/commits/{sha}/status")
    if status.get("state") == "failure":
        return "failing"
    if status.get("state") == "pending" and status.get("total_count", 0) > 0 and not runs:
        return "pending"
    return "green"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    try:
        prs = gh_api("/pulls?state=open&per_page=100")
    except Exception as e:
        print(f"ERROR: cannot list PRs: {e}", file=sys.stderr)
        return 1

    ready, blocked = [], []
    for pr in prs:
        if pr.get("draft"):
            continue
        age = (now - datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))).days
        if age < args.stale_days:
            continue
        is_fix = any(m in pr["title"].lower() for m in FIX_MARKERS)
        state = check_state(pr["head"]["sha"])
        row = {"n": pr["number"], "title": pr["title"], "age": age,
               "url": pr["html_url"], "fix": is_fix, "state": state}
        if state == "green" and is_fix:
            ready.append(row)
        elif is_fix:
            blocked.append(row)
        # non-fix PRs are branch_hygiene's beat; skip to keep this digest sharp

    for r in ready + blocked:
        print(f"  #{r['n']:<4} {r['age']:>2}d {r['state']:<8} {r['title'][:64]}")

    if not ready:
        print("no green fix PRs past the stale bound — staying silent.")
        return 0

    mentions, channel = approver_mentions()
    lines = [f"*{len(ready)} green fix PR{'s' if len(ready) != 1 else ''} waiting on a one-click merge* "
             f"(older than {args.stale_days} days, CI green)",
             ""]
    for r in sorted(ready, key=lambda x: -x["age"]):
        lines.append(f"• <{r['url']}|#{r['n']}> — {r['age']}d old — {r['title']}")
    lines += ["",
              f"{mentions} any of you can approve and squash-merge these "
              f"(granted 2026-08-20). The bug a fix PR fixes keeps firing until it lands.",
              "_This bot never merges anything itself._"]
    if blocked:
        lines += ["", f"_Also open but NOT mergeable ({len(blocked)}, no action needed here): "
                  + ", ".join(f"<{b['url']}|#{b['n']}> ({b['state']})" for b in blocked) + "_"]
    text = "\n".join(lines)

    if args.dry_run:
        print("\n--- DRY RUN, would post: ---\n" + text)
        return 0

    import requests
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"},
                      json={"channel": channel, "text": text, "unfurl_links": False},
                      timeout=20)
    ok = r.ok and r.json().get("ok")
    print(f"slack -> {'posted' if ok else r.text[:200]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
