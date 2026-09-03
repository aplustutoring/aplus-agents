---
description: Convene the A+ council on a question or thesis. Fixed seats argue from evidence, disagreements are surfaced, then one verdict and one go line. Usage: /council <question or thesis> [--save]
---

Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.

# /council

Roman 2026-09-02: "I would like a #council command and analysis." The council is
how a decision gets stress-tested before it becomes a campaign, a schema change,
or a process. It exists because a single perspective (usually sales) writes the
plan, and the seats that pay for it (ops, the customer, finance) find out later.

The topic is: $ARGUMENTS

## Ground rules

1. **Evidence before opinion.** Before any seat speaks, pull what the repo and
   the portal already know about the topic: `docs/CHANGELOG.md`, the relevant
   `ops/` or `scripts/` folder, prior campaign docs, and read-only HubSpot
   queries where a number settles an argument. Every seat cites at least one
   fact, or says "no evidence" out loud. Never invent a number.
2. **If Roman stated a thesis, test it.** Say in one line what the thesis is,
   then each seat says whether it holds and why. Do not restate the thesis as
   the verdict without testing it.
3. **Seats must take a position.** "It depends" is not a position. A seat may
   say "I'd change X" but must say what X is.
4. **Surface disagreement.** Where two seats conflict, name the conflict in
   the convergence section. Do not average them into mush.
5. **Roles, not names.** Seats are named by role (sales seat, charter_sales
   seat), never by the person who holds the role today. See CLAUDE.md.
6. **Enumeration rule.** Any HubSpot option you cite is its LABEL, never the
   internal value.
7. **Style.** Verdict first. Tables for anything with more than two options.
   No em dashes anywhere. No headers unless the output runs long. Close with
   ONE go line (approval-first: propose, execute only on explicit go).

## The seats

Convene these in order. Add a seat only if the topic clearly needs one (for a
tutor-facing question add the tutor's chair; for a schema question add the
data-model seat).

| Seat | Owns | Typical question it asks |
|---|---|---|
| **Sales seat** | New programs, multiple-student acquisition, teacher and director relationships | Does this get a school to send more kids? What does the teacher have to do? |
| **charter_sales seat** | Families, specific-student teacher contact, PO chase, consultations | What lands on my calendar, and how fast do we have to call? |
| **Ops / PO desk** | po_inbox, deal sync, invoices, Teachworks | What breaks in the paperwork? What gets created that nobody closes? |
| **Finance / data** | Revenue attribution, concentration, what the numbers actually say | Where is the money, and is the effort pointed at it? |
| **Risk / brand** | Cost commitments, compliance, reputation, what we can't measure | What does this cost if it works? What can't we see afterwards? |
| **The customer's chair** | The teacher, the family, or the director this is aimed at | What does this ask of me, and why would I do it this week? |
| **Devil's advocate** | The best case against the plan | Why is this the wrong move, or the wrong list? |

Each seat: 3 to 6 sentences, plain language, first person as the seat. Bold the
seat name. Cite the fact. Take the position.

## Convergence

After the seats:

1. **Verdict, one paragraph.** Does the thesis hold? What changes?
2. **The plan the council converges on.** A table if there are segments,
   options, or waves. Include counts when you have them.
3. **Fixes before go.** The things that have to be true before anything ships.
   Usually one to three. Not a wish list.
4. **One go line.** What Roman says to make it happen, and the smaller
   alternative if he wants a smaller first step.

## Saving

If `--save` is in the arguments, write the full council output to
`docs/councils/YYYY-MM-DD-<slug>.md` (slug from the topic, kebab-case) and add
a CHANGELOG entry if the verdict locks a decision. Otherwise the council lives
in the conversation only; remind Roman that a locked decision still goes to the
A+ Decision Log (#AP### format).

## What this is not

Not a research report. Not a place to list every option. Not a substitute for
Roman's decision. The council argues; Roman decides.
