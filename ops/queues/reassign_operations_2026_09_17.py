"""Move every open ticket still owned by the former operations seat to the
current one, one PATCH at a time with a note on each.

Why: the 2026-09-16 queue migration ran on 2026-09-17 with the operations
owner id hard-coded to Mandy (80047201), the morning she left. Roman set
Emily (39191217) as interim operations the same day.

Run from a terminal (bulk HubSpot writes are blocked for agent sessions):
    python3 ops/queues/reassign_operations_2026_09_17.py          # dry run
    python3 ops/queues/reassign_operations_2026_09_17.py --live
Token: HUBSPOT_PRIVATE_APP_TOKEN in the env or in ~/code/aplus-agents/.env.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

OLD, NEW = "80047201", "39191217"          # Mandy -> Emily (interim operations)
CLOSED = ["4", "1439476620", "1439476617", "1439476618", "1439476619", "1439554388"]
NOTE = ("Owner moved to the operations seat (Emily, interim) after the 2026-09-16 "
        "queue migration. Roman 2026-09-17.")

tok = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
if not tok:
    env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    for ln in open(env):
        if ln.startswith("HUBSPOT_PRIVATE_APP_TOKEN="):
            tok = ln.split("=", 1)[1].strip().strip('"').strip("'")
H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}


def call(method, path, body=None):
    r = urllib.request.Request("https://api.hubapi.com" + path,
                               data=json.dumps(body).encode() if body else None, headers=H, method=method)
    return json.load(urllib.request.urlopen(r))


def main():
    live = "--live" in sys.argv
    body = {"filterGroups": [{"filters": [
        {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": OLD},
        {"propertyName": "hs_pipeline_stage", "operator": "NOT_IN", "values": CLOSED}]}],
        "properties": ["subject", "hs_pipeline"], "limit": 100}
    rows = call("POST", "/crm/v3/objects/tickets/search", body)["results"]
    print(f"{'LIVE' if live else 'DRY'}: {len(rows)} open tickets on {OLD} -> {NEW}")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in rows:
        p = t["properties"]
        print(f"  {t['id']} pipeline={p.get('hs_pipeline')} {(p.get('subject') or '')[:60]}")
        if not live:
            continue
        call("PATCH", f"/crm/v3/objects/tickets/{t['id']}", {"properties": {"hubspot_owner_id": NEW}})
        n = call("POST", "/crm/v3/objects/notes", {"properties": {"hs_timestamp": stamp, "hs_note_body": NOTE}})
        call("PUT", f"/crm/v4/objects/notes/{n['id']}/associations/default/tickets/{t['id']}")
    print("done" if live else "dry run only; add --live to execute")


if __name__ == "__main__":
    main()
