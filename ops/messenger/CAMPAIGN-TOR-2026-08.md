# Charter TEACHER (TOR) 26/27 outreach — from Danielle

The teacher-side counterpart to `CAMPAIGN-2026-08-17.md` (families). Same rails,
different audience, different sender: this one goes out from Danielle
(Director of School Partnerships, owner `227538487`), because teachers are a
partnerships surface, not a sales-chase surface. Config: `campaign-tor.yml`.

Roman 2026-08-21: "segment same as we did with charter families."

## Why the axes are different from the family split

The family segmenter splits on recency x student-count x personalization. That
does not transfer: a teacher has no lessons of their own, and every teacher is
"lapsed" in August. What actually separates teachers is whether business has
already come through them this school year, and how much came through them last
year. So the axes are **26/27 activity x 25/26 volume**, with a school-based
split on the cold tail.

Built by `scripts/charter_tor_segments.py` (read-only by default).

## The audience

**The audience is `a_persona` = "Teacher of Record/EF/ES" and nothing else:
1,064 contacts.** The persona property is the master contact-type switch
(CLAUDE.md: every agent reads it FIRST), so it IS the audience, not one vote
among several.

An earlier version of this campaign unioned four signals. Roman, 2026-08-24:
"dont we have a persona for teachers as well in the A+ Persona property... we
created property architecture." Correct, and the union was bypassing it. The
persona is both cleaner and nearly as complete:

| Signal | Contacts | Families in it | Role mailboxes |
|---|---|---|---|
| **`a_persona` = Teacher of Record/EF/ES** | **1,064** | **6** | **20** |
| `hs_lead_status` = `Charter School Teacher TOR/EF` | 1,083 | 5 | 19 |
| `charter_school_teacher` is known | 1,173 | 48 | 35 |
| `educational_facillitator_teacher_of_record` = true | 548 | 3 | 0 |

The union added 121 contacts beyond the persona, and 57 of those 121 were the
junk. Only 64 were real people the persona was missing.

The other three signals are still read, but only to print a **persona backfill
queue**: 64 people who look like teachers and have no persona. They are
reported, never emailed. Tag them in the portal and the next run picks them up
(14 iLEAD, 13 Sage Oak, 6 Ocean Grove, 5 Visions, 5 Horizon, and a tail).

### The persona wins over heuristics

`looks_like_family` does not fire on a contact explicitly tagged
"Teacher of Record/EF/ES". That is the dual-persona case the 5-persona model
was built for (#AP030). **Kristy Doyal** is exactly it: a real Heartland teacher
who is also a parent, tagged `Teacher of Record/EF/ES;Family`, sitting in
segment A with 3 new families this year. A pure heuristic would have dropped
her. The persona keeps her.

Attribution is by NAME. Charter deals carry `teacher_of_record_name` but there
is no teacher email property on the deal (verified: 2,244 of 2,284 deals since
2025-08-01 have the name, **zero** have an email). The script normalizes and
matches full names against contacts and reports what it cannot match rather
than guessing.

## Segments (one static list each)

| Code | Segment | Total | Mailable | Angle |
|---|---|---|---|---|
| A | Restarted 26/27 | 18 | 18 | Thank you, and who else on your roster |
| B1 | Anchor, 5+ families in 25/26 | 18 | 18 | Named counts, roster offer, Danielle calls on Day 8 |
| B2 | Multi, 2-4 families | 63 | 62 | Named count, roster offer |
| B3 | Single, 1 family | 105 | 95 | Restart is easy, honest opt-out invited |
| C1 | Intro, iLEAD, no history | 157 | 141 | iLEAD AV Tier 3 results (published) |
| C2 | Intro, other schools, no history | 703 | 591 | Danielle's classroom story, funding-already-there |
| | **total** | **1,064** | **925** | |

**Wave 1 (A + B1 + B2 + B3) = 193 teachers.**

Exclusions (139): 62 Sage Oak, 53 opted out, 19 role mailboxes, 3
non-marketable, 1 no email, 1 internal. Zero hard bounces, because the 155
bounced TORs were archived on 2026-08-14.

The "families" exclusion is gone: with the persona as the audience, families
were never in it. The role-mailbox filter still earns its keep, because 19
`vendors@`/`ap@`-style addresses carry the teacher persona themselves.

### The audience needed tightening: `charter_school_teacher` is not "is a teacher"

Roman, 2026-08-24, looking at a family email: "is it going to teachers or
families? i feel like we have confusion somewhere." He was right, though not
about the email. That property holds WHICH SCHOOL a contact belongs to, and it
was one of the four signals building this audience, so it dragged in two
populations that are not teachers:

* **33 school role mailboxes** — `vendors@ileadexploration.org`, `ap@ieminc.org`,
  `accountspayable@theblueridgeacademy.com`, `noreply@`, `contractprograms@`.
  A personally-signed "I taught K-8, here is what I saw" landing in accounts
  payable is a deliverability problem, not just an awkward one.
* **48 actual families** — parents on personal gmail/yahoo with students and
  tutors stamped on them (Diana Torres, students Freddie & Sarai, tutor Fidah).
  They belong to the family campaign and were already receiving it.

Both are now hard exclusions in the segmenter (`is_role_mailbox`,
`looks_like_family`). A contact carrying real family signals is never a teacher
for this campaign's purposes, even when it is genuinely both people.

**78 contacts have no first name** and would have opened "Hi ,". All 78 sit in
the cold C1/C2 waves; wave 1 has none. Rather than drop them, every draft now
uses `{{ personalization_token('contact.firstname', 'there') }}`.

**Sage Oak is excluded at every segment.** Roman to Danielle in Slack
2026-08-20: "auto email campaign to all charter teachers from you (except sage
oak)"; reconfirmed 2026-08-21. Those 76 teachers are worked through the August
Summit booth follow-up Danielle is running, and double-touching them would
collide with it. The exclusion lives in `EXCLUDE_SCHOOLS` in the segmenter, so
it applies to every future wave too, not just wave 1.

