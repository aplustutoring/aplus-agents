#!/usr/bin/env python3
"""
A+ Tutoring — Archive disabled HubSpot workflows (Fleet Manager executor)

The deliberate WRITE counterpart to the read-only audit. Scope is exactly one
approved decision: delete workflows that are currently DISABLED, after backing
up their full JSON into the repo. It will never touch an enabled workflow.

Safety model:
  1. DRY-RUN by default — prints the manifest, deletes nothing.
     Execution requires BOTH --execute and --i-understand-deletion.
  2. Full JSON of every candidate is written to archive/<date>/ BEFORE any
     delete (HubSpot: API deletes are only restorable via HubSpot Support;
     UI deletes sit in "recently deleted" ~90 days).
  3. Cross-reference guard: a disabled workflow whose id appears anywhere in
     an ENABLED workflow's JSON (triggers, exclusions, unenrollment settings)
     is HELD — listed for manual review, never auto-deleted.
  4. Canary: the first delete is verified (DELETE 2xx + subsequent GET 404)
     before the bulk pass proceeds. The v4 docs show two path shapes; the
     canary resolves which one this portal accepts instead of guessing.
  5. Every run writes a manifest + outcome JSON to runs/ for the paper trail.

Usage:
  HUBSPOT_AUDIT_TOKEN=... python3 archive_disabled_workflows.py             # dry-run
  HUBSPOT_AUDIT_TOKEN=... python3 archive_disabled_workflows.py \
      --execute --i-understand-deletion                                     # for real
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://api.hubapi.com"
AUDIT_DIR = Path(__file__).resolve().parent
NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")


def log(msg):
    print(f"[archive] {msg}", flush=True)


def die(msg, code=2):
    print(f"[archive] FATAL: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "unnamed").lower()).strip("-")[:60]


class Client:
    """GET everywhere; DELETE allowed ONLY on the two workflow-delete paths,
    and only when constructed with deletes_armed=True."""

    DELETE_OK = (re.compile(r"^/automation/v4/(flows/)?\d+$"),
                 re.compile(r"^/automation/v3/workflows/\d+$"))

    def __init__(self, token, deletes_armed=False):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.deletes_armed = deletes_armed

    def _req(self, method, path, **kw):
        if method == "DELETE":
            if not self.deletes_armed:
                raise RuntimeError("delete attempted in dry-run mode")
            if not any(p.match(path) for p in self.DELETE_OK):
                raise RuntimeError(f"delete blocked for path: {path}")
        elif method != "GET":
            raise RuntimeError(f"blocked method: {method}")
        for attempt in range(5):
            resp = self.session.request(method, BASE + path, timeout=30, **kw)
            if resp.status_code == 429:
                time.sleep(min(float(resp.headers.get("Retry-After", 2 ** attempt)), 30))
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def get(self, path, params=None):
        return self._req("GET", path, params=params)

    def get_json(self, path, params=None):
        r = self.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def delete(self, path):
        return self._req("DELETE", path)


def fetch_inventory(client):
    """v4 flows with details, plus standalone v3 classic workflows (same
    name-merge rule as the audit so the two tools see the same census)."""
    flows = {}
    after = None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        page = client.get_json("/automation/v4/flows", params=params)
        for s in page.get("results", []):
            flows[str(s["id"])] = {"summary": s, "api": "v4"}
        after = (page.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    for fid, entry in flows.items():
        entry["detail"] = client.get_json(f"/automation/v4/flows/{fid}")

    v4_names = {(e["detail"].get("name") or "").strip().lower() for e in flows.values()}
    v3_standalone = []
    try:
        v3 = client.get_json("/automation/v3/workflows").get("workflows", [])
        for wf in v3:
            if (wf.get("name") or "").strip().lower() not in v4_names:
                v3_standalone.append(wf)
    except Exception as exc:
        log(f"v3 list unavailable ({exc}); v3-only workflows skipped this run")
    return flows, v3_standalone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="actually delete (default is dry-run)")
    ap.add_argument("--i-understand-deletion", action="store_true",
                    help="required with --execute: API deletes are only "
                         "restorable via HubSpot Support")
    args = ap.parse_args()

    do_execute = args.execute and args.i_understand_deletion
    if args.execute and not args.i_understand_deletion:
        die("--execute requires --i-understand-deletion")

    token = os.environ.get("HUBSPOT_AUDIT_TOKEN")
    if not token:
        die("HUBSPOT_AUDIT_TOKEN is not set")
    client = Client(token, deletes_armed=do_execute)

    log(f"mode: {'EXECUTE — deletions armed' if do_execute else 'DRY-RUN'}")
    flows, v3_standalone = fetch_inventory(client)
    log(f"inventory: {len(flows)} v4 flows, {len(v3_standalone)} standalone v3")

    disabled_v4 = {fid: e for fid, e in flows.items()
                   if not e["detail"].get("isEnabled")}
    disabled_v3 = [wf for wf in v3_standalone if not wf.get("enabled")]
    enabled_v4 = {fid: e for fid, e in flows.items()
                  if e["detail"].get("isEnabled")}
    log(f"disabled: {len(disabled_v4)} v4 + {len(disabled_v3)} standalone v3; "
        f"enabled (untouched): {len(enabled_v4)}")

    # Cross-reference guard: hold any disabled workflow an ENABLED one mentions.
    enabled_blobs = {fid: json.dumps(e["detail"]) for fid, e in enabled_v4.items()}
    held, kill_v4 = [], []
    for fid, e in sorted(disabled_v4.items(), key=lambda kv: kv[0]):
        referencing = [ename for eid, ename in
                       ((eid, enabled_v4[eid]["detail"].get("name"))
                        for eid in enabled_blobs)
                       if re.search(rf'\b{re.escape(fid)}\b', enabled_blobs[eid])]
        if referencing:
            held.append({"id": fid, "name": e["detail"].get("name"),
                         "referenced_by": referencing[:5]})
        else:
            kill_v4.append((fid, e))

    manifest = {
        "run_at": NOW.isoformat(timespec="seconds"),
        "mode": "execute" if do_execute else "dry-run",
        "to_delete_v4": [{"id": fid, "name": e["detail"].get("name")}
                         for fid, e in kill_v4],
        "to_delete_v3": [{"id": str(wf.get("id")), "name": wf.get("name")}
                         for wf in disabled_v3],
        "held_for_manual_review": held,
        "enabled_untouched": len(enabled_v4),
    }

    # Backup BEFORE anything else.
    backup_dir = AUDIT_DIR / "archive" / TODAY
    backup_dir.mkdir(parents=True, exist_ok=True)
    for fid, e in kill_v4:
        (backup_dir / f"v4-{fid}__{slug(e['detail'].get('name'))}.json"
         ).write_text(json.dumps(e["detail"], indent=2), encoding="utf-8")
    for wf in disabled_v3:
        (backup_dir / f"v3-{wf.get('id')}__{slug(wf.get('name'))}.json"
         ).write_text(json.dumps(wf, indent=2), encoding="utf-8")
    for entry in held:
        fid = entry["id"]
        (backup_dir / f"HELD-v4-{fid}__{slug(entry['name'])}.json"
         ).write_text(json.dumps(disabled_v4[fid]["detail"], indent=2),
                      encoding="utf-8")
    runs_dir = AUDIT_DIR / "runs"
    runs_dir.mkdir(exist_ok=True)
    manifest_path = runs_dir / f"archive-disabled-{TODAY}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"backed up {len(kill_v4) + len(disabled_v3)} workflow JSONs → {backup_dir}")
    log(f"manifest → {manifest_path}")
    if held:
        log(f"HELD {len(held)} disabled workflows referenced by enabled ones "
            "— review manually, not deleted:")
        for h in held:
            log(f"  · {h['name']} (id {h['id']}) referenced by: "
                f"{', '.join(h['referenced_by'])}")

    if not do_execute:
        log(f"DRY-RUN complete: would delete {len(kill_v4)} v4 + "
            f"{len(disabled_v3)} v3 workflows. Re-run with "
            "--execute --i-understand-deletion to proceed.")
        return

    # Canary: resolve the correct delete path shape on ONE workflow first.
    def delete_v4(fid):
        r = client.delete(f"/automation/v4/flows/{fid}")
        if r.status_code in (404, 405):
            r = client.delete(f"/automation/v4/{fid}")
        return r

    results = {"deleted": [], "failed": []}
    if kill_v4:
        cid, ce = kill_v4[0]
        log(f"canary: deleting v4 {cid} “{ce['detail'].get('name')}”…")
        r = delete_v4(cid)
        gone = client.get(f"/automation/v4/flows/{cid}").status_code == 404
        if not (r.status_code < 300 and gone):
            die(f"canary failed (DELETE {r.status_code}, gone={gone}) — "
                "aborting before bulk pass. Nothing else was deleted.")
        log("canary verified (DELETE ok + GET now 404) — proceeding")
        results["deleted"].append({"id": cid, "name": ce["detail"].get("name")})
        kill_v4 = kill_v4[1:]

    for i, (fid, e) in enumerate(kill_v4, 1):
        name = e["detail"].get("name")
        r = delete_v4(fid)
        if r.status_code < 300:
            results["deleted"].append({"id": fid, "name": name})
        else:
            results["failed"].append({"id": fid, "name": name,
                                      "status": r.status_code,
                                      "body": r.text[:200]})
        if i % 20 == 0:
            log(f"  … {i}/{len(kill_v4)} v4 deletes done")
        time.sleep(0.15)   # stay well under rate limits

    for wf in disabled_v3:
        wid = wf.get("id")
        r = client.delete(f"/automation/v3/workflows/{wid}")
        if r.status_code < 300:
            results["deleted"].append({"id": f"v3-{wid}", "name": wf.get("name")})
        else:
            results["failed"].append({"id": f"v3-{wid}", "name": wf.get("name"),
                                      "status": r.status_code,
                                      "body": r.text[:200]})
        time.sleep(0.15)

    manifest["results"] = results
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"EXECUTE complete: {len(results['deleted'])} deleted, "
        f"{len(results['failed'])} failed, {len(held)} held. "
        f"Outcome recorded in {manifest_path}")
    if results["failed"]:
        for f in results["failed"][:10]:
            log(f"  FAILED {f['id']} “{f['name']}” HTTP {f['status']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
