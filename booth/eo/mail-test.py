#!/usr/bin/env python3
"""Send two traceable test emails from two different sender addresses on the
same verified domain, and print the Resend message id for each.

The booth uses minion23@wetutorathome.com, which has never sent mail before.
photos@wetutorathome.com is the address the Sage Oak booth used successfully,
so it has a delivery history. If B lands and A does not, the problem is the
brand-new local part, not the code.

    RESEND_API_KEY=... python3 booth/eo/mail-test.py you@example.com
"""
import json
import os
import sys
import urllib.error
import urllib.request

KEY = os.environ.get("RESEND_API_KEY")
if not KEY:
    sys.exit("set RESEND_API_KEY")
TO = sys.argv[1] if len(sys.argv) > 1 else "roman@wetutorathome.com"

SENDERS = [
    ("A", "Minion #23 <minion23@wetutorathome.com>"),
    ("B", "Minion #23 <photos@wetutorathome.com>"),
]

for tag, frm in SENDERS:
    payload = {
        "from": frm,
        "to": [TO],
        "subject": f"M23 deliverability test {tag}",
        "html": f"<p>Test {tag} — sender: {frm}</p>",
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare; the default urllib UA gets a
            # 403 error-1010 bot block that looks like an auth failure.
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        print(f"{tag}  {frm}")
        print(f"   HTTP 200  id={body.get('id')}")
    except urllib.error.HTTPError as e:
        print(f"{tag}  {frm}")
        print(f"   HTTP {e.code}  {e.read().decode()[:300]}")
