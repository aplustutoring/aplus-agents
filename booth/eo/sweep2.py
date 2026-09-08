#!/usr/bin/env python3
"""Second pass over the forks, correcting the first sweep's mistake.

Sweep 1 counted agents/*.md in the repo and flagged anyone holding more than
one as "will spam the cohort". That was wrong: what matters is what the
WORKFLOW runs, not what the repo stores. Tallin keeps all nine on disk and
strips the checkout at CI time, which is fine — arguably better, since
nothing is destroyed.

So this pass reads each fork's workflows and works out what actually
executes.
"""
import base64
import json
import subprocess


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


forks = jgh(["api", "repos/aplustutoring/eo-cohort-agents/forks?per_page=100"]) or []

print(f"{'OWNER':24} {'AGENTS':>6}  {'WORKFLOW':22} {'SCOPED?':9} VERDICT")
print("-" * 92)

danger = []
for f in sorted(forks, key=lambda x: x["owner"]["login"]):
    owner = f["owner"]["login"]
    full = f["full_name"]

    agents = jgh(["api", f"repos/{full}/contents/agents"]) or []
    n = len([a for a in agents if a["name"].endswith(".md")])

    wfs = jgh(["api", f"repos/{full}/contents/.github/workflows"]) or []
    names = [w["name"] for w in wfs]

    scoped = False
    body_all = ""
    for w in wfs:
        blob = jgh(["api", f"repos/{full}/contents/.github/workflows/{w['name']}"])
        if blob:
            body_all += base64.b64decode(blob["content"]).decode("utf-8", "replace")
    # Does any workflow narrow the agent set before running the runner?
    if "-delete" in body_all or "! -name" in body_all or "rm agents/" in body_all:
        scoped = True

    if n <= 1:
        verdict = "fine — only own agent"
    elif scoped:
        verdict = "fine — strips at CI time"
    else:
        verdict = "WOULD EMAIL THE COHORT"
        danger.append(f"{owner} ({n} agents)")

    print(f"{owner:24} {n:>6}  {(names[0] if names else '-')[:22]:22} "
          f"{'yes' if scoped else 'no':9} {verdict}")

print()
if danger:
    print("NEEDS FIXING BEFORE THEIR NEXT RUN:")
    for d in danger:
        print(f"  - {d}")
else:
    print("No fork would email the cohort.")
