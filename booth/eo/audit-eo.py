#!/usr/bin/env python3
"""What has the EO booth agent actually touched? Read-only.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/audit-eo.py
"""
import json
import os
import sys
import urllib.request

TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
if not TOKEN:
    sys.exit("set HUBSPOT_PRIVATE_APP_TOKEN")

H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


res = post("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    "filterGroups": [{"filters": [{
        "propertyName": "aplus_event_tag",
        "operator": "CONTAINS_TOKEN",
        "value": "eo_lav_agents_2026",
    }]}],
    "properties": ["email", "firstname", "lastname", "eo_company_name",
                   "eo_demo_consent", "eo_payload1_sent", "eo_payload2_sent",
                   "eo_research_brief", "createdate"],
    "limit": 100,
})

print(f"contacts tagged eo_lav_agents_2026: {res.get('total', 0)}")
for c in res.get("results", []):
    p = c["properties"]
    print(f"  id={c['id']}  {p.get('firstname')} {p.get('lastname')} <{p.get('email')}>")
    print(f"     company={p.get('eo_company_name')!r} consent={p.get('eo_demo_consent')}")
    print(f"     payload1_sent={p.get('eo_payload1_sent')}  payload2_sent={p.get('eo_payload2_sent')}")
    print(f"     brief_stored={'yes' if p.get('eo_research_brief') else 'no'}  created={p.get('createdate')}")

sent1 = [c for c in res.get("results", []) if c["properties"].get("eo_payload1_sent")]
sent2 = [c for c in res.get("results", []) if c["properties"].get("eo_payload2_sent")]
print()
print(f"payload #1 stamped: {len(sent1)}")
print(f"payload #2 stamped: {len(sent2)}")
print("(a stamp means a send was ATTEMPTED for that contact; in dry_run "
      "the stamp is still written but nothing leaves the building)")