Counts above are post-matcher-fix. The first pass under-attributed: `norm_name`
deleted accents and glued hyphenated surnames, which orphaned 119 deals and put
23 teachers in the wrong segment. Fixed before any list was built.

Cross-reference: **168 teachers have 329 families sitting in the 26/27 gap
list** (list 3104). The teacher campaign and the family win-back campaign will
touch the same households from two directions. That is deliberate. It is also
the reason segment B leads with the roster offer rather than a second ask.

## Framing: back to school

Roman 2026-08-24: "we are focusing on charter school teachers and getting a
back 2 school workflow going". Every draft now opens on "Welcome back to the
school year" and the wave-1 subjects lead with "Welcome back", matching what
Roman pitched to Danielle on 2026-08-20 ("Welcoming back to the school year").

## A charter TOR's caseload turns over. Write to this year's.

Roman 2026-08-25: "they probably don't even have the same students on their case
this year that they had last year... they probably don't give a fuck about the
lesson notes from last year."

**Checked against the deal data, and he is right.** Of the teachers who have
returned so far in 26/27:

| Teacher | Families in 25/26 | Carried into 26/27 |
|---|---|---|
| Christine Gurney | 11 | 1 |
| Christie Beadle | 8 | 0 (1 new) |
| Mary Nieves | 6 | 2 |
| Maya Lee | 5 | 1 |
| Kristy Doyal | 5 | 2 |

Five of the seventeen returning families are now with a **different** teacher.
Caveat: only ~20 families have 26/27 deals so far, so this is directional rather
than conclusive. But the risk is asymmetric — an ask aimed at this year's
caseload works whether or not rosters persist, and an ask aimed at last year's
roster fails if they do not.

**Consequence for the copy:** last year is one line of thanks and never the ask.
The ask is whoever is on their case NOW. Session notes are a standing offer
mentioned once at the end, and deliberately absent from the follow-up — the
follow-up repeats the caseload question instead. B3 drops the notes offer
entirely: one family last year is not worth offering notes on, and raising it
only highlights how little we did together.

## Copy

Six drafts in `templates/campaign-tor-2026-08/`, written to the
`danielle-voice` skill: first-person, classroom-led, no em dashes, no
rule-of-three, no "all students", no hard-sell close.

### Length is a hard constraint, not a preference

Roman 2026-08-24: "why are these emails so verbose. its going to be clear that
AI wrote it. these are busy teachers. they dont need AI slop sent to them."

The first drafts ran ~200 words each: a welcome line, a process explainer, a
credibility paragraph, a CTA paragraph and a scholarship paragraph, which is
exactly the shape that reads as machine-written. Rewritten to **70 to 95 words**
with one ask each and the scholarship demoted to a one-line P.S.

Roman 2026-08-24, second pass: **"curiosity over bullshit, school year start is
busy."** That changed the ask, not just the length. "Want the roster of your
families?" is still handing a teacher an admin task in September. The rewrite
leads with something they do not have and cannot get anywhere else:

