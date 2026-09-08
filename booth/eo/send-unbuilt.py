#!/usr/bin/env python3
"""Email the nine attendees who came through the booth but never built an
agent. Each email quotes two of the ideas their OWN research brief handed
them, then gives a paste that builds it.

The prompt embeds their brief as context, so their Claude chat opens already
knowing the company instead of interviewing them from cold.

    HUBSPOT_PRIVATE_APP_TOKEN=... RESEND_API_KEY=... python3 booth/eo/send-unbuilt.py
    ... --live          send to attendees
    ... --live --only=Tamy
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HTOKEN = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
RKEY = os.environ["RESEND_API_KEY"]
LIVE = "--live" in sys.argv
ONLY = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)
REVIEW_TO = "roman@wetutorathome.com"

H = {"Authorization": f"Bearer {HTOKEN}", "Content-Type": "application/json"}

# Who has already been sent, so a retry after a quota reset cannot duplicate
# anyone. Resend's cap can clear mid-batch, which would otherwise mean the
# first few get two copies on the next attempt.
LOGFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".unbuilt-sent")


def already_sent():
    try:
        with open(LOGFILE) as fh:
            return {l.strip() for l in fh if l.strip()}
    except FileNotFoundError:
        return set()


def mark_sent(em):
    with open(LOGFILE, "a") as fh:
        fh.write(em + "\n")

BUILT = {
    "anna@showmyproperty.tv", "christophercusiter@gmail.com",
    "drkang@elitesedation.com", "jeff@neucpas.com", "kevin@kinected.com",
    "a@funbox.com", "gevorg@polymorphic.io", "tallin@hellotalentagency.com",
    "william.fikhman@gmail.com", "alexis@yourstartupoperations.com",
    "roman@wetutorathome.com",
}

PAGE, CARD = "#EFEEEA", "#FFFFFF"
HEAD, BODY, ACCENT, MUTED, RULE = "#18181B", "#3F3F46", "#3B3E8F", "#A1A1AA", "#E4E4E7"
CODE_BG, CODE_TX = "#FAFAFA", "#27272A"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
LOGO = "https://eo-booth.pages.dev/eo-logo.png?v=1"

P = f'style="font-family:{FONT};font-size:16px;line-height:1.65;color:{BODY};margin:0 0 18px;"'
EY = f'style="font-family:{FONT};font-size:13px;letter-spacing:0.6px;text-transform:uppercase;color:{ACCENT};font-weight:700;margin:28px 0 10px;"'
PRE = (f'style="background:{CODE_BG};border:1px solid {RULE};border-radius:8px;padding:16px;'
       f'margin:0 0 22px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;'
       f'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;'
       f'line-height:1.5;color:{CODE_TX};-webkit-user-select:all;user-select:all;"')


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def attendees():
    body = {
        "filterGroups": [{"filters": [{
            "propertyName": "aplus_event_tag",
            "operator": "CONTAINS_TOKEN", "value": "eo_lav_agents_2026"}]}],
        "properties": ["email", "firstname", "eo_company_name", "eo_research_brief"],
        "limit": 100,
    }
    r = urllib.request.Request(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        data=json.dumps(body).encode(), headers=H)
    return json.load(urllib.request.urlopen(r, timeout=60)).get("results", [])


def ideas(brief):
    m = re.search(r"Five agents you could build tonight:\s*(.+)", brief or "", re.S)
    if not m:
        return []
    return [re.sub(r"^\d+\.\s*", "", l.strip())
            for l in m.group(1).splitlines() if re.match(r"^\d+\.\s", l.strip())]


def prompt_for(name, email, company, brief):
    return f"""CONTEXT - you already know this about me, do not ask again.

My name: {name}
My email: {email}
My company: {company}

Research another agent did on my company last week:

{brief}

I am at the point where I want ONE of those five agents actually built and
running on a schedule. Interview me ONE question at a time to pick which one
and to fill out a RAFT job description for it:

R - ROLE: what the agent is, my company, what we do
A - AUDIENCE: who reads the output and how fast
F - FORMAT: the shape of the output
T - TASK: exactly what to check each run, what to skip, and what to say if
    nothing real happened

Keep me scoped: web search and public information only, no logins to my other
tools. If the idea is too big, shrink it to the first 20% and tell me the rest
is v2. Start by asking which of the five I want, and recommend one yourself.

Also collect a short agent name in lowercase-with-hyphens and what schedule it
should run on.

Then set it up for real:
- Fork and clone the repo. I do NOT have write access to the original, so I
  must work from my own fork:
      gh repo fork aplustutoring/eo-cohort-agents --clone
      cd eo-cohort-agents
- Create agents/<agent-name>.md with frontmatter (name, email, agent,
  schedule) followed by my ROLE, AUDIENCE, FORMAT and TASK.
