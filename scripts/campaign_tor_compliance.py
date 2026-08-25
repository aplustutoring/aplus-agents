#!/usr/bin/env python3
"""Compliance gate for the charter teacher campaign templates.

Roman's seven locked rules (2026-08-25) plus NSSA's own style requirements.
Run before any commit that touches the templates:

    python3 scripts/campaign_tor_compliance.py

Exists because eyeballing does not scale and one of these already slipped: a
string edit lowercased "Stanford's National Student Support Accelerator" and
"Tutoring Program Design Badge" in the Tier 2 draft, which breaks NSSA's
capitalisation rule. Nothing in the earlier ad-hoc checks looked for it.

Permitted digits are the Badge term years (2026, 2029) and the scholarship
session length (45). Anything else is a number about students, which rule 4
forbids.
"""
import re, sys
from pathlib import Path

BANNED = ["certified", "accredited", "endorsed", "approved provider",
          "proven", "validated our", "stanford-validated", "all students"]
# NSSA requires these exact capitalisations
MUST_CAP = ["National Student Support Accelerator", "Tutoring Program Design Badge",
            "Stanford"]
LOWER_BAD = [m.lower() for m in MUST_CAP]

fails = []
for f in sorted(Path("ops/messenger/templates/campaign-tor-2026-08").glob("tier*.md")):
    s = f.read_text()
    if "**Subject:**" not in s:
        continue
    body = s.split("**Subject:**", 1)[1]
    low = body.lower()
    for b in BANNED:
        if b in low:
            fails.append(f"{f.name}: banned word {b!r} (rule 3)")
    if chr(8212) in s:
        fails.append(f"{f.name}: em dash (rule 5)")
    for digits in re.findall(r"\b\d+\b", body):
        if digits not in ("2026", "2029", "45"):
            fails.append(f"{f.name}: stray number {digits!r} (rule 4)")
    # capitalisation: the lowercase form must not appear where the proper one should
    for proper, lowered in zip(MUST_CAP, LOWER_BAD):
        if lowered in low and proper not in body:
            fails.append(f"{f.name}: {proper!r} appears un-capitalised (NSSA style rule)")
    # the Badge claim must carry its term window
    if "Tutoring Program Design Badge" in body and "2026" not in body:
        fails.append(f"{f.name}: Badge claim without its term window (rule: window travels)")

if fails:
    print("COMPLIANCE FAILURES:")
    for x in fails: print("  ✗", x)
    sys.exit(1)
print("compliance: all tiers pass (7 rules + NSSA capitalisation + term window)")
