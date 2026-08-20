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

# ── Hand-maintained prose ───────────────────────────────────────────────────
# Everything below this line is context a reader (or a Claude chat) needs that
# registry.yml cannot express. Keep it short and keep it true — the per-agent
# detail is generated, this is the part a human has to maintain.

CONTEXT = """## What this is

A+ Tutoring runs its operations on a fleet of automated agents. They live in one
repo (`aplustutoring/aplus-agents`) and run on GitHub Actions cron — there is no
always-on server. Each run commits its own state back to the repo, which is why
the remote is usually well ahead of any local checkout.

**Not everything is a GitHub Action.** Most agents are Actions cron jobs, but some
run elsewhere — Google Apps Scripts (the Drive watcher, the Slack relay), and
Cloudflare Workers. Those carry a `runtime:` in the registry and show it in the
tables below. It matters because they deploy by hand, outside CI: editing the
file in this repo does **not** make the change live, and if one stops, nothing in
GitHub goes red.

**Systems in play:** HubSpot (CRM, portal 6312752) · Teachworks (lessons and
scheduling) · JustCall (phones + SMS) · Monday (boards) · Slack (where agents
talk to humans) · Google Drive/Sheets (spotlight intake, retention log).

**Sources of truth — these two settle every argument:**

| System | Owns |
|---|---|
| **HubSpot** | Families: all contact information AND all communication — contacts, deals, tickets, conversations, blog posts |
| **Teachworks** | Lessons: scheduling, attendance, invoices |

Agents sync **from Teachworks into HubSpot**. No sheet, cache, or state file
outranks those two. HubSpot is where humans act.
"""

RULES = """## Working rules every agent follows

Anyone reasoning about this fleet — human or Claude — needs these.

- **Registration.** If it isn't in `registry.yml`, it doesn't exist. That file is
  also the feedback agent's vocabulary and the DEMOTE path's target list, so an
  unregistered agent cannot be reported against or paused. Enforced in CI by
  `ops/fleet-health/registry_check.py`.
- **Read labels, never values.** Agents read HubSpot enumeration LABELS. Internal
  values differ from what humans see (e.g. lead status value `We Connected` is
  labeled "QTL - NEW").
- **Agent-written properties are marked.** Any property an agent writes carries
  the `[Agent] ` label prefix and a description starting "AGENT PROPERTY — written
  by <script>", so humans can tell agent fields from intake capture at a glance.
  New properties are declared in `ops/hubspot-schema/properties.yml` and synced by
  workflow — never created ad hoc.
- **Roles, not names.** Config keys, properties, and audit actions name roles
  (`charter_sales`), never people. Only the `staff:` block maps roles to humans.
- **Five personas.** Contacts are typed by `a_persona` (multi-select): Decision
  Maker/Director · Teacher of Record/EF/ES · Family · Tutors · Student.
- **Family→Teacher-of-Record is an association**, contact-to-contact, paired label
  "Teacher of Record" (typeId 15; reverse "Family" = 14). The stamped
  `teacher_of_record_name/email` text fields are legacy intake capture, not truth.
- **Charter PO deals** are named `Parent - Student - School N - YY/YY`. PO numbers
  are stored bare, with no "PO" prefix.
- **Pacific time.** Every workflow sets `TZ=America/Los_Angeles`. Human-facing
  output and date windows are PT; state cursors and audit logs are explicit UTC.
- **Exit codes.** An agent that accomplished NONE of its work must exit non-zero —
  the retry sweeper only reacts to non-zero exits, so a script that prints failures
  and exits 0 is invisible. Narrow on purpose: isolating one bad item so it can't
  kill a batch is good design. 0 of 50 is a failed run; 49 of 50 is a warning.
- **Concurrency.** Multiple Claude sessions share this checkout. Branch/PR work
  happens in a git worktree, never in the shared checkout.
- **Approval-first.** Nothing outbound ships without Roman's explicit go.

## How a problem gets fixed

Report it in the Slack channel `#agent-feedback` in plain English. The feedback
agent works out which agent you mean and how bad it is, asks at most one
clarifying question, files it as a correction, and proposes a fix in the thread.
Approve in the thread and a coding agent implements it on a branch and opens a PR
for Roman to merge; merging replies in the original thread to close the loop.

To stop a misbehaving agent, say so — the DEMOTE path produces a one-click PR
flipping it to draft-only. Honored first, reviewed after.

## Not built (deliberately)

**Charter prospecting / B2B sales engine.** Discussed, never built — no code, no
automation. What exists are five manual, read-only-by-default charter analysis
reports. If it is ever built for real it goes in as a fresh engine with registry
entries.
"""

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
    "Events",
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


def flatten(v, budget=260):
    """reads/writes are lists of strings, sometimes single-key dicts.

    Registry entries spell out implementation detail in parentheses — invaluable
    in registry.yml, unreadable in a table cell (email-po-inbox's writes run past
    900 characters). Over `budget`, keep each item's subject and drop its
    parenthetical; registry.yml is cited for the rest.
    """
    out = []
    for item in v or []:
        if isinstance(item, dict):
            out += [f"{k}: {vv}" for k, vv in item.items()]
        else:
            # Registry entries carry trailing `# comment` context; keep the
            # payload, drop the annotation.
            out.append(str(item).split("#", 1)[0].strip())
    out = [x for x in out if x]
    if sum(len(x) for x in out) > budget:
        out = [x.split("(", 1)[0].strip().rstrip(",;") if "(" in x else x for x in out]
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
    L.append("# A+ Automation Fleet — handoff brief")
    L.append("")
    L.append("**Generated from `registry.yml` — do not edit by hand.** Regenerated on every "
             "merge to `main` by `ops/fleet-health/fleet_brief.py`. Self-contained on "
             "purpose: paste the whole thing into a Claude chat (or hand it to a new person) "
             "and it is everything needed to reason about the fleet, current as of the last "
             "merge.")
    L.append("")
    L.append(f"**{len(agents)} registered agents** — {active} active · {manual} manual · "
             f"{depr} deprecated · across {len(engines)} engines.")
    L.append("")
    L.append(CONTEXT.strip())
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
            rt = a.get("runtime", "github-actions")
            # Only worth the ink when it is NOT the default — the exception is
            # the thing a reader needs to notice (different runtime, different
            # deploy path, different way of going wrong).
            runs = trigger_text(a) if rt == "github-actions" else f"{trigger_text(a)}<br>*{rt}*"
            L.append(f"| **{a['id']}**<br>{a.get('name','')} | {runs} | {status} "
                     f"| {reads} | {writes} |")
        notes = [(a["id"], first_sentence(a.get("notes"))) for a in by_engine[e]]
        notes = [(i, n) for i, n in notes if n]
        if notes:
            L.append("")
            for i, n in notes:
                L.append(f"- **{i}** — {n}")
    L.append("")
    L.append(RULES.strip())
    L.append("")
    L.append("---")
    L.append("")
    L.append("*Deeper detail: `ARCHITECTURE.md` for the engine map, autonomy, and known weak "
             "points · `registry.yml` for every trigger, read, and write per agent · "
             "`docs/CHANGELOG.md` for why things changed.*")
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
