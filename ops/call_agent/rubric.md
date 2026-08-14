# A+ Tutoring — Inbound Call Quality Rubric v2

Used by the call agent to score answered inbound calls **for coaching purposes**.
This file is loaded into the scoring prompt at runtime — edit the anchors and
weights here; no code changes needed. Scores are internal (private coaching
channel only) and are never written to the family's HubSpot record.

v2 aligns the rubric with the locked consultation doctrine in
`knowledge/CUSTOMER_JOURNEY.md` (trust-first/money-last): pricing is NEVER
read aloud (S3 inverted from v1), the student's name is used early and often
(S5), "what school do you guys go to currently" is the silent qualifier (S6),
TOR is captured on charter calls (S7), and the free trial is an earned close,
never an opener (S8).

Scoring: each dimension 1–5 against the anchors below, or N/A when the
dimension doesn't apply to the call. Overall = average of scored dimensions.

---

## Universal dimensions (every scored call)

### U1. Opening & professionalism
- **5** — Warm branded greeting ("Thank you for calling A+ Tutoring, this is ___"), gives own name, positive energy throughout
- **3** — Identifies the business but flat/rushed; name given only when asked
- **1** — No identification, cold or distracted opening

### U2. Listening & empathy
- **5** — Lets the caller finish, acknowledges the concern in their words ("it sounds like the confidence piece worries you most"), asks before assuming
- **3** — Hears the facts but skips the feeling; occasional interruptions
- **1** — Talks over the caller, misses or dismisses stated concerns

### U3. Call control & structure
- **5** — Guides the call through a clear arc (understand → respond → next steps) without rushing; tangents get gently returned
- **3** — Gets there eventually but meanders; caller drives
- **1** — Call wanders or stalls; ends without shape

### U4. Information capture & verification
- **5** — Confirms/collects contact info (spells email back, verifies best phone), captures how they found A+ and any referral name
- **3** — Collects some info but doesn't verify; misses referral source
- **1** — No attempt to confirm or capture contact details
- N/A for callers already fully on file when nothing changed

### U5. Next steps & ownership
- **5** — Call ends with a concrete plan: WHO does WHAT by WHEN, stated so the caller could repeat it back
- **3** — Vague commitment ("we'll get that over to you") with no timeframe or owner
- **1** — Call ends with no agreed next step

## New-inquiry dimensions (intent = new inquiry / school partnership)

### S1. Discovery depth
- **5** — Surfaces grade, school, subjects AND the underlying "why now" (confidence, grades slipping, test coming), prior tutoring history, and what success looks like to the parent
- **3** — Gets the surface facts (grade/subject) but not the underlying driver
- **1** — Pitches before understanding the student
- N/A for non-inquiry calls

### S2. Program fit & value
- **5** — Explains the A+ model tailored to what THIS parent said ("since spelling is the weak spot, the diagnostic will show us...") — not a generic pitch
- **3** — Accurate but generic program description
- **1** — Confusing, wrong, or no explanation of how A+ helps

### S3. Pricing discipline (visual, never aloud)
Pricing is visual — nobody absorbs prices auditorily. The play is always:
"Let me email you a graphic and we'll go over it together" (text it if they
won't give an email). Reading prices aloud is a scored fail.
- **5** — No numbers spoken. Deferred to the emailed pricing graphic with a committed follow-up (when it's being sent, and what happens next)
- **3** — Deferred to the graphic but with no committed follow-up ("I'll send you something"), or hedged/apologetic about not quoting
- **1** — Read prices aloud on the call (even partially, even with a graphic promised)
- N/A when pricing genuinely didn't come up and didn't belong in the call

### S4. Advance (the close)
- **5** — Call ends with a scheduled commitment: assessment booked, diagnostics sent with a return plan, or a specific follow-up date/time
- **3** — Soft advance ("look it over and call us back") — momentum left with the caller
- **1** — No advance; interested caller leaves with nothing to do
- N/A for non-inquiry calls

### S5. Student's name — captured early, used often
Stop saying "your child" — say "Marcus."
- **5** — Asked for the student's first name early and used it naturally throughout (discovery, presentation, close)
- **3** — Got the name but rarely used it; long stretches of "your child" / "your son"
- **1** — Never asked for or never used the student's name
- N/A for non-inquiry calls

### S6. The school question (silent qualifier)
"What school do you guys go to currently?" determines charter-vs-private and
vendor status without ever feeling like a money question.
- **5** — Asked the school question naturally in flow, then worked the right fork (charter: social proof + tenure + "who's your teacher of record?"; private: area/modality)
- **3** — Learned the school incidentally or asked late; fork not worked
- **1** — Never established what school the student attends
- N/A for non-inquiry calls

### S7. TOR capture (charter calls)
The joint TOR email is the non-negotiable charter close move.
- **5** — Captured the teacher of record's name AND email at the close, set up the joint email / next step with the TOR
- **3** — TOR mentioned or name captured, but no email / no joint-email setup
- **1** — Charter family identified, call ends with no TOR information
- N/A for non-charter calls

### S8. Free trial — earned, never an opener
Unprompted = desperation; after a stated objection = confidence. (Private:
beats doubt/online hesitation. Charter: tiebreaker vs a competing vendor.)
- **5** — No unprompted offer; when an objection surfaced, the trial was deployed as the put-our-money-where-our-mouth-is close
- **3** — Offered before any real objection surfaced (but not as an opener), or an objection surfaced that the trial could have cleared and it was never deployed
- **1** — Led with the free trial as an opener / used it as a first-resort pitch
- N/A when no objection surfaced and no trial was discussed

## Service-call dimensions (intent = scheduling / billing / complaint)

### V1. Ownership & recovery
- **5** — Takes responsibility without blame-shifting, apologizes once cleanly if A+ erred, commits to the fix with a timeline
- **3** — Fixes the issue but defensive, or fix lacks a timeline
- **1** — Deflects, blames the tutor/system, or leaves resolution unclear
- N/A for non-service calls

### V2. Confirmation of resolution
- **5** — Restates the fix back ("so: Wednesdays cancelled, back to 45 minutes, Mon/Tue/Thu at 6") and confirms the caller agrees
- **3** — Fix agreed but never summarized — room for mismatch
- **1** — Call ends with the two sides possibly expecting different things
- N/A for non-service calls

---

## Coaching output (produced per scored call)

- Dimension scores + overall
- **What went well** — 1–2 moments, with short verbatim quotes
- **Coaching moments** — 1–2 moments, each: the verbatim quote, why it's a
  miss, and a concrete alternative phrasing to try next time
- **Missed opportunities** — checklist style (didn't ask referral source,
  didn't verify email, no advance, etc.)

Tone: coach, not critic. Assume good intent; anchor every point to a quote.
