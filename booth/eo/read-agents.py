#!/usr/bin/env python3
"""Print the ROLE and FORMAT of every attendee agent, wherever it lives —
the cohort repo's main, an attendee's fork, or an unmerged branch."""
import base64
import json
import re
import subprocess

SOURCES = [
    ("aplustutoring/eo-cohort-agents", "main", None),
    ("annasingleton444/eo-cohort-agents", "main", "lease-up-radar.md"),
    ("polymorphicteam/eo-cohort-agents", "agent/eod-checker", None),
]


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


seen = set()
for repo, ref, only in SOURCES:
    listing = jgh(["api", f"repos/{repo}/contents/agents?ref={ref}"]) or []
    for item in listing:
        fn = item["name"]
        if not fn.endswith(".md"):
            continue
        if only and fn != only:
            continue
        if fn in seen:
            continue
        seen.add(fn)
        blob = jgh(["api", f"repos/{repo}/contents/agents/{fn}?ref={ref}"])
        if not blob:
            continue
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
        who = re.search(r"^name:\s*(.+)$", text, re.M)
        role = re.search(r"^ROLE:\s*(.+?)(?=\n[A-Z]+:|\Z)", text, re.M | re.S)
        fmt = re.search(r"^FORMAT:\s*(.+?)(?=\n[A-Z]+:|\Z)", text, re.M | re.S)
        print("=" * 76)
        print(f"{fn[:-3]}   [{who.group(1).strip() if who else '?'}]   ({repo.split('/')[0]})")
        if role:
            print("  ROLE  :", " ".join(role.group(1).split())[:340])
        if fmt:
            print("  FORMAT:", " ".join(fmt.group(1).split())[:200])
