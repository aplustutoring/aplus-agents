"""One-off: strip dollar figures and hourly prices from the descriptions of
existing 26/27 deals (Roman 2026-09-23: the description is what the tutor
channel sees; po_inbox.no_money() guards new deals from here on).

    python3 ops/hubspot-schema/scrub_deal_descriptions_2026_09_23.py          # dry run, prints before/after
    python3 ops/hubspot-schema/scrub_deal_descriptions_2026_09_23.py --live   # PATCH each deal

Token: HUBSPOT_PRIVATE_APP_TOKEN in the env or ~/code/aplus-agents/.env.
Human-run: bulk HubSpot writes are blocked for agent sessions.
"""
import json, os, sys, urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "email"))
from src.po_inbox import no_money  # noqa: E402

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


def main():
    live = "--live" in sys.argv
    rows, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [
            {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": "26/27"},
            {"propertyName": "description", "operator": "HAS_PROPERTY"}]}],
            "properties": ["dealname", "description"], "limit": 100}
        if after:
            body["after"] = after
        d = call("POST", "/crm/v3/objects/deals/search", body)
        rows += d.get("results", [])
        after = (d.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    todo = [(r["id"], r["properties"]["dealname"], r["properties"]["description"] or "")
            for r in rows if no_money(r["properties"]["description"] or "") != (r["properties"]["description"] or "").strip()]
    print(f"{'LIVE' if live else 'DRY'}: {len(rows)} 26/27 deals with a description, {len(todo)} carry money")
    for did, name, desc in todo:
        new = no_money(desc)
        print(f"\n{did} {name}\n  before: {desc[:600]}\n  after:  {new[:600]}")
        if live:
            call("PATCH", f"/crm/v3/objects/deals/{did}", {"properties": {"description": new}})
    print("\ndone" if live else "\ndry run only; add --live to write")


if __name__ == "__main__":
    main()
