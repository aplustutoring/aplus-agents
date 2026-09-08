#!/usr/bin/env python3
"""Where every attendee stands: booth pipeline (HubSpot) cross-referenced
against agents actually shipped (GitHub).

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/status.py
"""
import base64
import json
import os
import re
import subprocess
import urllib.request

TOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
REPO = "aplustutoring/eo-cohort-agents"


def hubspot():
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "aplus_event_tag",
            "operator": "CONTAINS_TOKEN", "value": "eo_lav_agents_2026"}]}],
        "properties": ["email", "firstname", "lastname", "eo_company_name",
                       "eo_research_brief", "eo_hero_image_url",
                       "eo_payload1_sent", "eo_payload2_sent", "eo_demo_consent"],
        "limit": 100,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    return json.load(urllib.request.urlopen(r, timeout=60)).get("results", [])


def gh(args):
    try:
        return subprocess.run(["gh"] + args, capture_output=True, text=True,
                              timeout=90).stdout
    except Exception:
        return ""


def shipped():
    """email -> agent name, for every agent merged to main."""
    out = {}
    listing = gh(["api", f"repos/{REPO}/contents/agents", "--jq", ".[].name"])
    for fn in [x for x in listing.split() if x.endswith(".md")]:
        raw = gh(["api", f"repos/{REPO}/contents/agents/{fn}", "--jq", ".content"])
        try:
            text = base64.b64decode(raw).decode("utf-8", "replace")
        except Exception:
            continue
        m = re.search(r"^email:\s*(.+)$", text, re.M)
        if m:
            out[m.group(1).strip().lower()] = fn[:-3]
    return out


people = hubspot()
ships = shipped()

print(f"{len(people)} attendees · {len(ships)} agents merged to main\n")
hdr = f"{'NAME':14} {'COMPANY':22} {'BRIEF':>6} {'HERO':5} {'P1':4} {'P2':4} {'SMS':4} AGENT SHIPPED"
print(hdr)
print("-" * len(hdr))

no_brief, no_hero, no_agent = [], [], []
for c in sorted(people, key=lambda x: (x["properties"].get("firstname") or "")):
    p = c["properties"]
    em = (p.get("email") or "").lower()
    nm = (p.get("firstname") or "?")[:13]
    co = (p.get("eo_company_name") or "-")[:21]
    nb = len(p.get("eo_research_brief") or "")
    hero = "yes" if p.get("eo_hero_image_url") else "NO"
    p1 = "yes" if p.get("eo_payload1_sent") else "NO"
    p2 = "yes" if p.get("eo_payload2_sent") else "NO"
    sms = "yes" if p.get("eo_demo_consent") == "true" else "no"
    ag = ships.get(em, "—")
    print(f"{nm:14} {co:22} {nb:>6} {hero:5} {p1:4} {p2:4} {sms:4} {ag}")
    if nb < 400:
        no_brief.append(nm)
    if hero == "NO":
        no_hero.append(nm)
    if ag == "—":
        no_agent.append(nm)

print()
print(f"no/thin brief : {', '.join(no_brief) if no_brief else 'none'}")
print(f"no hero image : {', '.join(no_hero) if no_hero else 'none'}")
print(f"no agent yet  : {', '.join(no_agent) if no_agent else 'none'}")
