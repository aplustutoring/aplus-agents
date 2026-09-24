#!/usr/bin/env python3
"""Fleet model-policy check: one declared source, no silent drift.

`models:` in email/config.yaml is the source of truth (see the comment there).
This script fails when any agent runs a model that is not one of the declared
tier values, and reports every file still carrying a hardcoded id instead of
naming a tier.

Two different things, deliberately:

  DRIFT (fails)  a hardcoded model string that matches no declared tier. This
                 is an agent nobody knows the model of, which is exactly the
                 state this policy exists to end.
  HARDCODED (warns) a string that matches a tier value but is written out
                 longhand. Correct today, but it will not follow the next
                 upgrade, so it is listed until it names a tier instead.

    python3 ops/fleet-health/model_check.py [--strict]   # --strict fails on warnings too
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODEL_RE = re.compile(r"claude-(?:opus|sonnet|haiku|fable|mythos)-[0-9][\w.-]*")
# Prose, history and generated inventories name models legitimately.
SKIP_DIRS = {".git", "node_modules", "docs", "knowledge", "corrections", "archive", "__pycache__"}
SKIP_FILES = {"registry.yml", "config.yaml"}          # config.yaml holds the block itself
SUFFIXES = {".py", ".yml", ".yaml"}


def declared() -> dict:
    cfg = yaml.safe_load((ROOT / "email" / "config.yaml").read_text()) or {}
    m = cfg.get("models") or {}
    if not m:
        sys.exit("email/config.yaml has no `models:` block — the policy is the point")
    return m


def scan(values: set) -> tuple[list, list]:
    drift, hardcoded = [], []
    for p in ROOT.rglob("*"):
        if p.suffix not in SUFFIXES or p.name in SKIP_FILES:
            continue
        if SKIP_DIRS & set(p.relative_to(ROOT).parts):
            continue
        try:
            lines = p.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for hit in MODEL_RE.findall(line):
                rel = f"{p.relative_to(ROOT)}:{n}"
                (hardcoded if hit in values else drift).append((rel, hit, line.strip()[:70]))
    return drift, hardcoded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail on hardcoded-but-correct too")
    strict = ap.parse_args().strict

    tiers = declared()
    values = set(tiers.values())
    print("Declared model policy (email/config.yaml `models:`)")
    for k, v in tiers.items():
        print(f"  {k:20} {v}")

    drift, hardcoded = scan(values)
    if drift:
        print(f"\n✗ DRIFT — {len(drift)} model string(s) matching no declared tier:")
        for rel, hit, line in drift:
            print(f"  {rel}  {hit}\n      {line}")
    if hardcoded:
        print(f"\n⚠ HARDCODED — {len(hardcoded)} correct-but-longhand id(s); "
              f"these will not follow the next upgrade:")
        for rel, hit, _ in hardcoded:
            print(f"  {rel}  {hit}")
    if not drift and not hardcoded:
        print("\n✓ every agent names a tier; nothing hardcoded")

    if drift or (strict and hardcoded):
        sys.exit(1)


if __name__ == "__main__":
    main()
