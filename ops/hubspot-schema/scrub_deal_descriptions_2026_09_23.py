"""One-off, human-run: money lives on the deal's Amount only (Roman 2026-09-23).

Step 1  every 26/27 deal description → no_money() (idempotent; the 2026-09-23
        first pass left a few clipped sentences that the tuned rules repair).
Step 2  open Support tickets and open tasks whose subject or body carries a
        dollar figure (PO watch / convert-to-invoice) → figure removed.
Step 3  Level Up deals (pipeline 88841552) named like Traditional ("iLead 4")
        → "<School> Level Up N", N counted per student inside that pipeline.

    python3 ops/hubspot-schema/scrub_deal_descriptions_2026_09_23.py          # dry run
    python3 ops/hubspot-schema/scrub_deal_descriptions_2026_09_23.py --live   # write

Token: HUBSPOT_PRIVATE_APP_TOKEN in the env or ~/code/aplus-agents/.env.
Human-run: bulk HubSpot writes are blocked for agent sessions.
"""
import json, os, re, sys, urllib.request
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "email"))
from src.po_inbox import no_money  # noqa: E402

LEVEL_UP_PIPELINE = "88841552"
OPEN_TICKET_STAGES_EXCLUDED = ["4", "1439476620", "131537028", "1263703060", "943335739"]   # Resolved, Won't fix, legacy

tok = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
if not tok:
    for ln in open(os.path.join(ROOT, ".env")):
        if ln.startswith("HUBSPOT_PRIVATE_APP_TOKEN="):
            tok = ln.split("=", 1)[1].strip().strip('"').strip("'")
H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}


def call(method, path, body=None):
    r = urllib.request.Request("https://api.hubapi.com" + path,
                               data=json.dumps(body).encode() if body else None, headers=H, method=method)
    return json.load(urllib.request.urlopen(r))


def search_all(obj, filters, props):
    rows, after = [], None
    while True:
        body = {"filterGroups": [{"filters": filters}], "properties": props, "limit": 100}
        if after:
            body["after"] = after
        d = call("POST", f"/crm/v3/objects/{obj}/search", body)
        rows += d.get("results", [])
        after = (d.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return rows


def subject_no_money(s: str) -> str:
    """'PO watch: Ana (iLEAD, PO 4471, $300)' → 'PO watch: Ana (iLEAD, PO 4471)'."""
    s = re.sub(r",\s*\$\s?\d[\d,]*(?:\.\d+)?\s*\)", ")", s or "")
    return no_money(s)


def body_no_money(s: str) -> str:
    """Drop the 'Amount: $300' line and the '@ $75/hr' tail from a ticket or task body."""
    s = re.sub(r"^Amount:.*\n?", "", s or "", flags=re.M)
    s = re.sub(r"\s*@\s*\$?\d[\d,]*(?:\.\d+)?\s*/\s*hr\b", "", s)
    return no_money(s)


def step_descriptions(live):
    rows = search_all("deals", [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": "26/27"},
                                {"propertyName": "description", "operator": "HAS_PROPERTY"}], ["dealname", "description"])
    todo = [(r["id"], r["properties"]["dealname"], r["properties"]["description"] or "")
            for r in rows if no_money(r["properties"]["description"] or "") != (r["properties"]["description"] or "").strip()]
    print(f"\nSTEP 1 descriptions: {len(rows)} 26/27 deals with a description, {len(todo)} change")
    for did, name, desc in todo:
        new = no_money(desc)
        print(f"\n{did} {name}\n  before: {desc[:600]}\n  after:  {new[:600]}")
        if live:
            call("PATCH", f"/crm/v3/objects/deals/{did}", {"properties": {"description": new}})


def step_tickets_and_tasks(live):
    tickets = search_all("tickets", [{"propertyName": "hs_pipeline", "operator": "EQ", "value": "0"},
                                     {"propertyName": "hs_pipeline_stage", "operator": "NOT_IN", "values": OPEN_TICKET_STAGES_EXCLUDED}],
                         ["subject", "content"])
    n = 0
    for t in tickets:
        p = t["properties"]
        subj, cont = p.get("subject") or "", p.get("content") or ""
        if not subj.startswith(("PO watch:", "new_po ")):        # only the PO agent's own tickets; AR / review stay
            continue
        ns, nc = subject_no_money(subj), body_no_money(cont)
        if ns != subj or nc != cont:
            n += 1
            print(f"\nticket {t['id']}\n  subject: {subj[:120]}\n       →   {ns[:120]}" + (f"\n  body changed" if nc != cont else ""))
            if live:
                call("PATCH", f"/crm/v3/objects/tickets/{t['id']}", {"properties": {"subject": ns, "content": nc}})
    tasks = search_all("tasks", [{"propertyName": "hs_task_status", "operator": "NEQ", "value": "COMPLETED"},
                                 {"propertyName": "hs_task_subject", "operator": "CONTAINS_TOKEN", "value": "invoice"}],
                       ["hs_task_subject", "hs_task_body"])
    m = 0
    for t in tasks:
        p = t["properties"]
        subj, body = p.get("hs_task_subject") or "", p.get("hs_task_body") or ""
        if not subj.startswith("Convert PO to TW invoice"):
            continue
        ns, nb = subject_no_money(subj), body_no_money(body)
        if ns != subj or nb != body:
            m += 1
            print(f"\ntask {t['id']}\n  subject: {subj[:120]}\n       →   {ns[:120]}" + (f"\n  body changed" if nb != body else ""))
            if live:
                call("PATCH", f"/crm/v3/objects/tasks/{t['id']}", {"properties": {"hs_task_subject": ns, "hs_task_body": nb}})
    print(f"\nSTEP 2 tickets/tasks: {len(tickets)} open Support tickets, {n} change; {len(tasks)} open invoice tasks, {m} change")


def step_level_up_names(live):
    rows = search_all("deals", [{"propertyName": "pipeline", "operator": "EQ", "value": LEVEL_UP_PIPELINE},
                                {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": "26/27"}],
                      ["dealname", "createdate", "student_first_name", "student_last_name_if_diff_from_parent"])
    rows.sort(key=lambda r: r["properties"]["createdate"])
    counts: dict = defaultdict(int)
    print(f"\nSTEP 3 Level Up names: {len(rows)} 26/27 deals in the Level Up pipeline")
    for r in rows:
        name = r["properties"]["dealname"] or ""
        m = re.match(r"^(.*?) - (.*?) - ([A-Za-z ]+?)(?: Level Up)? (\d+) - (\d\d/\d\d)$", name)
        if not m:
            print(f"  {r['id']} skip (name pattern): {name}")
            continue
        parent, student, school, _n, year = m.groups()
        counts[(student.lower(), year)] += 1
        new = f"{parent} - {student} - {school} Level Up {counts[(student.lower(), year)]} - {year}"
        if new != name:
            print(f"  {r['id']}: {name}  →  {new}")
            if live:
                call("PATCH", f"/crm/v3/objects/deals/{r['id']}", {"properties": {"dealname": new}})


def main():
    live = "--live" in sys.argv
    print("LIVE" if live else "DRY RUN (add --live to write)")
    step_descriptions(live)
    step_tickets_and_tasks(live)
    step_level_up_names(live)
    print("\ndone" if live else "\ndry run only; add --live to write")


if __name__ == "__main__":
    main()
