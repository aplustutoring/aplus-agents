"""Weekly sender-workflow liveness digest — no HubSpot workflow that sends to
customers gets to die silently again.

The lesson of the week (charter SMS flow dead 2 weeks; gold/trial limping
with day-late sends): 'enabled' tells you nothing. Enrollment COUNTERS do.
Every Monday this scans the enabled workflows for send actions (SMS =
to_number/body fields, email = content_id), reads each one's cumulative
enrollment counter (v3 — the only API that exposes totals), diffs against
last Monday's snapshot (email/state/sender_snapshot.json, committed with the
rest of the state), and posts ONE digest to #agent-feedback: which sender
workflows enrolled nobody all week. Zero enrollments is not proof of death —
low-traffic flows idle honestly — but a flow that WAS moving and stopped is
exactly the charter failure signature, and now it is visible within a week
instead of never. Runs from task_sweep (Monday), riding its state persist.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import hubspot_client as hs, slack_client
from .config import ROOT, cfg

SNAP = ROOT / "state" / "sender_snapshot.json"


def _sender_flows() -> dict:
    """{v4 flow id: name} for every ENABLED workflow with a send action."""
    flows, after = [], None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        d = hs._get("/automation/v4/flows", params)
        flows += d.get("results", [])
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    out = {}
    for f in flows:
        if not f.get("isEnabled"):
            continue
        try:
            w = hs._get(f"/automation/v4/flows/{f['id']}")
        except Exception:  # noqa: BLE001 — one bad flow must not kill the digest
            continue
        for a in (w.get("actions") or []):
            fl = a.get("fields") or {}
            if ("to_number" in fl and "body" in fl) or "content_id" in fl:
                out[str(f["id"])] = (w.get("name") or "").strip()
                break
    return out


def _enrollment_totals() -> dict:
    """{workflow NAME: cumulative enrolled} from v3 — totals live only there,
    and v3/v4 ids differ, so names are the join key (fleet-audit convention)."""
    d = hs._get("/automation/v3/workflows")
    return {(w.get("name") or "").strip():
            int(((w.get("contactCounts") or {}).get("enrolled") or 0))
            for w in d.get("workflows", [])}


def run() -> None:
    lc = cfg().get("sender_liveness") or {}
    if not lc.get("enabled", True):
        return
    senders = _sender_flows()
    totals = _enrollment_totals()
    now_counts = {name: totals.get(name, 0) for name in senders.values()}
    prev = {}
    if SNAP.exists():
        try:
            prev = json.loads(SNAP.read_text())
        except Exception:  # noqa: BLE001
            prev = {}
    SNAP.write_text(json.dumps(now_counts, indent=1, sort_keys=True))
    if not prev:
        print(f"sender_liveness: first snapshot ({len(now_counts)} sender workflows)")
        return
    quiet = sorted(n for n, c in now_counts.items()
                   if c - prev.get(n, 0) == 0 and n in prev)
    moving = len(now_counts) - len(quiet)
    lines = [f"📡 Weekly sender-workflow liveness: {len(now_counts)} enabled "
             f"workflows send SMS/email; {moving} enrolled someone this week."]
    if quiet:
        lines.append(f"ZERO enrollments this week ({len(quiet)}) — idle is fine, "
                     f"but a flow that WAS moving and stopped is the charter-SMS "
                     f"failure signature:")
        lines += [f"  • {n}" for n in quiet[:25]]
        if len(quiet) > 25:
            lines.append(f"  …and {len(quiet) - 25} more")
    else:
        lines.append("Every sender workflow enrolled at least one person. 🎉")
    channel = lc.get("channel", "C0BL05MCJ4B")
    try:
        slack_client.post_message(channel, "\n".join(lines))
    except Exception as e:  # noqa: BLE001
        print(f"sender_liveness: digest post failed ({e})")
    print(f"sender_liveness: {len(quiet)} quiet of {len(now_counts)}")
