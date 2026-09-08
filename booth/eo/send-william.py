#!/usr/bin/env python3
"""William's fix-your-run email. Defaults to Roman for review; pass --live to
send it to William for real.

    RESEND_API_KEY=... python3 booth/eo/send-william.py          # test to Roman
    RESEND_API_KEY=... python3 booth/eo/send-william.py --live   # to William
"""
import json
import os
import sys
import urllib.error
import urllib.request

KEY = os.environ["RESEND_API_KEY"]
LIVE = "--live" in sys.argv
TO = "william@marketplaceofficer.com" if LIVE else "roman@wetutorathome.com"

PAGE, CARD = "#EFEEEA", "#FFFFFF"
HEAD, BODY, ACCENT, MUTED, RULE = "#18181B", "#3F3F46", "#3B3E8F", "#A1A1AA", "#E4E4E7"
CODE_BG, CODE_TX = "#FAFAFA", "#27272A"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
LOGO = "https://eo-booth.pages.dev/eo-logo.png?v=1"

P = f'style="font-family:{FONT};font-size:16px;line-height:1.65;color:{BODY};margin:0 0 18px;"'
EY = f'style="font-family:{FONT};font-size:13px;letter-spacing:0.6px;text-transform:uppercase;color:{ACCENT};font-weight:700;margin:28px 0 10px;"'

PROMPT = """My agent is at williamfikhman/eo-cohort-agents. This morning's run
failed in 10 seconds with "FATAL: ANTHROPIC_API_KEY is not set". Fix my repo
so it runs properly.

1. Clone my fork and cd in. Confirm agents/ contains only
   cmo-prospect-scout.md - it should, so do not delete anything else.

2. Ask me for my Anthropic API key and my Resend API key, then set them as
   repository secrets named exactly ANTHROPIC_API_KEY and RESEND_API_KEY.
   Do not echo the values back to me and do not write them into any file.

3. In .github/workflows/first-shift.yml:
   - RESEND_FROM is currently an address on somebody else's domain and my
     key has no authority to send from it. Ask me whether to use
     onboarding@resend.dev (works immediately, but only sends to my own
     Resend account address) or an address on a domain I have verified.
   - Replace the cron "0 14 21 8 *" with a daily one. Ask me what time in
     my timezone and convert to UTC yourself.
   - Raise timeout-minutes to 60.

4. My agent took 26 minutes on the shared run, which is slow and expensive
   to repeat daily. Tighten the TASK in agents/cmo-prospect-scout.md so it
   checks the funding source FIRST and only opens a careers page for
   companies that pass that filter. Show me the change before committing.

5. Commit, push, then trigger the workflow manually and watch it. Tell me
   how long it took and whether the email actually sent. If it failed, read
   the log and explain the real reason in plain English."""


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


inner = f"""
  <h1 style="font-family:{FONT};font-size:22px;line-height:1.3;font-weight:700;color:{HEAD};margin:0 0 16px;">Your agent didn't fail. It never got its keys.</h1>
  <p {P}>I read the run on your repo this morning. It died after ten seconds with one line:</p>
  <pre style="background:{CODE_BG};border:1px solid {RULE};border-radius:8px;padding:14px;margin:0 0 18px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;color:{CODE_TX};">FATAL: ANTHROPIC_API_KEY is not set</pre>
  <p {P}>Both API secrets are empty on your fork, so it stopped before it ever looked at your agent. Nothing is wrong with what you built.</p>
  <p {P}>You did the important part right, by the way — your fork contains only <strong style="color:{HEAD};">cmo-prospect-scout.md</strong>. Most people leave the other eight in and quietly email the entire workshop every morning.</p>

  <p {EY}>Three things left</p>
  <p {P}>Your two API keys are missing. Your sender is still an address on someone else's domain, which your key can't send from. And your schedule is set to fire once a year rather than daily.</p>

  <p {EY}>Paste this into Claude Code</p>
  <pre style="background:{CODE_BG};border:1px solid {RULE};border-radius:8px;padding:16px;margin:0 0 22px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.5;color:{CODE_TX};-webkit-user-select:all;user-select:all;">{esc(PROMPT)}</pre>

  <p {P}>One observation worth your time: on the shared run yesterday your agent took <strong style="color:{HEAD};">26 minutes</strong> — more than half the entire job's budget, and the reason four other people's agents never ran at all. It works; it's just doing full research on every company before deciding whether it cares. Filter first, then investigate, and it should come in under five.</p>
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
    "subject": "Your agent didn't fail — it never got its keys",
    "html": html,
}
req = urllib.request.Request(
    "https://api.resend.com/emails",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        mode = "LIVE -> William" if LIVE else "TEST -> Roman"
        print(f"{mode}: sent to {TO} | id = {json.loads(r.read()).get('id')}")
except urllib.error.HTTPError as e:
    sys.exit(f"FAILED {e.code}: {e.read().decode()[:300]}")
