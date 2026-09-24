#!/usr/bin/env python3
"""Retire the contact→deal property copies now owned by email/src/student_stamp.py.

Roman, 2026-09-10: "turn off the workflows."

  34950163  "Contact to Deal Properties"  → switched OFF (all five copies are
            now fill-only in deal_sync; it overwrote per-deal student stamps on
            every sibling deal: Melara 9/4, Elenes 9/8).
  366207297 "Pipeline is Online Summer Boost, deal stage is Pre-Lesson"
            → ONLY its student_first_name copy (action 24) is removed; the
            other actions (lead status, TW sync flag, last_name, concerns)
            stay.

Backs both definitions up to backups/2026-09-10-contact-to-deal-workflows/
BEFORE writing, then verifies by re-reading. Dry run by default.

    python3 ops/fleet-health/audit/retire_contact_to_deal_workflows.py          # show
    python3 ops/fleet-health/audit/retire_contact_to_deal_workflows.py --live   # do it

Token: HUBSPOT_PRIVATE_APP_TOKEN (env or email/.env).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "email"))
from src.config import HUBSPOT_PRIVATE_APP_TOKEN as TOKEN  # noqa: E402

B = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BACKUP_DIR = Path(__file__).resolve().parent / "backups" / "2026-09-10-contact-to-deal-workflows"
OFF = "34950163"
TRIM = ("366207297", "24", "student_first_name")   # flow, action id, property it must be


def get(fid: str) -> dict:
    r = requests.get(f"{B}/automation/v4/flows/{fid}", headers=H, timeout=30)
    r.raise_for_status()
    return r.json()


def put(fid: str, body: dict) -> dict:
    r = requests.put(f"{B}/automation/v4/flows/{fid}", headers=H, json=body, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"PUT {fid} failed {r.status_code}: {r.text[:500]}")
    return r.json()


def setters(flow: dict) -> list[str]:
    return [a["fields"]["property_name"] for a in flow.get("actions", [])
            if a.get("actionTypeId") == "0-5"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    live = ap.parse_args().live
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    flows = {}
    for fid in (OFF, TRIM[0]):
        flows[fid] = get(fid)
        p = BACKUP_DIR / f"v4-{fid}.json"
        p.write_text(json.dumps(flows[fid], indent=1))
        print(f"backup {p.relative_to(Path.cwd()) if p.is_relative_to(Path.cwd()) else p}")
        print(f"  {fid} '{flows[fid]['name'].strip()}' enabled={flows[fid]['isEnabled']} "
              f"sets={setters(flows[fid])}")

    off = copy.deepcopy(flows[OFF])
    off["isEnabled"] = False
    trim = copy.deepcopy(flows[TRIM[0]])
    tgt = [a for a in trim["actions"] if a["actionId"] == TRIM[1]]
    if not tgt or tgt[0]["fields"].get("property_name") != TRIM[2]:
        raise SystemExit(f"flow {TRIM[0]} action {TRIM[1]} is not the {TRIM[2]} copy any more: {tgt}")
    nxt = (tgt[0].get("connection") or {}).get("nextActionId")
    for a in trim["actions"]:
        if (a.get("connection") or {}).get("nextActionId") == TRIM[1]:
            a["connection"]["nextActionId"] = nxt
            print(f"  rewire {TRIM[0]}: action {a['actionId']} -> {nxt}")
    if trim.get("startActionId") == TRIM[1]:
        trim["startActionId"] = nxt
    trim["actions"] = [a for a in trim["actions"] if a["actionId"] != TRIM[1]]

    if not live:
        print(f"\nDRY RUN — would: set {OFF} isEnabled=false; drop action {TRIM[1]} "
              f"({TRIM[2]}) from {TRIM[0]}. Re-run with --live.")
        return
    put(OFF, off)
    put(TRIM[0], trim)
    for fid in (OFF, TRIM[0]):
        d = get(fid)
        print(f"VERIFY {fid} '{d['name'].strip()}' enabled={d['isEnabled']} sets={setters(d)}")
    ok = (not get(OFF)["isEnabled"]) and (TRIM[2] not in setters(get(TRIM[0])))
    print("DONE" if ok else "CHECK FAILED — inspect the backups and the portal")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN not set")
    main()
