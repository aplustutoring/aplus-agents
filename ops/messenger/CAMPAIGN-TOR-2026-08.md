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

The TOR universe is the UNION of four signals, because no single one is
complete. Counts as of 2026-08-21:

| Signal | Contacts |
|---|---|
| `a_persona` contains "Teacher of Record/EF/ES" | 1,065 |
| `hs_lead_status` = `Charter School Teacher TOR/EF` | 1,086 |
| `charter_school_teacher` is known | 1,172 |
| `educational_facillitator_teacher_of_record` = true | 548 |
| **union** | **1,184** |

Attribution is by NAME. Charter deals carry `teacher_of_record_name` but there
is no teacher email property on the deal (verified: 2,244 of 2,284 deals since
2025-08-01 have the name, **zero** have an email). The script normalizes and
matches full names against contacts and reports what it cannot match rather
than guessing.

## Segments (one static list each)

| Code | Segment | Total | Mailable | Angle |
|---|---|---|---|---|
| A | Restarted 26/27 | 18 | 17 | Thank you, and who else on your roster |
| B1 | Anchor, 5+ families in 25/26 | 18 | 18 | Named counts, roster offer, Danielle calls on Day 8 |
| B2 | Multi, 2-4 families | 64 | 61 | Named count, roster offer |
| B3 | Single, 1 family | 105 | 95 | Restart is easy, honest opt-out invited |
| C1 | Intro, iLEAD, no history | 180 | 152 | iLEAD AV Tier 3 results (published) |
| C2 | Intro, other schools, no history | 800 | 625 | Danielle's classroom story, funding-already-there |
| | **total** | **1,185** | **968** | |

**Wave 1 (A + B1 + B2 + B3) = 191 teachers.**

Exclusions (217): 76 Sage Oak, 54 opted out, **48 families**, **33 role
mailboxes**, 4 non-marketable, 1 no email, 1 internal. Zero hard bounces,
because the 155 bounced TORs were archived on 2026-08-14.

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

## Copy

Six drafts in `templates/campaign-tor-2026-08/`, written to the
`danielle-voice` skill: first-person, classroom-led, no em dashes, no
rule-of-three, no "all students", no hard-sell close.

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

941 of the 1,122 mailable teachers have no deal history. Their engagement
history is stale but not toxic: 708 of 998 have been sent something before, 557
have opened at least once, 7 have ever replied, and **zero** have hard bounced.
The bulk were last emailed in 2025-01.

Sending 941 near-cold contacts in one morning off the same domain that is
currently running the family win-back is a real risk to the family campaign's
inbox placement. The ramp, unless Roman overrides it:

1. Week 1: A + B1 + B2 + B3 (191 contacts, warm, all have history)
2. Week 2: C1 iLEAD (152)
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
      B3, **191 mailable**. C1/C2 held for later waves.
- [x] **Sage Oak excluded (Roman 2026-08-21):** all 76, every segment.
- [x] **CTA per Danielle (Slack 2026-08-21):** "email me back and I will be your
      guide", plus a Teacher Scholarship Program mention, in all six drafts. No
      long dashes anywhere in the sent copy.
- [ ] Approve/edit the wave-1 copy drafts (`tors_a_restarted`, `tors_b1_anchor`,
      `tors_b2_multi`, `tors_b3_single`)
- [ ] Say GO for the wave-1 list/email/workflow build (ids into `campaign-tor.yml`)
- [ ] Flip `armed: true` + set `launch_date`
