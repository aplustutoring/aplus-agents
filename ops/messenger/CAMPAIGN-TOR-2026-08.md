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
| A | Restarted 26/27 | 14 | 14 | Thank you, and who else on your roster |
| B1 | Anchor, 5+ families in 25/26 | 17 | 17 | Named counts, roster offer, Danielle calls on Day 8 |
| B2 | Multi, 2-4 families | 60 | 60 | Named count, roster offer |
| B3 | Single, 1 family | 95 | 90 | Restart is easy, honest opt-out invited |
| C1 | Intro, iLEAD, no history | 181 | 171 | iLEAD AV Tier 3 results (published) |
| C2 | Intro, other schools, no history | 817 | 770 | Danielle's classroom story, funding-already-there |
| | **total** | **1,184** | **1,122** | |

Exclusions (62): 54 opted out, 6 non-marketable, 1 no email, 1 internal. Zero
hard bounces, because the 155 bounced TORs were archived on 2026-08-14.

Cross-reference: **168 teachers have 329 families sitting in the 26/27 gap
list** (list 3104). The teacher campaign and the family win-back campaign will
touch the same households from two directions. That is deliberate. It is also
the reason segment B leads with the roster offer rather than a second ask.

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

1. Week 1: A + B1 + B2 + B3 (181 contacts, warm, all have history)
2. Week 2: C1 iLEAD (171)
3. Week 3+: C2 in school-sized waves, largest last:
   Compass 108, Sage Oak 71, then the long tail, then Ocean Grove 348 split in two

Watch bounce and spam-complaint rate after each wave before releasing the next.

## Hygiene queue (found while building this)

**75 teacher names appear on 218 charter deals with no matching contact
record.** Top offenders: Heather Pfeifer Tolan (22 deals), Christina Mondolo
(21), Crystal Uribe Schoelen (14), Stephanie Negrete Claar (14). Some are
missing contacts, some are name variants of contacts we do have, and 13 deals
literally say "no EF info". These teachers are invisible to every segment here.
Worth a pass before the send, but not a blocker.

Also: `mina chang` matches more than one contact. The script takes the first and
flags it.

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

- [ ] Approve/edit the six copy drafts
- [ ] Confirm the from-address. Danielle's owner email is
      `success@wetutorathome.com`. That is a shared-looking mailbox for a
      personally-voiced email signed by her.
- [ ] Confirm audience scope: warm 181 only, or the full 1,122 on the ramp
- [ ] Say GO for the list/email/workflow build (ids into `campaign-tor.yml`)
- [ ] Flip `armed: true` + set `launch_date`
