#!/usr/bin/env python3
"""
branch_hygiene.py — catches work stranded outside main before it goes stale.

Two failure modes, two modes (both real incidents, 2026-08-05):
  remote (default, weekly Actions): remote branches with commits not on main,
    and open PRs idle > stale_days — the "merged-feeling but unmerged PR" trap.
  --local (laptop cron): commits on local branches never pushed to any remote —
    invisible to GitHub, e.g. the CallRail-fix commit stranded for 16 days.

Posts to Slack only when something is found; silence means clean.
Env: SLACK_BOT_TOKEN (+ optional GITHUB_TOKEN/GITHUB_REPOSITORY in remote mode).
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANNEL = "#calls"
STALE_PR_DAYS = 3


def sh(*args):
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, text=True).stdout.strip()


def post(text):
    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        print("SLACK_BOT_TOKEN not set — printing instead:\n" + text)
        return
    r = requests.post("https://slack.com/api/chat.postMessage",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"channel": CHANNEL, "text": text, "unfurl_links": False},
                      timeout=15)
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Slack error: {r.json().get('error')}")


def check_local():
    out = sh("log", "--branches", "--not", "--remotes",
             "--format=%h %cs %d %s")
    strays = [l for l in out.splitlines() if l.strip()]
    if not strays:
        print("local: clean — every local commit is pushed somewhere")
        return
    lines = [":warning: *Branch hygiene — unpushed local commits on this Mac*",
             f"_{len(strays)} commit(s) exist only in {REPO_ROOT} — invisible to GitHub:_"]
    lines += [f"• `{l}`" for l in strays[:10]]
    if len(strays) > 10:
        lines.append(f"_...and {len(strays) - 10} more_")
    lines.append("Push them (or delete the branch) so work can't quietly go stale.")
    post("\n".join(lines))


def check_remote():
    sh("fetch", "--all", "--quiet")
    findings = []
    branches = sh("for-each-ref", "refs/remotes/origin",
                  "--format=%(refname:short)").splitlines()
    for b in branches:
        short = b.replace("origin/", "")
        if short in ("main", "HEAD"):
            continue
        ahead = sh("rev-list", "--count", f"origin/main..{b}")
        if ahead and int(ahead) > 0:
            last = sh("log", "-1", b, "--format=%cs %s")
            findings.append(f"• `{short}` — {ahead} commit(s) not on main ({last[:90]})")

    repo = os.getenv("GITHUB_REPOSITORY") or "aplustutoring/aplus-agents"
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        r = requests.get(f"https://api.github.com/repos/{repo}/pulls?state=open",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.ok:
            now = datetime.now(timezone.utc)
            for pr in r.json():
                updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
                idle = (now - updated).days
                if idle >= STALE_PR_DAYS:
                    findings.append(f"• PR #{pr['number']} \"{pr['title'][:60]}\" — "
                                    f"open, idle {idle}d: {pr['html_url']}")

    if not findings:
        print("remote: clean — no stranded branches, no stale PRs")
        return
    post("\n".join(
        [":compass: *Branch hygiene — work stranded outside main*",
         "_Unmerged work goes stale silently; merge it, PR it, or delete it:_"]
        + findings[:15]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true",
                    help="laptop mode: find commits never pushed to any remote")
    args = ap.parse_args()
    if args.local:
        try:
            from dotenv import load_dotenv
            load_dotenv(REPO_ROOT / ".env")
        except ImportError:
            pass
        check_local()
    else:
        check_remote()
