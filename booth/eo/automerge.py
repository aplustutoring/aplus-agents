#!/usr/bin/env python3
"""Watch eo-cohort-agents and merge attendee PRs as they arrive.

Auto-merging into someone's repo needs a narrow, stated rule. A PR is merged
ONLY if all of these hold:

  * it comes from a fork (attendees cannot push to the repo directly)
  * it changes exactly ONE file
  * that file is agents/<something>.md
  * it adds lines and deletes none

Anything else — a workflow edit, a runner change, a multi-file PR, a deletion
— is left alone and printed once as NEEDS REVIEW. The rule has to be tight
enough that a surprising PR stops rather than lands.

Uses the REST API, not `gh pr list`: the GraphQL endpoint was timing out
repeatedly from this process while plain REST and curl were fine.

Transient failures are reported ONCE and then stay quiet until the next
success, so a flaky network cannot bury the user in identical notifications.
"""
import json
import re
import subprocess
import sys
import time

REPO = "aplustutoring/eo-cohort-agents"
POLL = 30
SAFE_PATH = re.compile(r"^agents/[A-Za-z0-9._-]+\.md$")


def gh(args, timeout=60):
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "timed out"


def stamp():
    return time.strftime("%H:%M:%S")


def open_prs():
    """REST, not GraphQL. Returns (list, error_or_None)."""
    code, out, err = gh(["api", f"repos/{REPO}/pulls?state=open&per_page=50"])
    if code != 0:
        return None, (err or "unknown").splitlines()[0][:90]
    try:
        return json.loads(out or "[]"), None
    except json.JSONDecodeError:
        return None, "bad JSON from api"


def pr_files(num):
    code, out, err = gh(["api", f"repos/{REPO}/pulls/{num}/files"])
    if code != 0:
        return None
    try:
        return json.loads(out or "[]")
    except json.JSONDecodeError:
        return None


def verdict(pr, files):
    if not pr.get("head", {}).get("repo", {}).get("fork"):
        return False, "not from a fork"
    if files is None:
        return False, "could not read file list"
    if len(files) != 1:
        return False, f"touches {len(files)} files"
    f = files[0]
    if not SAFE_PATH.match(f["filename"]):
        return False, f"path outside agents/: {f['filename']}"
    if f.get("deletions", 0) != 0:
        return False, f"deletes {f['deletions']} lines"
    return True, f["filename"]


print(f"[{stamp()}] auto-merge armed on {REPO} — single-file agents/*.md from forks only",
      flush=True)

flagged = set()
last_error = None

while True:
    prs, err = open_prs()
    if err:
        # Report a given failure once, then stay silent until it recovers.
        if err != last_error:
            print(f"[{stamp()}] github unreachable ({err}) — retrying quietly", flush=True)
            last_error = err
        time.sleep(POLL)
        continue

    if last_error:
        print(f"[{stamp()}] github reachable again", flush=True)
        last_error = None

    for pr in prs:
        n = pr["number"]
        who = pr.get("user", {}).get("login", "?")
        ok, why = verdict(pr, pr_files(n))
        if not ok:
            if n not in flagged:
                flagged.add(n)
                print(f"[{stamp()}] NEEDS REVIEW #{n} by {who} — {why} — left for Roman",
                      flush=True)
            continue
        code, out, merr = gh(["pr", "merge", str(n), "--repo", REPO, "--merge"])
        if code == 0:
            print(f"[{stamp()}] MERGED #{n} {pr['title'][:44]} — {who} ({why})", flush=True)
        else:
            print(f"[{stamp()}] merge failed #{n} {who}: {(merr or out)[:100]}", flush=True)

    sys.stdout.flush()
    time.sleep(POLL)
