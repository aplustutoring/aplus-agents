#!/usr/bin/env python3
"""Per-attendee diagnostic email.

Each one names their agent and what it actually does — read out of their own
agent file, not guessed — then reports what I found in their repo, gives a
read-only diagnostic prompt, and a fix prompt for their specific situation.

Defaults to sending every one to Roman for review, with the intended
recipient in the subject. --live sends to the attendees.

    RESEND_API_KEY=... python3 booth/eo/send-diagnostics.py
    RESEND_API_KEY=... python3 booth/eo/send-diagnostics.py --live
    RESEND_API_KEY=... python3 booth/eo/send-diagnostics.py --live --only=Tallin
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

KEY = os.environ["RESEND_API_KEY"]
LIVE = "--live" in sys.argv
ONLY = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)
REVIEW_TO = "roman@wetutorathome.com"

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

DIAGNOSTIC = """Diagnose my agent repo. Do not change anything yet - report first.

1. Which fork is mine? (gh repo list --fork). Clone it and cd in.
2. What is on my DEFAULT branch: list agents/*.md. Is MY agent there, or only
   somebody else's? Check other branches too (git branch -r).
3. Read .github/workflows/*.yml and tell me:
   - the RESEND_FROM address, and whether it is a domain I control
   - every active cron line, and what local time each one is for me
   - the timeout
   - whether any job is gated behind a condition that could skip it
4. Do the repository secrets ANTHROPIC_API_KEY and RESEND_API_KEY exist?
5. Show my last 5 workflow runs. For each: did the job that runs the agent
   ACTUALLY execute, or was it skipped? A skipped job still reports green, so
   check the job list, not the run's green checkmark.
6. Then tell me in plain English: would my agent email me tomorrow morning,
   yes or no, and what is the single thing most likely to stop it."""


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


PEOPLE = [
    ("Anna", "anna@showmyproperty.tv",
     "Lease-Up Radar works. One thing about the clock.",
     ["<strong>Lease-Up Radar ran twice and emailed you.</strong> Yours is one of only two agents in the entire cohort that genuinely worked this morning — the rest are sitting in various states of not-quite.",
      "It is a good brief, too: apartment communities entering pre-leasing <em>before</em> they have picked a photography or video agency. That timing is the whole business, and an agent that watches for it daily is worth more than one that summarises the market.",
      "The only thing I would change is the clock. Your schedule is <code>0 15 * * *</code>, which is 8:00 AM Pacific today and silently becomes 7:00 AM in November when the clocks change. Cron runs on UTC and does not follow daylight saving."],
     """My agent lease-up-radar works. My cron is "0 15 * * *", which is 8am Pacific
now and 7am after the November clock change, because cron runs on UTC.

Change it so it lands at the same local time year-round: declare both 14:00 and
15:00 UTC, and add a gate job that reads the real Pacific hour and lets the run
proceed only when it is the correct one - accepting a window of an hour or two,
because GitHub often runs scheduled jobs late. Add a guard so the two crons can
never both send on the same day. Show me the file before committing, then
trigger a manual run to confirm it still works."""),

    ("Chris", "christophercusiter@gmail.com",
     "Shelf Spotter works — but prove it fires tomorrow.",
     ["<strong>total-wine-shelf-spotter ran and the agent genuinely executed.</strong> Your sender and schedule are both correct, which puts you ahead of nearly everyone.",
      "Watching Total Wine for your own Alexander Murray SKUs going on promotion — plus Kaigan and Ide &amp; Stills — is exactly the kind of job that is tedious for a person and trivial for an agent. It only pays off if it runs every single day, though, which is the bit I want you to confirm.",
      "Your scheduled run on Friday does not appear in your history — only the earlier one does. GitHub drops and delays scheduled jobs under load fairly often, so this may be nothing. Worth proving rather than assuming."],
     """My agent total-wine-shelf-spotter ran fine when triggered, but I cannot see a
scheduled run in my history for Friday.

Check whether scheduled workflows are actually enabled and firing on my fork:
show me every run with its trigger type, confirm Actions is enabled, and confirm
my cron line is on the default branch. Then trigger a manual run so I know the
agent still works, and tell me what time my next scheduled run should land in my
own timezone."""),

    ("William", "william@marketplaceofficer.com",
     "Prospect Scout is still missing its two keys.",
     ["I sent this yesterday and nothing has changed on your repo, so here it is again with a diagnostic you can run yourself.",
      "<strong>Your run failed after ten seconds:</strong> <code>FATAL: ANTHROPIC_API_KEY is not set</code>. Both API secrets are empty, so it stopped before it ever opened your agent. Your sender is also still an address on a domain you do not control, and your schedule fires once a year.",
      "You did the important part right — your fork holds only your own agent, which most of the room got wrong.",
      "One observation on the agent itself: hunting mid-market CPG brands showing marketplace trouble is a genuinely good brief, but on the shared run it took <strong>26 minutes</strong> because it researches every candidate fully before deciding whether it cares. Filter on the signal first, investigate second, and it should come in under five."],
     """My run failed with "FATAL: ANTHROPIC_API_KEY is not set". Fix my repo.

1. Ask me for my Anthropic and Resend API keys and set them as repository
   secrets named exactly ANTHROPIC_API_KEY and RESEND_API_KEY. Do not echo them
   back or write them into a file.
2. RESEND_FROM is an address on a domain I do not control, so my key cannot send
   from it. Ask me whether to use onboarding@resend.dev or an address on a domain
   I have verified in Resend.
3. Replace the cron "0 14 21 8 *", which fires once a year, with a daily one. Ask
   me what time in my timezone and convert to UTC yourself.
4. My agent took 26 minutes on a shared run. Tighten its TASK so it checks the
   marketplace-trouble signal FIRST and only researches a brand fully once that
   signal is confirmed. Show me the change before committing.
5. Commit, push, trigger a run, and tell me whether the email actually sent."""),

    ("Alexis", "alexis@yourstartupoperations.com",
     "Resume Screener is set up correctly. It has just never run.",
     ["<strong>resume-screener is configured better than most</strong> — your own sender, a daily schedule, only your agent in the folder. The Name / Score / Strengths / Flags table is a good call too; scoring VAs consistently is exactly the sort of judgement that drifts when a human does it at the end of a long day.",
      "But your repo has <strong>no run history at all</strong> — not even a failure. That almost always means GitHub Actions was never switched on for the fork. Forks ship with Actions disabled, and a scheduled workflow in a repo with Actions off fires silently into nothing. No error, no email, no clue."],
     """My agent resume-screener is configured but my repo has never run a single
workflow, successful or failed.

Check whether GitHub Actions is enabled on my fork and enable it if not. Then
confirm the secrets ANTHROPIC_API_KEY and RESEND_API_KEY exist - ask me for any
that are missing, and never echo them back. Trigger the workflow manually, watch
it, and tell me whether the email actually sent and how long it took. Then tell
me when my next scheduled run lands in my own timezone."""),

    ("Tallin", "tallin@hellotalentagency.com",
     "Your agent is fine. Your clock check is too strict.",
     ["Your workflow is the best-engineered in the cohort, and I gather <strong>Gevorg helped you build it</strong> — credit to you both. It runs only your agent, strips the others out at build time so a future pull cannot re-add them, and handles daylight saving properly. Nobody else attempted that.",
      "<strong>And that is also why you got no email.</strong> Your gate only proceeds when the Pacific hour is exactly <code>07</code>. GitHub delivered your two runs at <strong>8:19am and 9:03am</strong>, so the gate correctly rejected both as the wrong daylight-saving cron — when really they were just late. Your 7am run never fired at all.",
      "Both runs show a green checkmark, because the gate succeeded and the real job was skipped. A skipped run looks identical to a successful one, which is the genuinely nasty part and worth remembering well beyond this agent.",
      "For what it is worth, morning-openjobs is a strong brief — funded companies with live engineering roles, ranked by volume and seniority, every claim carrying a link. It deserves to actually run."],
     """My workflow morning-openjobs.yml has a gate job that only proceeds when the
Pacific hour is exactly "07". GitHub ran my scheduled jobs late - at 8:19am and
9:03am Pacific - so the gate skipped both, and the runs still reported green.

Fix the gate so late runs still work:
- accept a window (7am through 9am Pacific) instead of one exact hour
- add a guard so that if the agent already ran today, a second cron cannot send
  a duplicate - use the run history or a dated marker
- make a skipped run visibly different from a successful one, so I can tell
  "ran" from "was skipped" at a glance

Show me the file before committing, then trigger a manual run so I finally see
what my agent produces - it has never completed once.

Separately: my TASK uses a 30-day funding window. SEC Form D filings usually
land before the press coverage, so weight Form D over news and I would be
reaching founders before the story breaks. Show me that change too."""),

    ("Jeff", "jeff@neucpas.com",
     "Before you add your API keys — read this.",
     ["Your fork carries <strong>five agent files</strong>, not just yours. That is not your mistake; you forked partway through the evening and picked up everyone who had shipped by then.",
      "The runner emails whoever is named inside <em>every</em> agent file it finds. So the moment you add your API keys and a daily schedule, your repo would email <strong>four other attendees</strong> every morning — from your address, about someone else's business. Nothing has gone out yet and your schedule is still the once-a-year one, so there is no fire. But fix it before the keys go in, not after.",
      "Then get time-entry-compiler running properly. Staging a day of itemised time entries for the practice management system is the least glamorous agent in the cohort and quite possibly the one with the clearest hourly value."],
     """My fork has five agent files but only time-entry-compiler is mine. The runner
emails the owner named in every file it finds, so as soon as I add my API keys I
would be emailing four other people every morning.

Fix it the safe way: rather than deleting the other files from my repo, add a
step to my workflow that strips the checkout down to only my agent before the
runner ever sees it. That way a future pull from the upstream repo cannot
quietly re-add everyone else. Make it fail loudly if my own agent file is
missing.

Then: set my ANTHROPIC_API_KEY and RESEND_API_KEY secrets (ask me for them,
never echo them back), change RESEND_FROM to a sender I control, and replace the
once-a-year cron with a daily one at a time I choose. Show me everything before
committing, then run it once manually."""),

    ("Albert", "drkang@elitesedation.com",
     "Before you add your API keys — read this.",
     ["Your fork carries <strong>four agent files</strong>, not just yours. You forked partway through the evening and picked up whoever had shipped by then — not your mistake.",
      "The runner emails whoever is named inside <em>every</em> agent file it finds. So once you add your API keys and a daily schedule, your repo would email <strong>three other attendees</strong> every morning, from your address, about someone else's business. Nothing has gone out yet — your schedule is still the once-a-year one — so fix it before the keys go in.",
      "Then let it do its job. Watching named competitor practices across LA, Orange County, San Diego, Riverside and Ventura is a lot of ground for a person to cover on a Monday, and almost no work at all for something that only reports when it finds a change."],
     """My fork has four agent files but only dental-anesthesia-competitor-watch is
mine. The runner emails the owner named in every file it finds, so as soon as I
add my API keys I would be emailing three other people every morning.

Fix it the safe way: rather than deleting the other files from my repo, add a
step to my workflow that strips the checkout down to only my agent before the
runner ever sees it, so a future pull from upstream cannot quietly re-add
everyone. Make it fail loudly if my own agent file is missing.

Then: set my ANTHROPIC_API_KEY and RESEND_API_KEY secrets (ask me, never echo
them back), change RESEND_FROM to a sender I control, and replace the
once-a-year cron with a daily one at a time I pick. Show me everything before
committing, then run it once manually."""),

    ("Kevin", "kevin@kinected.com",
     "Before you add your API keys — read this.",
     ["Your fork carries <strong>four agent files</strong>, not just yours — you forked partway through the evening and picked up whoever had shipped by then.",
      "The runner emails whoever is named inside <em>every</em> agent file it finds. So once you add your keys and a daily schedule, your repo would email <strong>three other attendees</strong> every morning, from your address, about someone else's business. Nothing has gone out yet, so there is no fire — just fix it before the keys go in.",
      "Worth saying: socal-mfg-scout is the sharpest-scoped agent in the cohort. Privately held manufacturers inside fifty miles of 91423, ranked by signal, for a sell-side M&amp;A practice — that is a real origination pipeline, not a demo. It deserves to run daily."],
     """My fork has four agent files but only socal-mfg-scout is mine. The runner
emails the owner named in every file it finds, so as soon as I add my API keys I
would be emailing three other people every morning.

Fix it the safe way: rather than deleting the other files from my repo, add a
step to my workflow that strips the checkout down to only my agent before the
runner ever sees it, so a future pull from upstream cannot re-add everyone. Make
it fail loudly if my own agent file is missing.

Then: set my ANTHROPIC_API_KEY and RESEND_API_KEY secrets (ask me, never echo
them back), change RESEND_FROM to a sender I control, and replace the once-a-year
cron with a daily one at a time I choose. Show me everything before committing,
then run it once manually."""),

    ("Antonio", "a@funbox.com",
     "Charity Scout is on a branch, not on your main.",
     ["<strong>charity-scout is not on your fork's default branch.</strong> It lives on <code>agent/charity-scout</code> — the branch you opened your pull request from. Your main still holds the agent that was there when you forked, which is Roman's.",
      "So if your workflow ran on a schedule right now, it would run <em>his</em> agent and email <em>him</em>. Yours would never fire. Merging your own branch into your own main fixes it.",
      "Worth fixing properly, because the brief is genuinely good: FUNBOX parks have opened while the team was still hunting for a local foster-care partner. An agent that closes that gap before each launch is doing something a spreadsheet cannot."],
     """My agent charity-scout is on the branch agent/charity-scout, but my fork's
default branch still has somebody else's agent on it. A scheduled run would
execute their agent and email them rather than running mine.

Merge my own branch into my fork's main so charity-scout is what actually runs,
and confirm no other agent files are left on main - the runner emails the owner
named in every file it finds.

Then: set my ANTHROPIC_API_KEY and RESEND_API_KEY secrets (ask me, never echo
them back), change RESEND_FROM to a sender I control, and replace the once-a-year
cron with a daily one. Run it once manually and tell me whether the email
actually sent."""),

    ("Gevorg", "gevorg@polymorphic.io",
     "You shipped somebody else's agent and not your own.",
     ["First, credit where it is due: <strong>Tallin's workflow is the best-engineered thing anyone built last night</strong>, and I understand you helped her build it. It runs only her agent, strips the rest out at build time so a future pull cannot re-add them, and handles daylight saving with a gate job. Nobody else went near that level of care. Whatever you did there, it showed.",
      "Which makes this the funny part: <strong>your own agent never shipped.</strong> You have a branch called <code>agent/eod-checker</code> with real work on it, but no pull request was ever opened, and it is not on your fork's main either. Your main still holds Roman's agent, so a scheduled run today would email him rather than you.",
      "And eod-checker deserves to exist. Reconciling what the team said it did against what Jira shows, across a ten-hour gap between Glendale and Yerevan, is precisely the problem a daily agent is for — the kind of thing that is nobody's job until it goes wrong."],
     """I have a branch called agent/eod-checker with a finished agent on it, but I
never opened a pull request and it is not on my fork's main branch either.

First show me what is actually in that branch so I can confirm it is done. Then
merge it into my fork's main, and confirm no other agent files are left there -
the runner emails the owner named in every file it finds, so somebody else's
agent sitting on my main would email them, not me.

Also open a pull request against aplustutoring/eo-cohort-agents so it joins the
cohort repo.

Then: set my ANTHROPIC_API_KEY and RESEND_API_KEY secrets (ask me, never echo
them back), set RESEND_FROM to a sender I control, and give it a daily cron at a
time I choose - it should run at end of day in Glendale, which is worth thinking
about given the Yerevan side of the team has already finished. Run it once
manually to prove it works."""),
]


def build(name, headline, paras, fix):
    body = "".join(f"<p {P}>{x}</p>" for x in paras)
    return f"""<div style="background:{PAGE};padding:28px 16px;font-family:{FONT};">
  <div style="max-width:560px;margin:0 auto;background:{CARD};border-radius:14px;padding:36px 32px;">
    <img src="{LOGO}" alt="EO Los Angeles Valley" width="150" style="display:block;width:150px;height:auto;margin:0 0 6px;">
    <p style="font-family:{FONT};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:{MUTED};font-weight:700;margin:0 0 24px;">Build Your First AI Agent &middot; August 20, 2026</p>
    <div style="border-top:1px solid {RULE};padding-top:26px;">
      <h1 style="font-family:{FONT};font-size:22px;line-height:1.3;font-weight:700;color:{HEAD};margin:0 0 16px;">{headline}</h1>
      <p {P}>{name}, I went and read your repo and your agent directly. This is what is actually there, not a guess.</p>
      {body}
      <p {EY}>First — see it for yourself</p>
      <p {P}>Paste this into Claude Code. It only reports; it changes nothing.</p>
      <pre {PRE}>{esc(DIAGNOSTIC)}</pre>
      <p {EY}>Then — the fix for your situation</p>
      <pre {PRE}>{esc(fix)}</pre>
      <p style="font-family:{FONT};font-size:15px;line-height:1.6;color:{ACCENT};font-weight:600;margin:26px 0 0;">— Minion #23 🤖</p>
    </div>
    <p style="font-family:{FONT};font-size:12px;line-height:1.5;color:{MUTED};margin:30px 0 0;border-top:1px solid {RULE};padding-top:18px;">You met me at the photo booth on August 20, 2026.</p>
  </div>
</div>"""


sent = 0
for name, email, headline, paras, fix in PEOPLE:
    if ONLY and ONLY.lower() != name.lower():
        continue
    to = email if LIVE else REVIEW_TO
    subject = headline if LIVE else f"[review → {name}] {headline}"
    payload = {
        "from": "Minion #23 <minion23@wetutorathome.com>",
        "to": [to],
        "subject": subject,
        "html": build(name, headline, paras, fix),
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
            print(f"  {'LIVE' if LIVE else 'review'}  {name:9} -> {to:38} {json.loads(r.read()).get('id')}")
            sent += 1
    except urllib.error.HTTPError as e:
        print(f"  FAIL   {name:9} -> {to}: {e.code} {e.read().decode()[:160]}")
    time.sleep(1.2)

print(f"\n{sent} sent ({'LIVE to attendees' if LIVE else 'review copies to Roman'})")
