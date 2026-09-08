#!/usr/bin/env python3
"""Teacher outreach 26/27: build Wave 2 of the campaign rail (the remaining
stranger schools) as a static list + a workflow created OFF, reusing the three
published stranger-school emails. Roman 2026-09-08: "what's missing that we can
act on today" — 182 teachers were queued on list 3212 with no workflow behind them.

  python3 scripts/teacher_outreach_wave2.py            # dry run: who would be in Wave 2
  python3 scripts/teacher_outreach_wave2.py --create   # list + workflow (OFF)

Wave 2 = list 3212 minus list 3215 (Wave 1), minus generic inboxes, opt-outs,
bounces, no-email. Turning the workflow ON is a human decision after Wave 1's
day-10 numbers (ops/messenger/CAMPAIGN-2026-09-08-teachers.md).
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teacher_outreach_workflows as w   # hs(), payload()

LIST_STRANGER, LIST_WAVE1 = 3212, 3215
WAVE2_NAME = "Teacher Outreach 26/27 - 3b Wave 2 remaining stranger schools (campaign)"
WF_NAME = "Teacher Outreach 26/27 - Campaign - Wave 2 (remaining stranger schools)"
EMAILS = ("221134168440", "221140381845", "221140381849")   # stranger-school email 1/2/3, published


def members(list_id):
    ids, after = [], None
    while True:
        j = w.hs("GET", f"/crm/v3/lists/{list_id}/memberships?limit=250" + (f"&after={after}" if after else ""))
        ids += [str(m["recordId"]) for m in j.get("results", [])]
        after = (j.get("paging", {}).get("next") or {}).get("after")
        if not after:
            return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--create", action="store_true")
    args = ap.parse_args()
    pool = sorted(set(members(LIST_STRANGER)) - set(members(LIST_WAVE1)))
    props = {}
    for i in range(0, len(pool), 100):
        j = w.hs("POST", "/crm/v3/objects/contacts/batch/read",
                 json={"inputs": [{"id": c} for c in pool[i:i + 100]],
                       "properties": ["email", "school_canonical", "generic_inbox", "hs_email_optout", "hs_email_bounce"]})
        for r in j.get("results", []):
            props[str(r["id"])] = r.get("properties", {})
    keep, skipped = [], collections.Counter()
    for c in pool:
        p = props.get(c, {})
        if not p.get("email"): skipped["no email"] += 1; continue
        if (p.get("hs_email_optout") or "").lower() == "true": skipped["opted out"] += 1; continue
        if (p.get("hs_email_bounce") or "0") not in ("0", ""): skipped["bounced"] += 1; continue
        if (p.get("generic_inbox") or "") == "true": skipped["generic inbox"] += 1; continue
        keep.append(c)
    print(f"Wave 2 pool: {len(pool)} on 3212 not in Wave 1 → {len(keep)} mailable; skipped {dict(skipped)}")
    print("by school:", collections.Counter(props[c].get("school_canonical") for c in keep).most_common())
    if not args.create:
        print("DRY RUN — nothing created. Re-run with --create."); return
    s = w.hs("POST", "/crm/v3/lists/search", json={"query": WAVE2_NAME, "count": 20})
    hit = next((l for l in s.get("lists", []) if l.get("name") == WAVE2_NAME), None)
    lid = hit["listId"] if hit else w.hs("POST", "/crm/v3/lists", json={"name": WAVE2_NAME, "objectTypeId": "0-1",
                                                                     "processingType": "MANUAL"})["list"]["listId"]
    for i in range(0, len(keep), 250):
        w.hs("PUT", f"/crm/v3/lists/{lid}/memberships/add", json=keep[i:i + 250])
    print(f"  ✔ list {lid}: {len(keep)} members")
    f = w.hs("POST", "/automation/v4/flows", json=w.payload(WF_NAME, lid, *EMAILS))
    print(f"  ✔ workflow {f.get('id')} enabled={f.get('isEnabled')}\n     https://app.hubspot.com/workflows/6312752/platform/flow/{f.get('id')}/edit")
    out = Path("ops/messenger/state/teacher-outreach-2026-09/teacher_outreach_wave2.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"wave2_list": lid, "workflow": f.get("id"), "members": len(keep)}, indent=1))


if __name__ == "__main__":
    main()
