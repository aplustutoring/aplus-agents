#!/usr/bin/env python3
"""Close every ticket still open from before 2026-09-01.

Roman, 2026-09-29: "Close everything before September 1."

A ticket that has been open across a month boundary and two school-year weeks
is not being worked; it is being carried. Closing it is a truer statement of
where things stand than leaving it to age, and HubSpot keeps it reopenable.

Each pipeline gets its own closed stage, taken from the pipeline definition
rather than hardcoded, and a note is added saying why it closed and on whose
instruction, so nobody finds it later and wonders.

Usage:
  python3 scripts/close_pre_september.py            # dry run
  python3 scripts/close_pre_september.py --execute
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
if load_dotenv:
    for _p in [HERE] + list(HERE.parents):
        if (_p / ".env").exists():
            load_dotenv(_p / ".env")
            break

HS = "https://api.hubapi.com"
TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
CUTOFF = "2026-09-01"


def hs(method: str, path: str, **kw):
    for _ in range(6):
        try:
            r = requests.request(method, HS + path, headers=H, timeout=60, **kw)
        except requests.exceptions.RequestException:
            time.sleep(3)
            continue
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        return r.json() if r.text else {}
    raise RuntimeError("gave up after six tries")


def pipelines():
    """(stage -> label, stage -> closed?, pipeline -> its closed stage id)."""
    label, is_closed, closer, pname = {}, {}, {}, {}
    for p in hs("GET", "/crm/v3/pipelines/tickets")["results"]:
        pname[p["id"]] = p["label"]
        closed_here = []
        for s in p["stages"]:
            label[s["id"]] = s["label"]
            shut = (s.get("metadata") or {}).get("isClosed") in (True, "true")
            is_closed[s["id"]] = shut
            if shut:
                closed_here.append(s)
        if closed_here:
            # prefer a stage that reads as resolved over one that reads as lost
            pick = next((s for s in closed_here
                         if "resolv" in s["label"].lower()
                         or "closed" in s["label"].lower()), closed_here[0])
            closer[p["id"]] = (pick["id"], pick["label"])
    return label, is_closed, closer, pname


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if not TOKEN:
        raise SystemExit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    mode = "EXECUTE" if a.execute else "DRY RUN"
    label, is_closed, closer, pname = pipelines()
    open_stages = [s for s, shut in is_closed.items() if not shut]

    rows, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "hs_pipeline_stage", "operator": "IN",
             "values": open_stages},
            {"propertyName": "createdate", "operator": "LT", "value": CUTOFF}]}],
            "properties": ["subject", "createdate", "hs_pipeline",
                           "hs_pipeline_stage", "hubspot_owner_id",
                           "case_client", "support_category"], "limit": 100}
        if after:
            body["after"] = after
        d = hs("POST", "/crm/v3/objects/tickets/search", json=body)
        rows += d.get("results", [])
        after = ((d.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break

    owners = {str(o["id"]): ("%s %s" % (o.get("firstName") or "",
                                        o.get("lastName") or "")).strip()
              for o in hs("GET", "/crm/v3/owners?limit=300").get("results", [])}
    now = datetime.now(timezone.utc)

    print(f"{'=' * 78}\n{mode}: close every ticket still open from before {CUTOFF}")
    print(f"open tickets created before {CUTOFF}: {len(rows)}\n")
    if not rows:
        return

    done, skipped = 0, []
    for r in sorted(rows, key=lambda x: x["properties"].get("createdate") or ""):
        p = r["properties"]
        pipe = p.get("hs_pipeline")
        created = (p.get("createdate") or "")[:10]
        try:
            age = (now - datetime.fromisoformat(
                p["createdate"].replace("Z", "+00:00"))).days
        except Exception:  # noqa: BLE001
            age = -1
        who = owners.get(str(p.get("hubspot_owner_id")), "(unassigned)").split(" ")[0]
        target = closer.get(pipe)
        if not target:
            skipped.append((r["id"], "that pipeline has no closed stage"))
            continue
        print(f"  {r['id']:<12} {created}  {age:>3}d  {who:<10} "
              f"{(p.get('subject') or '')[:44]:<44} "
              f"{label.get(p.get('hs_pipeline_stage'), '?')[:18]:<18} -> {target[1]}")
        if not a.execute:
            done += 1
            continue
        hs("PATCH", f"/crm/v3/objects/tickets/{r['id']}",
           json={"properties": {"hs_pipeline_stage": target[0]}})
        try:
            hs("POST", "/crm/v3/objects/notes", json={
                "properties": {
                    "hs_timestamp": int(time.time() * 1000),
                    "hs_note_body": (
                        f"Closed in the 2026-09-29 sweep of everything still open "
                        f"from before {CUTOFF} (Roman's instruction). This ticket "
                        f"was {age} days old and had not reached a resolution. "
                        f"Reopen it if the work is still live.")},
                "associations": [{"to": {"id": r["id"]},
                                  "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                             "associationTypeId": 228}]}]})
        except RuntimeError as e:
            print(f"        (note failed, ticket still closed: {e})")
        done += 1

    print(f"\n{'=' * 78}\nSUMMARY ({mode})")
    print(f"  closed          : {done}")
    print(f"  left alone      : {len(skipped)}")
    for pl, n in Counter(pname.get(r['properties'].get('hs_pipeline'), '?')
                         for r in rows).most_common():
        print(f"     {pl:<36} {n}")
    for tid, why in skipped:
        print(f"  SKIP {tid}: {why}")
    if not a.execute:
        print("\nDry run. Nothing was written. Re-run with --execute.")


if __name__ == "__main__":
    main()
