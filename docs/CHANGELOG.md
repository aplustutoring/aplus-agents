# aplus-agents changelog

Session-level record of changes to agent behavior, schema, skills, or process —
the shared memory between Claude-in-chat and Claude Code sessions. Every session
that changes how the fleet behaves appends an entry here (see the Session
Documentation Protocol in `CLAUDE.md`): date, what changed, WHY, files touched.
Newest entries first.

---
## 2026-08-25 — Teacher emails now ask about THIS year's caseload

**Roman:** "they probably don't even have the same students on their case this
year that they had last year... they probably don't give a fuck about the lesson
notes from last year."

**Checked before rewriting, and the data agrees.** Of the teachers who have
returned in 26/27 so far: Christine Gurney had 11 families last year and carried
1; Christie Beadle had 8 and carried 0; Maya Lee had 5 and carried 1; Mary
Nieves 6 and carried 2. Five of the seventeen returning families are now with a
different teacher. A charter TOR's caseload turns over, so an email built on
last year's roster is about children who are no longer theirs.

Caveat recorded in the campaign doc: only ~20 families have 26/27 deals this
early, so this is directional. It did not change the decision, because the risk
is asymmetric — an ask aimed at this year's caseload works either way, and one
aimed at last year's roster fails if rosters turn over.

**What changed:** the session-notes offer went from being the ask to a single
standing line at the end, and it is gone from the follow-up entirely — the
follow-up now repeats the caseload question. The new ask is "You probably have a
different caseload this year. If there is a student on it who is behind and not
getting targeted support anywhere else, tell me about them." Naming the turnover
out loud is also a small credibility signal: it shows we know how their year
works.

B3 drops the notes offer completely. One family last year is not worth offering
notes on, and raising it only highlights how little we did together.

**Second-order effect worth noting:** this weakens the case for the B1/B2/B3
volume split at the copy level. All three now say nearly the same thing, because
the ask no longer depends on how many families a teacher sent us last year. The
split still earns its keep for the Day-8 call ranking and for sequencing, but
three near-identical emails is now a live merge question for Roman.

**Files:** `ops/messenger/templates/campaign-tor-2026-08/` (4 drafts),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-25 — Teacher emails: the Badge leads instead of hiding in the signature

**Roman:** "why cant we just share it in the first emial as hey, guess who got
this shit, woooptii what."

Fair. I had put the NSSA Badge in a credential line under the signature, which
treats real news as fine print. Worse, it wasted the best thing about the news
for THIS audience: the program these teachers sent students to was reviewed and
passed. That reflects on their judgment, not just ours.

**All four wave-1 emails now open on it**, subject "We got some good news":

> Stanford's National Student Support Accelerator reviewed how our tutoring
> program is built, step by step. We passed. A+ Tutoring holds their Tutoring
> Program Design Badge for 2026-2029.
>
> I wanted you to hear it from me. You trusted us with your students, and that
> is the whole reason we care about getting this right.

The second paragraph is what keeps this from being an email about us: it turns
straight back to their students, which is Danielle's own note from 2026-08-24.
Then the segment ask, one line.

**The NSSA guardrails held automatically**, and it is worth recording why the
copy is safe rather than just asserting it:
- "reviewed how our program is BUILT" and "Program Design Badge" keep the claim
  on DESIGN. NSSA is explicit the Badge does not denote effectiveness.
- **These emails make no outcome claim at all** — no percentages, no RIT gains —
  so the Badge and results never appear together. Checked programmatically: the
  only digits in any body are 2026 and 2029.
- No "certified", "accredited", "endorsed", "approved provider", "proven
  results", "Stanford-validated". Also checked programmatically.
- Term window travels. "Badge" capitalised. Text only, no image: a trademark
  graphic in a 60-word personal note reads as marketing, which is the opposite
  of what these are.

Length went from ~60 to ~130 words. That is the real cost, and it is worth it:
the news earns the extra paragraph, and the ask still sits in one line.

**Files:** `ops/messenger/templates/campaign-tor-2026-08/` (4 wave-1 drafts).

---
## 2026-08-21 — TOR name matching: 119 of 218 orphaned deals were ours all along

**What:** Rewrote the name matcher in `scripts/charter_tor_segments.py`. Deals
attributed 2,026 -> 2,145; teachers with attributed deals 186 -> 205; orphaned
deals 218 (75 names) -> 99 (41 names). Still read-only — nothing built in the
portal, no properties stamped.

**Why:** the previous entry logged "75 teacher names on 218 deals have no
contact record" as a hygiene queue. Triaging it showed that was the wrong
diagnosis for more than half the queue: **119 of those deals name a teacher we
already have.** `norm_name` did `re.sub(r"[^a-z ]", "", s.lower())`, which
deletes rather than folds. Four structural patterns fell through it:

| pattern | deal value | contact | deals |
|---|---|---|---|
| accent deleted, not folded | `Veronique Fabre` | Véronique Fabre | 8 |
| hyphen glued the surname | `Stephanie Negrete-Claar` | Stephanie Claar | 14 |
| double/married surname | `Heather Pfeifer Tolan` | Heather Tolan | 26 |
| `Last, First` (Ocean Grove import) | `Wood, Colleen ` | Colleen Wood | 3 |
| curly apostrophe + reversed | `O’Hagan, Whitney` | Whitney O'Hagan | 1 |
| middle initial | `Dawn L Gordon` | Dawn Gordon | 2 |
| email localpart as the name | `bthurman` | Brittany Thurman | 5 |

`norm_name` now NFKD-folds and maps punctuation to a separator; new
`name_tokens` un-reverses `Last, First` and drops middle initials; `attribute`
matches over four tiers (exact / token-set / surname-subset / email-localpart)
and reports the tier mix. **Every tier only fires on a UNIQUE match** — ties are
reported, never guessed, which is the same discipline as the original.

**Why it mattered to fix BEFORE the portal build:** 23 teachers were in the
wrong segment and 27 had understated merge tokens. Crystal Schoelen sat in
C1 "Intro" on 14 deals; Brittany Thurman in C2 "Intro" on 5 — both queued to be
told we had never worked together. Heather Tolan's copy would have read 9
students instead of 13, Christine Mondolo 1 instead of 7. Nothing was built
yet, so this cost one commit; after the build it would have meant re-stamping
1,184 contacts and rebuilding six lists.

**The 99 that remain are a real queue, triaged and verified against the portal:**
- **34 deals / 17 names — the contact EXISTS** but under a nickname, spelling or
  truncation the matcher must not guess (Judith->Judy Flora 5, Margaret->Maggie
  Pulley 4, Diana->Diane Miscione 3, Katherine K Sommer->Kate Sommer 2). Two are
  contact-side defects, not deal-side: `kbrown@ieminc.org` has lastname stored
  as literally "F", and `Kathryn Connely` carries the email localpart
  `kylee.connelly`. Awaiting Roman's row-by-row go.
- **50 deals / 20 people — genuinely missing**, verified zero surname match
  anywhere in the portal (Catherine Peloso 9, Brigid Feeney-Sherry 9). Cannot be
  created from CRM data: deals carry no teacher email (0 of 2,284), so this needs
  a school roster. **Does not block the send** — with no contact record they are
  not on any list either way.
- **15 deals / 3 values — junk.** `No EF Info` x13 (fix the intake form, not the
  data), plus two unresolvable single tokens. `bthurman` was NOT junk.

**Separate defect found, needs a merge decision:** `mina chang` matches two
contacts carrying **23 deals** — `3609251` (`mina.chang@`, FORM, 2023-11-06, 19
deals) and `195319672330` (`evcott@ileadexploration.org`, INTEGRATION,
2026-01-22, 1 deal). Same name, school, persona and lead status; no "EV Cott"
contact exists, so the second looks like an integration duplicate with a
mis-keyed email. The matcher correctly refuses to pick.

**Files:** `scripts/charter_tor_segments.py`, `docs/CHANGELOG.md`.