- Delete every OTHER file in agents/. The runner emails the owner named in
  every file it finds, so leaving them in means I email the whole workshop.
- Enable GitHub Actions on my fork - forks ship with it disabled.
- Ask me for my Anthropic and Resend API keys and set them as repository
  secrets ANTHROPIC_API_KEY and RESEND_API_KEY. Never echo them back or write
  them to a file.
- In .github/workflows/first-shift.yml set RESEND_FROM to a sender I control
  (ask me), replace the once-a-year cron with a daily one at a time I choose,
  and raise timeout-minutes to 60.
- Commit, push, then run it manually and tell me whether the email actually
  arrived."""


def build(name, company, picks, prompt):
    lis = "".join(
        f'<li style="font-family:{FONT};font-size:15px;line-height:1.6;color:{BODY};margin:0 0 12px;">{esc(x)}</li>'
        for x in picks)
    return f"""<div style="background:{PAGE};padding:28px 16px;font-family:{FONT};">
  <div style="max-width:560px;margin:0 auto;background:{CARD};border-radius:14px;padding:36px 32px;">
    <img src="{LOGO}" alt="EO Los Angeles Valley" width="150" style="display:block;width:150px;height:auto;margin:0 0 6px;">
    <p style="font-family:{FONT};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:{MUTED};font-weight:700;margin:0 0 24px;">Build Your First AI Agent &middot; August 20, 2026</p>
    <div style="border-top:1px solid {RULE};padding-top:26px;">
      <h1 style="font-family:{FONT};font-size:22px;line-height:1.3;font-weight:700;color:{HEAD};margin:0 0 16px;">Your ideas are still sitting there.</h1>
      <p {P}>{esc(name)}, last Thursday I researched {esc(company)} while you were finding your seat, and handed you five agents worth building. Eight people in that room built one before they left. You did not, which is entirely reasonable — it was late, and there was food.</p>
      <p {P}>The ideas have not expired. Two of yours I would start with:</p>
      <ul style="margin:0 0 18px;padding-left:20px;">{lis}</ul>
      <p {P}>Either one is roughly ten minutes of work now, and ends with something that emails you every morning without being asked.</p>

      <p {EY}>Paste this into Claude Code</p>
      <p {P}>It already knows your company — the whole brief is in there — so it starts by asking which agent you want rather than what you do for a living.</p>
      <pre {PRE}>{esc(prompt)}</pre>

      <p {P}>One thing that caught most of the room: you have to <strong>fork</strong> the repo, not clone it. Cloning works right up until you try to push, then stops with a permissions error that explains nothing. The paste above handles it.</p>
      <p {P}>Reply to this and Roman will see it. So will I.</p>
      <p style="font-family:{FONT};font-size:15px;line-height:1.6;color:{ACCENT};font-weight:600;margin:26px 0 0;">— Minion #23 🤖</p>
    </div>
    <p style="font-family:{FONT};font-size:12px;line-height:1.5;color:{MUTED};margin:30px 0 0;border-top:1px solid {RULE};padding-top:18px;">You met me at the photo booth on August 20, 2026.</p>
  </div>
</div>"""


sent = 0
DONE = already_sent() if LIVE else set()
quota_hit = False
for c in sorted(attendees(), key=lambda x: (x["properties"].get("firstname") or "")):
    p = c["properties"]
    em = (p.get("email") or "").lower()
    if em in BUILT:
        continue
    if em in DONE:
        print(f"  skip   {(p.get('firstname') or '?'):9} — already sent")
        continue
    name = p.get("firstname") or "there"
    if ONLY and ONLY.lower() != name.lower():
        continue
    company = p.get("eo_company_name") or "your company"
    brief = p.get("eo_research_brief") or ""
    picks = ideas(brief)[:2]
    if not picks:
        print(f"  SKIP   {name:9} — no suggestions in brief")
        continue

    to = em if LIVE else REVIEW_TO
    subject = ("Your ideas are still sitting there" if LIVE
               else f"[review → {name}] Your ideas are still sitting there")
    payload = {
        "from": "Minion #23 <minion23@wetutorathome.com>",
        "to": [to],
        "subject": subject,
        "html": build(name, company, picks, prompt_for(name, em, company, brief)),
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {RKEY}",
            "Content-Type": "application/json",
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"  {'LIVE' if LIVE else 'review'}  {name:9} -> {to:34} {json.loads(r.read()).get('id')}")
            sent += 1
            if LIVE:
                mark_sent(em)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:140]
        if e.code == 429:
            quota_hit = True
        print(f"  FAIL   {name:9} {e.code} {detail}")
    time.sleep(1.2)

print(f"\n{sent} sent ({'LIVE to attendees' if LIVE else 'review copies to Roman'})")
if quota_hit:
    # Signals the retry loop that this was a cap, not a real failure.
    sys.exit(3)
