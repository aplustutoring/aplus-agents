#!/usr/bin/env python3
"""Tell the attendees who have not yet had their follow-up email that it is
coming — the send hit Resend's daily cap.

Only the seven who ticked demo consent at the booth. Mariam and Robert
declined and were not among the four Roman said reached out to him
afterwards, so they are deliberately left out rather than force-sent.

    python3 booth/eo/send-heads-up.py          # show the plan
    python3 booth/eo/send-heads-up.py --go
"""
import json
import sys
import time
import urllib.parse
import urllib.request

WORKER = "https://eo-booth.nameless-mountain-bafa.workers.dev"
KEY = "m23diag"
GO = "--go" in sys.argv

MSG = ("Quick one — I owe you an email with the five agents I picked out for "
       "your business, and I have just hit my own daily sending limit. Rate "
       "limits: they get all of us. It will land tonight. — Minion #23 🤖")

# Booth demo consent = yes
SEND = [
    ("Bill", "bilduf25@gmail.com"),
    ("Jason", "jason.zdenek@mobileillumination.com"),
    ("Larry T'kertenian", "larry@bioluzled.com"),
    ("Larry Treystman", "ltreystman@me.com"),
    ("Natela", "nshenon@grantshenon.com"),
    ("Paul", "pdashevsky@hotmail.com"),
    ("Tamy", "tamysloboda@gmail.com"),
]
# Declined at the booth, no separate outreach on record — Roman's call.
HELD = [("Mariam", "maryzakharyan@gmail.com"), ("Robert", "robert@pandiaseeds.com")]

if not GO:
    for n, e in SEND:
        print(f"  would text {n:18} {e}")
    print("\n  HELD (declined SMS, no verbal consent on record):")
    for n, e in HELD:
        print(f"    {n:18} {e}")
    print(f"\n{len(SEND)} planned. Re-run with --go.")
    sys.exit(0)

ok = fail = 0
for n, e in SEND:
    q = urllib.parse.urlencode({"key": KEY, "email": e, "msg": MSG})
    req = urllib.request.Request(f"{WORKER}/debug/text?{q}", headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
        if d.get("ok"):
            ok += 1
            print(f"  sent {n:18} basis={d.get('basis')}")
        else:
            fail += 1
            print(f"  FAIL {n:18} {str(d)[:110]}")
    except Exception as ex:
        fail += 1
        print(f"  FAIL {n:18} {ex}")
    time.sleep(1.5)

print(f"\nsent {ok}, failed {fail}")
print("held back: " + ", ".join(n for n, _ in HELD))
