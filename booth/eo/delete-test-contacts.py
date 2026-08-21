#!/usr/bin/env python3
"""Delete the test contacts this session created at the EO booth.

Only touches the four synthetic addresses below — Roman's own contact and any
real attendee is never in this list. Verifies the email matches before issuing
the delete, so a recycled object id cannot take out the wrong record.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/delete-test-contacts.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
if not TOKEN:
    sys.exit("set HUBSPOT_PRIVATE_APP_TOKEN")

H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# id -> the email it MUST have for the delete to proceed
TARGETS = {
    "243300602787": "smoke-test-eo@wetutorathome.com",
    "243299512095": "diag-two-eo@wetutorathome.com",
    "243292411251": "diag-three-eo@wetutorathome.com",
    "243294391956": "diag-four-eo@wetutorathome.com",
}


def req(url, method):
    r = urllib.request.Request(url, headers=H, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.status, resp.read()


for cid, expected in TARGETS.items():
    url = f"https://api.hubapi.com/crm/v3/objects/contacts/{cid}?properties=email"
    try:
        _, body = req(url, "GET")
    except urllib.error.HTTPError as e:
        print(f"  {cid}: already gone ({e.code})")
        continue

    actual = json.loads(body)["properties"].get("email")
    if actual != expected:
        print(f"  {cid}: SKIPPED — email is {actual!r}, expected {expected!r}")
        continue

    try:
        status, _ = req(f"https://api.hubapi.com/crm/v3/objects/contacts/{cid}", "DELETE")
        print(f"  {cid}: deleted <{actual}>  (HTTP {status})")
    except urllib.error.HTTPError as e:
        print(f"  {cid}: delete failed {e.code} {e.read()[:200]!r}")

print("\nRoman's contact 67483477029 deliberately untouched.")
