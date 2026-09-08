#!/usr/bin/env python3
"""Attendees who came through the booth but never forked the repo — plus the
five agent ideas their own research brief already handed them.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/unbuilt.py
"""
import json
import os
import re
import subprocess
import urllib.request

TOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# fork owner -> attendee email, established by reading each fork's agent
# frontmatter and the booth records.
FORKED = {
    "anna@showmyproperty.tv", "christophercusiter@gmail.com",
    "drkang@elitesedation.com", "jeff@neucpas.com", "kevin@kinected.com",
    "a@funbox.com", "gevorg@polymorphic.io", "tallin@hellotalentagency.com",
    "william.fikhman@gmail.com", "alexis@yourstartupoperations.com",
    "roman@wetutorathome.com",
}


def attendees():
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "aplus_event_tag",
            "operator": "CONTAINS_TOKEN", "value": "eo_lav_agents_2026"}]}],
        "properties": ["email", "firstname", "lastname", "eo_company_name",
                       "eo_research_brief"],
        "limit": 100,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    return json.load(urllib.request.urlopen(r, timeout=60)).get("results", [])


def ideas(brief):
    """The five suggestions the research agent already wrote for them."""
    m = re.search(r"Five agents you could build tonight:\s*(.+)", brief or "", re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if re.match(r"^\d+\.\s", line):
            out.append(re.sub(r"^\d+\.\s*", "", line))
    return out


for c in sorted(attendees(), key=lambda x: (x["properties"].get("firstname") or "")):
    p = c["properties"]
    em = (p.get("email") or "").lower()
    if em in FORKED:
        continue
    sug = ideas(p.get("eo_research_brief"))
    print("=" * 76)
    print(f"{p.get('firstname')} {p.get('lastname')}  <{em}>   [{p.get('eo_company_name')}]")
    for s in sug[:5]:
        print(f"   - {s[:150]}")
    if not sug:
        print("   (no suggestions found in brief)")
