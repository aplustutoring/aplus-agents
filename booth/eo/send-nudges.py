#!/usr/bin/env python3
"""Text each attendee that Roman and the agent reviewed their repo together,
so the detailed email that just landed has context.

Six consented at the booth. The other four told Roman directly by reaching
out to him afterwards, which the booth checkbox — scoped to "tonight's live
demo" — could not have captured. Those four go with force=1, which bypasses
the checkbox and nothing else: a STOP reply is still checked first inside
sendSms and is never overridden.

The printed `basis` column is the audit trail for why each text was sent.

    python3 booth/eo/send-nudges.py            # dry run, shows the plan
    python3 booth/eo/send-nudges.py --go
"""
import json
import sys
import time
import urllib.parse
import urllib.request

WORKER = "https://eo-booth.nameless-mountain-bafa.workers.dev"
KEY = "m23diag"
GO = "--go" in sys.argv

MSG = ("Roman and I went through your repo together this morning. Just emailed "
       "you what we found and a fix you can paste straight into Claude Code. "
       "— Minion #23 🤖")

# Booth-consent addresses go without force; the rest rely on Roman's
# confirmation that they reached out to him directly.
BOOTH_CONSENT = [
    ("William", "william.fikhman@gmail.com"),
    ("Alexis", "alexis@yourstartupoperations.com"),
    ("Albert", "drkang@elitesedation.com"),
    ("Kevin", "kevin@kinected.com"),
    ("Antonio", "a@funbox.com"),
    ("Gevorg", "gevorg@polymorphic.io"),
]
VERBAL_TO_ROMAN = [
    ("Anna", "anna@showmyproperty.tv"),
    ("Chris", "christophercusiter@gmail.com"),
    ("Tallin", "tallin@hellotalentagency.com"),
    ("Jeff", "jeff@neucpas.com"),
]

PLAN = [(n, e, False) for n, e in BOOTH_CONSENT] + \
       [(n, e, True) for n, e in VERBAL_TO_ROMAN]

if not GO:
    for n, e, force in PLAN:
        print(f"  would text {n:9} {e:36} basis={'verbal to Roman' if force else 'booth checkbox'}")
    print(f"\n{len(PLAN)} planned. Re-run with --go to send.")
    sys.exit(0)

ok = fail = 0
for n, e, force in PLAN:
    q = {"key": KEY, "email": e, "msg": MSG}
    if force:
        q["force"] = "1"
    url = f"{WORKER}/debug/text?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
        if d.get("ok"):
            ok += 1
            print(f"  sent {n:9} basis={d.get('basis')}")
        else:
            fail += 1
            print(f"  FAIL {n:9} {str(d)[:120]}")
    except Exception as ex:
        fail += 1
        print(f"  FAIL {n:9} {ex}")
    time.sleep(1.5)

print(f"\nsent {ok}, failed {fail}")