* **B1 / B2** — a teacher never finds out what happened to the students they
  referred. Nobody reports back. "Some finished the year, some stopped partway,
  and I doubt anyone told you which. I can, in one email. Want it?" One word
  costs them nothing and the answer is genuinely theirs.
* **B3** — one family is not enough to offer a report on, so it asks the single
  question a teacher three weeks into the year already knows the answer to:
  "Is there a student you are already worried about?"
* **C1** — the numbers are the hook, so they are the subject line:
  "Sixteen of twenty".
* **C2** — the hook is the thing most teachers do not know: the money is
  already allocated.

56 to 77 words each.

### ⚠ The B1/B2 promise has an operational dependency

Those two emails promise an answer, and the answer needs Teachworks lesson
history (did each family finish or stop partway). **The Teachworks key lives
ONLY in GitHub Actions secrets, not locally**, so nobody can pull it ad hoc.

**Pre-send requirement:** generate the per-teacher answer sheets BEFORE wave 1
goes out, via one `charter-gap-analysis.yml` run, and hand Danielle the file.
80 teachers replying to a promise she cannot fulfil for three days turns the
curiosity hook into the thing that burns her.

### The scholarship P.S.: nominate, then WE select

**Canonical description now lives at `knowledge/programs/teacher-scholarship.md`.
All copy must match that file, not the marketing emails.** That file exists
because this campaign described the offer wrong twice in one day, both times by
reading the funnel instead of a definition. There was no definition.

Roman 2026-08-24: "teachers nominate, we select. scarcity component in play...
has to be universal."

The P.S. in all four warm segments now reads:

> Teacher Scholarship Program: nominate a student and tell me why them. They get
> a free session with one of our tutors. Who comes to mind?

