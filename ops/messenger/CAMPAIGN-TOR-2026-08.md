# Charter TEACHER (TOR) 26/27 outreach — from Danielle

The teacher-side counterpart to `CAMPAIGN-2026-08-17.md` (families). Same rails,
different audience, different sender: this one goes out from Danielle
(Director of School Partnerships, owner `227538487`), because teachers are a
partnerships surface, not a sales-chase surface. Config: `campaign-tor.yml`.

Roman 2026-08-21: "segment same as we did with charter families."

## HARD COMPLIANCE RULES (Roman 2026-08-25, locked)

Every template in this campaign obeys all seven. They are not guidance.

1. The Badge denotes quality of program **DESIGN** only. Not implementation.
   Not effectiveness.
2. No copy may imply Stanford validated our student outcomes.
3. Never use: certified, accredited, endorsed, approved provider.
4. **No numbers about students anywhere.** No counts, no percentages, no
   outcome data. The only digits permitted in a body are the Badge term years
   (and the scholarship's session length, which is part of the offer).
5. No em dashes, ever.
6. Student-centered voice. Thank teachers for trusting us with **students**.
   Never thank them for sending business.
7. Text only. No Badge image in email.

Checked programmatically before every commit, not by eye.

## Structure: one campaign, four tiers, one shared Badge paragraph

**Segmentation is by relationship history, not by volume sent last year.** The
old 5+ / 2-4 / 1 split is retired. Once the ask became "who is on your caseload
THIS year", how many families a teacher sent last year stopped changing what the
email says. What still changes it is whether they have trusted us at all, and
how recently.

What varies per tier is the opening move and how hard the ask is.

| Tier | Who | Mailable | Opening move | Primary ask |
|---|---|---|---|---|
| 1 | All TORs, no referral history | 674 | No trust to reference. Badge does the credibility work. | **Scholarship nomination**, not a P.S. |
| 2 | Referred in 24/25, sat out 25/26 | 45 | Warm reopen, not a thank-you. Name the skipped year. | This year's caseload |
| 3 | Last year's referrers | 169 | **Locked opening, verbatim** | This year's caseload |
| 4 | Heavy referrers | 24 | **Pulled OUT of the campaign** | Individual sends, one personal line each |

Total mailable across tiers 1 to 3: **888**. Tier 4 is not enrolled anywhere.

**On the Tier 3 count:** Roman's spec says 193. That figure included the heavy
referrers, who are now Tier 4. Tier 3 as a campaign list is 169.

**Tier 4 is a correctness constraint, not a preference.** A merge-field email to
someone who sent us five or more families reads as exactly what it is. If a
Tier 4 contact appears in a campaign list, that is a bug.

## Tier 3 locked opening

Verbatim, not to be edited:

> You trusted us with your students last year, before any outside review of how
> we work existed. Stanford's National Student Support Accelerator has now
> reviewed how our tutoring program is designed and awarded us their Tutoring
> Program Design Badge for 2026 through 2029. Thank you for trusting us first.

Remaining beats may be rewritten but not restructured: caseload ask for this
year, session notes offer, scholarship P.S., signature.

**Note for the fact-check gate:** this renders the claim in prose ("for 2026
through 2029") rather than matching `claim_string` character for character. That
is fine and deliberate. The rule that matters is that the full Badge name and
its term window are both present. `aplus-fact-check` currently says to flag
"wording that does not match claim_string", which is too strict for prose. Worth
a follow-up on main.

## Tier 2's recency bound

Roman asked what the filter is for "how long we haven't spoken". There was none:
the tier was any prior deal, however old, paired with copy that says "it has
been a while". True at fourteen months, absurd at six years.

Measured 2026-08-25: **all 45 last referred 1.2 to 1.4 years ago.** One clean
cohort, not a spread. They referred in 24/25, sat out 25/26 entirely, and it is
now 26/27, so the copy names the skipped year instead of a vague "once".

`TIER_2_MAX_YEARS = 3` is now explicit in the segmenter. It changes nothing
today, because nobody is near it. It exists for next year, when the 25/26
non-returners age into this tier and the 24/25 cohort ages out of it: past the
bound a teacher is functionally cold and falls to Tier 1, so this copy can
always assume the gap is one or two school years and never longer. Every run
prints the tier's actual recency spread, so the bound cannot go invisible again.

## Why the ask is about THIS year

A charter TOR's caseload turns over. Of the teachers who returned in 26/27:
Christine Gurney had 11 families last year and carried 1; Christie Beadle had 8
and carried 0; Maya Lee had 5 and carried 1. Five of seventeen returning families
are now with a different teacher. An email built on last year's roster is about
children who are no longer theirs.

Session notes are therefore a standing offer mentioned once, never the ask, and
absent from every follow-up.

## The audience

`a_persona` = "Teacher of Record/EF/ES" and nothing else. 1,064 contacts.
Excluded (152): 62 Sage Oak, 53 opted out, 32 role mailboxes, 3 non-marketable,
1 no email, 1 internal.

Sage Oak is excluded at every tier: those teachers are worked separately through
the August Summit booth follow-up.

## Scholarship

Spec is locked in `knowledge/programs/teacher-scholarship.md`. Two 45-minute
sessions per nominated student, one assessment and one instruction. Two
nominations per teacher. **Overflow honoured on request** — if a teacher says
they have more than two, the answer is yes. Danielle must know the cap is a
starting point, not policy, before this sends.

## Runbook

```bash
python3 scripts/charter_tor_segments.py                  # read-only tiers
python3 scripts/charter_tor_segments.py --write-props    # stamp tor_* props
python3 scripts/charter_tor_segments.py --build-lists    # build the 4 lists
python3 ops/messenger/enroll.py --config campaign-tor.yml --force   # dry run
```

## Before launch (Roman)

- [ ] Approve the four tier drafts
- [ ] Confirm Danielle knows the scholarship overflow rule
- [ ] Generate Tier 4's per-person data so Danielle can write 24 personal lines
- [ ] GO for the portal build (ids into `campaign-tor.yml`)
- [ ] Flip `armed: true` + set `launch_date`

Separate and not built: `CAMPAIGN-CHARTER-ADMINS.md`.
