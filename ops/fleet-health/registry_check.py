#!/usr/bin/env python3
"""Enforce registry.yml's own first rule: if it's not here, it doesn't exist.

On 2026-08-20 an audit found NINE live workflows with no registry entry — three
writing to HubSpot, one opening PRs. They had been running for weeks. The rule
existed the whole time; nothing was watching. This is the watcher.

Why it matters beyond tidiness: registry.yml is the feedback agent's
classification vocabulary and the DEMOTE path's target list. An unregistered
agent cannot be reported against in #agent-feedback and cannot be paused.

Checks:
  1. every .github/workflows/*.yml has a registry entry pointing at it
  2. every workflow referenced by the registry exists on disk
  3. every agent has id / name / owner / status / engine
  4. ids are unique (they become HubSpot source_agent enum values)
  5. repo-relative entrypoints exist on disk
  6. docs/FLEET.md is current (delegated to fleet_brief.py --check)

  --warn   report findings, always exit 0 (rollout mode)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "registry.yml"
WORKFLOW_DIR = REPO / ".github" / "workflows"

REQUIRED = ("id", "name", "owner", "status", "engine", "runtime")
VALID_STATUS = {"active", "manual", "deprecated", "unverified"}
VALID_RUNTIME = {"github-actions", "cloudflare-worker", "apps-script", "zapier"}

# Non-Actions agents have no workflow file to enumerate, so they cannot be
# discovered the way Actions agents can. These heuristics are the next best
# thing: a marker file that means "something runs here". Anything matched but
# unreferenced by the registry gets flagged.
#
# Added 2026-08-20: the Sage Oak photo booth — a Cloudflare Worker writing to
# production HubSpot, emailing via Resend, sending MMS from the main A+ line —
# appeared in no fleet map at all, and this checker could not have caught it,
# because it only ever looked at .github/workflows/.
# The 4th field is whether a reference to a SIBLING file counts as coverage.
# True for wrangler.toml — it is config sitting beside a worker script the
# registry does name. False for *.gs — an Apps Script IS the agent, so it must
# be named outright. (Learned the hard way: with sibling-coverage on, the
# spotlight watcher's .gs was masked by download-drive-folder.py in the same
# directory, and pulling its registry entry did not trip the check.)
DISCOVERY = (
    ("wrangler.toml", "cloudflare-worker", "a Cloudflare Worker", True),
    ("*.gs", "apps-script", "a Google Apps Script", False),
)
DISCOVERY_IGNORE = (".git", "node_modules", ".claude/worktrees", "archive")


def registry_workflows(agent):
    """Workflow basenames an entry claims — `workflow:` or `workflows:`."""
    t = agent.get("trigger") or {}
    found = []
    for key in ("workflow", "workflows"):
        v = t.get(key)
        if isinstance(v, str):
            found.append(os.path.basename(v))
        elif isinstance(v, list):
            found += [os.path.basename(x) for x in v]
    return found


def referenced_paths(agents):
    """Every repo path any registry entry points at — entrypoint, source, deps."""
    paths = set()
    for a in agents:
        for key in ("entrypoint", "source"):
            v = a.get(key)
            if isinstance(v, str):
                paths.add(v.split("#", 1)[0].strip())
        for dep in a.get("depends_on") or []:
            if isinstance(dep, str):
                paths.add(dep.split("#", 1)[0].strip())
        for key in ("reads", "writes"):
            for item in a.get(key) or []:
                if isinstance(item, str):
                    paths.add(item.split("#", 1)[0].strip())
    return {p for p in paths if p}


def discover_unregistered(agents):
    """Find non-Actions agents on disk that no registry entry mentions.

    A path counts as referenced if any registry entry names it or a directory
    containing it — `booth/worker.js` covers `booth/wrangler.toml`.
    """
    refs = referenced_paths(agents)
    found = []
    for pattern, runtime, human, sibling_ok in DISCOVERY:
        for path in REPO.rglob(pattern):
            rel = path.relative_to(REPO).as_posix()
            if any(part in rel for part in DISCOVERY_IGNORE):
                continue
            parent = path.parent.relative_to(REPO).as_posix()
            covered = any(rel == r or rel.startswith(r.rstrip("/") + "/") for r in refs)
            if not covered and sibling_ok:
                covered = any(r.startswith(parent + "/") for r in refs)
            if not covered:
                found.append((rel, runtime, human))
    return found


def entrypoints(agent):
    """Repo-relative entrypoint paths worth existence-checking.

    Skipped: third-party action refs (feedback-fix runs claude-code-action) and
    anything carrying a `#` note or an absolute path.
    """
    ep = agent.get("entrypoint")
    if not isinstance(ep, str):
        return []
    ep = ep.split("#", 1)[0].strip()
    if not ep or ep.startswith("/") or "@" in ep or " " in ep:
        return []
    return [ep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn", action="store_true",
                    help="report but always exit 0 (rollout mode)")
    args = ap.parse_args()

    problems, notes = [], []

    reg = yaml.safe_load(REGISTRY.read_text())
    agents = reg.get("agents") or []
    if not agents:
        print("FAIL: registry.yml has no agents")
        return 1

    # 3 + 4 — shape and uniqueness
    seen = {}
    for a in agents:
        aid = a.get("id", "<no id>")
        for f in REQUIRED:
            if not a.get(f):
                problems.append(f"{aid}: missing required field `{f}`")
        st = a.get("status")
        if st and st not in VALID_STATUS:
            problems.append(f"{aid}: status `{st}` not one of {sorted(VALID_STATUS)}")
        rt = a.get("runtime")
        if rt and rt not in VALID_RUNTIME:
            problems.append(f"{aid}: runtime `{rt}` not one of {sorted(VALID_RUNTIME)}")
        # Only Actions agents have a workflow file; everything else must say
        # where its code lives, or nothing can verify it exists at all.
        if rt and rt != "github-actions" and not a.get("source"):
            problems.append(f"{aid}: runtime `{rt}` needs a `source:` path "
                            f"(no workflow file to point at)")
        if aid in seen:
            problems.append(f"{aid}: duplicate id (ids become HubSpot enum values)")
        seen[aid] = a

    # 1 + 2 — workflows both directions
    claimed = {}
    for a in agents:
        if a.get("runtime") not in (None, "github-actions"):
            continue   # a Worker or Apps Script has no workflow to claim
        for wf in registry_workflows(a):
            claimed.setdefault(wf, []).append(a.get("id"))

    on_disk = {p.name for p in WORKFLOW_DIR.glob("*.yml")} | \
              {p.name for p in WORKFLOW_DIR.glob("*.yaml")}

    for wf in sorted(on_disk - set(claimed)):
        problems.append(
            f"{wf}: live workflow with NO registry entry — it cannot be reported "
            f"against in #agent-feedback or demoted. Add it to registry.yml.")
    for wf in sorted(set(claimed) - on_disk):
        problems.append(
            f"{wf}: registry references this workflow but it is not on disk "
            f"(claimed by {', '.join(claimed[wf])})")

    # 5 — entrypoints exist
    for a in agents:
        for ep in entrypoints(a):
            if not (REPO / ep).exists():
                problems.append(f"{a.get('id')}: entrypoint `{ep}` does not exist")
        src = a.get("source")
        if isinstance(src, str) and src and not (REPO / src.split("#", 1)[0].strip()).exists():
            problems.append(f"{a.get('id')}: source `{src}` does not exist")

    # 5b — non-Actions agents nobody registered
    for rel, runtime, human in discover_unregistered(agents):
        problems.append(
            f"{rel}: looks like {human} that no registry entry mentions. If it runs, "
            f"register it with `runtime: {runtime}` and a `source:` path — nothing else "
            f"in the fleet can see it.")

    # 6 — generated brief is current
    r = subprocess.run([sys.executable, str(REPO / "ops/fleet-health/fleet_brief.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        problems.append("docs/FLEET.md is stale — run "
                        "`python3 ops/fleet-health/fleet_brief.py` and commit the result")

    # Not a failure, but worth saying out loud in the run log.
    depr = [a["id"] for a in agents if a.get("status") == "deprecated"]
    if depr:
        notes.append(f"{len(depr)} deprecated entries kept for dispatch: {', '.join(depr)}")

    print(f"registry.yml: {len(agents)} agents · {len(on_disk)} workflows on disk")
    for n in notes:
        print(f"  note: {n}")

    if not problems:
        print("OK — every workflow is registered and every entry resolves.")
        return 0

    print(f"\n{len(problems)} problem(s):")
    for p in problems:
        print(f"  ✗ {p}")

    if args.warn:
        print("\n(--warn: not failing the build)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
