#!/usr/bin/env python3
"""Who received what, reconstructed from the flags the system actually wrote
rather than from anyone's memory.

Automatic sends are proven by their flags: eo_payload1_sent and
eo_payload2_sent on the contact, and sent:buildkit / sent:positive /
sent:thanks keys in KV. Script-driven sends are recorded here as constants
because they are one-shot runs whose results were printed at the time.

    HUBSPOT_PRIVATE_APP_TOKEN=... python3 booth/eo/who-got-what.py
"""
import json
import os
import subprocess
import urllib.request

TOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
NS = "38b24fd52f064143a0273d9f43a85a3c"

# Sent by one-shot scripts; results were printed when they ran.
GOT_DIAGNOSTIC = {  # live per-person repo diagnosis, Aug 21
    "anna@showmyproperty.tv", "christophercusiter@gmail.com",
    "william@marketplaceofficer.com", "alexis@yourstartupoperations.com",
    "tallin@hellotalentagency.com", "jeff@neucpas.com",
    "drkang@elitesedation.com", "kevin@kinected.com",
    "a@funbox.com", "gevorg@polymorphic.io",
}
EXTRA = {  # one-offs
    "tallin@hellotalentagency.com": ["personal pre-shift notes"],
    "william@marketplaceofficer.com": ["keys-missing email (x2)"],
}
# Everyone tagged got these two from bulk scripts that reported 20/20.
BULK = ["build kit (fork-corrected resend)", "make your agent yours"]


def contacts():
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "aplus_event_tag",
            "operator": "CONTAINS_TOKEN", "value": "eo_lav_agents_2026"}]}],
        "properties": ["email", "firstname", "eo_payload1_sent",
                       "eo_payload2_sent", "eo_demo_consent"],
        "limit": 100,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    return json.load(urllib.request.urlopen(r, timeout=60)).get("results", [])


def kv_keys(prefix):
    try:
        out = subprocess.run(
            ["npx", "wrangler", "kv", "key", "list",
             f"--namespace-id={NS}", f"--prefix={prefix}", "--remote"],
            capture_output=True, text=True, timeout=180, cwd="booth/eo").stdout
        return {k["name"].split(":")[-1] for k in json.loads(out[out.index("["):])}
    except Exception:
        return set()


bk = kv_keys("sent:buildkit:")
pos = kv_keys("sent:positive:")
thx = kv_keys("sent:thanks:")

rows = []
for c in sorted(contacts(), key=lambda x: (x["properties"].get("firstname") or "")):
    p = c["properties"]
    em = (p.get("email") or "").lower()
    got = ["photo email"]
    if p.get("eo_payload1_sent"):
        got.append("research brief")
    if c["id"] in bk:
        got.append("build kit (6:35)")
    if p.get("eo_payload2_sent"):
        got.append("closing email")
    got += BULK
    if em in GOT_DIAGNOSTIC:
        got.append("REPO DIAGNOSTIC")
    got += EXTRA.get(em, [])

    texts = []
    if p.get("eo_demo_consent") == "true":
        texts.append("photo MMS + 3 pestering + hero MMS")
    else:
        texts.append("photo MMS only")
    if c["id"] in pos:
        texts.append("encouragement")
    if c["id"] in thx:
        texts.append("thank-you")
    if em in GOT_DIAGNOSTIC:
        texts.append("review nudge")

    rows.append((p.get("firstname") or "?", em, got, texts))

print(f"{len(rows)} attendees\n")
for name, em, got, texts in rows:
    print(f"{name} <{em}>")
    print(f"   EMAIL: {', '.join(got)}")
    print(f"   TEXT : {', '.join(texts)}")
    print()

print("NOT SENT (blocked by Resend daily quota):")
print("  'Your ideas are still sitting there' -> Bill, Jason, Larry T'kertenian,")
print("  Larry Treystman, Mariam, Natela, Paul, Robert, Tamy")
