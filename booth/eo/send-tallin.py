#!/usr/bin/env python3
"""One-off: send Tallin the notes on her agent before its first shift.

Matches the Minion #23 mail styling used for every other attendee email so
it reads as the same sender, not a stray message from a stranger.

    RESEND_API_KEY=... python3 booth/eo/send-tallin.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

KEY = os.environ["RESEND_API_KEY"]
TO = "tallin@hellotalentagency.com"
BCC = "roman@wetutorathome.com"

PAGE, CARD = "#EFEEEA", "#FFFFFF"
HEAD, BODY, ACCENT, MUTED, RULE = "#18181B", "#3F3F46", "#3B3E8F", "#A1A1AA", "#E4E4E7"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
LOGO = "https://eo-booth.pages.dev/eo-logo.png?v=1"

P = f'style="font-family:{FONT};font-size:16px;line-height:1.65;color:{BODY};margin:0 0 18px;"'
EY = f'style="font-family:{FONT};font-size:13px;letter-spacing:0.6px;text-transform:uppercase;color:{ACCENT};font-weight:700;margin:28px 0 10px;"'

inner = f"""
  <h1 style="font-family:{FONT};font-size:22px;line-height:1.3;font-weight:700;color:{HEAD};margin:0 0 16px;">Before your first shift.</h1>
  <p {P}>Your agent is merged and runs tomorrow at 7am. Three notes — the first one actually matters, the other two are polish.</p>

  <p {EY}>1 — Your schedule line is decorative</p>
  <p {P}>Your file says <em>Weekdays (Mon&ndash;Fri) at 7:00am US Pacific</em>. That line is documentation. The thing that decides when your agent actually runs is a cron in the workflow, and right now it is set to fire <strong style="color:{HEAD};">once, tomorrow morning, and then not again until next August</strong>.</p>
  <p {P}>So you will get one email and then silence — not because it broke, but because nobody told it to come back. The <em>&ldquo;Make your agent yours&rdquo;</em> email already in your inbox fixes exactly this: your own copy, your own key, a real daily schedule.</p>

  <p {EY}>2 — Your agent calls you &ldquo;he&rdquo;</p>
  <p {P}>The AUDIENCE line reads <em>&ldquo;He acts on strong leads the same day.&rdquo;</em> If that is not right, it is one word — and that line shapes the voice of every email it writes you.</p>

  <p {EY}>3 — Judge tomorrow on the links, not the length</p>
  <p {P}>You told it that every factual claim links out, and to cut any claim without one. So if tomorrow lands with three companies instead of ten, that is your own honest-empty rule working. Ten companies with dead links would be the failure.</p>

  <p {EY}>One idea, if you want an edge</p>
  <p {P}>Your 30-day funding window is generous, and by the time a Series B is on TechCrunch every recruiter in Los Angeles has already seen it. SEC Form D filings — which you already list as a source — usually land <em>before</em> the press release. Weight Form D over news coverage and you would be reaching those founders before the story breaks rather than after.</p>
  <p {P}>Two lines in your own file. You do not need anyone's permission to change it — that is rather the point.</p>

  <p style="font-family:{FONT};font-size:15px;line-height:1.6;color:{ACCENT};font-weight:600;margin:26px 0 0;">— Minion #23 🤖</p>
"""

html = f"""<div style="background:{PAGE};padding:28px 16px;font-family:{FONT};">
  <div style="max-width:560px;margin:0 auto;background:{CARD};border-radius:14px;padding:36px 32px;">
    <img src="{LOGO}" alt="EO Los Angeles Valley" width="150" style="display:block;width:150px;height:auto;margin:0 0 6px;">
    <p style="font-family:{FONT};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:{MUTED};font-weight:700;margin:0 0 24px;">Build Your First AI Agent &middot; August 20, 2026</p>
    <div style="border-top:1px solid {RULE};padding-top:26px;">{inner}</div>
    <p style="font-family:{FONT};font-size:12px;line-height:1.5;color:{MUTED};margin:30px 0 0;border-top:1px solid {RULE};padding-top:18px;">You met me at the photo booth on August 20, 2026.</p>
  </div>
</div>"""

payload = {
    "from": "Minion #23 <minion23@wetutorathome.com>",
    "to": [TO],
    "bcc": [BCC],
    "subject": "Before your agent's first shift",
    "html": html,
}
req = urllib.request.Request(
    "https://api.resend.com/emails",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        # Resend sits behind Cloudflare; the default urllib UA gets bot-blocked.
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print("sent to", TO, "| id =", json.loads(r.read()).get("id"), "| bcc", BCC)
except urllib.error.HTTPError as e:
    sys.exit(f"FAILED {e.code}: {e.read().decode()[:300]}")