**Decision-log candidate for Roman (#AP format):** "name matching against CRM
contacts folds accents and punctuation and matches on a surname subset, but only
ever accepts a UNIQUE match — an ambiguous name is reported for a human, never
auto-assigned."

---
## 2026-08-24 — Scholarship: selection criteria, the post-session path, and a scarcity call

**Roman filled in three of the five blanks** the canonical file flagged:

1. **Criteria:** the student's need, and the teacher's rationale for nominating.
2. **In practice we do not reject nominations** — "we wont say no, but they need
   to feel like we did."
3. **After the free session:** the family is expected to continue on their
   **instructional funds**. Where a family has none, we look at other avenues,
   and "hope to not get to them."

**On (2) I pushed back and then built the honest version.** Copy that asserts
selection ("we select from the nominations", "limited spots") is manufacturing
scarcity if nothing is ever turned down, and it fails in a specific, likely way:
a teacher nominates three students, all three are accepted, and teachers at the
same school compare notes. The cost of being caught is larger than the lift.

The effect Roman wants is real and reachable without the claim. **Asking a
teacher to justify a nomination is what makes the choice feel weighed**, and the
rationale IS the criterion, so it is simply true. The P.S. became:

> Teacher Scholarship Program: nominate a student and tell me why them. They get
> a free session with one of our tutors. Who comes to mind?

Recorded in the canonical file as a rule with its reasoning, plus the note that
if a genuine cap is introduced later the copy can say so plainly.

**On (3),** three new copy rules: never present the free session as the end of
the offer; never lead a nomination ask with funding mechanics, because the
teacher's job is to name a student, not to means-test a family; and a stated
honest answer for "what happens after?".

**Still unknown, still not to be invented:** how many are selected per period
(no cap exists today), cadence, what the family is told about how their student
was chosen, and what "other avenues" concretely means.

**Files:** `knowledge/programs/teacher-scholarship.md`,
`ops/messenger/templates/campaign-tor-2026-08/` (4 P.S. blocks),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Teacher Scholarship Program gets a canonical description

**Roman:** "it has to be clearly and properly identified here. and we have a
criteria that we select them. teachers nominate, we select. scarcity component
in play. but you are right. has to be universal."

**New `knowledge/programs/teacher-scholarship.md`** — the source of truth for how
the programme is described. Every email, SMS, landing page, agent template and
human reply must match it.

**Why it needed to exist:** this campaign described the same offer wrong twice in
one day. Draft 1: "covers one student in full, no charter funds involved."
Draft 2, after correction: "gives a student of your choosing one free session,
tell me who and I will set it up" — right about the session, wrong about who
decides, and it deleted the selection step. Both errors came from paraphrasing
the 22 marketing emails, because those emails were the ONLY written description
of the programme anywhere. A definition that lives only inside its own marketing
will drift every time someone reads it.

**The programme, correctly:** a teacher nominates a student (up to three, one
form each). **We select from the nominations.** The selected student receives
**one free session.** Nomination is not acceptance, and the scarcity is
deliberate. Approved short form now in all four warm drafts:

> Teacher Scholarship Program: you nominate a student, we select from the
> nominations, and the student selected gets a free session. Who would you put
> forward?

**The file also records what is NOT known**, explicitly so no agent invents it:
selection criteria, how many are selected per period, cadence, what happens
after the free session, and whether families are told there was a pool. Copy
stays silent on all of it until Danielle fills them in.

**Known drift documented, not fixed:** the live funnel contradicts this on both
points. Stage 1.3 (`217749216439`) promises ongoing "one-on-one tutoring...
plus session notes"; Stage 3.1 (`217749280608`) says "we can't wait to reach out
to their families" as though nominating were being accepted. Those are
Danielle's live emails; rewording them is hers and Roman's call, not this
session's. Wave 1 points teachers at that funnel, so it is a launch dependency.

**Files:** `knowledge/programs/teacher-scholarship.md` (new),
`ops/messenger/templates/campaign-tor-2026-08/` (4 P.S. blocks),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Scholarship offer corrected: one free session, not a funded spot

**Roman:** "our scholarship program provides 1 free session to a child that the
teacher wants."

The teacher drafts said the Teacher Scholarship Program "covers one student in
full, no charter funds involved". That is a materially bigger promise than one
session, and it was in the P.S. of all four warm segments. Corrected to "gives a
student of your choosing one free session. Tell me who and I will set it up."

Where the error came from: the live funnel's own language. Its emails are the
only written description of the programme, and Stage 1.3 is titled "A free
tutoring spot for one of your students". Reading that as a funded spot is the
natural reading, which is the point below.

**⚠ The live funnel carries the same overclaim.** Stage 1.3 (`217749216439`)
describes "free, synchronous one-on-one tutoring with a real tutor, matched to
exactly where they need support, plus session notes so everyone stays in the
loop" and never says one session. Stage 3.1 adds that a teacher may nominate up
to three students, one per form submission, which reinforces the impression of
something ongoing. **22 automated emails currently set an expectation the
programme does not meet.**

This is now a dependency of the teacher campaign rather than a separate issue:
wave 1 points teachers at that funnel, so it inherits the mismatch. Flagged for
a pass with Danielle before launch. **Not changed** — those are her emails and
live automation, so editing them is Roman's and Danielle's call, not this
session's.

**Files:** `ops/messenger/templates/campaign-tor-2026-08/` (4 P.S. blocks),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Teacher copy: curiosity over pitch (and a promise we could not keep)

**Roman:** "curiosity over bullshit, school year start is busy."

That changed the ASK, not just the length. The previous pass got the emails
short but the ask was still "want me to send you the roster of your families?"
which is handing a teacher an admin task in the busiest month of their year.

Rewritten so each segment leads with something the teacher does not have and
cannot get elsewhere:

* **B1 / B2** — a teacher never finds out what happened to the students they
  referred, because nobody reports back to them. "Some finished the year, some
  stopped partway, and I doubt anyone told you which. I can, in one email.
  Want it?" Replying costs one word; the answer is genuinely theirs.
* **B3** — one family is too thin to offer a report on, so it asks the one
  question a teacher three weeks in already knows the answer to: "Is there a
  student you are already worried about?"
* **C1** — the numbers ARE the hook, so they became the subject: "Sixteen of
  twenty".
* **C2** — the hook is what most teachers do not know: the money is already
  allocated.

**56 to 77 words each** (was 70-95, was ~200 before that).

**⚠ The rewrite created a promise we cannot currently keep, caught before send.**
B1 and B2 now promise an answer that requires Teachworks lesson history, and
**the Teachworks key exists only in GitHub Actions secrets** — it is not in the
local .env and cannot be pulled ad hoc. If 80 teachers reply and Danielle cannot
answer for three days, the curiosity hook becomes the thing that burns her.

**New hard pre-send step, documented in the campaign doc:** generate the
per-teacher answer sheets via one `charter-gap-analysis.yml` run BEFORE wave 1
goes out, and hand Danielle the file. Not yet built as a per-teacher view.

**Files:** `ops/messenger/templates/campaign-tor-2026-08/` (all 6),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Teacher copy cut from ~200 words to 70-95 (Roman: "AI slop")

**Roman:** "why are these emails so verbose. its going to be clear that ai wrote
it. these are busy teachers. they dont need ai slop sent to them. the goal is to
replicate danielles brand voice. but to be concise."

**He is right, and the failure was structural, not stylistic.** Every draft had
grown the same five-part shape: welcome line, process explainer, credibility
paragraph, CTA paragraph, scholarship paragraph. Each addition was individually
defensible (the scholarship line came from Danielle's own note, the CTA rewrite
came from her too) and the result was a 200-word email to a teacher in September.
Following the voice skill's rules on vocabulary and punctuation while ignoring
its rule about ending on the human reality produced something that passed every
check and still read as machine-written.

**All six rewritten. 70 to 95 words each**, one ask, scholarship demoted to a
one-line P.S., short signature on the warm segments (full title kept on the cold
intros, where the credential does work). What got cut: the "welcome back to the
school year" line as its own paragraph, every explanation of the PO process the
teacher already runs, and the second CTA.

What was deliberately kept: the honest opt-out ("if nobody needs it right now,
say so and I will check back later in the year"). It is the most in-voice line
in the set and it is what stops the email reading as a pitch.

Length is now a documented constraint in the campaign doc, with editing rules,
so the next pass does not re-inflate them.

**Files:** `ops/messenger/templates/campaign-tor-2026-08/` (all 6),
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Persona hygiene: 7 contacts are tagged as the wrong persona

**What:** New `scripts/tor_persona_backfill.py` (read-only). Roman, on the Sage
Oak backfill candidates: "i'm assuming [they] are support staff or
administrators?" Correct — 4 self-identified as support staff at the booth,
1 as administrator, 2 more are admin/director by job title, 2 are system
mailboxes, 4 unverified. **None were confirmed teachers**, and 12 of the 13 were
flagged only because `hs_lead_status` said TOR.

**The most valuable finding was not in the backfill list at all.** The first
version proposed re-tagging 16 "Decision Makers" — but 15 of them were ALREADY
tagged Decision Maker/Director correctly. What was stale was their lead status.
Excluding anyone carrying any persona shrank the list from 121 to 101 and turned
up the real problem: **7 contacts carry a persona that contradicts their job
title.**

| Contact | Job title | Tagged | Should be |
|---|---|---|---|
| **Lisa Barlow** | Educational Facilitator | Decision Maker/Director | **Teacher of Record** |
| Brittany Carper | ELD TOSA / Home School Teacher | Decision Maker/Director | Teacher of Record |
| Kathleen Hermsmeyer | Superintendent | Teacher of Record | Decision Maker/Director |
| Lisa Fishman | Chief Operations Officer | Teacher of Record | Decision Maker/Director |
| Heidi Gasca | Superintendent | Teacher of Record | Decision Maker/Director |
| Dawn Anthney | Academic Dean | Teacher of Record | Decision Maker/Director |
| Richard Noblett | Chief of Outreach and Development | Teacher of Record | Decision Maker/Director |

**Lisa Barlow is the expensive one.** She is named as Teacher of Record on
**16 charter deals** — the single largest name in the orphaned-deals hygiene
queue — and the mis-tag was silently excluding one of our most active teachers
from a campaign built for exactly her. The other five would have received a
"welcome back, I know what it costs you to keep track of your students" email
addressed to a Superintendent or a COO.

A mis-tag costs in both directions, and neither direction raises an error. The
conflict scan is now a permanent section of the script's output.

**Also:** the role-mailbox filter was widened. It was prefix-anchored, so
`summit-techteam@sageoak.education` slipped through. It now matches whole words
anywhere in the localpart (split on separators and camelCase) plus a substring
pass for run-together forms, and a companion `looks_like_team_name` catches
records literally named "Summit Tech Team" or "Enrichment Team". Verified it
still does NOT fire on `apadilla@ileadca.org` — a person whose initials happen
to spell a role. Role mailboxes caught: 19 -> 32. **Wave 1 unchanged at 193.**

**Nothing was written to the portal.** All three lists (1 to tag as teacher,
8 high-confidence not-teachers, 7 conflicts, 20 lead-status mismatches, 28
shared inboxes, 63 needing a human) are read-only output plus a CSV.

**Files:** `scripts/tor_persona_backfill.py` (new),
`scripts/charter_tor_segments.py`.

---
## 2026-08-24 — a_persona is the teacher audience (the architecture already existed)

**Roman:** "dont we have a persona for teachers as well in the A+ Persona
property, or did i get amnesia. we creaed property architecture."

No amnesia. `a_persona` = "Teacher of Record/EF/ES" existed, was populated on
1,064 contacts, and this campaign was using it as **one vote in a four-signal
union** instead of as the audience. CLAUDE.md says every agent reads a_persona
FIRST to know who a contact is. The union bypassed that, and everything fixed
earlier today was downstream damage from it.

**The persona is cleaner AND nearly as complete as the union:**

| Signal | Contacts | Families | Role mailboxes |
|---|---|---|---|
| a_persona TOR | 1,064 | 6 | 20 |
| lead status TOR | 1,083 | 5 | 19 |
| charter_school_teacher known | 1,173 | 48 | 35 |
| EF flag | 548 | 3 | 0 |

The union added 121 beyond the persona; 57 of those were junk (42 families,
15 role mailboxes) and only 64 were real teachers the persona was missing.

**Changed:** audience is now the persona alone. The other three signals feed a
printed **persona backfill queue** — 64 people who look like teachers and carry
no persona (14 iLEAD, 13 Sage Oak, 6 Ocean Grove, 5 Visions, 5 Horizon, tail).
Reported, never emailed. Tag them in the portal and the next run includes them.

**Persona now beats heuristics.** `looks_like_family` no longer fires on a
contact explicitly tagged Teacher of Record. That is the dual-persona case the
5-persona model was designed for (#AP030): **Kristy Doyal**, a real Heartland
teacher who is also a parent, tagged `Teacher of Record/EF/ES;Family`, sitting
in segment A with 3 new families this year. The heuristic added this morning
would have silently dropped her. Verified she is included.

**Counts:** audience 1,064, **mailable 925**, **wave 1 = 193** (A 18, B1 18,
B2 62, B3 95). The "family, not a teacher" exclusion disappeared entirely,
because with the persona as the audience families were never in it. The
role-mailbox filter stays: 19 `vendors@`/`ap@` addresses carry the persona
themselves, so the persona is not perfectly clean either.

**Lesson worth keeping:** the fix for a dirty audience was not a better
heuristic, it was using the property architecture that was already built. Two
rounds of filtering this morning were treating symptoms.

**Files:** `scripts/charter_tor_segments.py`, `ops/messenger/campaign-tor.yml`,
`ops/messenger/CAMPAIGN-TOR-2026-08.md`.

---
## 2026-08-24 — Teacher audience was leaking families and AP inboxes; back-to-school framing

**Reported:** Roman, looking at a family win-back email: "is it going to teachers
or families? i feel like we have confusion somewhere."

**The email was fine** (219949261351 is a family email: from Paola, reply-to
admin@, body reads "we'd love to pick things back up with your family"; its list
had zero teacher signal). **The confusion was real but it was upstream, in the
teacher audience this campaign builds.**

`charter_school_teacher` holds WHICH SCHOOL a contact belongs to, not "is a
teacher". It was one of the four union signals, so it pulled in two populations
that are not teachers, 167 contacts in total:

* **33 school role mailboxes** — `vendors@ileadexploration.org`, `ap@ieminc.org`,
  `accountspayable@theblueridgeacademy.com`, `noreply@`, `contractprograms@`,
  `vendorsupport@`. Danielle's copy is a personally-signed "I taught K-8, here is
  what I saw". Into accounts payable, that is a deliverability problem.
* **48 actual families** — parents on personal gmail/yahoo with students and
  tutors stamped (Diana Torres / Freddie & Sarai / tutor Fidah; Veronica Lemus
  Sanchez / Natalia & Nicolas; Karla Diaz / Alicia & Emilie). All three were
  already sitting on the family Win-back Multi list, so they would have received
  BOTH campaigns.
* **78 with no first name**, which would have rendered "Hi ,".

**Fix:** `is_role_mailbox()` and `looks_like_family()` are hard exclusions in
`scripts/charter_tor_segments.py`. A contact carrying real family signals is
never a teacher for this campaign, even when the person is genuinely both.
The nameless contacts are kept, not dropped: every draft now uses
`{{ personalization_token('contact.firstname', 'there') }}`. All 78 are in the
cold C1/C2 waves anyway; wave 1 has none.

**Mailable 1,049 -> 968. Wave 1 is 191.**

**Also:** framing is now BACK TO SCHOOL per Roman ("we are focusing on charter
school teachers and getting a back 2 school workflow going") — every draft opens
on "Welcome back to the school year" and wave-1 subjects lead with "Welcome
back". Matches what Roman pitched to Danielle on 2026-08-20.

**Why it matters beyond this campaign:** the property NAME lies about its
contents, and it will mislead the next thing that segments on it. Worth either a
relabel or a note in the registry. Flagged, not changed — portal relabels are
Roman's call.

**Files:** `scripts/charter_tor_segments.py`, `ops/messenger/campaign-tor.yml`,
`ops/messenger/CAMPAIGN-TOR-2026-08.md`,
`ops/messenger/templates/campaign-tor-2026-08/` (all 6).

---
## 2026-08-21 — Teacher campaign: Sage Oak excluded, Danielle's own CTA applied

**What:** Two changes on top of the segmentation and the matcher fix.

**1. Sage Oak excluded at every segment (76 teachers).** New `EXCLUDE_SCHOOLS`
in `scripts/charter_tor_segments.py`, so it applies to every future wave, not
just wave 1. Source: Roman to Danielle in Slack 2026-08-20, "auto email campaign
to all charter teachers from you (except sage oak)", reconfirmed to this session
2026-08-21 ("exclude sage oak, they will be separate"). Those teachers are
worked through the August Summit booth follow-up Danielle is running, and the
campaign would have double-touched them. **This constraint existed before the
campaign was built and was not in the repo** — it was only in a DM. Worth a
decision-log entry so the next session does not rediscover it.

**2. Danielle's own copy note applied to all six drafts.** She reviewed the
unrelated Sage Oak booth samples the same day and asked for: no long dashes; the
CTA to be "email back and I can help be your guide to get you started"; and a
mention of the Teacher Scholarship Program alongside the main ask. All three
applied here. The sent copy now has zero em dashes (the six that remained were
in internal header lines and are gone too). Scholarship framing checked against
the live funnel before use: 22 automated emails, stages 1 to 6, the pitch is a
fully funded tutoring spot for a nominated student. **No collision** — zero
wave-1 teachers have ever submitted the nomination form, and only 2 contacts
portal-wide have.

**Counts after the matcher fix + Sage Oak (was 1,184 / 1,122):**
1,185 total, **1,049 mailable**. A 17, B1 18, B2 63, B3 96, C1 170, C2 685.
**Wave 1 is now 194**, up from 181, because the matcher fix moved 23 teachers
out of the "no history" intro segments into history-based ones.

**Branch note:** the hygiene follow-up session took `tor-campaign-2026-08` and
committed the matcher fix to it while this session was mid-flight. Rather than
write into a live worktree (the exact collision the concurrency rule exists to
prevent), this work is stacked on `tor-campaign-sageoak`, based on that commit,
so both are preserved and the branch fast-forwards.

**Files:** `scripts/charter_tor_segments.py`, `ops/messenger/campaign-tor.yml`,
`ops/messenger/CAMPAIGN-TOR-2026-08.md`,
`ops/messenger/templates/campaign-tor-2026-08/` (all 6).

---
## 2026-08-21 — Charter TEACHER outreach from Danielle: 6-way segmentation, DISARMED

**What:** The teacher-side counterpart to the family win-back campaign, built to
Roman's ask ("outreach email campaign and workflow in HubSpot for emails to go
out from Danielle to all of our charter school teachers, segment same as we did
with charter families"). New `scripts/charter_tor_segments.py` +
`ops/messenger/campaign-tor.yml` + `CAMPAIGN-TOR-2026-08.md` + six copy drafts
in `templates/campaign-tor-2026-08/`. **Nothing built in the portal** — no
lists, no emails, no workflows. Read-only analysis only.

**Why the axes are NOT the family axes:** the family split is recency x
student-count x personalization. That does not transfer. A teacher has no
lessons of their own and every teacher is "lapsed" in August. What separates
teachers is whether business has already come through them in 26/27 and how
much came through them in 25/26. Segments (total / mailable): A Restarted 14/14,
B1 Anchor 5+ families 17/17, B2 Multi 2-4 60/60, B3 Single 95/90, C1 Intro-iLEAD
181/171, C2 Intro-other 817/770. Total 1,184 / 1,122 mailable; 62 excluded
(54 opt-out, 6 non-marketable, 1 no email, 1 internal), zero hard bounces
because the 155 bounced TORs were archived 2026-08-14.

**Three things the data turned up that were not known going in:**
1. **Deals have no teacher EMAIL.** `teacher_of_record_name` is on 2,244 of the
   2,284 charter deals since 2025-08-01; `teacher_of_record_email_address` does
   not exist as a deal property at all. Attribution is a normalized full-name
   match, which is why the script reports unmatched names instead of guessing.
2. **Token trap:** `charter_school_teacher` is an enumeration and HubSpot email
   tokens render the LABEL. The Ocean Grove label is
   `IEM Inc South Sutter/Ocean Grove/Sky Mountain`, so a school token would have
   printed that to 348 teachers. School wording belongs in the segment, never in
   a token. (The enumeration rule in CLAUDE.md, biting from the other direction.)
3. **75 teacher names on 218 charter deals have no contact record** (Heather
   Pfeifer Tolan 22 deals, Christina Mondolo 21, Crystal Uribe Schoelen 14,
   Stephanie Negrete Claar 14; 13 deals say "no EF info"). They are invisible to
   every segment. Hygiene queue, not a blocker.

**Pilot learnings carried over:** exit goal is `hs_email_last_reply_date`
IS_KNOWN plus meeting booked, **never lead status** (that is what silently
skipped 34 families in the family pilot); Mon-Fri 09:00-18:00 PT action windows.

**Deliverability flagged, not decided:** 941 of the 1,122 mailable teachers have
no deal history. Not toxic (557 of 998 have opened something, 7 ever replied,
zero hard bounces) but stale — most were last emailed 2025-01. Sending them in
one morning off the domain currently running the family win-back risks that
campaign's placement. The doc proposes a 3-week ramp, warm first, Ocean Grove's
348 last and split.

**Also:** `enroll.py` gained `--config` (defaults to `campaign.yml`, so the live
family campaign is untouched) so the two campaigns cannot arm each other.
4 new `[Agent]`-labeled properties in the `tor` group: `tor_family_count`,
`tor_student_count`, `tor_families_lapsed`, `tor_segment`.

**Two decisions locked same session (Roman 2026-08-21):** (1) send-from is
`danielle@wetutorathome.com` / fromName "Danielle Brodetsky", NOT her owner
email `success@` — checked the portal and that exact pair is already on 30
recent marketing emails, so no sender setup is needed. (2) Scope is warm-first:
**wave 1 = A + B1 + B2 + B3 only, 181 mailable.** C1/C2 (941 near-cold) stay
unbuilt until wave-1 reply and bounce data lands. Both recorded in
`campaign-tor.yml` and the campaign doc. **Decision-log candidates for Roman
(#AP format):** the warm-first ramp rule for cold charter sends, and
"personally-signed campaign email sends from the person's own alias, never a
shared mailbox".

**Still blocked on Roman:** wave-1 copy approval, then GO for the portal build.

**Noticed, not fixed:** `registry_check.py` flags `automation-audit.yml` as a
live workflow with no registry entry. Pre-existing, unrelated to this session.

**Files:** `scripts/charter_tor_segments.py` (new), `ops/messenger/`
{`campaign-tor.yml`, `CAMPAIGN-TOR-2026-08.md`, `enroll.py`, `README.md`,
`templates/campaign-tor-2026-08/` (+6)}, `ops/hubspot-schema/properties.yml`,
`registry.yml`.

---
## 2026-08-20 — Spotlight Orchestrator: a missing reel is no longer a silent miss

**Reported:** Paola — the case study for Amelia arrived in
#student-spotlight-ready with the blog, graphics and text-stories, but no
superhero reel, and nothing said one had been attempted.

**Diagnosis (correcting the filed one):** the reel IS wired into the
orchestrator — `stage_reel` sits in `STAGE_ORDER`/`STAGE_DISPATCH` between
`slack` and `textstory`, and the workflow installs ffmpeg for it. The reel
scripts missing from the registry's `depends_on` is a documentation gap, not
the cause. The real defect is that the stage has no failure signal at all:
`stage_reel` caught every exception, wrote `reel_status` into
`marketing/state/spotlight-runs.json` (gitignored — it does not survive the CI
job), printed to stderr, and exited 0 under a "SPOTLIGHT ORCHESTRATION
COMPLETE" banner that never mentioned the reel. The neighbouring textstory
stage already solved exactly this with a SLACK_FAILURE_CHANNEL heads-up; the
reel stage was never given one. On top of that a single flaky Veo beat killed
the whole reel with no retry, and `make_clips.py` polls Veo with no ceiling of
its own, so a stuck generation could burn the job's 30-minute timeout and take
the later stages down with it.

**Why it matters:** the reel is the only asset in the pack whose absence is
invisible. Every other piece either lands in the thread or fails the run. A
bonus asset being non-fatal is right; being unobservable is not — the miss
surfaces only when a human notices the gap days later, which is exactly how
this was found.

**Fix:** in `stage_reel` — one retry of the generation steps (all of them are
resumable, so the retry only regenerates what failed); a shared wall-clock
budget, `SPOTLIGHT_REEL_TIMEOUT_S` (default 900s), so the stage cannot eat the
job; delivery kept to a single attempt and budgeted separately so a retry can
never double-post into Paola's review thread; and a Slack heads-up on failure
via the same channel the textstory stage uses. `stage_complete` now prints the
reel status. The textstory alert was refactored onto the shared
`_post_stage_alert` helper with its message unchanged.

**Verified:** seven stubbed scenarios against `stage_reel` (happy path, flaky
step rescued by the resumable retry, hard failure, hang past the budget,
delivery failure, `--skip-hubspot`, no failure channel configured) — no APIs,
Slack or ffmpeg touched. Textstory alert text confirmed byte-identical.

**NOT verified against Amelia's bundle.** Bundles are gitignored and built in
CI (30-day Actions artifact), and re-running the reel needs Gemini/OpenAI/Slack
credentials, so the approved plan's steps 1–3 and 5 (locate the bundle, re-run
the pipeline standalone, diff against the last good reel, deliver to Paola)
cannot be done from the repo. They need a re-dispatch of Amelia's Drive folder.

**Left undone deliberately:** the reel scripts are still absent from the
registry's `depends_on` for `spotlight-orchestrator` — the session was scoped
out of `registry.yml`. Worth a one-line follow-up.

**Files:** `marketing/scripts/b2c/spotlight_orchestrator.py`.

---
## 2026-08-20 — Photo booth registered (39 agents, new Events engine)

**What:** `sage-oak-booth` is in `registry.yml` — the Cloudflare Worker + Pages
booth from PR #66, under a new `Events` engine. Written by reading `worker.js`
rather than the README, so the entry lists what it actually does: upserts the
HubSpot contact by email with the five events-group properties, applies a
CREATE-ONLY persona stamp by self-identified role (teacher → TOR persona + lead
status, administrator → Decision Maker, support_staff → none, existing contacts
never overwritten — po_inbox doctrine), logs an email engagement and a photo
note on the contact, sends the framed photo via Resend, and sends MMS from the
main A+ line via JustCall.

**Why now:** PR #66 merged mid-session and `registry_check.py` flagged
`booth/wrangler.toml` within a minute — the discovery heuristic added earlier
today doing exactly its job on a real merge rather than a simulated one.

**Two things recorded in the entry that are not in its README:**
- It is hand-deployed in TWO pieces (`wrangler deploy` + `wrangler pages
  deploy`); editing this repo makes neither live.
- **REVIEW ITEM for Roman:** `GET /photo/<key>` is public and unauthenticated —
  unguessable-key privacy only — and the archive copy is written with NO TTL, so
  attendee photos stay publicly retrievable indefinitely. Reasonable for MMS
  delivery, worth a deliberate decision for a school event.

**Also flagged:** status is `active`, but this is scoped to one event. When Sage
Oak BTSC 2026 is done it should go `unverified` or be retired rather than sit
`active` forever.

**Files:** `registry.yml`, `ops/fleet-health/fleet_brief.py` (Events in the
engine order), `docs/FLEET.md`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — Feedback agent: the pinned channel post is not a report

**What:** Intake now drops "channel furniture" before classification. A
top-level message matching ≥2 distinct phrases from the pinned how-to-use post
(`intake.ignore.meta_markers` in `ops/feedback-agent/config.yml`) is logged and
skipped — nothing filed, no thread reply, marked processed so Slack retries
don't re-run it. A companion `intake.ignore.sender_app_ids` knob ignores posts
by a given Slack app/workflow; it ships EMPTY on purpose (below). Also withdrew
the mis-filed report from `state/state.json` so Friday's digest doesn't count
it against the feedback agent.

**Why:** Roman posted the channel's own pinned explainer into the channel on
2026-08-20 and the classifier filed it as an IDEA against the feedback agent
(thread 1787258667.896529). The post is written by a human into the channel, so
it carries no `bot_id` and the relay forwards it like any report; the classifier
then did its job on text that describes every agent in the fleet.

**Correction to the approved plan:** the plan proposed ignoring sender
`U0AKFN28V1U` ("the Slack workflow bot at the bottom is the giveaway"). It
isn't one — that ID is the "*Sent using* <@…>" attribution Roman's client
appends to everything he types, including real reports (content-build carousel
overflow 2026-08-04, call-agent exit code 2026-08-20) and his `status` queries.
Ignoring it would have silently swallowed every report Roman files. The knob
exists, documented, empty.

**Files:** `ops/feedback-agent/feedback_agent.py`,
`ops/feedback-agent/config.yml`, `ops/feedback-agent/README.md`,
`ops/feedback-agent/state/state.json`,
`ops/feedback-agent/tests/test_meta_posts.py` (new, 7 tests green).

---
## 2026-08-20 — Screenshot relay: fix shipped, problem NOT closed

**What:** Stopped debugging and wrote the state down. The relay's subtype filter
fix is deployed (Apps Script Version 3, 2:14 PM PT) but screenshots STILL do not
reach the agent: a screenshot posted at 2:15:57 PM produced no dispatch, while a
plain-text reply 35 seconds earlier did. Necessary but not sufficient. Logged as
an open weak point plus a TODO in `ARCHITECTURE.md` carrying the next diagnostic
step (Apps Script -> Executions at 2:15:57; present = script bug, absent = Slack
app config, most likely a missing `files:read` bot scope requiring a reinstall).

**Also:** posted a correction into the pinned #agent-feedback thread. The pin
told the team screenshots were fixed. They are not, and leaving that standing
would have kept people posting reports into a void believing they had landed.
The correction names Danielle's three lost reports explicitly — she has been
reporting the same bug since Aug 13 and getting silence — and gives the
workaround: report in text, attach the screenshot as a thread reply afterwards.

**Roman should edit the pinned message itself** (it was posted under his
account, and the API cannot edit it) to strike the "Screenshots are welcome /
Fixed now" paragraph.

**Rule going in:** do not announce this fixed again without a passing test. It
was announced once already on a fix that was real but incomplete.

**Files:** `ARCHITECTURE.md`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — Approve + merge opened to Danielle, Paola and Emily

**What:** Split `slack.approvers` out of `slack.alerts_to`. `alerts_to` still
controls who gets @-pinged (Roman only — pinging four people on every proposal
trains everyone to ignore pings); `approvers` controls who may fire the coding
agent and squash-merge its PR from a thread reply. Set to Roman, Danielle, Paola,
Emily. Falls back to `alerts_to` when unset, so older configs are unaffected.
The proposal message now names who can act, reporter first.

**Why:** Roman 2026-08-20 — "i want it that danielle or paola or emily could do
the approve and merges." The case it unlocks: whoever reports a problem can ship
its fix. Paola reports the missing reel, Paola approves, Paola merges — no round
trip through Roman for work she is closest to. An unnamed permission is one
nobody uses, hence naming the approvers in the message itself.

**Not delegated:** DEMOTE registry flips stay with Roman until a Fleet Manager
exists to verify state changes (#AP011).

**Also:** posted a pinned explainer to #agent-feedback covering how to report,
the approve/merge/no vocabulary, that screenshots now work, the FERPA rule, and
what to do when the agent stays silent.

**Files:** `ops/feedback-agent/config.yml`, `ops/feedback-agent/feedback_agent.py`,
`docs/CHANGELOG.md`.

---

## 2026-08-20 — Feedback agent: schema debris no longer reaches HubSpot ticket subjects

**What:** The classifier's free-text fields are now scrubbed of leaked schema
fragments, the classification retries once when debris appears, and the ticket
subject truncates on a word boundary instead of mid-token.

**Why:** Caught live on Paola's spotlight report. Structured output is
schema-constrained and `json.loads` parsed it fine — but the model lost the thread
mid-field and wrote schema INTO a value:

    summary = "...the other assets rendered successfully.','clarifying_question':"

That summary flowed unvalidated into `subject: f"[AGENT] {label}: {summary[:120]}"`,
so the drafted HubSpot ticket read `...successfully.','clari` — a corrupted subject
line on a ticket the whole team sees.

**How:** `scrub_debris()` cuts any trailing `'...','field':` fragment out of
summary / ack_message / clarifying_question and reports which fields were dirty;
one retry (degraded output rarely repeats), then ship the scrubbed value rather
than fail — a slightly clipped summary still reaches a human, a crash does not.
`truncate_words()` replaces the raw `[:120]` slice. Verified against the real
failure plus false-positive guards: legitimate apostrophes ("Danielle's op-ed")
and colons ("Ratio is 3:1") are untouched.

**Files:** `ops/feedback-agent/feedback_agent.py`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — INCIDENT: every #agent-feedback report with a screenshot was silently dropped

**What:** The Slack relay dropped any message carrying a file. Slack tags an
attachment-bearing message `subtype: "file_share"`, and the relay's filter was a
bare `if (ev.subtype) return textOut_('ok')` — written to drop edits, deletes and
joins. The relay answers Slack `ok`, so there was no error, no retry, and no
Actions run. The report simply evaporated, and from the reporter's side the agent
had ignored them.

**Evidence (100% correlation across the visible channel history):** reports WITH
a screenshot — Danielle Aug 13, Aug 17, Aug 18; Paola Aug 20 — got no agent reply
at all. Reports WITHOUT one — Paola Aug 14, Roman Aug 20 09:21, the Aug 20 13:11
test — were all answered within a minute.

**Why it matters more than the count suggests:** people attach a screenshot
exactly when a problem is visual and hard to put in words, so this ate the most
careful reports. Danielle reported the LinkedIn op-ed being cut off THREE times
(Aug 13/17/18), each with a screenshot, each into a void — while the one report
of hers that did land (Aug 11) had its fix run die on the claude-code-action bot
guard. She has never once seen this loop work.

**Fix:** allow `file_share` and `thread_broadcast` through; keep dropping edits,
deletes, joins and bot messages. A file-only post (screenshot, no words) now
falls back to the file title instead of being dropped for having no text. The
dispatch payload carries `has_files` so the agent can ask what the screenshot
shows rather than guess — it classifies from text and does not read images.
Filter verified against seven event shapes; the script parses.

**NOT LIVE YET.** This is an Apps Script: it deploys by hand from the Apps Script
UI, and editing the file in this repo changes nothing until someone pastes it in.
That deploy is Roman's. (Exactly the hazard the `runtime:` field added earlier
today exists to make visible.)

**Files:** `ops/feedback-agent/relay/apps-script.gs`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — `runtime:` — the fleet is not all GitHub Actions

**What:** Added a required `runtime:` field (`github-actions` | `cloudflare-worker`
| `apps-script` | `zapier`) plus `source:` for non-Actions agents, registered the
two Google Apps Scripts that were previously named only as the `source:` of other
entries (`spotlight-drive-watcher`, `feedback-slack-relay`), and taught
`registry_check.py` to DISCOVER non-Actions agents rather than only validate
declared ones — `wrangler.toml` means a Worker, `*.gs` means an Apps Script, and
anything unreferenced by the registry is flagged. FLEET.md now prints the runtime
when it is not the default and warns that those agents deploy by hand.

**Why:** Roman asked why the photo booth agents were not in the handoff. Three
reasons, worst last: it is on the unmerged `booth-backend` branch (PR #66 open,
22 commits); it is a Cloudflare Worker + Pages app, which the registry's
workflow-shaped schema could not express; and **registry_check.py structurally
could not have caught it** — it compared registry.yml against
`.github/workflows/` only, so Workers, Apps Scripts, and Zapier zaps were an
invisible class. The booth writes four contact properties to production HubSpot,
emails via Resend, and sends MMS from the main A+ line.

**Bug found while testing:** sibling-directory coverage was too loose — the
spotlight watcher's `.gs` was masked by `download-drive-folder.py` in the same
directory, so deleting its registry entry did NOT trip the check. Sibling
coverage is now per-pattern: on for `wrangler.toml` (config beside a named
worker script), off for `*.gs` (the script IS the agent). Both discovery paths
verified by removing entries and confirming the flag fires.

**Still unregistered:** the Sage Oak photo booth itself. Its code is not on main,
and another session is actively working that branch — the entry should land with
PR #66. Once merged, the new discovery heuristic will flag it if it does not.

**Files:** `registry.yml` (runtime on 38 entries + 2 new Apps Script agents),
`ops/fleet-health/registry_check.py`, `ops/fleet-health/fleet_brief.py`,
`docs/FLEET.md`, `docs/CHANGELOG.md`.

---

## 2026-08-20 — Prevention: generated FLEET.md, an enforced registry, an exit-code rule

**What:** Three mechanisms, in the order Roman picked (3, 1, 2).

1. **`docs/FLEET.md` is now generated** from `registry.yml` by
   `ops/fleet-health/fleet_brief.py`, regenerated on every merge to main.
   Grouped by engine, with an autonomy section and per-agent reads/writes.
   Handing the fleet to Claude-in-chat is now "copy one file" instead of a
   hand-written summary that is stale on arrival. Required a new `engine:`
   field on all 36 registry entries (inferring it from entrypoint paths breaks
   on cases like tw-invoice-xref, which lives in email/ but is a charter tool).
2. **`ops/fleet-health/registry_check.py`** enforces the registry's own first
   rule: workflows <-> registry both directions, required fields, unique ids,
   entrypoints exist, FLEET.md current. Wired up as the `fleet-docs` workflow —
   which had to register itself to pass its own check. ROLLOUT: PRs run with
   `--warn` (annotate, don't block); drop the flag in a couple of weeks.
3. **Exit-code rule** added to ARCHITECTURE.md governance: an agent that
   accomplished NONE of its work must exit non-zero. Deliberately narrow — a
   sweeping "any failure exits non-zero" would break call-agent's per-call
   isolation, which is correct design. 0 of 50 is a failed run; 49 of 50 is a
   warning. Three agents still need the change: campaign-launch (enroll.py),
   bulk-messenger (messenger.py), call-agent (all-calls-failed case only).

**Why:** Roman — "we do it in code, but then claude chat doesnt know about it and
neither does github, and i always feel like we are back asswards." The diagnosis:
these mechanisms already existed as CONVENTIONS (register everything, update the
changelog) and conventions decay silently. Nine workflows broke the registration
rule for weeks; ARCHITECTURE.md was wrong for seven. Nothing was watching, and
nothing published what the repo already knew.

**Files:** `ops/fleet-health/fleet_brief.py` (new),
`ops/fleet-health/registry_check.py` (new), `.github/workflows/fleet-docs.yml`
(new), `docs/FLEET.md` (new, generated), `registry.yml` (engine field on 36
entries + the fleet-docs entry), `ARCHITECTURE.md`, `docs/CHANGELOG.md`.

**Decision-log candidates for Roman:** (a) generated fleet breakdown as the
canonical handoff artifact; (b) registry check blocking merges after rollout;
(c) the exit-code rule as a fleet-wide convention.

---

## 2026-08-20 — ARCHITECTURE.md rewritten to match the fleet as it actually is

**What:** The human-readable fleet map described four engines with email in a
separate repo — the world as of ~2026-06. Rewritten for the real eight: added
the call agent, feedback agent, messenger, and fleet-health; folded email in;
replaced the finished migration history with an **Autonomy** section (what
writes without asking vs. what only drafts) and a **Known weak points** section.
Added the rule that `registry.yml` wins on conflict.

**Why:** Roman — it was the last fleet doc still wrong after the registry pass,
and it is the file a human reads first.

**Note:** this entry was written when the rewrite was committed (231ab2d) but
silently failed to land — the insert matched on surrounding prose, which a
concurrent session had just changed, so the no-op reported success. Restored
here, and the insert is now anchored on structure. A small live instance of the
exact failure mode the entry above is about.

---


## 2026-08-20 — Charter campaign: wave 2 sent, all segments built, Paola hot list

**What:** (1) WAVE 2 SENT: 213 more Win-back-1-student families through live
workflow 1868435042 (Roman "lets move on to the next list") — campaign total
259 emailed; 11 prior-repliers held back (reply-date exit goal would silently
skip them), 27 excluded, 2 enrollment-blocked (Aquaddoomi, DaVault → Paola
calls). Weekday-only action windows (Mon–Fri 9:00–18:00 PT) set on the live
workflow — wave-2's Day-3 nudge moved off Sunday. (2) PILOT LEARNINGS baked
in: lead-status=OPEN_DEAL exit goal removed (34 families carried stale
Open-deal status from 25/26 and were silently skipped — root cause of the
13/47 partial send); reply exit = hs_email_last_reply_date IS_KNOWN (UI-valid
shape; the API accepted an IS_AFTER timePoint the UI rendered "always
False"). Both live-verified: Surova + Potter replies exited them. (3) ALL
REMAINING SEGMENTS BUILT (OFF, pending Roman publish+enable — marketing-email
publish scope unavailable at account tier): queues 3162 Never-Started (28),
3163 No-Lesson (10), 3164 Multi (71); emails 219949380453 / 219949261351 /
219949261355 / 219949261359 / 219949380457; workflows 1869922921 / 1869934421 /
1869933870 (same goal trio, weekday windows, Paola Day-7 task). Multi
student_names scrubbed: Munoz "Alanna/Alannah" deduped; White (Yari/Yuri)
+ Lopez (Mathew/Matthew) HELD for Roman (twins vs typo — not queued). (4)
PAOLA HOT LIST 3161 (55) Slack-DM'd to Paola: T1 replied (Surova asked for
Fred/Vlado; Potter), T2 opened (30, revenue-ranked), T3 Hot-12 never emailed
(personal calls), T4 email-unreachable (7). Behavior at 48h: 46 sent /
18 opened (39%) / 2 replied / both repliers auto-exited before the nudge.
**Files:** portal-side builds; durable scripts already in scripts/. Session
worktree was reset mid-flight — recreated per concurrency rule before this
commit.

## 2026-08-20 — registry.yml: the 9 unregistered workflows are now registered

**What:** Added registry entries for every live workflow that was running
without one — `email-po-daily-report`, `email-draft-feedback`, `feedback-fix`,
`campaign-launch` (monday-launch.yml), and the five manual charter/Teachworks
analysis tools (`charter-gap-analysis`, `tw-tutor-active-check`,
`tw-invoice-status`, `tw-invoice-xref`, `tw-invoice-backfill`). The charter
section's "NOT BUILT" note is kept — the prospecting ENGINE still doesn't
exist — with a new paragraph distinguishing it from the manual read-only
analysis tools that do. Registry is now 35 agents (22 active, 10 manual,
3 deprecated) and `.github/workflows/` ⇄ `registry.yml` cross-check is clean
in both directions.

**Why:** Roman, reviewing a fleet breakdown: the registry's own first rule is
"if it's not here, it doesn't exist," and the feedback agent classifies every
`#agent-feedback` report against this file's vocabulary. Nine live workflows —
including two that write to HubSpot and one that opens PRs — were invisible to
that vocabulary, so nobody could report a problem against them and the DEMOTE
path had no target to flip.

**Follow-up:** `source_agent` and `ticket_source` derive their enum options
from this file (`options_from: registry`), so the HubSpot schema sync
(`.github/workflows/hubspot-schema.yml`) needs a run to pick up the 9 new
options. Not run in this session — portal writes are Roman's call.

**Files:** `registry.yml`, `docs/CHANGELOG.md`.

---

## 2026-08-18 — Parent resolution step 2: the student in Teachworks (Roman: "build")

**What:** New tw.find_family_by_student(): searches both TW accounts for the
PO's student by exact name, scores candidates by real lesson history (+100 when
the PO's tutor is their last tutor; 0-lesson shells never count), returns the
family (parent name/email/phone, last tutor, lesson count). Wired into
po_inbox parent resolution as STEP 2 — after "parent email in the PO", BEFORE
prior deals and the surname search — with the extractor now pulling
`tutor_name` off the PO. Internal-domain families skipped; tutor mismatch adds
a "verify same student" flag. Matthew Rose (iLEAD, 3 POs) resolved this way
by hand today: TW showed Megan Miller's Matthew with 104 lessons, all with
Jacquelyn Lemerond — the tutor on the new PO — while the "Dina Rose / Matthew"
record had 0 lessons (a 2022 Gold-pipeline shell). Deals renamed "Megan Miller
- Matthew Rose - iLead 1/2/3 - 26/27", Megan attached + stamped, family→TOR
(Sara Ramirez), SMS armed, chases closed. Also: tw_student_lookup.py + xref
workflow input for ad-hoc "have we ever tutored X?" checks (shows last tutor).

**Why:** Roman: "matthew rose can be found in teachworks, to eliminate if we
ever tutored him before… cross reference who the last teacher [tutor] was for
both of the matthews and you will know" → "build".

**Files:** `email/src/teachworks_client.py`, `email/src/po_inbox.py`,
`email/tw_student_lookup.py` (new), `.github/workflows/tw-invoice-xref.yml`,
`email/tests/test_po_inbox.py` (suite 246 green), `docs/PO-PROCESS.md`.

## 2026-08-18 — Week audit + wrong-family fix (Matthew Rose) + South Sutter errant PO

**What:** Week-of-Aug-10 PO audit (16 emails → 43 deals, $9.8k, 72% same-day
TW-invoiced). Roman caught: (1) Matthew Rose (iLEAD, 3 POs) attached to
"Dina Rose" — a 2022 contact with the same surname and no student data. Root
cause: find_family_contact() returned a LONE surname match without ever
checking the student name (the same-surname tiebreak only ran on 2+ matches).
Fixed: a single surname match is accepted only when the contact's student-name
props or an associated deal name carry the student's first name; else [] →
the parent chase runs. Deals detached from Dina, renamed NEEDS PARENT, parent
stamps cleared; PO replayed so the agent re-chases via TOR Sara Ramirez.
(2) South Sutter/IEM PO 1309153 ($3,010, 3 students, "submitted 4/3/2025") is
a stale 2025 errant — 3 deals ARCHIVED (Roman). Also fixed during audit: Seeley
×5 amounts → reissued $75/hr ($637.50; Kath caught the old-rate PO, Christine
Gurney reissued Aug 18); Heartland ×5 stale parent_email from the Pilibos
incident corrected; Kruz Invoice # tab char cleaned. Open for Kath: confirm
Seeley TW invoices 54435–439 at new amounts; Cooper Doyal Invoice # 54422 not
found under Kristy's TW record.

**Files:** `email/src/hubspot_client.py`, `email/tests/{test_family_contact,
test_po_inbox}.py` (suite 242 green).

## 2026-08-17 — Draft feedback loop (Tiers 1+2) — the team's edits train the drafter

**What:** New `email/src/draft_feedback.py`. Tier 1: every agent-created draft
(chase + reply, charter@ inbox) is registered with its exact text
(state/draft_registry.jsonl); each 15-min run settles drafts that left Gmail
Drafts by comparing to what was actually SENT on the thread — sent_as_is (≥97%
similar) / edited (≥50%) / rewritten / discarded — flips the sent message to
`A+ Agent/Sent`, and stores the unified diff. Tier 2: edits/rewrites/discards
become one file each in `corrections/email-drafts/` (fleet corrections format)
plus a distilled line in `STYLE-RULES.md`, which BOTH drafting prompts (PO
extractor + admin classifier) load at runtime (last 25 rules) — tomorrow's
drafts carry yesterday's edits. Weekly Friday 4 PM PT one-liner to the
visionary seat (new email-draft-feedback-weekly.yml). Tier 3 unchanged: a reply
to the aplus bot in #agent-feedback files a rule via the feedback agent.
Admin-inbox drafts (HubSpot conversation comments) consume the rules but
aren't outcome-tracked yet — different plumbing, follow-up.

**Why:** Roman: "is there a way for the agent to get input from kath and from
all others when drafts are made whether the draft was good or needs
improvement" → "LETS DO IT".

**Files:** `email/src/draft_feedback.py` (new), `email/src/po_inbox.py`,
`email/src/classifier.py`, `email/tests/test_draft_feedback.py` (new; suite
239 green), `.github/workflows/{email-po-inbox,email-draft-feedback-weekly}.yml`,
`corrections/email-drafts/README.md` (new).

## 2026-08-17 — INCIDENT: chase self-resolve renamed 5 Heartland deals to "Pilibos Student"

**What:** Roman: "how come heartland deals were named pilibos?" Property
history: integration 39943154 (our app) at 2026-08-14 19:35Z — the po_inbox
`_sweep_chase_self_resolve` shipped that day. Root cause: the Heartland chases
were opened BEFORE the multi-student fix, so their audit records carried the
placeholder student "the student"; the sweep searched family contacts for it,
found exactly one match — Roman's TEST contact "Pilibos Student"
(roman+001@wetutorathome.com) — and "resolved" all five chases against deals
Kath had already fixed by hand: renamed them from the audit's STALE
"NEEDS PARENT - Heartland N" to "Pilibos Student - Heartland N" and attached
the test contact. Repaired in-portal: five names restored (Kristy Doyal /
Angela Czaja ×3 / Jamie Holloway), test contact detached from all five (real
parents untouched). Code guards: (1) placeholder student strings never
searched; (2) the deal must STILL say NEEDS PARENT in the LIVE portal (human-
fixed deals just close their chase, touching nothing); (3) internal-domain
(@wetutorathome.com) contacts never auto-attached; (4) resolution renames
from the LIVE deal name, never the audit copy. 4 regression tests.

**Why:** Wrote automation that trusted its own stale bookkeeping over the
portal and treated a placeholder as data. Both fixed at the root.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 231 green).

---

## 2026-08-17 — Charter Monday launch: 6-way family segmentation + student names (Roman)

**What:** Roman: "split list as segmented as you can make them" (after
catching that 1-student copy undersold multi-student families — 81 of 389).
New `scripts/charter_gap_segments.py`: derives EVERY student per family from
charter deal titles since 2025-08-01, stamps NEW contact props `student_names`
("Brooke, Haven & Lillie") + `student_count` ([Agent]-labeled, registry +2,
UPDATE-only import — 419 stamped), and builds 6 static lists = recency ×
student-count × personalization: 3138 Hot-1 (9), 3140 Hot-Multi (3),
3136 Win-back-1 (299), 3135 Win-back-Multi (78), 3137 Never Started (30),
3139 No Lesson Data (10) — sums to the 429 gap families. campaign.yml
re-wired to the six (2-way lists 3112/3113 superseded, kept). New copy
drafts: families_winback_multi / families_hot_multi / families_no_lesson_data
(multi variants use {{student_names}} and "their tutors" — no single-tutor
token, since siblings often had different tutors). Still DISARMED.
**Files:** scripts/charter_gap_segments.py (new), ops/hubspot-schema/
properties.yml, ops/messenger/campaign.yml, ops/messenger/templates/
campaign-2026-08-17/ (+3).

---

## 2026-08-17 — Lead status: unhidden, funnel-ordered, persona-labeled + Meeting Booked hard-wired

**What:** (1) `hs_lead_status` had 14 of 17 options HIDDEN (unknown when/who —
property updatedAt stale at 2024-09). Roman: "I don't want anything hidden" →
all 17 unhidden (backup `ops/fleet-health/audit/backups/2026-08-11-hs_lead_
status-before-unhide.json`). (2) Options reordered to the funnel Roman
described: New (Inbox) → Attempting to Contact → Meeting Booked → QTL-NEW /
QTL-Charter / QTL-Diagnostic Sent → Open deal → Past Customer / Check Back
Quarterly / Dead Opportunity; then the persona labels; then leftovers.
(3) LOCKED rule (Roman): for non-family personas the lead-status LABEL = the
persona name. Two label renames (internal values unchanged, so no workflow or
agent breaks): `Charter School Teacher TOR/EF` → label "Teacher of Record/EF/ES";
`Teacher in a School` ("School Personnel") → label "Decision Maker/Director".
Call agent LEAD_STATUS_LABELS + README updated. (4) Meeting Booked was a manual
gap (Paola set it by hand; nurtures kept chasing booked families) → NEW
event-based workflow 1868302723 "Lead funnel — Meeting Booked (Paola consult)
→ lead status": trigger = HubSpot meeting booked with title containing
"Tutoring Call w/" (Paola's meetings-link consults; excludes Spotlight/TSN
meetings), sets hs_lead_status = Meeting Booked; ENABLED. Cloned from the
Spotlight #5 pattern. (5) Nurture exit: added a second OR-goal
"lead status = Meeting Booked" to `Lead Pipe Line - Online` (50818589) so
booked families drop out of the New/Attempting chase. The same goal edit on
`Lead Pipe Line - Ads - Free Lesson` (149937308) FAILED via API (500 on
round-trip PUT — custom-code actions) → flow untouched, **needs a 30-second UI
edit: Settings → Goal → add "Lead status is any of Meeting Booked"**.

**Why:** Roman 2026-08-17 walkthrough of the funnel: form → New + text/email
push to book → Attempting to Contact + "inbox is full" email → Meeting Booked
(Paola's new manual step) → QTL after consult. Also surfaced: 10,064 of 11,115
contacts have NO a_persona; lead status is doing identity duty for them
(Tutors 1,249 / Student 191 / School Personnel 97 / CBQ 4,453 = families).
Persona backfill-from-status proposed, NOT run — Roman to approve. 25 Decision
Makers still carry the TOR status value — pending Roman's call.

**Files:** `ops/call_agent/call_agent.py`, `ops/call_agent/README.md`,
`ops/fleet-health/audit/backups/2026-08-17-*` (flow snapshots + created flow).

---

## 2026-08-14 — Agent-property labeling rule + TOR/DM hygiene (Roman)

**What:** (1) NEW RULE: every property an agent writes carries the `[Agent] `
label prefix + "AGENT PROPERTY — written by <script>" description (CLAUDE.md
+ registry header comment). Applied: last_tutor_name, student_first_name,
sms_opt_out relabeled in-portal (sync never relabels) and in properties.yml.
(2) TOR persona hygiene: 77 non-marketing TOR contacts set as marketing via
import; **155 hard-bounced TOR contacts ARCHIVED** (backup with associations
in ops/fleet-health/audit/backups/2026-08-14-bounced-tors/; recycle-bin
90 days); one bounced contact kept — Cynthia Rachel (IEM) — because she is
now a Decision Maker (needs a fresh email). (3) Decision Maker/Director
persona: 17 real school DMs now tagged — Covil, Hetrick, Rachel (IEM);
Chapin, Budke, Barlow, Joy, Kim, Rogers (iLEAD); Smith (Compass), Jorgensen
(Elite), Brackett (Forest), Sutton (Harvest Ridge), Corioso (Pacific
Coast), King (Sage Oak), Woodard (Taylion), Houchin (VIEDU). Title-based
sweep deliberately EXCLUDED 38 non-school "directors" (vendors, media).
Pending Roman: 5 Sage Oak mock contacts (nameless 2026-03-24 records +
Courtney Gibson) to delete — the other 28 Sage Oak contacts are real TORs
with live deals; DMs still missing for Compass/Heartland/Gorman/Blue Ridge/
Pacific Charters/Granite Mountain/Heartwood/Suncoast.
**Also flagged for Monday copy:** 81/389 personalized gap families have >1
student in last year's deals — one-student template undersells them
(decision pending: split list vs multi-student variant).
**Files:** CLAUDE.md, ops/hubspot-schema/properties.yml,
ops/fleet-health/audit/backups/2026-08-14-bounced-tors/.

---

## 2026-08-14 — Charter 26/27 launch scaffolding (Monday 08-17, DISARMED)

**What:** Segmented Monday-morning campaign per Roman ("families from charter
schools where we worked with them last year, and some where we didn't...
teachers who we worked with last year, or didn't"). 5 NEW static lists built
from gap list 3104 + Family→TOR associations (typeId 15): 3107 Families-Hot
(12), 3108 Families-Win-back (387), 3109 Families-Never-Started (30), 3110
TORs-Worked-With-Us (163), 3111 TORs-New-Outreach (8). 329/429 gap families
have a TOR association (100 without — hygiene queue candidate). Campaign
program: ops/messenger/CAMPAIGN-2026-08-17.md (cadence: Day 0 email, Day 3
follow-up, Day 7 CHARTER SALES task, goal-exit on renewal/reply); 5 copy
drafts in ops/messenger/templates/campaign-2026-08-17/ (HubSpot tokens;
never-started segment deliberately token-free). Launch rail:
ops/messenger/enroll.py + monday-launch.yml (daily 9 AM PT cron, exits unless
campaign.yml armed: true AND today == launch_date 2026-08-17; enrollment via
automation v2 per-contact endpoint). **DISARMED — blocked on Roman:** copy
approval, base branded email id (or "plain"), workflow build go (ids →
campaign.yml), armed flip.
**Files:** ops/messenger/{CAMPAIGN-2026-08-17.md,enroll.py,campaign.yml,
templates/campaign-2026-08-17/}, .github/workflows/monday-launch.yml.

---

## 2026-08-14 — EOS knowledge ingested from Monday (knowledge/eos/)

**What:** New `knowledge/eos/README.md` — synced snapshot of the FY2027 Annual
Goals (16k package hours / 900 students / 2 intervention programs / 75%
retention / 100% tutors scored / 70 referral families) and Q1 FY2027 Rocks by
seat, with Monday board ids (Goals 18419427040, Rocks 18421156386, L10
Scorecard 18402267902, L10 Agenda, Data Review Protocol) and usage guidance:
seats map to config roles:, work should cite the Rock/Goal it serves, the ops
scorecard sync feeds the L10 Scorecard, Monday stays source of truth.

**Why:** Roman: "do our agents have our EOS knowledge?" — they had none;
"check in monday.com you will find our goals for the year and our rocks."

**Files:** `knowledge/eos/README.md` (new).

---

## 2026-08-14 — NEW ENGINE: bulk messenger (on-demand email/SMS to lists)

**What:** `ops/messenger/` — on-demand bulk email + SMS to a HubSpot list,
per Roman's rail decisions: EMAIL via HubSpot marketing email (agent clones an
in-portal template, retargets the clone at the list, leaves it DRAFT with a
review link — Roman clicks Send, HubSpot suppression applies; personalization
via native contact tokens incl. student_first_name / last_tutor_name); SMS via
JustCall with from-number routing (sales +18185736644, conference
+18188506284), rendered per-contact from repo templates. Guardrails: BULK
ONLY (min_bulk 25, refuses 1:1), dry-run default + live requires
confirm=SEND, sms_opt_out contacts skipped (NEW contact property, group
master), STOP line required in every SMS template, 9:00–20:00 PT quiet hours,
E.164 normalization. Trigger: workflow_dispatch (messenger.yml); the Slack
front door + JustCall STOP-reply ingestion are phase 2 (README).
First template: templates/charter_win_back.txt (uses first-name-only
last_tutor_name). Registry: new `bulk-messenger` entry (status manual).
**WHY:** Roman 2026-08-14: "we need to have a programmed agent that can send
out custom email and text messaging to customers whenever called upon. only
for bulk options." Rail + trigger choices confirmed by Roman same day.
**Decision-log candidates (pending Roman):** bulk-only threshold (25); email
sends stay human-clicked in HubSpot for now; SMS number routing map.
**Files:** ops/messenger/{messenger.py,config.yml,README.md,templates/},
.github/workflows/messenger.yml, registry.yml, ops/hubspot-schema/properties.yml
(+sms_opt_out).

---
## 2026-08-14 — Accountability chart: roles resolve to people at config load (Roman)

**What:** New `roles:` block in email/config.yaml — the EOS-style seat map
(visionary/roman, operations/emily, scheduling_lead/mandy, scheduler_a_l/janelle,
scheduler_m_z/yolanda, charter_admin/kath, sales/danielle, charter_sales/paola).
Every functional key now names a SEAT (routing owners, scheduler_split,
escalation level2/3, recipients, cc, missing_info_dms, charter_sales, internal
fallback); cfg() resolves roles → staff keys at load time so all consumers and
tests keep seeing resolved people, and config.staff() resolves either form.
Hardcoded "paola" in main.py's pre-deal routing → charter_sales seat. Team
change = edit `roles:`, nothing else. Claude-to-Roman comms keep using NAMES
(memory rule). Seat titles are inferred from function — Roman to correct
against the real accountability chart.

**Why:** Roman: "lets give all team members a role title and that way its
never tied to anyones name... if a team member moves or leaves or gets added
i just have to add it for you."

**Files:** `email/config.yaml`, `email/src/config.py`, `email/src/main.py`,
`email/src/po_inbox.py`, `email/tests/{test_invoice_sweep,test_hourly_update,
test_po_inbox}.py` (suite 227 green).

## 2026-08-14 — Parent-chase: CHARTER SALES notified at 24h (Roman; role, not name)

**What:** Family contact info still missing 24 HOURS (calendar, configurable
`parent_chase.notify_charter_sales_after_hours`) after the chase email was
SENT → the CHARTER SALES role gets a DM to chase the TOR/school directly —
ahead of the existing Kath+Roman escalation at 2 business days. Once per chase
(parent_chase_sales_notified); unsent drafts never trigger it (the send is the
anchor). NEW RULE (Roman, same session): functional config keys and audit
actions name ROLES, never people — new `po_inbox.charter_sales: paola` role
map; change the person in config, never in code. First-pass person-named key
(notify_paola_after_hours / parent_chase_paola_notified) renamed same day,
legacy names still honored on read.

**Why:** Roman: "If a family is missing contact info for longer than 24 hours
after an email Paola must be notified too" + "make sure that no properties are
named after people. notify charter sales instead of paola."

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 227 green).

## 2026-08-14 — Draft guidelines: humans only, tracked, context-aware (Roman: "yes")

**What:** 14-day audit found 55 drafts/512 emails, 21 of them po_inbox warm
replies to vendor-admin mail nobody sends. Six-part fix, all live: (1) extractor
drafts ONLY when a named human asked A+ something — never for mass notices,
onboarding confirmations, DocuSign/portal notices, auto-acks. (2) Robot
recipients banned (`noreply/donotreply/notifications@/mailer.*`) for chase AND
reply drafts — no human to write to → 📨 gap note → 🚩 DM instead. (3) Chase
drafts to a TOR who wasn't the sender go out as FRESH emails ("Parent contact
info needed — Student (School)") — no more replies quoting portal robots;
chase records track the NEW thread so replies still auto-resolve. (4) Every
agent draft: Gmail label `A+ Agent/Draft Pending`, HubSpot BCC
(hubspot.bcc_log_address — verify on first real send) so sends log to contact
timelines; NEW _sweep_chase_drafts detects the draft leaving Drafts →
parent_chase_sent (TOR reply clock starts AT SEND, and unsent chases never
escalate the TOR) / still sitting after 4 business hours → 🚩 nag. (5) Call-
context check before chasing: recent [Call Agent] engagements on the TOR's
contact surface on the ticket ("a recent call may ALREADY have this info") and
add a P.S. to the draft — built after the Karen Mercer case (parent's name was
on her contact an hour before the chase drafted). (6) _sweep_chase_self_resolve:
open chases re-check HubSpot for a newly appeared family contact each run — the
August Vouniozos case (family called in; contact existed before anyone read a
reply) now closes itself. ALSO: Kruz Vouniozos chases resolved by hand via
call context (deals renamed to August Vouniozos, parent attached+stamped,
family→TOR to Karen Mercer, SMS armed); guidelines DM'd to Paola + Danielle.

**Why:** Roman: excessive drafts; noreply senders; "is it in any way possible
that this agent has already checked the transcript... from last call" — it
couldn't; now it does.

**Files:** `email/src/po_inbox.py`, `email/src/gmail_client.py`,
`email/src/hubspot_client.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 225 green).

## 2026-08-14 — PO improvement batch (Roman: "lets go") — 5 changes

**What:** (1) SMS flow 1603217415 rev 42: second OR-branch enrolls contacts
whose a_persona includes Family even when they also carry the TOR persona —
dual-role parents (Kristy Doyal) get their scheduling texts; pure teachers stay
blocked. (2) SLA sweep now tracks PO-inbox tickets (po_processed records carry
ticket_id + sla_due) — PO ticket breaches finally escalate (the silent Taylion
breach can't recur). (3) Chase-resolved parents get their SMS: on resolution
the agent stamps contact_level_deal_stage = "Pre-Lesson (Charter Traditional)"
on the new parent contact, arming the texting flow that fired at deal creation
when no parent existed (Charter Trad only). (4) Pending-approval sweep: order-
agreement deals log pending_po_opened; the duplicate alert (approved PO
re-arriving) logs pending_po_confirmed; unconfirmed past 16 business hours →
ONE ⏳ nag to missing_info_dms (kath+roman) + pending_po_reminded. (5) Multi-
student certificates codified (yesterday's Heartland run needed hand-cleanup):
extractor returns per-student pos[] entries (student/grade/parent per family,
synthesized '<PO>-<StudentName>' numbers), _split_pos merges them, seq numbers
per student, scheduling alert per student, and the parent chase sends ONE draft
per recipient listing all students (was 5 identical drafts to the same TOR)
with per-deal chase records; replies resolve the chases whose student they
name (multi-family threads), else all (single-family multi-month).

**Why:** Roman's approved batch, triggered by the Kristy Doyal dual-persona PO
and the Heartland 5-student certificate.

**Files:** `email/src/po_inbox.py`, `email/src/sla_sweep.py`,
`email/config.yaml`, `email/tests/test_po_inbox.py` (suite 219 green);
HubSpot flow 1603217415 rev 42.

---

## 2026-08-14 — Charter gap: tutor/student enrichment + property stamping (Roman)

**What:** `scripts/charter_gap_analysis.py` extended — Step 3b pulls each
matched gap family's most recent COMPLETED Teachworks lesson (per-customer
students → per-student lessons, the proven email-client query pattern, both
accounts) and captures tutor name + student first name; new Tab-1 columns
Last Tutor / Student First / Last Lesson; match rate printed. New OPT-IN
write stage (--write-props / workflow input write_props): stamps
`last_tutor_name` + `student_first_name` onto list-3104 gap contacts via an
UPDATE-only email-keyed import (crm.import scope — added by Roman 2026-08-13).
BOTH `last_tutor_name` and `student_first_name` newly declared as CONTACT
properties (group family) in ops/hubspot-schema/properties.yml. Registry trap
hit on the way: the pre-existing `student_first_name` at line ~407 is a DEAL
property (dealinformation) — the first declaration attempt landed in the
deals: section and created a stray empty deals/last_tutor_name (archived
immediately, no values ever written). The deal-level student_first_name is
untouched; the contact-level one is its counterpart.
**Duplicate-list flag for Roman:** the parallel session's run created static
list 3106 "Charter Re-Engagement 26/27 - Gap Families (Aug 2026)" (426
members, pre-correction cutoff). List 3104 (429, corrected cutoff) is
canonical per Roman's instructions; 3106 is a duplicate awaiting his
keep/delete call. **Also reconciles the script fork:** ece98a0 (parallel
session) had overwritten the executed PR-#68 version on main; this change
re-bases on the executed version and absorbs ece98a0's invoice-level name
fallback (customer_first_name/customer_last_name when the customer record is
missing). Base run stays read-only.
**WHY:** Roman 2026-08-14: win-back outreach personalization — "your student
X's tutor was Y" needs the last tutor on the contact record.
**Run results (2026-08-14, run 31769645948):** MATCH RATE 389/429 gap
families got a tutor name (91%) — every matched-with-invoices family that had
a completed lesson. Import 78996473 DONE; full verify: 389/429 list-3104
contacts carry BOTH last_tutor_name and student_first_name. The 40 without:
30 never-invoiced (no TW match) + 10 invoiced but no completed lesson in
window. Same-day follow-up (Roman: "tutors first name only no last names"):
last_tutor_name now holds the tutor's FIRST NAME only (parsed from
Teachworks "Last, First"); all 389 re-stamped.
**Files:** scripts/charter_gap_analysis.py,
.github/workflows/charter-gap-analysis.yml,
ops/hubspot-schema/properties.yml (+2 contact properties).

---

## 2026-08-13 — Charter re-engagement gap analysis + static list (Roman)

**What:** New reusable `scripts/charter_gap_analysis.py`: pulls charter deals
(5 pipelines, created since 2025-08-01) + associated contacts from HubSpot,
excludes school-staff email domains (student.* subdomains stay family),
classifies RENEWED (deal created ≥ 2026-06-01 OR "26/27" in dealname) vs GAP,
merges against Teachworks invoices (email match, name fallback), writes
`~/Desktop/charter_gap_analysis.xlsx` (4 tabs) + non-marketable CSV, and
creates HubSpot static list "Charter Re-Engagement 26/27 - Gap Families
(Aug 2026)" (id 3106, 426 members verified). Run results 2026-08-13:
439 families / 13 renewed / 426 gap — matched Roman's expected ~439/~11/~428.
TEACHWORKS_API_KEY only lives in Actions secrets, so a new manual workflow
`charter-gap-tw-fetch.yml` runs the read-only Teachworks fetch stage and hands
the JSON back as an artifact (`--fetch-teachworks` / `--tw-json` split).
One-off run, structured for weekly scheduling later (`--start`,
`--renewal-cutoff`, `--renewal-token`, `--skip-list`, `--list-only` flags).

**Why:** Charter re-engagement email going out tomorrow AM needs the gap-family
list + prioritized call-down sheet; repo keeps the script as the reusable
engine for a weekly cadence.

**Files:** `scripts/charter_gap_analysis.py` (new),
`.github/workflows/charter-gap-tw-fetch.yml` (new), `docs/CHANGELOG.md`.

---

## 2026-08-13 — Charter renewal gap analysis (one-off report, schedulable)

**What:** New read-only report script `scripts/charter_gap_analysis.py` +
manual workflow `.github/workflows/charter-gap-analysis.yml` (workflow_dispatch;
xlsx uploaded as a 7-day run artifact — Teachworks tokens live only in Actions
secrets, so the run happens in CI). Charter families with a 25/26 deal but no
26/27 renewal, enriched with Teachworks invoice history across both accounts.
5 charter pipelines (907748, 72281989, 88841552, 5119061, 1066195), deals since
2025-08-01; school-staff contacts excluded by email domain (student.* subdomains
stay family); RENEWED = deal created ≥2026-08-01 OR "26/27" in dealname
(cutoff tightened same day from 2026-06-01 — late spring 25/26 POs were
counting as renewals; Roman 2026-08-13).
**WHY:** 26/27 renewal season — Roman needed the call/win-back list ranked by
actual invoiced value, plus the deal-but-never-invoiced and TW-no-charter-deal
hygiene queues. First run 2026-08-13: 439 families → 13 renewed / 426 gap
(396 with invoices: 10 Hot, 386 Win-back; 30 never invoiced; 278 mismatches).
Corrected re-run same day (cutoff Aug 1): 439 families → 10 renewed / 429 gap
(399 with invoices: 12 Hot, 387 Win-back; 30 never invoiced; 278 mismatches).
HubSpot static list "Charter 26/27 Gap Families" (listId 3104) built from the
corrected gap set — all 429 contacts — with marketability audit: 378 fully
clean, 42 not marketing contacts, 4 opted out, 4 hard bounced, 1 no email.
Follow-up: the 42 were set as marketing contacts (helper list "Charter 26/27
Gap - Upgrade to Marketing", listId 3105; done via portal UI bulk action —
hs_marketable_status is API-read-only and the private app lacked crm.import;
Roman added the crm.import scope later that day — verified working, so future
status flips can use an UPDATE-only import with marketableContactImport=true).
Marketing tier after: 9,751/12,000. Reachable gap now 420/429.
**Files:** scripts/charter_gap_analysis.py, .github/workflows/charter-gap-analysis.yml
(temporary branch push trigger dropped at merge).
**Merge note:** a PARALLEL implementation of the same script landed on main
from another session (e20a8ec script + bfb0a07 charter-gap-tw-fetch.yml,
list name "Charter Re-Engagement 26/27 - Gap Families (Aug 2026)" — never
executed, no such list in the portal, no changelog entry). Superseded at merge
by this branch's executed version; charter-gap-tw-fetch.yml removed (it calls
a --fetch-teachworks flag only the superseded script had). Restore from
e20a8ec/bfb0a07 if anything from it is wanted.

---

## 2026-08-11 — iLead purge completed + one-student decision + teacher-email verdict (Roman)

**What:** Forms scope added → the two iLead intake forms ("Level up - Ilead",
"A+ Tutoring x iLEAD Tiered Support") backed up + archived, all 10 blocked
iLead scheduling properties archived, empty `level-up_ilead` group DELETED.
Roman decisions, same session: (1) ONE student per contact record — the plan
is the A+ persona system; sibling fields retire: `sibling_school`,
`student_3`, `student_3_school`, `student_4_school` ARCHIVED;
`sibling_current_grade_level` KEPT (Roman, same day: "if it's in the main
consultation form definitely keep it" — submissions API shows Get Started Now
Full Length live, last submission 2026-07-23). (2) `teacher_email_address` un-kept —
`teacher_of_record_email_address` is the teacher-email property; Roman then
redirected (same day): NOT archived — it is a Spotlight field: moved to group
`spotlight`, relabeled "Spotlight Teacher Email Address" per the Spotlight
nomenclature (live TSN Workflow 3b still reads it — flagged). (3)
`student_last_name_if_diff_from_parent` confirmed staying. Registry 42→41
contacts; KEEPERS 81→80. Pending code change before the last sibling fields
go: email/config.yaml teachworks.student_name_properties reads
student_full_name_clone_/student_3_full_name/student_4_full_name.

**Why:** Roman's verdicts on the low-fill review, 2026-08-11. Decision-log
entries pending: one-student model; canonical teacher-email property.

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/KEEPERS.md`,
`ops/fleet-health/audit/backups/2026-08-11-ilead-forms/` (new).

---

## 2026-08-13 — call_agent: Roman-answered calls hand follow-up to Paola

**What:** (refined same-day: first pass forced Paola on ALL tasks; Roman
narrowed it to his own calls + handoff context.) Two changes:
(1) `_resolve_owner()` — when JustCall `agent_name` shows ROMAN answered,
the task owner is forced to `default_task_owner` (Paola), `owner_hint`
ignored; other answerers keep hint routing with Paola default.
(2) New `handoff_note` field in the summary schema/prompt — a Claude-written
brief for the teammate who wasn't on the call (what was promised, pricing
quoted, names, timing, suggested opener). Tasks from Roman-answered calls
(action items AND the no-next-step guard task) open with a handoff block:
"HANDOFF — Roman spoke with this caller on <date>; follow-up is assigned to
Paola." + the brief.

**Why:** Roman 2026-08-13: sales calls ring Roman first, overflow to Paola,
and Paola does 100% of follow-up — but the hint mapping assigned tasks to
whoever was named on the call (both Karen Mercer call tasks, 404280341,
landed on Roman because he answered). Paola also needs enough context to
pick up a conversation she wasn't part of — hence the handoff brief.

**Files:** `ops/call_agent/call_agent.py`, `ops/call_agent/config.yml`,
`ops/call_agent/README.md`.

---

## 2026-08-13 — Verified 69-deal invoice backfill EXECUTED + PO day report

**What:** (1) The parked $17.5k backlog closed with VERIFICATION instead of
blind stamping: new email/invoice_backfill.py (+ tw-invoice-backfill workflow)
matched each swept deal to a Teachworks invoice (family + amount, service-month
due preferred, one claim per invoice, Paid/Approved/Sent only) — **64/69
verified & stamped** (invoice_submitted_date = service-month end, Invoice #,
Invoice Submitted stage; Jamie Holloway's date hand-corrected to 2026-08-13,
its "(Aug) 25/26" name tag is a year off). **5 EXCEPTIONS for Kath**: Christina
Duran/Talia Visions ×2 ($495) + Myra Garcia/Jason Gorman ($67) have NO TW
invoice (possible genuinely-unbilled); Katherine Perez ×2 ($1,200) have no
family contact on the deal (can't verify). (2) NEW daily report (Roman):
email/src/po_daily_report.py + 6 PM PT weekday cron DMs Roman the day's PO
deal count/value ⇄ how many already have TW invoices (Invoice # stamp or
amount-matched invoice dated on/after the deal), misses named.

**Why:** Roman: "yes" to verified backfill; "at the end of each day i get a
slack message that tells me the value of the POs that came in and corresponds
them to how many teachworks invoices created."

**Files:** `email/invoice_backfill.py` (new), `email/src/po_daily_report.py`
(new), `.github/workflows/{tw-invoice-backfill,email-po-daily-report}.yml`
(new), `email/tests/test_daily_summary.py` (suite 213 green).

---

## 2026-08-13 — TOR got the parent SMS (Mary Nieves) — persona-gated texting

**What:** Mary Nieves (TOR) received the parent schedule-confirmation SMS.
Chain: the agent now attaches TORs to deals AT CREATION → deal flow 1608222821
stamps contact_level_deal_stage on ALL associated contacts (no persona filter)
→ SMS flow 1603217415 enrolled her. Worse, deal flow 64686392 (Charter
Pre-Lesson) had ALREADY flipped her hs_lead_status to OPEN_DEAL — so a
status-based exclusion could never have saved her, and the flip also silently
broke the TOR name-matching pool. Fixes (all executed): (1) a_persona
"Teacher of Record/EF/ES" backfilled onto 1,170 of 1,203 TOR-status contacts
(append-only) — the persona is now the un-corruptible teacher marker.
(2) SMS flow 1603217415 enrollment now excludes a_persona containing the TOR
persona (revision 41, verified; unenroll-on-criteria ejects mid-flow slips).
(3) Agent self-healing: whenever po_inbox touches a TOR contact it re-asserts
persona + lead status (skipping dual-role Family+TOR contacts). Mary's lead
status restored in-portal. NOT changed: deal flows 1608222821/64686392 still
stamp/flip all associated contacts (their action type can't filter targets) —
harmless for texting now; the status flips on TORs heal on next agent touch.

**Why:** Roman 2026-08-13: "mary nieves received the sms ont the parent...
what do we do to make sure this doesnt happen in future."

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py` (suite 211
green); HubSpot: flow 1603217415 rev 41, 1,170 contact persona backfills.

---

## 2026-08-12 — Zie Rojas PO: net-payout misread + dropped correction + TOR variant (3 fixes)

**What:** Roman caught the Zie Rojas deals at $140/$280 when the PO he was
reading says $150/$300. TRUE root cause (recovered replies told the story):
the extractor read the OA CORRECTLY — iLEAD issued the POs at the old $70/hr
rate (140/280 = 2h/4h @ 70); Kath had already replied asking iLEAD to REISSUE
at $75/hr (=150/300), and Christina Mondolo acknowledged — but BOTH replies
were SILENTLY SKIPPED by the closed-thread guard, so nobody downstream saw the
rate dispute. Fixes: (1) closed PO threads are no longer skipped — replies
process (is_po replies trip the duplicate alert; others get a "↩️ PO-thread
reply" ticket); cursor rewound to 19:30Z and both dropped replies recovered as
tickets 47559984489 + 47563508797. (2) TOR 'Christina Mondolo' didn't link
because the portal contact is 'ChristinE' — name fallback now accepts a UNIQUE
last-name match in the TOR pool on first-name variants (her reply confirmed
christina.mondolo@ileadexploration.org). (3) Prompt guardrail added anyway:
use the PO value/'Total Cost', never a net-of-fee payout figure. Portal: both deals corrected to $150/$300,
Christine Mondolo associated (+family→TOR label, TOR fields stamped), Kath's
two tasks rewritten with AMOUNT CORRECTED flags. Also: teachworks
customers_for_family() (email + name match, active first) — the Aly Daly
inactive-dupe case; wired into calendar/schedule lookups and invoice_xref.

**Why:** Roman 2026-08-12: PO says 150; "there was a follow up email that came
from school with correct amount. but why is the teacher not tied to the deal?"

**Files:** `email/src/po_inbox.py`, `email/src/teachworks_client.py`,
`email/invoice_xref.py`, `email/tests/test_po_inbox.py` (suite 208 green),
`email/state/po_cursor.json` (rewound).

---

## 2026-08-12 — Missed 8/10 iLEAD PO recovered + seq double-count fix

**What:** Kath flagged a PO from 8/10 that never became deals. Found it: an OPS
order agreement (5 POs, 3114057042–46, Zackarias Barajas / Mari Barajas,
phonics w/ Fidal Williams, $1,630.38 total) arrived 8/10 09:45 PT — ~4 hours
BEFORE the OAs-are-POs rule deployed, and the evening replay list only covered
the two older iLEAD emails. Replayed via replay_msg_ids → 5 deals created with
the full current pipeline (TOR Mary Nieves name-matched WITH resolved email,
parent attached, pending flag, tutored=No, invoice tasks). Audit of every other
po_inbox record since 8/9 confirmed nothing else was missed. Also fixed the
bug the replay exposed: 'School N' came out 1,2,4,7,9 because the base count
was re-searched per sibling while the index caught up — the base is now
searched ONCE per email (seq_cache) and offsets applied locally; the three
misnumbered deals were renamed to iLead 3/4/5 in-portal.

**Why:** Kath's report (via Roman): "a PO came in on 8.10 that we never
caught." Root cause was rule-deployment timing, not a pipeline gap.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 206 green).

---

## 2026-08-12 — TOR name + email stamped on PO deals

**What:** PO deals now stamp `teacher_of_record_name` + `teacher_of_record_email`
(the deal properties built for exactly this) via the deal_property_map. Bonus:
when the PO names the TOR without an email and the name-match fallback finds
the contact, the RESOLVED email is stamped on the deal anyway. Both fields flag
on the ticket + 🚩 DM when the PO omits the TOR entirely. Backfilled today's 13
live deals (Mary Nieves ×3, Véronique Fabre ×9, Shauna Smith ×1). Note: the
deal-level TEXT fields are convenience copies for filters/reports — the
contact-to-contact "Teacher of Record" association (#AP031) remains the source
of truth. PO-PROCESS.md property table updated.

**Why:** Roman (2026-08-12): "we need to make sure we have the teacher of
record name and email address extracted from PO as well." Extraction already
existed; the deal-level stamps did not.

**Files:** `email/src/po_inbox.py`, `email/config.yaml`,
`email/tests/test_po_inbox.py` (suite 205 green), `docs/PO-PROCESS.md`.

---

## 2026-08-11 — Low-fill review round 1: iLead scheduling + tutor credentials un-kept (Roman)

**What:** Roman's picks from low-fill-review.md: the whole Level-Up iLead
scheduling set (7 contact per-day *_schedule_preference — previously #AP029
family keepers, now un-kept; tutoring_frequency; when_would_you_like_the_
tutoring_to_start; which_days_of_the_week_do_you_prefer_) + degree_received +
university_attended. Outcome: degree_received + university_attended ARCHIVED;
the 10 scheduling fields BLOCKED by two iLead intake forms (0-10a7465d…7f48,
0-529c7788…7a66) — they archive the moment those forms are deleted (needs
forms scope or UI). DEAL-side per-day preferences remain keepers. Removed the
9 un-kept contact declarations from properties.yml (51→42 contacts);
KEEPERS.md 90→81.

**Why:** Roman 2026-08-11: "all level up ilead scheduling can be archived,
that whole group. degree received archive, university archive."

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/{KEEPERS,contacts-proposal,low-fill-review}.md`.

---

## 2026-08-11 — QuickBooks refs archived + low-fill review list (Roman's orders)

**What:** (1) "Archive all quickbooks references": the only two QBO assets in
the portal scan — workflow `Quickbooks` (323730202, was ON) and list `Ready
for Onboarding to QBO` (1176) — backed up to
`ops/fleet-health/audit/backups/2026-08-11-quickbooks/` and DELETED
(HubSpot-restorable ~90 days). (2) "All properties with under 150 contacts
presented for review": counted fills for all 454 live custom contact
properties; 378 are under 150 — organized by disposition in NEW
`ops/hubspot-schema/consolidation/low-fill-review.md` (22 keepers FYI /
168 keep-in-place / 112 storage-only / 52 already-retire / 4 new booth props /
20 system) with a tick-box column for Roman's archive picks.

**Why:** Roman 2026-08-11, verbatim orders. QBO context: no automation — Kath
marks invoices in TW, Claude cowork records payments in TW, manual QBO sync.

**Files:** `ops/hubspot-schema/consolidation/{automation-purge-proposal,low-fill-review}.md`,
`ops/fleet-health/audit/backups/2026-08-11-quickbooks/` (new).

---

## 2026-08-11 — Feedback-agent dedupe fix + automation purge proposal

**What:** (1) Fixed the feedback agent double-filing reports: Slack retries land
as second dispatches pinned to a stale commit, so the retry run read a
state.json without the first run's processed-mark (root cause of duplicate PRs
#63/#64 for Danielle's LinkedIn-op-ed report; `Ev0BPLGNF12N` appeared twice in
state.processed). Fix: `ref: main` on checkout in feedback-intake/-digest/-fix
(close-loop already had it) — the concurrency group already serializes runs, so
the second run now sees fresh state and the existing event_id dedupe catches
the retry. Removed the orphan duplicate correction file (#64's) + doubled state
entry. (2) NEW `ops/hubspot-schema/consolidation/automation-purge-proposal.md`:
the 87 workflows/lists + 43 forms + 8 misc blockers holding up the 78 blocked
retire candidates, each with DELETE (25) / EDIT (43) / VERIFY (19) verdicts,
3 high-risk callouts (TW-sync Zapier path, SMS deal-token stack, Quickbooks),
a text-scan accuracy caveat for generic names, and an authoritative
delete-probe step. PROPOSAL — pending Roman.

**Why:** Roman: "do 1 and 2" (feedback-agent diagnosis + purge proposal).
Optional relay hardening (CacheService dedupe in apps-script.gs) offered but
needs Roman's web-app redeploy — not done.

**Files:** `.github/workflows/feedback-{intake,digest,fix}.yml`,
`corrections/content-build/` (dup removed), `ops/feedback-agent/state/state.json`,
`ops/hubspot-schema/consolidation/automation-purge-proposal.md` (new).

**Addendum (Roman's answers, same day):** callout 1 RESOLVED — `Non Charter/A+
Sync to TW` is the LIVE path putting Gold + Free Trial deals into A+ Teachworks
(deal_sync covers charter POs only): flow KEEP; `sync_to_teachworks_` and
`sync_to_teachworks_slp` reclassified KEEP-IN-PLACE (only `_cap` still retires,
with the CAP flows). Callout 3 context: NO QBO automation exists — Kath marks
invoices in TW, Claude cowork records payments in TW, QBO synced manually; the
`Ready for Onboarding to QBO` list + onboarding flow are the manual queue
(KEEP; `is_the_online_tutor_ready_for_onboarding` + `business_license_on_file`
reclassified KEEP-IN-PLACE). Contacts: KEEP-IN-PLACE 185→189,
RETIRE-CANDIDATE 99→95. Verdicts now: 25 DELETE / 43 EDIT / 4 KEEP / 15 VERIFY.

---

## 2026-08-12 — Booth: role picker + attendee list + short consent

**What:** (1) NEW `aplus_event_role` (events group, dropdown
Administrator/Teacher/Support Staff), declared + synced; required pill picker
on the booth form. Role now drives the create-only persona stamp:
teacher→TOR persona+lead status, administrator→Decision Maker/Director,
support_staff→no stamp, missing→teacher default (verified e2e). (2) NEW
ACTIVE list 3103 "Sage Oak BTSC 2026 — Booth Attendees" on
aplus_event_tag=sage_oak_btsc_2026 — auto-enrolls all booth contacts;
future events get one list per appended tag option. Enrollment verified
(<30s); team test runs (Roman/Emily/Hugh Jazz/Danielle) already enrolled,
personas behaved per doctrine. (3) Consent copy shortened (Roman):
"Send my photo + A+ can reach out about tutoring for my students 📸".

**Why:** Roman 2026-08-12: role segmentation + "every contact that submits
this photo booth ends up on a hubspot list."

**Files:** `booth/worker.js`, `booth/index.html`,
`ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/KEEPERS.md` (81→82).

---

## 2026-08-11 — Booth round 3: enum-write bugfix, frame design, delivery=All

**What:** (1) CRITICAL FIX: worker.js wrote enum LABELS ("Print") where the
HubSpot API takes internal VALUES ("print") — every booth submission failed
the contact upsert silently while photos still delivered (the fleet "read
labels" rule is about reading, not writing). Verified fixed end-to-end:
test contact created with all 6 props + TOR persona, then archived.
(2) Email timeline logging verified live: test submission → 1 email
engagement on the contact (subject/SENT), then archived. BCC workaround
declined — sender isn't a HubSpot user so BCC logging would misattribute;
API logging is deterministic. (3) Frame redesign: both logos in the header
band, fun banners ("Best. Year. Ever. ✨" etc.), 2026–2027 school year on
frame/attract/email, type sized for 2x3" prints (~600dpi: old 24-30px text
printed at ~3pt). (4) Delivery "Both" → "All 3!" (email+text+print);
aplus_booth_delivery += all (synced; "both" kept legacy). (5) Screens
scroll when content overflows (kiosk overflow:hidden clipped the 4-card
delivery screen with no way to reach the rest). (6) Photo retention is
DOCUMENTED as ephemeral: email=attachment only, text=KV 7-day TTL,
print=nothing. Archive-all option proposed to Roman, not yet approved.

**Why:** The event capture chain (contact + persona + timeline email) is the
point of the booth; the silent enum failure was defeating exactly that.

**Files:** `booth/worker.js`, `booth/index.html`,
`ops/hubspot-schema/properties.yml`.

---

## 2026-08-11 — Booth round 2: branding, TOR audience, JustCall texts, email logging

**What:** (1) Logos: Sage Oak pennant + white A+ on attract, color A+ in the
email. (2) All outbound links → wetutorathome.com/home-school-tutoring
(aplustutoring.com is NOT ours — email CTA, SMS body, photo-frame footer).
(3) TOR audience (Roman: attendees are homeschool charter TORs, not parents):
teacher-facing copy pitching one-on-one tutoring + intervention programs, and
booth-CREATED contacts stamped a_persona="Teacher of Record/EF/ES" +
hs_lead_status="Charter School Teacher TOR/EF" (create-only, mirrors
po_inbox TOR_CREATE_PROPS; existing contacts never overwritten). (4) NEW
"Text it" delivery via JustCall MMS from the main A+ line +18188506284:
photo stored in Workers KV (7-day TTL, UUID keys) and served publicly at
<worker>/photo/<uuid> as the media_url; JUSTCALL_API_KEY/SECRET set as Worker
secrets; `aplus_booth_delivery` gained option Text(text) — declared in
properties.yml and synced (R2 skipped: not enabled on the account, KV needs
nothing). (5) Booth photo emails logged to the contact's HubSpot timeline
via engagements API (assoc 198; write scope verified create+delete). (6)
Photo canvas 1200×1500 (4:5) → 1200×1800 (2:3) to fit Roman's 2x3" portable
printer (also fits 4x6); camera preview ratio matched.

**Why:** Event capture should classify TORs correctly for the fleet, deliver
photos the way teachers actually want them, and leave a full trail (email on
timeline) in HubSpot.

**Files:** `booth/worker.js`, `booth/index.html`, `booth/wrangler.toml`,
`ops/hubspot-schema/properties.yml`.

**What:** New `booth/` directory: Cloudflare Worker `sage-oak-booth`
(worker.js — `/submit` upserts the HubSpot contact with the 4 events-group
props from PR #65 and emails the framed photo via Resend) + kiosk front-end
(index.html — attract → banner → camera → form → delivery, client-side photo
composite) + wrangler.toml + README. DEPLOYED live:
Worker `https://sage-oak-booth.nameless-mountain-bafa.workers.dev` (secrets
HUBSPOT_TOKEN + RESEND_API_KEY set via wrangler), Pages
`https://sage-oak-booth.pages.dev`; CONFIG.WORKER_URL and ALLOWED_ORIGIN
cross-wired; smoke-tested (CORS preflight, input validation, Pages 200).
Sender is `photos@wetutorathome.com` — that's the Resend-verified domain
(aplustutoring.com is NOT verified there; Roman verified wetutorathome.com
in-session).

**Why:** Sage Oak BTSC 2026 event capture — booth attendees become HubSpot
contacts (event-tagged, consent recorded) with zero manual entry.

**Files:** `booth/worker.js`, `booth/index.html`, `booth/wrangler.toml`,
`booth/README.md`.

---

## 2026-08-11 — Concurrency rule: branch work in worktrees (Roman: "lfg")

**What:** New mandatory rule in `CLAUDE.md`: sessions doing branch/PR work use
a git worktree; never create/commit branches directly in the shared main
checkout.

**Why:** Two concurrent sessions collided today — a po_inbox commit from one
session landed on the other's PR branch (this one, #65) and the branch had to
be rebuilt by hand. Worktrees isolate each session's working tree while
sharing history.

**Files:** `CLAUDE.md`.

---

## 2026-08-11 — Booth properties for Sage Oak BTSC 2026 (PR #65)

**What:** Declared 4 new contact properties in the registry for the photo
booth: `aplus_event_tag` (multi-checkbox, one option `sage_oak_btsc_2026`;
future events APPEND options), `aplus_booth_goal` (banner text), `aplus_booth_delivery`
(Email/Print/Both dropdown), `aplus_marketing_consent` (Yes/No dropdown).
Added a new `events` contact property group — booth attendees can be any
persona, so none of the 5 persona groups fit. LOCKED by Roman 2026-08-11:
the `events` group + the event-tag append pattern (one multi-select property,
future events append options) — decision-log number pending. POST-MERGE
EXECUTED same day (Roman: "run"): PR #65 squash-merged, `create_properties.py`
run (4 created / 0 updated / 87 already in sync), all 4 verified live in
portal 6312752 by independent API read (labels, group, options correct),
KEEPERS.md +Events section (86→90).

**Why:** Booth capture tools need declared properties (registry rule: never
create ad hoc); event attendance is designed as one multi-select tag property
so each future event is an appended option, not a new property.

**Files:** `ops/hubspot-schema/properties.yml`.

---

## 2026-08-11 — PO hours computed from rate + Kath's invoice fields + PO-PROCESS.md

**What:** (1) Extractor now pulls the PO's HOURLY RATE; when hours aren't
stated, they're computed (amount ÷ rate, e.g. $150 ÷ $75/hr = 2, fractional ok)
and noted on the ticket — stated hours are never overwritten. (2) Kath's
convert-to-invoice task now explicitly instructs filling `invoice__` (Invoice #)
with the TW invoice number and confirming `lessons_fulfilled_date` (prefilled
to the end of the PO month = the invoice due date). (3) NEW `docs/PO-PROCESS.md`:
the complete PO-receipt reference — every stage, every property with its
decision rule, and the human ownership table. Keep it in sync with po_inbox.py.

**Why:** Roman (2026-08-11): "for PO hours, you might have to calculate. but
our rate will be in the po. kath also has to fill out the properties of
invoice number and invoice due date" + asked for the guided walkthrough.

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(suite 202 green), `docs/PO-PROCESS.md` (new).

---

## 2026-08-11 — SMS workflow audited: property routes (never suppresses) + schedule stamp

**What:** Audited SMS flow 1603217415 ("Charter Traditional SMS New Deal
Created", contact-based) end-to-end via the automation API. Findings: BOTH
branches of `is_the_family_currently_being_tutored_by_us_` send the
schedule-confirmation texts — "No" only adds an internal staff email + delay
first; texts are per-CONTACT enrollment (re-armed when the flow clears
`contact_level_deal_stage`), so frequency is structurally one text pair per kid
per PO event, never daily. Two fixes from that: (1) REVERTED the sibling-deal
"Yes" suppression (texts were never per-deal; the flow fetches ONE associated
deal, so a lying sibling could skip the staff alert) — every deal now carries
the true month-scoped value; the 10 sibling deals in-portal reset to "No".
(2) The SMS inserts `{{schedule_preferences}}` from the DEAL — PO deals never
had it, so charter texts ended in a BLANK. The agent now stamps it at PO time
with the student's live TW schedule ("Wednesdays 3:30 PM with Sarah Lee"),
derived from upcoming lessons, else the recent-lesson pattern (new
upcoming_lessons/recent_lessons detail in tw.student_lesson_activity);
nothing derivable → 🚩 gap DM instead of a half-written text.

**Why:** Roman shared the live SMS workflow; reading it showed the property's
real semantics (routing, not suppression) and the blank-schedule content bug.
Roman: "yessssss. fix the schedule. i agree with it all."

**Files:** `email/src/po_inbox.py`, `email/src/teachworks_client.py`,
`email/tests/test_po_inbox.py` (suite 198 green).

---

## 2026-08-10 — PO deal naming convention + parent-chase flow (Roman: "implement")

**What:** (1) PO-created deals are now named `Parent - Student - School N - YY/YY`
(Roman's convention, e.g. "Alexandra Lauterio - Genevieve Lauterio - Taylion 1 -
26/27"): N = the student's deal count at that school this school year + 1 (staggered
across multi-PO emails), school year derived from the PO's service month (Aug–Dec =
first year), school shorthand from new `po_inbox.school_short_names` config map
(unmapped school → extracted name used + ticket flags the gap). Parent contact is
now resolved BEFORE naming; the PO number moves out of the name entirely (the
`po_number` property is canonical). Bonus: parent-led names pass deal_sync's
`_contact_matches_dealname` check, which the old "School - Student - PO #" names
failed. (2) NEW parent-chase flow: a PO with no parent info and no unique HubSpot
match creates the deal as `NEEDS PARENT - ...` and DRAFTS a parent-info request
(name + email + phone) to the TOR (else sender) on the same Gmail thread — human
sends it (agent still never sends from charter@). The reply is caught on the open
thread: Family contact auto-created (email + phone + `a_persona=Family`), associated
to the deal, deal renamed to the real parent, family→TOR link synced (#AP031), and
the Teachworks sync runs immediately — unblocking the whole downstream chain
(TW family/student → scheduling → invoice hours) with zero manual data entry.
No reply within `parent_chase.escalate_business_hours` (16 = 2 business days) →
one escalation DM to Kath. The live Taylion deal 63551218500 was renamed to the
new convention in-portal.

**Why:** Roman (2026-08-10): the deal name must lead with the parent, and a missing
parent blocks more than the name — the Teachworks sync keys the family on the deal's
contact email, so every PO without parent info silently stalled TW creation,
scheduling alerts, and invoice hour-tracking until someone chased it by hand.

Also: extracted PO numbers are normalized — a leading "PO"/"P.O.#" prefix is
stripped ("PO7514044381" → "7514044381"; letters that are PART of the number,
like Blue Ridge's "PF593736", are kept) before dedupe, the deal property, and
the audit record.

(3) Order agreements ARE POs (Roman, same session): OPS/iLEAD Vendor Agreement
Forms stamped "THIS IS NOT A PO" now get the FULL PO flow (deals per PO number,
invoice tasks, chase) with a new `pending_approval` flag — ticket + invoice task
carry "⏳ PENDING school approval — confirm in the school's ordering portal".
This partially supersedes the 2026-08-06 iLEAD thread-stays-open fix: OA threads
now close as processed POs; the approved-PO email arriving later trips the
po_number dedupe, which alerts Kath (that alert now doubles as the approval
signal). Thread guard refined: a closed thread with an OPEN parent chase still
processes replies (the TOR's parent-info answer must get through). NEW replay
tool: `PO_REPLAY_MSG_IDS` env / `replay_msg_ids` workflow input reprocesses
specific Gmail messages, bypassing guards — for backfilling under new rules
(same pattern as deal-sync's FORCE_DEAL_ID).

(4) Scheduler visibility (Roman, same session): every PO-created deal now sets
`should_this_deal_be_posted_to_a_slack_channel_="true"` — the existing HubSpot
workflow behind that checkbox posts the deal to the per-pipeline Slack channel.
And the assigned scheduler (deal owner, A-L/M-Z) gets ONE direct DM per PO email
listing the deal(s) created: "In Pre-Lesson now — get lessons scheduled to hit
the 72-hr Post-Lesson target", with the pending-approval warning when it applies.
Previously schedulers only saw deals appear in HubSpot; the sole Slack signal
was the no-lessons alert in #email-agent.

(5) TOR name-only fallback (Roman, same session — "why weren't TORs associated?"):
OPS/iLEAD PDFs name the TOR without an email, and the TOR association keyed only
on email, skipping SILENTLY. Now a bare TOR name is looked up among existing
TOR-flagged contacts (lead status "Charter School Teacher TOR/EF" OR the TOR
persona), last name via search + first name compared accent-insensitively
('Véronique' portal vs 'Veronique' PDF); a UNIQUE match is associated (+#AP031
family→TOR link) — lookup only, never created from a bare name; no/ambiguous
match now flags the ticket. Backfilled in-portal: Mary Nieves → Isaac's 3 deals,
Véronique Fabre → Evrsen's 9, Shauna Smith → Taylion, + 3 labeled family→TOR
links (Jessica→Mary, Aly→Véronique, Alexandra→Shauna).

(6) Missing-info alerting (Roman, 2026-08-11: "whenever something is missing it
is vital to send Roman and Kath Slack messages"): any gap on PO intake — fields
the PO didn't state, unmatched TOR/parent, NEEDS PARENT deals, failed uploads,
any "do it manually" follow-up — now triggers a direct 🚩 DM to EVERYONE in new
config `po_inbox.missing_info_dms` (kath + roman), with the gap list + ticket
link, on top of the ticket flags. Parent-chase escalations also go to both.

(7) `is_the_family_currently_being_tutored_by_us_` (Roman, 2026-08-11: gates the
scheduling-text workflow). THE RULE (locked with Roman same day; amended twice
in-session to its final form — student-level, CALENDAR-ONLY, stamped once at PO
time): **"Yes" = the PO's student has a lesson booked in Teachworks; "No" =
nothing on the calendar, period — the text goes out (recent lessons don't excuse
an empty calendar; a second kid with no lessons of their own is "No" even while
the sibling is active). ONE text per KID: a multi-PO email is always one student — only its FIRST
deal carries "No", same-student siblings are stamped "Yes" so the texting workflow cannot fire
9 times for a 9-PO order agreement (the Aly Daly case). Unverifiable (no parent
email / TW error) = left unset + 🚩 gap DM, never guessed; student absent from
TW = confident "No". MONTH-SCOPED: the check is against the PO's SERVICE MONTH — a September PO texts unless September itself has lessons booked (leftover August lessons do not count); month unparseable → any-upcoming fallback.** Checked against the RESOLVED parent email (PO or contact
record) via new tw.student_lesson_activity(), memoized per email; the no-lessons
scheduling alert shares the lookup, so it also works for parents resolved from
prior deals. Backfilled accordingly: Isaac's + Evrsen's FIRST deals "No", their
10 sibling deals corrected to "Yes"; Taylion left for Kath/Janelle to set once
booking is confirmed; Taylion dealtype corrected newbusiness → existingbusiness
(Genevieve had a prior deal).

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`,
`email/config.yaml`, `email/src/teachworks_client.py`, `email/tests/test_po_inbox.py` (32 new tests; email suite
191 green), `.github/workflows/email-po-inbox.yml` (replay_msg_ids input).

---

## 2026-08-10 — Retire-candidate archive pass (Roman: "go")

**What:** Registry sync run (`source_agent` +fleet-retry/+branch-hygiene). All
113 retire candidates audited for usage against 342 workflows (v3+v4), 214
lists, and calculated-property formulas (forms API not scannable — token lacks
forms scope). Outcome: **30 ARCHIVED** (audit-clean; reversible 90 days),
**35 BLOCKED** by live workflow/list references, **43 BLOCKED by HubSpot's own
PROPERTY_USAGE validation** (in use by forms — incl. pre-approved
`lead_ad_prop0`), **5 HOLD** (sibling fields, pending multi-child data-model
decision). Per-property outcomes stamped into the proposal docs.

**Why:** Roman's "go" on the remaining consolidation items. The API's
delete-time usage check covered the forms gap, so nothing referenced anywhere
was archived. Unblocking the 78 BLOCKED rows means cleaning up the referencing
workflows/lists/forms first — most are dead flows (Diagnostic Testing, CAP,
summer-2021 scheduling) that are themselves retirement candidates.

**Files:** proposal docs (outcome column), `ops/hubspot-schema/consolidation/`.

---

## 2026-08-10 — Consolidation APPROVED + persona group moves executed

**What:** Roman approved the consolidation proposal. Executed the 36 remaining
persona group moves via `ops/hubspot-schema/consolidation/execute_group_moves.py`
(idempotent, PATCH groupName only — names/types/options/data untouched);
verified 41/41 keepers now sit in `family`/`tor`/`tutor`/`student`. Declared all
86 keepers in `ops/hubspot-schema/properties.yml` (46 contacts + 38 deals +
existing a_persona/tickets); enum options intentionally omitted so the portal
stays authoritative for option lists (e.g. the master school list) —
`create_properties.py --dry-run` confirms 0 creates, 86 in sync.

**Why:** "approved" (Roman, 2026-08-10) on the committed proposal. NOT done:
archives — all 113 retire candidates still require Roman's per-property
"Used in" check first (locked rule). Also pending: dry-run shows `source_agent`
wants 2 new registry options (fleet-retry, branch-hygiene) — pre-existing sync
behavior, not run.

**Files:** `ops/hubspot-schema/properties.yml`,
`ops/hubspot-schema/consolidation/execute_group_moves.py` (new),
proposal docs restamped APPROVED/EXECUTED.

---

## 2026-08-10 — HubSpot property consolidation proposal (contacts + deals)

**What:** Read-only audit of all 884 contact / 718 deal properties in portal
6312752; every custom property (479 contacts, 107 deals) assigned a proposed
disposition in `ops/hubspot-schema/consolidation/` — persona-group move
(family 26, tor 4, tutor 9, student 1), KEEP-IN-PLACE (188 / 83),
STORAGE-ONLY (119 / 10), RETIRE-CANDIDATE (97 / 14, each with fill count +
last-modified + a required manual "Used in" check), or SYSTEM (35 custom
integration-written, excluded). `KEEPERS.md` distills the 88-property
vocabulary agents should use. Rule 12 enforced: repo grepped for every
internal name; code-referenced properties are keepers regardless of fill rate.

**Why:** Finishes what the persona architecture (#AP024/#AP028/#AP029,
commits 73837d3/f22fd07/60457fc) was built to enable — a single reviewable
sorting of years of program-specific property sprawl. This session PROPOSES;
Roman approves before anything moves, syncs, or archives. `properties.yml`
deliberately untouched — keeper declarations land after approval.

**Files:** `ops/hubspot-schema/consolidation/contacts-proposal.md`,
`deals-proposal.md`, `KEEPERS.md`.

**Addendum (same day, Roman's verdicts):** `what_is_your_child_s_current_grade_level_`
is THE canonical student grade property — agents use it always; the other grade
fields are program/form capture only. `what_grade_is_your_child_in` (9 fills) and
`payment_on_file_` (270 fills) demoted to RETIRE-CANDIDATE. Roman executed the
first group moves himself: `parent_concerns_what_can_we_do_to_help_`,
`student_school`, `student_additional_information` → `family`;
`student_last_name`, `student_last_name_if_diff_from_parent` → `student`
(the latter three out of CAP form_fields). Keeper set now 86.

---

## 2026-08-06 — PO agent: parent resolved from the student's prior deal

**What:** POs typically omit parent info; Kath's manual fix — look the student
up in HubSpot and read the parent off their prior deal — is now the agent's
second resolution step (after PO-provided parent email, before the last-name
guess): search deals by student first name, narrow to names containing the
student's last name, collect the deals' non-TOR contacts (persona/tor-email
filtered), and use a UNIQUE parent; anything ambiguous falls through
unchanged. Resolution method is noted on the ticket.

**Why:** Roman — "POs typically do not include parent name; Kath does this
manually so it's possible for you to do it." No student↔parent association
exists in the portal (verified read-only), so deal names are the link.

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`
(`get_deal_contacts`), `email/tests/test_po_inbox.py` (4 new tests; suite
159 green).

---

## 2026-08-06 — PO agent: one deal per PO number (multi-PO emails) + review threads stay open

**What:** (1) The extractor now returns `pos: [...]` when one email carries
several distinct POs (schools issue one per service month); deal handling
loops — one deal, invoice task, and TOR sync per PO number, scheduling alert
once per email. Fallback: comma-jammed `po_number` values split into one deal
each with amounts flagged for manual fill. (2) Thread dedupe now closes a
thread only after a REAL PO was processed (`category=new_po`); review-only
threads (order agreements marked "THIS IS NOT A PO") stay open so the actual
POs arriving as replies aren't silently dropped.

**Why:** Roman, on the live iLEAD/Jaramillo case (order agreement announcing
POs 3114047368/69/70, Aug/Sept/Oct): each PO number is its own deal. The old
code would have made one mashed deal (or skipped same-thread POs entirely).

**Files:** `email/src/po_inbox.py`, `email/tests/test_po_inbox.py`
(5 new/updated tests; suite 155 green).

---

## 2026-08-06 — PO agent: family→TOR association sync (#AP031) + persona stamping

**What:** Every incoming PO now syncs the family contact's "Teacher of Record"
association (contact→contact, typeId 15 USER_DEFINED): no-op when already
linked, create when missing, ADD-and-flag when the family is linked to a
different TOR — existing links are never auto-removed (multi-kid families).
TOR lookup falls back to secondary email before creating (prevents duplicates
like the Kristy Doyal case). Contacts CREATED by the agent are persona-stamped:
TOR → `hs_lead_status="Charter School Teacher TOR/EF"` +
`a_persona="Teacher of Record/EF/ES"`; parent → `a_persona="Family"`. Existing
contacts are never overwritten. Association labels/personas/lead-status value
verified read-only against portal 6312752 before implementation.

**Why:** #AP031 — the PO is the source-of-truth event for teacher assignment;
yesterday's ~405-association backfill goes stale without a per-PO sync.

**Files:** `email/src/po_inbox.py`, `email/src/hubspot_client.py`,
`email/tests/test_po_inbox.py` (7 new tests; suite 150 green).

---

## 2026-08-06 — Session Documentation Protocol installed

**What:** Created `CLAUDE.md` (session protocol + durable key context: property
registry, enumeration label rule, 5-persona contact model, family→TOR
association model) and this changelog.

**Why:** Claude-in-chat and Claude Code sessions were drifting — decisions made
in one surface weren't reliably visible in the other. The repo is now the
shared memory; the protocol makes documentation a mandatory session exit step.

**Files:** `CLAUDE.md`, `docs/CHANGELOG.md`.
