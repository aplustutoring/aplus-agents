#!/usr/bin/env python3
"""
event_lists.py — one active HubSpot list per event (Roman 2026-09-22).

Every event A+ shows up at gets a segment in HubSpot: an ACTIVE contact list
named "Event: <label>" for each option of the multi-select `aplus_event_tag`
property, filtered on contacts carrying that tag. Active, not static, so a
late booth submission or a backfill joins on its own.

Options are read from the PORTAL (the enumeration rule: read the labels),
not from properties.yml, so an option added by hand still gets a list.
Existing lists are matched by exact name and never touched. Idempotent.

  python3 event_lists.py --dry-run   # print the plan, write nothing
  python3 event_lists.py             # create the missing lists

Auth: HUBSPOT_API_KEY or HUBSPOT_PRIVATE_APP_TOKEN (env, or repo-root .env).
Runs on Actions right after the property sync (hubspot-schema.yml), which is
the moment a new event exists in the portal.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
log = logging.getLogger("event_lists")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY", "") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
HS_BASE = "https://api.hubapi.com"
TAG_PROPERTY = "aplus_event_tag"
NAME_PREFIX = "Event: "
CONTACTS = "0-1"


def hs(method, path, payload=None):
    r = requests.request(
        method, f"{HS_BASE}{path}",
        headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


# ---------- pure helpers (unit-tested) ----------

def list_name(label):
    """'Sage Oak Park Day 2026' -> 'Event: Sage Oak Park Day 2026'."""
    return f"{NAME_PREFIX}{str(label).strip()}"


def filter_branch(value):
    """Contacts whose aplus_event_tag (multi-checkbox) includes `value`."""
    return {
        "filterBranchType": "OR",
        "filterBranchOperator": "OR",
        "filters": [],
        "filterBranches": [{
            "filterBranchType": "AND",
            "filterBranchOperator": "AND",
            "filterBranches": [],
            "filters": [{
                "filterType": "PROPERTY",
                "property": TAG_PROPERTY,
                "operation": {
                    "operationType": "ENUMERATION",
                    "operator": "IS_ANY_OF",
                    "values": [value],
                    "includeObjectsWithNoValueSet": False,
                },
            }],
        }],
    }


def create_payload(value, label):
    return {
        "name": list_name(label),
        "objectTypeId": CONTACTS,
        "processingType": "DYNAMIC",
        "filterBranch": filter_branch(value),
    }


def is_duplicate_name(error_text):
    """HubSpot refuses a second list with the same name (ILS.DUPLICATE_LIST_NAMES)."""
    return "DUPLICATE_LIST_NAMES" in error_text or "already exist" in error_text


def plan(options, existing_names):
    """options: [{value,label}], existing_names: set of list names -> (create, keep)."""
    create, keep = [], []
    for opt in options:
        name = list_name(opt["label"])
        (keep if name in existing_names else create).append({**opt, "name": name})
    return create, keep


# ---------- portal I/O ----------

def portal_options():
    prop = hs("GET", f"/crm/v3/properties/contacts/{TAG_PROPERTY}")
    return [{"value": o["value"], "label": o["label"]}
            for o in prop.get("options", []) if not o.get("hidden")]


def existing_event_lists():
    """All lists whose name starts with the prefix, by exact name."""
    names, offset = {}, 0
    while True:
        page = hs("POST", "/crm/v3/lists/search",
                  {"query": "Event", "count": 200, "offset": offset})
        for l in page.get("lists", []):
            if l["name"].startswith(NAME_PREFIX):
                names[l["name"]] = l["listId"]
        if not page.get("hasMore"):
            return names
        offset = page.get("offset", offset + 200)


def main():
    ap = argparse.ArgumentParser(description="One active HubSpot list per event")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args()
    if not HUBSPOT_API_KEY:
        log.error("HUBSPOT_API_KEY / HUBSPOT_PRIVATE_APP_TOKEN not set")
        return 2

    options = portal_options()
    existing = existing_event_lists()
    create, keep = plan(options, set(existing))
    created = kept_late = 0
    for k in keep:
        log.info("keep    %-45s list %s", k["name"], existing[k["name"]])
    for c in create:
        if args.dry_run:
            log.info("WOULD CREATE %-40s (%s = %s)", c["name"], TAG_PROPERTY, c["value"])
            continue
        try:
            made = hs("POST", "/crm/v3/lists", create_payload(c["value"], c["label"]))
        except RuntimeError as e:
            # List search is eventually consistent: a list made moments ago
            # can be missing from the search and then refused here as a
            # duplicate name. That IS the list we want, so it counts as kept.
            if is_duplicate_name(str(e)):
                log.info("exists  %-45s (search lag; not recreated)", c["name"])
                kept_late += 1
                continue
            raise
        list_id = made.get("list", {}).get("listId") or made.get("listId")
        log.info("created %-45s list %s", c["name"], list_id)
        created += 1
    if args.dry_run:
        log.info("%d event options, %d lists kept, %d would be created", len(options), len(keep), len(create))
    else:
        log.info("%d event options, %d lists kept, %d created", len(options), len(keep) + kept_late, created)
    return 0


if __name__ == "__main__":
    sys.exit(main())
