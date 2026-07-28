#!/usr/bin/env python3
"""
HubSpot property/schema sync — properties.yml is the registry, the portal
follows it.

Idempotent and additive only:
  - creates missing property groups
  - creates missing properties
  - adds missing enumeration options to existing properties
  - NEVER deletes or renames anything, never touches HubSpot-defined
    properties (#AP008 spirit — schema changes are deliberate and reviewable)

`options_from: registry` generates enum options from registry.yml agent ids
(value = internal id, label = the human name — labels, never internal names,
in everything the team sees, #AP014).

Usage:
  python3 create_properties.py --dry-run    # print the plan, write nothing
  python3 create_properties.py              # apply
  CHECK_ONLY=true python3 create_properties.py   # secrets/config smoke test

Auth: HUBSPOT_API_KEY or HUBSPOT_PRIVATE_APP_TOKEN (env, or repo-root .env
locally). Requires the private app to have the crm.schemas.* write scope.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("hubspot-schema")

REPO_ROOT = Path(__file__).resolve().parents[2]

try:  # local runs pick up the repo-root .env (call-agent convention)
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY", "") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
HS_BASE = "https://api.hubapi.com"


def hs(method, path, payload=None):
    r = requests.request(
        method, f"{HS_BASE}{path}",
        headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def registry_agent_options():
    """Enum options from the fleet manifest: value = agent id, label = name."""
    reg = load_yaml(REPO_ROOT / "registry.yml")
    return [{"value": a["id"], "label": a.get("name", a["id"])}
            for a in reg.get("agents", [])]


def resolve_options(prop):
    opts = list(prop.get("options") or [])
    if prop.get("options_from") == "registry":
        have = {o["value"] for o in opts}
        opts += [o for o in registry_agent_options() if o["value"] not in have]
    return opts


def sync_groups(object_type, wanted, dry_run):
    existing = {g["name"] for g in hs("GET", f"/crm/v3/properties/{object_type}/groups").get("results", [])}
    for g in wanted:
        if g["name"] in existing:
            log.info(f"  group {g['name']}: exists")
            continue
        log.info(f"  group {g['name']}: CREATE ('{g['label']}')")
        if not dry_run:
            hs("POST", f"/crm/v3/properties/{object_type}/groups",
               {"name": g["name"], "label": g["label"]})


def sync_property(object_type, prop, existing_by_name, dry_run):
    name = prop["name"]
    options = resolve_options(prop)
    current = existing_by_name.get(name)

    if current is None:
        payload = {
            "name": name,
            "label": prop["label"],
            "type": prop["type"],
            "fieldType": prop["fieldType"],
            "groupName": prop["group"],
            "description": prop.get("description", ""),
            "formField": False,   # automation-set, not a form field
        }
        if options:
            payload["options"] = [
                {"value": o["value"], "label": o["label"], "displayOrder": i, "hidden": False}
                for i, o in enumerate(options)
            ]
        log.info(f"  {name}: CREATE ({prop['type']}/{prop['fieldType']}, "
                 f"{len(options)} options)")
        if not dry_run:
            hs("POST", f"/crm/v3/properties/{object_type}", payload)
        return "created"

    if prop["type"] != "enumeration":
        log.info(f"  {name}: exists")
        return "ok"

    # Option merge — PATCH replaces the option list, so send existing +
    # missing. Additive on VALUES (never removes, order of existing options
    # wins), but LABELS follow this registry (#AP014 — the label shown to the
    # team is declared here, so label drift heals on re-run).
    desired = {o["value"]: o["label"] for o in options}
    have = {o["value"] for o in current.get("options", [])}
    missing = [o for o in options if o["value"] not in have]
    relabeled = [o["value"] for o in current.get("options", [])
                 if o["value"] in desired and desired[o["value"]] != o["label"]]
    if not missing and not relabeled:
        log.info(f"  {name}: exists, options complete")
        return "ok"
    merged = [
        {"value": o["value"], "label": desired.get(o["value"], o["label"]),
         "displayOrder": i, "hidden": o.get("hidden", False)}
        for i, o in enumerate(current["options"])
    ] + [
        {"value": o["value"], "label": o["label"],
         "displayOrder": len(current["options"]) + i, "hidden": False}
        for i, o in enumerate(missing)
    ]
    changes = []
    if missing:
        changes.append("ADD " + ", ".join(o["value"] for o in missing))
    if relabeled:
        changes.append("RELABEL " + ", ".join(relabeled))
    log.info(f"  {name}: exists, " + " · ".join(changes))
    if not dry_run:
        hs("PATCH", f"/crm/v3/properties/{object_type}/{name}", {"options": merged})
    return "updated"


def main():
    ap = argparse.ArgumentParser(description="Sync properties.yml into HubSpot")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args()

    spec = load_yaml(Path(__file__).parent / "properties.yml")

    if os.getenv("CHECK_ONLY") == "true":
        if not HUBSPOT_API_KEY:
            log.error("CHECK_ONLY: HUBSPOT_API_KEY / HUBSPOT_PRIVATE_APP_TOKEN not set")
            sys.exit(1)
        n = sum(len(v) for v in spec.get("properties", {}).values())
        log.info(f"CHECK_ONLY: token wired, properties.yml parses ({n} properties), "
                 f"registry.yml parses ({len(registry_agent_options())} agents). OK.")
        return

    if not HUBSPOT_API_KEY:
        log.error("HUBSPOT_API_KEY / HUBSPOT_PRIVATE_APP_TOKEN not set")
        sys.exit(1)

    summary = {"created": 0, "updated": 0, "ok": 0}
    for object_type, groups in (spec.get("groups") or {}).items():
        log.info(f"{object_type} groups:")
        sync_groups(object_type, groups, args.dry_run)
    for object_type, props in (spec.get("properties") or {}).items():
        log.info(f"{object_type} properties:")
        existing = {p["name"]: p
                    for p in hs("GET", f"/crm/v3/properties/{object_type}").get("results", [])}
        for prop in props:
            summary[sync_property(object_type, prop, existing, args.dry_run)] += 1

    verb = "would be" if args.dry_run else "were"
    log.info(f"\n{summary['created']} {verb} created, {summary['updated']} {verb} "
             f"updated, {summary['ok']} already in sync.")


if __name__ == "__main__":
    main()
