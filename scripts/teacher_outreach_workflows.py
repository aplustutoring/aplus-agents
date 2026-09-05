#!/usr/bin/env python3
"""Teacher outreach 26/27: create the campaign-rail workflows (OFF) that send
the three drafts to lists 3 (wave 1) and 4 (IEM).

Shape cloned from the August family workflow 1868435042 (list-based
enrollment, weekday 9-17 send windows, reply-date exit) with the teacher
rules applied: no task step, no call, exit also on `campaign_replied = Yes`
and on a Teacher Scholarship nomination (the form stamps
teacher_scholarship_nomination__student_1__student_first_name), and on a new
26/27 charter deal associated to the contact.

  python3 scripts/teacher_outreach_workflows.py            # dry run: prints the two payloads
  python3 scripts/teacher_outreach_workflows.py --create   # POSTs both, disabled

Email ids come from teacher_outreach_drafts.json (--drafts). Roman/Danielle
publish the emails and enable the workflow in the portal on send day.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent.parent
    load_dotenv(_here / ".env", override=False)
    if "/.claude/worktrees/" in str(_here):
        load_dotenv(Path(str(_here).split("/.claude/worktrees/")[0]) / ".env", override=False)
except ImportError:
    pass

HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "") or os.getenv("HUBSPOT_API_KEY", "")
HS_BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
CHARTER_PIPELINES = ["1066195", "5119061", "907748", "72281989", "88841552"]
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]


def hs(method, path, **kw):
    for _ in range(6):
        r = requests.request(method, f"{HS_BASE}{path}", headers=H, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)) or 10)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.text else {}


def prop_filter(prop, operator, values=None, op_type="ALL_PROPERTY"):
    op = {"operator": operator, "includeObjectsWithNoValueSet": False, "operationType": op_type}
    if values is not None:
        op["values"] = values
    return {"property": prop, "operation": op, "filterType": "PROPERTY"}


def branch(filters, sub=None):
    return {"filterBranches": sub or [], "filters": filters, "filterBranchType": "AND", "filterBranchOperator": "AND"}


def goal_branch():
    """Exit when ANY of: replied by email, campaign_replied stamped, nominated a
    scholarship student, or a 26/27 charter deal now names them."""
    deal_assoc = {
        "filterBranches": [], "objectTypeId": "0-3", "operator": "IN_LIST", "associationTypeId": 4,
        "associationCategory": "HUBSPOT_DEFINED", "filterBranchType": "ASSOCIATION", "filterBranchOperator": "AND",
        "filters": [prop_filter("pipeline", "IS_ANY_OF", CHARTER_PIPELINES, "ENUMERATION"),
                    prop_filter("dealname", "CONTAINS", ["26/27"], "MULTISTRING")],
    }
    return {"filterBranches": [
        branch([], [deal_assoc]),
        branch([prop_filter("hs_email_last_reply_date", "IS_KNOWN")]),
        branch([prop_filter("campaign_replied", "IS_ANY_OF", ["true"], "ENUMERATION")]),
        branch([prop_filter("teacher_scholarship_nomination__student_1__student_first_name", "IS_KNOWN")]),
    ], "filters": [], "filterBranchType": "OR", "filterBranchOperator": "OR"}


def send(aid, content_id, nxt):
    return {"actionId": str(aid), "actionTypeId": "0-4", "actionTypeVersion": 0, "type": "SINGLE_CONNECTION",
            "fields": {"content_id": str(content_id)}, "connection": {"edgeType": "STANDARD", "nextActionId": str(nxt)}}


def delay_days(aid, days, nxt):
    return {"actionId": str(aid), "actionTypeId": "0-1", "actionTypeVersion": 0, "type": "SINGLE_CONNECTION",
            "fields": {"delta": str(days), "time_unit": "DAYS", "time_of_day": {"hour": 9, "minute": 0}},
            "connection": {"edgeType": "STANDARD", "nextActionId": str(nxt)}}


def payload(name, list_id, e1, e2, e3):
    return {
        "name": name, "type": "CONTACT_FLOW", "objectTypeId": "0-1", "flowType": "WORKFLOW", "isEnabled": False,
        "description": ("Teacher outreach 26/27, campaign rail. Copy: ops/messenger/templates/teacher-outreach-2026-09/"
                        "campaign_cold.md. Email only, no call (Roman 2026-09-03). Exits on reply, campaign_replied, "
                        "scholarship nomination, or a new 26/27 charter deal."),
        "startActionId": "1", "nextAvailableActionId": "6",
        "actions": [send(1, e1, 2), delay_days(2, 4, 3), send(3, e2, 4), delay_days(4, 6, 5),
                    {"actionId": "5", "actionTypeId": "0-4", "actionTypeVersion": 0, "type": "SINGLE_CONNECTION",
                     "fields": {"content_id": str(e3)}}],
        "enrollmentCriteria": {"shouldReEnroll": False, "type": "LIST_BASED", "unEnrollObjectsNotMeetingCriteria": False,
                               "reEnrollmentTriggersFilterBranches": [],
                               "listFilterBranch": {"filterBranches": [branch([{"listId": str(list_id), "operator": "IN_LIST", "filterType": "IN_LIST"}])],
                                                    "filters": [], "filterBranchType": "OR", "filterBranchOperator": "OR"}},
        "goalFilterBranch": goal_branch(),
        "timeWindows": [{"day": d, "startTime": {"hour": 9, "minute": 0}, "endTime": {"hour": 17, "minute": 0}} for d in DAYS],
        "blockedDates": [], "suppressionListIds": [], "canEnrollFromSalesforce": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", default="teacher_outreach_drafts.json")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--out", default="teacher_outreach_workflows.json")
    args = ap.parse_args()
    if not HUBSPOT_TOKEN:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN missing")
    snap = json.loads(Path(args.drafts).read_text())
    d = {k.split(" - ")[-1]: v for k, v in snap["drafts"].items()}   # "Email 1 (stranger schools)" -> {...}
    plans = [
        ("Teacher Outreach 26/27 - Campaign - Wave 1 (Compass + Elite)", snap["wave1_list"],
         d["Email 1 (stranger schools)"]["email_id"], d["Email 2 (stranger schools)"]["email_id"], d["Email 3 (stranger schools)"]["email_id"]),
        ("Teacher Outreach 26/27 - Campaign - IEM Education Specialists", d["Email 1 (IEM)"]["list_id"],
         d["Email 1 (IEM)"]["email_id"], d["Email 2 (IEM)"]["email_id"], d["Email 3 (IEM)"]["email_id"]),
    ]
    out = {}
    for name, lid, e1, e2, e3 in plans:
        body = payload(name, lid, e1, e2, e3)
        print(f"\n{name}\n  list {lid} | emails {e1} → +4d → {e2} → +6d → {e3} | OFF | weekdays 9-17 | 4 exit conditions")
        if not args.create:
            continue
        f = hs("POST", "/automation/v4/flows", json=body)
        out[name] = {"flow_id": f.get("id"), "list_id": lid, "enabled": f.get("isEnabled"),
                     "url": f"https://app.hubspot.com/workflows/6312752/platform/flow/{f.get('id')}/edit"}
        print(f"  ✔ workflow {f.get('id')} (enabled={f.get('isEnabled')})\n     {out[name]['url']}")
    if args.create:
        Path(args.out).write_text(json.dumps(out, indent=1))
        print(f"\nsnapshot → {args.out}")
    else:
        print("\nDRY RUN — nothing created. Re-run with --create.")


if __name__ == "__main__":
    main()
