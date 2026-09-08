#!/usr/bin/env python3
"""State of every attendee fork of eo-cohort-agents.

Read-only. For each fork: how many agents it still carries, whether the two
required secrets exist, whether the sender is still Roman's domain, what the
schedule is, and how the last run went.

The column that matters most is AGENTS. A fork still holding all nine emails
every owner in the folder on every run — one person's setup mistake spams the
whole cohort.

    python3 booth/eo/sweep-forks.py
"""
import json
import subprocess

REPO = "aplustutoring/eo-cohort-agents"


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


forks = jgh(["api", f"repos/{REPO}/forks?per_page=100"]) or []
print(f"{len(forks)} forks\n")

hdr = (f"{'OWNER':22} {'AGENTS':>6} {'SECRETS':9} {'SENDER':9} {'SCHEDULE':10} LAST RUN")
print(hdr)
print("-" * (len(hdr) + 12))

spam_risk, no_secrets, never_ran = [], [], []

for f in forks:
    owner = f["owner"]["login"]
    full = f["full_name"]

    agents = jgh(["api", f"repos/{full}/contents/agents"]) or []
    n_agents = len([a for a in agents if a["name"].endswith(".md")])

    # Secret NAMES are readable on a public repo; values never are.
    sec = jgh(["api", f"repos/{full}/actions/secrets"])
    names = {s["name"] for s in (sec or {}).get("secrets", [])} if sec else set()
    have = {"ANTHROPIC_API_KEY", "RESEND_API_KEY"} <= names
    sec_txt = "both" if have else ("partial" if names else "NONE")
    if sec is None:
        sec_txt = "hidden"

    wf = jgh(["api", f"repos/{full}/contents/.github/workflows/first-shift.yml"])
    sender_txt, sched_txt = "?", "?"
    if wf:
        import base64
        body = base64.b64decode(wf["content"]).decode("utf-8", "replace")
        sender_txt = "ROMAN'S" if "agents@wetutorathome.com" in body else "own"
        active = [l.strip() for l in body.splitlines()
                  if l.strip().startswith("- cron:")]
        sched_txt = "once/yr" if any('"0 14 21 8 *"' in l for l in active) else "daily?"

    runs = jgh(["api", f"repos/{full}/actions/runs?per_page=1"])
    wr = (runs or {}).get("workflow_runs", [])
    last = f"{wr[0]['conclusion']}" if wr else "never ran"

    print(f"{owner:22} {n_agents:>6} {sec_txt:9} {sender_txt:9} {sched_txt:10} {last}")

    if n_agents > 1:
        spam_risk.append(f"{owner} ({n_agents})")
    if sec_txt in ("NONE", "partial"):
        no_secrets.append(owner)
    if not wr:
        never_ran.append(owner)

print()
print(f"SPAMS THE COHORT (>1 agent) : {', '.join(spam_risk) if spam_risk else 'none'}")
print(f"missing secrets             : {', '.join(no_secrets) if no_secrets else 'none'}")
print(f"never run                   : {', '.join(never_ran) if never_ran else 'none'}")