**It asks for a rationale. It does not claim we reject anyone.** Roman
2026-08-24: "we wont say no, but they need to feel like we did." The criteria
are real (student need plus the teacher's reasoning) but nominations are not
turned down in practice, so copy that asserts selection would be manufacturing
scarcity. A teacher who nominates three students and sees three accepted has
worked that out, and teachers at the same school compare notes. Asking someone
to justify a choice is what makes the choice feel weighed, and "tell me why
them" is both true and the actual criterion. Full reasoning in
`knowledge/programs/teacher-scholarship.md`.

The line ends on a question, which is the curiosity rule doing its job.

### Earlier drafts of this same P.S. (kept as a warning)

Roman 2026-08-24: **"our scholarship program provides 1 free session to a child
that the teacher wants."**

The drafts had it as "covers one student in full, no charter funds involved",
which is a much bigger promise. Corrected in all four warm segments to:
"gives a student of your choosing one free session. Tell me who and I will set
it up." One session that a teacher can picture giving to a specific kid is a
fine offer. A funded tutoring programme that turns out to be one session is a
trust problem.

**⚠ The LIVE scholarship funnel has the same overclaim, and it is not ours to
fix from here.** Stage 1.3 (`217749216439`) is subject-lined "A free tutoring
spot for one of your students" and describes "free, synchronous one-on-one
tutoring with a real tutor, matched to exactly where they need support, plus
session notes so everyone stays in the loop". Nothing in it says one session.
A teacher reading that expects ongoing tutoring.

Once this campaign starts pointing teachers at that funnel, it inherits the
mismatch. Worth a pass over those 22 emails with Danielle before wave 1.

Rules for anyone editing these:
* One ask per email. If there are two CTAs, cut one.
* Lead with what they do not have, not with what we want. A teacher in
  September will answer curiosity and will bin a request for their time.
* Never ask them to do admin. "Want the roster?" is homework; "want to know
  which ones stopped?" is a gift.
* No paragraph explaining a process the teacher already runs every year.
* Danielle's classroom credibility is worth one clause, not a paragraph.
* The honest opt-out ("if nobody needs it, say so") stays. It is the most
  in-voice line in the set and it is what keeps this from reading as a pitch.

### Token trap: do NOT put the school in the copy

`charter_school_teacher` is an enumeration and HubSpot renders the option
**label**, not the value. The Ocean Grove label is
`IEM Inc South Sutter/Ocean Grove/Sky Mountain`, so `{{contact.charter_school_teacher}}`
would print that string to 348 teachers. School-specific wording belongs in the
segment, not in a token.

Live tokens are `{{contact.firstname}}`, `{{contact.tor_family_count}}`,
`{{contact.tor_student_count}}`. The counts are stamped snapshots: **re-run
`--write-props` the morning of any send**, or the email will assert a number
that has drifted.

## The workflow (per segment)

Enrollment is API-driven, so the workflows need no enrollment trigger. Built
from the family campaign's post-pilot shape:

- Day 0: segment email 1
- Day 4 (A, B1) / Day 5 (B2, B3): email 2, only if no reply. C1 and C2 get no
  nudge on the first pass.
- Day 8 (B1 only): call task for the **sales seat** (Danielle), ranked by 25/26
  invoiced value, roster attached
- Exit goals: `hs_email_last_reply_date` IS_KNOWN, plus meeting booked.
  **NOT lead status.** The family pilot used `lead status = OPEN_DEAL` as an
  exit goal and silently skipped 34 families carrying stale status from 25/26.
- Action windows: Mon-Fri, 09:00-18:00 PT, so no nudge lands on a Sunday.
- Suppression: HubSpot-native (opt-out, bounce, non-marketable) at every send.

## Deliverability: segment C is a cold send, treat it as one

732 of the 925 mailable teachers have no deal history. Their engagement
history is stale but not toxic: 708 of 998 have been sent something before, 557
have opened at least once, 7 have ever replied, and **zero** have hard bounced.
The bulk were last emailed in 2025-01.

Sending 941 near-cold contacts in one morning off the same domain that is
currently running the family win-back is a real risk to the family campaign's
inbox placement. The ramp, unless Roman overrides it:

1. Week 1: A + B1 + B2 + B3 (193 contacts, warm, all have history)
2. Week 2: C1 iLEAD (141)
3. Week 3+: C2 in school-sized waves, largest last:
   Compass, then the long tail, then Ocean Grove's ~348 split in two.
   Sage Oak is not in any wave.

Watch bounce and spam-complaint rate after each wave before releasing the next.

**Roman confirmed this ramp on 2026-08-21.** Wave 1 is the only wave being
built. C1 and C2 lists, emails and workflows stay unbuilt until wave 1 reply
and bounce data lands.

## Hygiene queue (found while building this)

The first pass logged "75 teacher names on 218 deals have no contact record" as
a hygiene queue. **That was the wrong diagnosis for more than half of it:** 119
of those deals named a teacher we already had, and the matcher was dropping
them. Fixed (accent folding, hyphenated surnames, "Last, First" order, middle
initials, email localparts). Orphans are now 99: 34 need a row-by-row call, 50
need a school roster, 15 are junk.

`mina chang` matches two contacts holding 23 deals between them and needs a
merge decision before those deals attribute correctly.

## Runbook

```bash
# 1. see the segmentation (read-only, safe any time)
python3 scripts/charter_tor_segments.py

# 2. stamp the tokens + segment property (needs contacts write)
python3 scripts/charter_tor_segments.py --write-props

# 3. build/refresh the six static lists, ids go into campaign-tor.yml
python3 scripts/charter_tor_segments.py --build-lists

# 4. dry-run enrollment
python3 ops/messenger/enroll.py --config campaign-tor.yml --force

# 5. live (after arming)
python3 ops/messenger/enroll.py --config campaign-tor.yml --confirm LAUNCH
```

New properties declared in `ops/hubspot-schema/properties.yml` (group `tor`):
`tor_family_count`, `tor_student_count`, `tor_families_lapsed`, `tor_segment`.
Run the schema sync before `--write-props`.

## Before launch (Roman)

- [x] **From-address (Roman 2026-08-21):** `danielle@wetutorathome.com`,
      fromName "Danielle Brodetsky". Already proven in the portal: 30 recent
      marketing emails use exactly that pair, so no new sender setup is needed.
      Not `success@`, which reads as a shared mailbox under a personally-signed
      email.
- [x] **Audience scope (Roman 2026-08-21):** warm first. Wave 1 = A + B1 + B2 +
      B3, **193 mailable**. C1/C2 held for later waves.
- [x] **Sage Oak excluded (Roman 2026-08-21):** all 76, every segment.
- [x] **CTA per Danielle (Slack 2026-08-21):** "email me back and I will be your
      guide", plus a Teacher Scholarship Program mention, in all six drafts. No
      long dashes anywhere in the sent copy.
- [ ] Approve/edit the wave-1 copy drafts (`tors_a_restarted`, `tors_b1_anchor`,
      `tors_b2_multi`, `tors_b3_single`)
- [ ] Say GO for the wave-1 list/email/workflow build (ids into `campaign-tor.yml`)
- [ ] Flip `armed: true` + set `launch_date`
