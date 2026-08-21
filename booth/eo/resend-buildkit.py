#!/usr/bin/env python3
"""Resend the build-kit email to every tagged attendee, personalised with
their own brief. Used after the prompt was corrected to fork before pushing.

Sequential and paced: the preview route re-fetches each contact and renders
their brief, and hammering 20 concurrent requests at the Worker risks
tripping over the same subrequest limits the queue already lives inside.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/resend-buildkit.py [--go]
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

TOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
WORKER = "https://eo-booth.nameless-mountain-bafa.workers.dev"
KEY = "m23diag"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def attendees():
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "aplus_event_tag",
            "operator": "CONTAINS_TOKEN",
            "value": "eo_lav_agents_2026",
        }]}],
        "properties": ["email", "firstname"],
        "limit": 100,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    d = json.load(urllib.request.urlopen(r, timeout=60))
    return [(c["properties"].get("firstname") or "?",
             c["properties"].get("email")) for c in d.get("results", [])
            if c["properties"].get("email")]


people = attendees()
print(f"{len(people)} tagged attendees\n")

if "--go" not in sys.argv:
    for n, e in people:
        print(f"  would send -> {n:12} {e}")
    print("\nRe-run with --go to actually send.")
    sys.exit(0)

ok = fail = 0
for n, e in people:
    q = urllib.parse.urlencode({"key": KEY, "which": "buildkit", "to": e})
    try:
        # Browser UA: Cloudflare bot-filters urllib's default user-agent and
        # returns a bare 403 that looks exactly like a failed auth check.
        req = urllib.request.Request(
            f"{WORKER}/debug/preview?{q}",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        if d.get("ok"):
            ok += 1
            print(f"  sent {n:12} {e:38} {d.get('bytes')}b")
        else:
            fail += 1
            print(f"  FAIL {n:12} {e:38} {str(d)[:120]}")
    except Exception as ex:
        fail += 1
        print(f"  FAIL {n:12} {e:38} {ex}")
    time.sleep(1.5)

print(f"\nsent {ok}, failed {fail}")
