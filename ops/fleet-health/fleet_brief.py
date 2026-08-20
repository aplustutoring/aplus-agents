#!/usr/bin/env python3
"""Generate docs/FLEET.md — the always-current fleet breakdown, straight from
registry.yml.

Roman 2026-08-20: "we do it in code, but then claude chat doesnt know about it."
The repo already knows the truth; nothing published it. Hand-written breakdowns
go stale the moment an agent changes, so this one is generated on every merge to
main and committed back. Handing the fleet to Claude-in-chat is now: copy
docs/FLEET.md.

Deliberately reads ONLY registry.yml. If an agent is missing here it is missing
from the registry, which is the same bug registry_check.py catches — not
something this script should paper over by scanning the filesystem.

  python3 ops/fleet-health/fleet_brief.py            # write docs/FLEET.md
  python3 ops/fleet-health/fleet_brief.py --check    # exit 1 if out of date
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "registry.yml"
OUT = REPO / "docs" / "FLEET.md"

# Engine order for the document — narrative order, not alphabetical: the two
# content engines, then the operational core, then the plumbing.
ENGINE_ORDER = [
    "B2B blogs",
    "B2C spotlights",
    "Email / inbox ops",
    "Data sync",
    "Call agent",
    "Messenger",
    "Feedback agent",
    "Fleet health",
    "Charter analysis",
]


def load_agents():
    reg = yaml.safe_load(REGISTRY.read_text())
    return reg.get("agents", [])


def trigger_text(a):
    """One human-readable cadence string per agent."""
    t = a.get("trigger") or {}
    sched = t.get("schedule")
    if sched:
        # Prefer the parenthetical PT gloss the registry carries: the cron is
        # UTC and means nothing to a human reading this in chat.
        first = sched[0]
        if "(" in first:
            return first.split("(", 1)[1].rstrip(")").strip()
        return first
    events = t.get("events") or []
    if t.get("type") == "workflow_dispatch" or events == ["workflow_dispatch"]:
        return "manual"
    if "repository_dispatch" in events:
        return "on event"
    return t.get("type", "—")


def flatten(v):
    """reads/writes are lists of strings, sometimes single-key dicts."""
    out = []
    for item in v or []:
        if isinstance(item, dict):
            out += [f"{k}: {vv}" for k, vv in item.items()]
        else:
            # Registry entries carry trailing `# comment` context; keep the
            # payload, drop the annotation.
            out.append(str(item).split("#", 1)[0].strip())
    return [x for x in out if x]


def first_sentence(note, limit=240):
    if not note:
        return ""
    s = " ".join(str(note).split())
    for stop in (". ", " — ", "; "):
        if stop in s[:limit]:
            s = s.split(stop, 1)[0]
            break
    return (s[:limit].rstrip() + "…") if len(s) > limit else s


def render(agents):
    by_engine = {}
    for a in agents:
        by_engine.setdefault(a.get("engine", "Unassigned"), []).append(a)

    engines = [e for e in ENGINE_ORDER if e in by_engine]
    engines += sorted(e for e in by_engine if e not in ENGINE_ORDER)

    active = sum(1 for a in agents if a.get("status") == "active")
    manual = sum(1 for a in agents if a.get("status") == "manual")
    depr = sum(1 for a in agents if a.get("status") == "deprecated")

    L = []
    L.append("# A+ Automation Fleet — current breakdown")
    L.append("")
    L.append("**Generated from `registry.yml` — do not edit by hand.** Regenerated on every "
             "merge to `main` by `ops/fleet-health/fleet_brief.py`. Safe to paste anywhere "
             "(a Claude chat, an email, a doc) knowing it matches what is actually running.")
    L.append("")
    L.append(f"**{len(agents)} registered agents** — {active} active · {manual} manual · "
             f"{depr} deprecated · across {len(engines)} engines.")
    L.append("")
    L.append("Everything runs on GitHub Actions cron out of one repo "
             "(`aplustutoring/aplus-agents`). No always-on machine. HubSpot owns families "
             "and all communication; Teachworks owns lessons; engines sync from Teachworks "
             "into HubSpot. For architecture and governance read `ARCHITECTURE.md`; for the "
             "full per-agent detail read `registry.yml`.")
    L.append("")

    L.append("## At a glance")
    L.append("")
    L.append("| Engine | Agents | Active |")
    L.append("|---|---|---|")
    for e in engines:
        ags = by_engine[e]
        L.append(f"| {e} | {len(ags)} | {sum(1 for a in ags if a.get('status') == 'active')} |")
    L.append("")

    # The question people actually ask: what changes my data on its own?
    autonomous, drafts, manual_only = [], [], []
    for a in agents:
        if a.get("status") == "deprecated":
            continue
        writes = " ".join(flatten(a.get("writes"))).lower()
        touches_live = any(k in writes for k in ("hubspot", "teachworks", "monday", "googlesheets", "github:"))
        if a.get("probation") == "draft":
            drafts.append(a)
        elif a.get("status") == "manual":
            manual_only.append(a)
        elif touches_live:
            autonomous.append(a)
        else:
            drafts.append(a)

    L.append("## Autonomy — what acts without asking")
    L.append("")
    L.append("The distinction that matters most, and it does not follow engine lines.")
    L.append("")
    L.append(f"**Writes to live systems on its own ({len(autonomous)}):** "
             + ", ".join(f"`{a['id']}`" for a in autonomous) + ".")
    L.append("")
    L.append(f"**Reports, drafts, or waits for a human ({len(drafts)}):** "
             + ", ".join(f"`{a['id']}`" for a in drafts) + ".")
    L.append("")
    L.append(f"**Manual dispatch only ({len(manual_only)}):** "
             + ", ".join(f"`{a['id']}`" for a in manual_only) + ".")
    L.append("")
    L.append("Note: *writes to live systems* includes agents whose only write is a **draft** "
             "(blog drafts, draft replies) — the agent creates the object, a human still ships "
             "it. `ARCHITECTURE.md` draws that finer line.")
    L.append("")

    L.append("## By engine")
    for e in engines:
        L.append("")
        L.append(f"### {e}")
        L.append("")
        L.append("| Agent | Runs | Status | Reads | Writes |")
        L.append("|---|---|---|---|---|")
        for a in sorted(by_engine[e], key=lambda x: (x.get("status") != "active", x["id"])):
            reads = ", ".join(flatten(a.get("reads"))) or "—"
            writes = ", ".join(flatten(a.get("writes"))) or "—"
            status = a.get("status", "?")
            if a.get("probation") == "draft":
                status += " (draft)"
            L.append(f"| **{a['id']}**<br>{a.get('name','')} | {trigger_text(a)} | {status} "
                     f"| {reads} | {writes} |")
        notes = [(a["id"], first_sentence(a.get("notes"))) for a in by_engine[e]]
        notes = [(i, n) for i, n in notes if n]
        if notes:
            L.append("")
            for i, n in notes:
                L.append(f"- **{i}** — {n}")
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if docs/FLEET.md is stale (CI use)")
    args = ap.parse_args()

    content = render(load_agents())

    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != content:
            print(f"{OUT.relative_to(REPO)} is out of date — "
                  f"run: python3 ops/fleet-health/fleet_brief.py")
            return 1
        print(f"{OUT.relative_to(REPO)} is current.")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content)
    print(f"wrote {OUT.relative_to(REPO)} ({len(content.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
