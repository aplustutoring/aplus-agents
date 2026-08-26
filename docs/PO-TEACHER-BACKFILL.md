# Recovering teacher attribution from historical POs. Feasibility, not a plan.

Roman 2026-08-25: "The only way to truly find and associate those things would
be looking at each individual PO that's attached to either the contact or the
deal and seeing the name of the teacher there."

Correct. This records what that would actually cost, measured rather than
guessed, so the decision is not made twice.

## The gap

We only began recording the teacher on the deal in 25/26:

| School year | Charter deals | Name a teacher | Coverage |
|---|---|---|---|
| 2019/20 to 2022/23 | 242 | 0 | 0% |
| 2023/24 | 909 | 1 | 0% |
| 2024/25 | 2,105 | 528 | 25% |
| 2025/26 | 2,221 | 2,181 | 98% |
| 2026/27 | 78 | 78 | 100% |

**2,727 pre-25/26 charter deals have no teacher recorded.** For those, an absent
teacher means we did not capture one, not that nobody referred.

## What is recoverable without touching a PO

**45 teachers**, via `teacher_of_record_email_address` / `_name` stamped on
family contacts at intake. Already wired into
`scripts/charter_tor_segments.py`. Sparse (about 475 families, 258 distinct
teachers) and its only date is the family contact's createdate, which is a weak
proxy: 14 of those 45 turned out to be RECENT referrals, not lapsed ones, and
would have received a "it has been a while" email.

That leaves roughly 639 Tier 1 teachers whose history is genuinely unknowable
from CRM fields.

## What the PO route would cost

Sampled 40 of the 2,727 unattributed deals for fetchable attachments:

* **22%** carried at least one attached file reachable via the deal's notes
* extrapolates to roughly **613 files** to fetch and parse

**That 22% is a floor, not a ceiling.** The sample only looked at note
attachments on the deal, capped at five notes each. POs also live on contact
records, in the email engine's own records, and in inboxes. A fuller sweep would
find more, at more cost.

The parsing itself is the cheap part: `email/src/po_inbox.py` already extracts
names from POs in production. What does not exist is the backfill job that walks
historical deals, pulls attachments, runs the extractor, and reconciles a
parsed name against a contact record.

## Recommendation: not for this campaign

The reason to know a teacher's history is to pick a tier. Tier 1's copy is
deliberately **history-agnostic**: it opens on Danielle's own classroom and
never implies first contact, so a teacher with unrecorded history who receives it
gets an email that is slightly less warm than ideal, not one that is wrong or
insulting. That is a much smaller cost than the backfill.

Worth doing later if the tiers are reused for something where being wrong is
expensive, or if a PO backfill is wanted for its own sake. It should be scoped
as a data project, not smuggled into a campaign.

## If it is done

1. Walk pre-25/26 charter deals lacking `teacher_of_record_name`.
2. Collect attachments from the deal AND its associated contact, not just notes.
3. Run the existing PO extractor over each.
4. Match parsed names to TOR contacts with the same four-tier matcher the
   segmenter uses. Report ambiguous matches; never guess.
5. Write to a NEW property, not `teacher_of_record_name`, so a parsed value is
   never confused with one a human recorded.
