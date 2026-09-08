#!/usr/bin/env python3
"""Per-fork detail: what each attendee's repo will actually do tomorrow.

Read-only. For each fork it reports the workflow that exists, the agents it
would run, the sender, the schedule, and — crucially — whether the last runs
ACTUALLY executed the agent or were skipped by a gate. A skipped run reports
green, so "success" in the Actions tab is not evidence anything was sent.
"""
import base64
import json
import subprocess
from datetime import datetime
import zoneinfo

PT = zoneinfo.ZoneInfo("America/Los_Angeles")
UPSTREAM = "aplustutoring/eo-cohort-agents"


def gh(args, timeout=60):
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""


def jgh(args):
    code, out = gh(args)
    if code != 0 or not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


forks = jgh(["api", f"repos/{UPSTREAM}/forks?per_page=100"]) or []

for f in sorted(forks, key=lambda x: x["owner"]["login"]):
    owner, full = f["owner"]["login"], f["full_name"]
    print("=" * 78)
    print(owner)

    agents = [a["name"] for a in (jgh(["api", f"repos/{full}/contents/agents"]) or [])
              if a["name"].endswith(".md")]
    print(f"  agents in repo : {len(agents)}  {', '.join(a[:-3] for a in agents[:6])}"
          + (" ..." if len(agents) > 6 else ""))

    wfs = [w["name"] for w in (jgh(["api", f"repos/{full}/contents/.github/workflows"]) or [])]
    print(f"  workflows      : {', '.join(wfs) if wfs else 'NONE'}")

    body = ""
    for w in wfs:
        blob = jgh(["api", f"repos/{full}/contents/.github/workflows/{w}"])
        if blob:
            body += base64.b64decode(blob["content"]).decode("utf-8", "replace") + "\n"

    sender = "own"
    if "agents@wetutorathome.com" in body:
        sender = "ROMAN'S DOMAIN (will be rejected)"
    crons = [l.strip().replace("- cron:", "").strip()
             for l in body.splitlines()
             if l.strip().startswith("- cron:") and not l.strip().startswith("#")]
    gated = "needs.gate" in body or "outputs.run" in body
    strips = "-delete" in body or "! -name" in body
    print(f"  sender         : {sender}")
    print(f"  crons          : {', '.join(crons) if crons else 'none active'}")
    print(f"  DST gate       : {'yes' if gated else 'no'}")
    print(f"  strips agents  : {'yes' if strips else 'no'}")

    runs = (jgh(["api", f"repos/{full}/actions/runs?per_page=4"]) or {}).get("workflow_runs", [])
    if not runs:
        print("  runs           : never run")
    for r in runs:
        t = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone(PT)
        jobs = (jgh(["api", f"repos/{full}/actions/runs/{r['id']}/jobs"]) or {}).get("jobs", [])
        detail = "; ".join(
            f"{j['name']}={j['conclusion'] or j['status']}" for j in jobs)
        real = any(j["conclusion"] == "success" and j["name"] != "gate" for j in jobs)
        note = "AGENT RAN" if real else "agent did NOT run"
        print(f"  run {t:%m-%d %-I:%M%p} PT : {r['conclusion']:9} [{note}] {detail[:70]}")
    print()
