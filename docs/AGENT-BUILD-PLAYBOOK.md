# Building an agent at A+

For Danielle, Paola and Emily. One page. Read it once, then just start.

## What you are getting

You have all watched the agents work: the PO inbox, the low-balance sequence,
the tutor tickets, the call agent. Until now, when you wanted one, you asked
Roman and waited.

Now you describe it and Claude builds it. Roman approves it. It goes live. You
do not need to learn to code, and you do not need anything installed on your
laptop beyond the Claude app.

## Setup, once, about ten minutes

1. Create a free account at **github.com**. Use your @wetutorathome.com email.
2. Post your username in #leadership-team. Roman adds you to the repo.
3. Accept the invite email from GitHub.
4. Open the Claude desktop app. Start a session and choose **Cloud**, not Local.
5. Connect your GitHub account when it asks. One button.
6. Pick **aplus-agents** from the repo list.

That is the whole setup. After this, step 6 is the only step.

## Where your work actually happens

Nothing runs on your computer, and nothing runs on Roman's. When you start a
session, Claude gets a temporary machine in a datacenter, copies the repo onto
it, does the work, and throws the machine away. The agents themselves run on
GitHub's computers on a schedule, which is why they keep working when everyone's
laptops are shut.

So there is nothing you can break by trying. Your changes live on a branch until
Roman merges them.

## How to ask for what you want

Talk to it the way you would explain the problem to a new hire. Plain English is
correct. Do not try to sound technical.

A good first message names the annoyance, not the solution:

> Every morning I check which tutors have not confirmed their lessons for the
> week, and I chase the ones who haven't. It takes me 20 minutes and I sometimes
> forget on Fridays. Can we automate the checking part?

Claude will read the repo, ask you the questions it needs (which line, who owns
the follow-up, what counts as "not confirmed"), and then write it.

Say "explain what you are about to build before you build it" if you want to see
the plan first. Always fine to ask.

## What makes a good first agent

| Good first agent | Save for later |
|---|---|
| Reads something and reports it to you in Slack | Sends a text or email to a family |
| Runs once a day and tells you what it found | Runs every minute |
| Watches one thing | Does five things |
| Writes nothing, or writes one note | Changes deals or bulk-updates HubSpot |

The pattern that works: **first make it watch and tell you.** Live for a week.
Then, if the reports are right every day, ask for the part where it acts. Almost
every agent in this repo got built in that order, and the ones that skipped it
are the ones that caused incidents.

## What happens after you build it

1. Claude opens a **pull request**. That is just a proposal, visible to
   everyone, with a list of exactly what changed.
2. The test suite runs on it automatically.
3. Roman reads it and merges, or sends it back with questions.
4. It runs in **shadow mode**: on its real schedule, with its real data, sending
   nothing. It logs what it *would* have done.
5. When a week of shadow output looks right, Roman flips one switch and it is
   live.

Merged does not mean live. That is on purpose, and the switch is Roman's.

## The rules you inherit without doing anything

The repo carries its own rules and your session reads them automatically. You do
not have to memorise any of this, but it helps to know it is there:

- **CLAUDE.md** at the root: the house rules, loaded into every session.
- **`.claude/skills/`**: three skills that load themselves when relevant.
  `aplus-new-agent` (how we build and ship), `aplus-outbound-copy` (every locked
  rule about what we say to families, teachers and tutors), `aplus-hubspot`
  (how to touch the CRM without breaking it).
- **`knowledge/journey/`**: the customer journey and the six pre-send checks
  that every outbound message passes.
- **`ops/values/care-values.md`**: CARE. Every agent that reasons is grounded in
  it.

So when you ask for something that would text a family at 6am on a Saturday,
your session already knows not to. It will tell you why.

## Four things never to do

1. **Never flip a `_LIVE` switch.** Going live is Roman's decision, every time.
2. **Never send to a family, teacher or tutor without a go for that exact
   message, that exact audience, that exact line.** "Watch the replies" means
   read and report. It does not mean answer.
3. **Never run a bulk HubSpot update.** Write the script, get it reviewed, and
   Roman runs it. A bad bulk write is very hard to undo.
4. **Never paste an API key, token or password into a session.** You will never
   need to. If something asks you for one, stop and ask Roman.

## When you get stuck

Ask Claude in the session first. "I don't understand what you just did",
"explain this like I'm not technical", "what would break if we did it the other
way" are all good questions and it will answer them properly.

If it is a judgment call about the business (which line, whose name goes on it,
whether we are allowed to say something), that is Roman, not Claude.

## The one habit worth having

When something annoys you twice, write it down. Not the solution, the annoyance.
Half of the agents in this repo exist because somebody noticed they were doing
the same small thing over and over. You are the ones doing that work, so you are
the ones who can see it.
