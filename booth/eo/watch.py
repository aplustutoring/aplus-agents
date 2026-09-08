#!/usr/bin/env python3
"""Watch one contact through the booth pipeline, printing a line per state
change. Requires a FRESH capture before it will call anything ready — the
first version declared success against data left over from an earlier run.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/watch.py roman@wetutorathome.com
"""
import json
import os
import sys
import time
import urllib.request

TOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
EMAIL = sys.argv[1] if len(sys.argv) > 1 else "roman@wetutorathome.com"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

PROPS = ["email", "firstname", "eo_company_name", "eo_research_brief",
         "eo_hero_image_url", "eo_demo_consent", "lastmodifieddate"]


def find():
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": EMAIL}]}],
        "properties": PROPS, "limit": 1,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    d = json.load(urllib.request.urlopen(r, timeout=30))
    return d["results"][0]["properties"] if d.get("total") else None


def stamp():
    return time.strftime("%H:%M:%S")


baseline = find() or {}
base_mod = baseline.get("lastmodifieddate")
print(f"[{stamp()}] armed — brief and hero are cleared. Take the photo.", flush=True)

captured = False
seen_brief = False
seen_hero = False

deadline = time.time() + 8 * 60
while time.time() < deadline:
    time.sleep(10)
    try:
        p = find()
    except Exception as e:
        print(f"[{stamp()}] poll error: {e}", flush=True)
        continue
    if not p:
        continue

    if not captured and p.get("lastmodifieddate") != base_mod:
        captured = True
        print(f"[{stamp()}] 1. CAPTURE landed — company={p.get('eo_company_name')!r} "
              f"consent={p.get('eo_demo_consent')}  "
              f"(photo text + photo email sent)", flush=True)

    if not seen_brief and p.get("eo_research_brief"):
        seen_brief = True
        b = p["eo_research_brief"]
        print(f"[{stamp()}] 2. BRIEF stored — {len(b)} chars, five-agents section: "
              f"{'yes' if 'Five agents' in b else 'NO'}", flush=True)

    if not seen_hero and p.get("eo_hero_image_url"):
        seen_hero = True
        print(f"[{stamp()}] 3. HERO ready", flush=True)

    # Only ready once we have seen this run produce both.
    if captured and seen_brief and seen_hero:
        print(f"[{stamp()}] READY — fire the dry run for beats 3-8.", flush=True)
        break

if not captured:
    print(f"[{stamp()}] no capture seen in 8 minutes", flush=True)
print(f"[{stamp()}] watch ended", flush=True)
