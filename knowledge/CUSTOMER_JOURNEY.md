# A+ Tutoring — Customer Journey & Agent Map (Master)

**The canonical map of the B2C family journey, where agents are implemented, and what has been decided.**
**Last updated:** June 11, 2026 (Roman + Claude working session)
**Status legend:** [LOCKED] decided · [BUILDING] · [SPEC'D] designed not built · [OPEN] questions outstanding

**Storage:** lives at `knowledge/CUSTOMER_JOURNEY.md` in the `aplustutoring/aplus-agents` repo (renamed from `aplus-marketing-skills`; Option B: one repo, `/marketing` + `/ops` folders). Every Claude Code build prompt references this file for context. After June 19, 2026, a summary folds into the Master Document (Google Doc).

---

## Definitions [LOCKED]

- **Lead:** anyone who contacted us without a deal yet. **Customer/deal:** created only when someone agrees to start tutoring.
- Private: deal created same-call (Paola manual) or via Get Started Now form (auto + pricing template).
- Charter: deal created by **Kath** only when the PO arrives. Gap between yes and PO = "PO purgatory" (currently invisible).
- QTL = Qualified Tutoring Lead. Lead statuses carry the journey until commitment; deal pipelines (Pre-Lesson / Post-Lesson / Stop) take over after.
- Paola's five call types: charter consult, private consult, TOR conversations, CARE calls, Spotlight calls. Only consults are sales calls; the evaluation agent must classify call type before scoring.

## Core economics [LOCKED]

- Private packages — Online: 8h/$88 · 20h/$83 (Prep, most popular) · 50h/$73 · 100h/$68 · hourly $95. In-person: $115/$108/$103/$93 · hourly $130.
- Charter: $60 per 45-min session, 2x/week ≈ $480–540/mo. Designed to fit iLEAD's $500/mo PO cap. iLEAD = bulk of charter B2C clientele; a few schools allow larger POs (exceptions). Monthly PO = effectively a 30-day renewal cycle per family.
- Charter and private materials strictly separated: no package ladder to charter families, no session pricing to private.
- iEM (Angie) $241K funded programs start 2026-27 — separate motion from this B2C journey (Danielle's lane).
- No Google Ads. Yelp sponsorship is the only paid channel.

---

# THE NINE STAGES

## Stage 0 — Awareness
**What happens:** SEO (wetutorathome.com), **Yelp sponsorship (only paid channel)**, TOR referrals (base business), charter newsletters, Instagram. Magnet/gifted-program webpage exists (Walter Reed IHP, Science Academy, Armstrong math).
**Built:** blog agent (3x/wk), SEO audit done, Instagram growth plan.
**Agents here:** blog agent [LIVE]. Spotlight pipeline [BUILDING] (feeds proof content).
**[OPEN]:** Yelp spend vs leads vs enrollments (only paid channel = cleanly measurable ROI; wire source→enrollment for Yelp first); whether source→enrollment is tracked at all today.

## Stage 1 — First touch
**What happens:** Web form ("Main InTake Form") creates contact w/ grade/charter/source; HubSpot workflow 50818589 fires instant auto text + auto email. Inbound calls via JustCall; missed calls get a 24/7 auto-text from the 6644 number ("on the phone with another learner, please text us back") but do NOT create a HubSpot contact (deliberate, to avoid spam-caller flooding).
**Decided:**
- Machine first-touch is FAST on both paths (instant form text+email; 24/7 missed-call text). The gap is everything AFTER, not first touch.
- ~30% of inbound calls are MISSED (Roman estimate) — roughly 1 in 3 prospects hits the deflection text.
- Junk records ("Call Tracking Email" / "Middletown Nj"-type, no status, qualified_score "Not Scored") come from missed/unhandled calls.
- **Reply-gated contact creation [SPEC'D]:** create a contact only when a missed number REPLIES to the 6644 text. Spammers don't reply; real parents do — the reply IS the spam filter. Solves junk records AND lead invisibility without importing spam.
**Agents here:**
- [BUILDING] **Call evaluation agent (sensor #1)** — every inbound call >=60 sec analyzed [LOCKED threshold].
- [LOCKED build] **AI SMS responder (agent 1b)** — two-way; handles replies to the missed-call 6644 text AND replies to the form auto-text; qualifies, answers basics, offers/books the consultation, creates+enriches the lead on reply. High priority given 30% miss rate. This is the monitored-reply layer the funnel lacks today.
**[OPEN]:** where SMS replies currently land (JustCall inbox? monitored by whom?); SMS agent autonomy (draft-for-Paola vs auto-send) at launch.

## Stage 2 — Pursuit (lead → connected)
**What happens today:** Workflow 50818589: form → status New (Inbox) → owner Paola → instant email (53% click) → SMS → delay to 5PM → branch (Connected / Sale in Process / Not Connected) → 55-min delay → call-outcome branches (Left Voicemail / Connected / VM not set up) → "Attempting to Contact" → **ENDS. No day 2+.** Leak #1 — leads age out silently (Jonathan, Stone, Brandy, Hnin, Melanie parked >1 week as of Jun 10). NOTE: branches depend on call dispositions, which **nobody logs** — so the sensor feeding this automation is unplugged; leads likely fall to default branch regardless of reality.
**Decided [LOCKED]:**
- **Cadence = 3 calls + 3 texts + 3 emails** (9 touches), then disposition to a terminal state (enrolled / committed / check-back-quarterly w/ date / dead w/ reason).
- **Division of labor (core philosophy):** the AGENT owns pursuit — texts, emails, call scheduling/reminders, follow-up tracking, never-forgets persistence. PAOLA owns only what humans do better — the live consultation and the close. She receives warm, ready leads.
- "Unable to Leave VM" email (3% click) needs rewrite.
**Agents here:**
- [SPEC'D] **Pursuit cadence agent** — runs the 3x3x3 sequence: schedules Paola's call tasks, sends agent-personalized texts+emails, tracks responses, advances or dispositions. Replaces the day-1 dead-end.
- [SPEC'D] **Stale-lead watchdog** — daily scan; anything past SLA → Slack alert + auto-advance. Extends existing sync scripts.
- Mid-cadence replies route to the SAME AI SMS responder (shared monitored-reply layer — recurring gap across stages: inbound replies need ONE always-on monitored surface).
**[OPEN]:** spacing of the 9 touches (propose: call+text+email day 1, text+email day 3, call day 5, email day 7, call+text day 10, disposition day 14); branch conditions in workflow steps 7/9 (Roman to check what property they read); which channel converts best (53% email click suggests email strong).

## Stage 3 — Consultation (THE PLAY) — most important stage, being built in depth
**What happens:** First connect IS the consultation [LOCKED]. Two entry modes: A cold inbound (capture name/mobile/email/student first), B booked w/ form context (prep from record, open by referencing what they wrote). Modes merge into one play.

**CORE PHILOSOPHY [LOCKED — supersedes earlier hard-Sandler budget-gate version]:**
- **TRUST FIRST, MONEY LAST.** Build trust and get to the bottom of what's going on with the child BEFORE money. Money never raised proactively — only if the parent asks, or as the end-of-call "let me email you a pricing breakdown."
- **THE RESTAURANT PRINCIPLE (training centerpiece, Roman's words):** a great waiter asks about allergies/dietary needs FIRST — he doesn't pitch the pasta then wait to learn the diner is gluten-free. Ask the right questions up front so every recommendation fits the kid and lines up to our core values, moving them down the pipeline.
- **Qualification is invisible, embedded in ONE question: "What school do you guys go to currently?"** Determines charter-vs-private AND whether A+ is a vendor there, without feeling like a money question. Natural follow-up: "Who's your teacher of record / facilitator?" (deepens charter path + captures TOR for the joint email).
- **Pricing is NEVER read aloud.** Always: "Let me email you a graphic and we'll go over it together." Won't give email → text the graphic. They MUST SEE it — pricing is visual; nobody absorbs prices auditorily. (Reason the pricing cards exist.)
- **TWO UNIVERSAL CLOSING QUESTIONS [Roman — every call, every type]:**
  1. **The humility question:** "Is there anything else about [Name] that I haven't asked but should have?" Catches whatever the script missed, surfaces the detail the parent was holding, signals we care about the whole child.
  2. **The attribution question:** "If you don't mind me asking, how did you hear about us?" We ALWAYS want to know the source. Feeds the growth engine — tells us which channels actually convert (Yelp / Google reviews / TOR referral / friend referral / magnet webpage). Capture it in HubSpot. Especially valuable since Yelp is our only PAID channel — this is how we measure what's working.
- **TRAINING FRAME for Paola (no formal sales experience): "Be the parent, not the salesperson."** She already knows how to interrogate a kid about school. She doesn't need sales technique — she needs to ask what any mom/dad would ask. Relaxes her into natural curiosity.

**SECTION 1 — Open / rapport:** [OPEN — need Roman's exact opener words for inbound vs booked.]

**SECTION 2 — DISCOVERY (the heart):**
- **Opener: "What's going on?" then STAY CURIOUS as long as humanly possible.** #1 skill and #1 failure point — untrained reps get one sentence ("he's behind in math") and jump to pitching. The skill is the follow-up thread.
- **Get the kid's NAME early and USE it.** Stop saying "your child" — say "Marcus." [SCOREABLE non-negotiable — agent counts name usage.]
- **Discovery FORKS by age/subject/goal — THREE branches, not one script:**
  - *Older kid / grades:* "Tell me more." · "When's the next test?" · "Does he have missing assignments?" · "What did he get on the last test?" · "Have you talked to the teacher?" · "Have you talked to him about it?"
  - *Younger kid / reading & foundational:* "What does reading look like at home?" · "What does homework look like?" · "Does he do it on his own or does someone have to sit with him?" · "Have you tried tutoring before?"
  - *Test-prep / entrance-exam (own animal — has a DATE = built-in urgency):* "Have you taken the test before?" · "When do you plan to take it officially?" · "Have you done a practice test yet?" (practice test = the diagnostic; SAT self-scores via College Board, others graded by Kath.)
- **"Have you tried tutoring before?"** = key cross-cutting question (prior experience, what failed, expectations).
- **HOMEWORK is the richest probe vein:** "What does homework look like? How much is assigned? Who does it with them? What happens if no one is there?" — surfaces real household pain points.
- **STAKES layer (Roman DOES go here — educate, don't fear-monger):** name the SUBJECT-SPECIFIC inflection point (do NOT lump reading + math together — that sounds scripted):
  - **Reading: 3rd grade** = the shift from "learning to read" to "reading to learn." Not solid by then → every subject suffers (all reading-dependent).
  - **Math: MIDDLE SCHOOL** = where it gets hard for most kids (abstraction, multi-step, pre-algebra). Shaky foundation surfaces fast.
  Today's small gap compounds. Converts "shopping" → "act now." Naming the RIGHT inflection point for the kid's subject = sounds like an educator who knows the terrain.

**SECTION 3 — Transition to qualifier + school fork:**
- Grade level usually surfaces when they say what's going on; follow with "What school do you guys go to currently?" — natural, no record-scratch.
- *Charter we serve:* "That's amazing — we have lots of students at your school and we've heard great things about it. How long have you guys been at [charter]?" (social proof + warmth + tenure discovery in one. Tenure matters: charter enrollment is long — a kid can be at iLEAD 4th–12th. Early-arc family = potential MULTI-YEAR client, not one package.)
- *Private pay:* serve ALL schools; only distinction is whether we cover their AREA (for in-person). LAUSD = main private-pay + test-prep district.
- **LAUSD gifted / magnet angle:** OLSAT itself is NOT a tutoring product — it's the 2nd-grade gateway that identifies gifted kids. The real test-prep money is ENTRANCE PREP for the magnet/highly-gifted programs those kids apply to: **Walter Reed IHP, Science Academy, Armstrong math** (majority gifted, OLSAT-identified). A+ has a webpage for these. OLSAT = context Paola references to sound knowledgeable, not the service. Anxious high-investment parents = premium test-prep customers.
- **TEST-PREP gets the MOST coaching [LOCKED]:** highest stakes, most objection-clearing, most technique-dependent, likely best private-pay margin. Call agent weights test-prep heavily in coaching rollup.

**STRUGGLING-STUDENT CALL specifics (Roman, distinct from IHP):**
- **Diagnose the CAUSE of low grades immediately:** if a grade is low, ask right away — is it low TEST SCORES, MISSING ASSIGNMENTS, or a COMBINATION? Pinpointing the cause early shapes everything (a missing-work kid ≠ a doesn't-understand-the-material kid).
- **Tutor credibility framing:** "Our tutors are experienced educators who LIKE working with kids, have a track record getting results, and are good at it / enjoy teaching." (Warmth + competence, not credentials dump.)
- **Lesson notes as a CARE feature:** every session, parents get full lesson notes — including a couple of questions the PARENT can ask the child afterward to check retention / real understanding. Turns the parent into part of the loop, not a bystander.
- **The ROUND TABLE / no-sides frame (ties to core value CARE):** "There are no sides here — we're all stakeholders in [Name]'s well-being. The tutor, you, and us are around one table." This is the relational heart of the struggling-student call and a direct expression of A+'s CARE value.

**SECTION 4 — Present how A+ helps (it's our TEACHING PHILOSOPHY made concrete, not a feature pitch):**
- Lead with relationship: "The first thing our tutor does is earn your child's trust."
- "The material isn't rocket science — it's how it's DELIVERED that matters. We get to know what makes [name] click."
- Rigor calibrated for INDEPENDENCE: "We apply the right amount of rigor to teach [name] to work independently — the goal is accountability and confidence."
- **Signature method (HW-completion lessons):** start from the BACK of the problem set (hardest first). Student handles the first couple alone → tutor works the hard ones WITH them → student finishes the mid-level ones independently. Concrete proof of method = credibility.
- Presentation LOOPS BACK into discovery (homework probes); not linear.
- **Logistics explained during presentation (Roman's real language):**
  - *Curiosity bridge:* "Tell me a little bit more about what's going on" (keep pulling the thread even here).
  - *Matching:* "We match tutors based on what we learn from you and the tutor with the best skillset to fulfill it."
  - *Fit guarantee (defuses the #1 unspoken fear — getting stuck with a bad-fit tutor):* "No one teacher is perfect for every student, so if it's not a good fit, we'll gladly provide another tutor."
  - *First lesson:* "The tutor informally assesses [name]'s skills, gets to know them, and establishes trust."
  - *Materials ask:* "If you have anything to share — past scores, current assignments, anything — email it to our admin account; we always appreciate it." (Feeds the tutor AND closes part of the assessment-data gap.)

**SECTION 5 — Online vs in-person + scarcity [LOCKED technique]:**
- Online-vs-in-person is THE objection battleground. When a parent insists on in-person, that's where most objection-clearing happens.
- **Scarcity play:** ask where they live. Even if in our area, say in-person availability is LIMITED — most in-person tutors work with very young kids. If they insist: "we understand and we'll do our absolute best to staff it." But STEER toward online. Honest (real constraint) and strategic (online = scalable, better leverage, wider tutor pool, no commute).
- Free trial was created largely to overcome the ONLINE hesitation (let them feel it works).

**SECTION 6 — Money / close branches:**
- **Branch-specific objection map:** Charter = if they're calling, they already KNOW they need it; low objection load; main risk is vendor competition for units → free-trial tiebreaker; don't over-sell a sold buyer. Private = PRICING is the #1 obstacle. Online-vs-in-person = the battleground.
- **Money branches:** (a) parent asks price mid-call → "let me email you the graphic, we'll go over it together" (never read aloud); (b) clearly ready → straight to enrollment / Get Started link; (c) interested but hesitant/objecting → surface the objection, THEN the free-lesson close; (d) noncommittal "send me info" → pricing graphic emailed + agent follow-up cadence.
- **FREE TRIAL = earned closing tool, NOT an opener.** Surface objections FIRST, then: "I'm a firm believer in what we do and that we can help your child. To put our money where our mouth is, I'll give you a free lesson. If you don't like it, I understand. If you do, we hope to earn your business." Unprompted = desperation; after a stated objection = confidence.
  - Private-pay: trial overcomes hesitation/doubt (esp. the online objection).
  - Charter: trial is the TIEBREAKER vs another vendor competing for the same units ("we have another subscription somewhere" → "just give us a try then").
- **Charter close:** joint TOR email at the close (still the non-negotiable charter move) → pricing graphic emailed → narrate PO timeline.
- **Free-trial pipeline EXISTS but is 100% manual** — Paola pings post-lesson to convert to a "gold deal." Big agent opportunity (offered→scheduled→delivered→won/lost is invisible like PO purgatory).

**Diagnostic play [UPDATED]:** PDF sent live on the call; take-by + upload-by dates locked; **results call booked BEFORE the test is taken** via the booking link IN THE INSTRUCTIONS (not just the post-scoring auto-invite). Sequencing fix: booking-before-completion creates the deadline that drives completion + a soft commitment that prevents ghosting; Paola nudges the booking live on the call/in the thread. Post-scoring invite stays as confirmation (belt + suspenders). Results-call booking link: https://meetings.wetutorathome.com/meetings/roman27/test-score-review (book ~5–7 days out so Kath has graded by then). Results call = the second close. SAT practice self-scores via College Board; everything else uploaded via A+ form, Kath grades.

**SCORING [pending rescore against the rewritten play]:** Remove the old hard "funding-before-pitch" non-negotiable. Proposed new non-negotiables: discovery depth (got to the bottom of the child's situation), used the kid's name EARLY + often, asked "what school" (the silent qualifier), captured TOR on charter calls, **pricing shown visually NEVER read aloud [SCORED FAIL if numbers spoken]**, free trial offered only AFTER an objection surfaced, **ended with a DATED next step locked live [SCORED FAIL if call ends on "we'll email you" / "we'll go from there" with no date]**. Coached behaviors + the single-lowest-category weekly coaching model carry over.

**REAL CALL LEARNING — Conor Dougherty / IHP / Jun 16 (Roman's own call, scored ~15/20):**
- STRENGTHS (the model to teach): elite curiosity (let parent talk through Beast Academy / tears / "teaching her to struggle"), credibility flex in context ("9 years at Walter Reed"), real-data fluency (GATE/OLSAT/CAST/cohorting), stakes done right ("humbling experience for all the gifted kids in 6th"), clean diagnostic setup (4th+5th math + writing, "devil hides in the details, show your work").
- LEAK #1 (biggest, SYSTEM-LEVEL not a Paola miss): NO DATED next step locked — in the CALL or the EMAIL thread. Email follow-up was actually FAST and strong (Paola sent diagnostics within the hour, answered 2 follow-up questions same afternoon; Conor engaged 3x). BUT across 5 emails, the results call was never booked and no return-by date set — when Conor asked about a time limit, the answer was "no strict time limit, complete in one sitting." Completion driver (deadline + scheduled reveal) is missing. Fix once at the system level (call script + email template + agent), not as a rep critique.
- LEAK #2: prices READ ALOUD ("73 on a large package... 95 hourly") — violates the never-read-aloud rule even though a graphic was promised. Confirmed by Roman.
- LEAK #3 (minor): kid's name ("Cali") not captured until 4:31, used sparingly after.
- TAKEAWAY: a 9/10 consultation + fast email follow-through, but the CLOSE (call + email both) never sets a deadline or books the results call. The diagnostic template literally says "no time limit" — which removes urgency for a hot lead. FIX: (1) call script locks take-by/upload-by + books results call live; (2) the diagnostic email template should include a soft deadline + a results-call booking link, not "no time limit"; (3) agent chases in days. This is exactly what the eval agent auto-flags. NOTE: Paola's speed was genuinely good — the gap is structural (no dated next step anywhere), not effort.

**Agents here:**
- [BUILDING] **Call evaluation agent** — daily GitHub Actions job: pull call engagements from HubSpot (JustCall native integration logs them), fetch transcript, Claude CLASSIFIES call type → scores vs SOP → scorecard to #call-coaching Slack [LOCKED single channel] → auto-fills properties (qualified_score, most_recent_call_sentiment, why_did_they_not_commit_now_, lead status, transcripts, quoted_price_per_hour) + extracts checklist fields. CRM fills itself from the conversation. Becomes the disposition system the Stage-2 workflow needs.
- [SPEC'D] **Friday coaching rollup** — weekly aggregate: top objections, weakest stage, win/loss patterns; test-prep weighted.
- [SPEC'D] **Free-trial conversion tracker (agent 5b)** — track offered→scheduled→delivered→outcome, remind Paola/tutor, post-lesson follow-up sequence, flag won/lost. New invisible pipeline.
- [PLANNED] **School/program cheat-sheet** — surface vendor status, student count, PO cap, magnet-program talking points the moment Paola types the school name. Roman's expertise available to whoever's on the phone; makes "we've heard great things" specific.
- [SPEC'D — HIGH VALUE] **Promise-keeping agent (commitment fulfillment)** — Roman's ask: "an agent that listened to everything we promised to send or do, and does it." Rides on the call-eval agent's transcript read. Extracts every commitment made on the call ("send diagnostics," "send pricing graphic," "book results call," "email TOR"), checks each against what actually happened, then fulfills or flags. STAGED: Phase 1 = detect + post "promises made" checklist to Slack/contact (pure detection, easy, catches every dropped ball — would have caught Conor's unbooked results call). Phase 2 = draft the standard fulfillments (diagnostic email WITH grade-correct PDFs auto-attached, pricing graphic, booking nudge) for one-click approval. **Grade-specific file attachment is deterministic/low-risk** — agent reads student grade (from transcript/HubSpot) → maps to the right diagnostic PDFs + writing prompt via a grade→files table → attaches. No judgment, just lookup. PREREQ: (1) PDF library ALREADY EXISTS in a HubSpot Files folder — agent reaches it via HubSpot Files API by file ID (stays in-system since the agent already sends the email from HubSpot). CHECK naming is machine-readable (e.g. Math_Diagnostic_Grade_6.pdf, not 'diagnostic final v3.pdf') — a quick rename pass if not. (2) grade→file-ID mapping table (e.g. IHP 6th = grade 5+6 math; Science Academy by applicant grade 6–12). This table is institutional knowledge in Roman's/Paola's heads — write it down; it's the only real missing piece. Phase 3 = trusted promise-types fire auto, novel ones flag. Promises are patterned (~5-6 recurring types), which makes the action library small. This is the natural endgame of the eval agent + a small action set; same rails (transcript access, HubSpot writes).
- Danielle's partner calls (virtual/Zoom) = later build [LOCKED deferral].
**Requirements [CONFIRMED]:** JustCall = **Pro Monthly** plan + **API key in hand** (Roman confirmed Jun 16). Pro includes unlimited AI transcription (already running — transcripts logging into HubSpot with a JustCall AI Transcription link on each call record) + HubSpot integration + API access. DO NOT buy AI Review Assist ($9/user) or Pro Plus — their generic scoring is inferior to our custom rubric; we only need the API to PULL transcripts. Agent fetches transcript by JustCall `sid` (found in hs_call_body) via API. HubSpot Private App needs engagement-read + notes-write scopes. JustCall API key → repo secrets. Coaching loop: scores → weekly review → ONE focused conversation w/ Paola on her lowest category. Paola must be told calls are scored (scorecards without coaching breed resentment).
**[OPEN]:** Roman's exact opener words (Section 1); who delivers weekly coaching (Mandy or Roman); typical PO processing days for the timeline script; logistics-explanation depth before money; post-trial conversion ownership.

## CHARTER BASELINE-DATA CAPTURE [Roman — the real charter gap, not the consultation]

**The insight: charter CONSULTATIONS are easy (warm TOR referral, low objection, Paola converts them start-to-finish). The actual gap is DATA CAPTURE during onboarding — we don't systematically grab the kid's PRIOR scores, so later we can't build a before/after Student Spotlight (no baseline = no "from X to Y" story). This starves the Stage 8 proof engine at the front of the funnel.**

- **Data points to capture (families have them, worst case by summer):** iReady, CAASPP, MAP scores, in-class grade. Any/all.
- **Why it matters (the flywheel):** baseline → deliver results → before/after Spotlight → Yelp/Google reviews + TOR proof ("look what we did for your students") → more research-driven private-pay families AND more charter/TOR referrals. Charter is the easiest, highest-volume, sibling-multiplying segment, so systematic baselines here = a stockpile of proof stories from our best segment by spring.
- **FERPA REALITY [Roman]:** schools/TORs will talk about the scores but often won't hand them over, citing FERPA. FERPA is a wall between the SCHOOL and us — NOT between the PARENT and us. The parent has an absolute right to their own child's records and can share them freely. So the PARENT must be the primary source, not the TOR. (NOTE: Conor was PRIVATE-PAY/LAUSD, not charter — he read his own kid's scores off the LAUSD parent portal. That proves a PARENT can pull their own data, but does NOT confirm charter-homeschool families have the same portal/scores — see open question below.)
- **CORRECTED SOURCE CASCADE (FERPA-aware):**
  1. *PARENT (PRIMARY):* the parent has the right to their own child's records and can share freely (no FERPA issue). HOW they access depends on the charter — see OPEN QUESTION. Ask: "Can you send us [Name]'s latest iReady/MAP/CAASPP scores or report card?" Folded into the existing "email materials to admin" ask, made specific + required.
  - ⚠️ **OPEN QUESTION [Roman to answer]:** do charter HOMESCHOOL families have a score portal like traditional-public parents do? A charter homeschooler (parent-chosen curriculum) may not have taken iReady/MAP/CAASPP at all, or the scores may live with the charter/TOR rather than a parent portal. This determines whether "parent pulls their own scores" even works for the charter segment, or whether the tutor-first-session floor becomes the DE FACTO primary for charter.
  2. *TOR as ENCOURAGER not conduit:* the TOR's role is to TELL the family it's helpful to share their scores — advocate for the data flow without BEING the data flow (sidesteps the FERPA awkwardness of teacher-sends-records). Clean, and still leverages the relationship.
  3. *Tutor at first session (GUARANTEED FLOOR):* informal first-session assessment IS the documented "before" if the parent doesn't come through. Softer, but never zero baseline.
- **FERPA bottom line:** parent-pulls-own-portal-data sidesteps the entire FERPA conversation. TOR encourages, never transmits.
- **ENFORCEMENT = the watering [BUILD SPEC'D — schema-as-code]:** make baseline a REQUIRED FIELD to advance a charter deal **Pre-Lesson → Post-Lesson**, on all 3 charter pipelines (907748 traditional, 72281989 Terri iLead, 88841552 Amy iLead — now standardized to Pre-Lesson→Post-Lesson→Invoice Submitted→Stopped). Tutor session-1 assessment happens in Pre-Lesson = the guaranteed floor before the gate, so no conflict. BUILT: `hubspot-schema/` module (baseline_properties.json = 4 props [source/subject/score-level/date] as version-controlled schema; create_properties.py = idempotent creator via Properties API; SETUP.md = full spec). Properties created by CODE (Private App, needs crm.schemas.deals.write); the STAGE GATE is UI-only (HubSpot has no API for stage-required properties) — set Post-Lesson required props on each pipeline by hand. Decision: HubSpot-config-as-code, `hubspot-schema/` is the new home for CRM config. [LATER: parallel outcome_* props for the 'after' at CC3/75d; baseline-request agent to auto-ask + flag.]
- **Connects to:** Stage 8 Spotlight pipeline (the consumer), the CARE calls (CC3 at 75 days could capture updated scores = the "after"), the TOR relationship (proof drives referrals).

## CHARTER CALL — full mechanics & psychology (Roman)

**Charter is a DIFFERENT BEAST: not the parent's money (school instructional funds), a TOR/EF gatekeeps the spend, units expire, and the emotional core is homeschool-parent burnout — not the private-pay "panic" or test-prep "aspiration."**

### The money mechanics
- **Funds:** parents get instructional funds annually — sometimes one drop, sometimes per-semester, sometimes multiple drops/year. School-specific. (iLEAD example, verified: ~$1,200/yr = $600/semester for materials + services; "allocated for student use but still school funds" — which is why the TOR gatekeeps.) [Fund-drop timing is datable per charter — cross-reference each school; useful for timing outreach.]
- **PO process (all schools similar, details differ):** parent OR teacher creates the purchase order in their portal → **teacher (TOR/EF) approves** → order comes to us via email to **charter@wetutorathome.com** → we create the deal → goes to scheduling team.
- **Pricing [CURRENT, updated]:** 45-min session @ **$60** (was 45-min @ $56.25 or hourly @ $75 last year; moved to $60/45-min for better margin + easier numbers). 
- **PO size varies wildly by school:** some have NO cap on PO size. Real example: a family with a **$1,500 PO for 20 hours.** KEY MOVE: we can **stretch the hours into more sessions** — "20 hours" actually becomes 24–25+ sessions (45-min sessions, not full hours). And 3×/wk @ 45min = 2.25 hr/wk > 2×/wk hourly = 2.0 hr/wk — MORE weekly time, not less.
- **FRAME IT AS MORE SESSIONS — and it's RESEARCH-BACKED, not just margin [verified studies]:** frequency beats duration. Present "more sessions" as the pedagogically superior choice:
  - A review of ~200 rigorous studies: high-dosage tutoring (3+ sessions/week) is one of the few school interventions with large positive effects on math AND reading. (EdResearch for Action; NSSA/Stanford)
  - One meta-analysis: high-dosage tutoring was **~20x more effective than low-dosage in math, ~15x in reading.** (EdResearch for Action)
  - Effective sessions are **~30–60 min** — so 45 min is squarely in the sweet spot, NOT a compromise. (EdResearch for Recovery)
  - "Students who met more often over a shorter period had stronger learning gains than students who met occasionally over a longer period" — same content, frequency wins. (Catapult Learning)
  - WHY: concepts stay fresh between sessions, small gains compound instead of resetting, and seeing the same tutor more often builds the trust/relationship that drives improvement. (Catapult; NSSA)
  - Elementary kids especially benefit from "shorter but more frequent" sessions. (EdResearch for Recovery)
  - **THE CONCRETE NUMBER that makes it tangible [Roman]:** 3×/week at 45 min = **2.25 hours/week** vs 2×/week hourly = **2.0 hours/week.** So the family gets MORE total instructional time per week AND more frequency (3 touchpoints vs 2) — strictly better on every axis, no tradeoff. Use this exact comparison on the call.
  - **The pitch:** "We run 45-minute sessions on purpose — the research is clear that frequency beats length. Three 45-minute sessions a week is actually 2.25 hours versus 2 hours from two hourly sessions — so [Name] gets more total time, more often, which keeps it fresh, compounds the gains, and builds the tutor relationship. Your funds go further AND it's the more effective way to learn." Margin AND pedagogy aligned. Ties to A+'s NSSA Program Design Badge + high-dosage proof points.
- **USE IT OR LOSE IT:** funds MUST be used by year-end or **we have to return the money.** This is the core urgency lever — unspent units vanish.

### The TOR/EF relationship (our secret weapon)
- **TORs refer us:** "a lot of the time our teachers of record tell families to reach out to us because we have a good relationship with these teachers." The TOR referral is a warm, trusted hand-off — these are NOT cold leads.
- **HubSpot:** we ASSOCIATE both the teacher AND the parent to the deal → accurate portrayal of our kick-ass teacher referrals (track which TORs drive business).
- **TOR enters at the END of the consult:** we don't loop them in mid-call. At the end, we ask the family for the **teacher of record's name + email**, put it in the customer profile in HubSpot, and mark the **"charter school family" property = Yes.** (TOR name/email captured → enables the joint email + referral tracking.)

### The psychology — DIFFERENT from private/test-prep [THE HEART]
- Charter families are **homeschooling** — the onus falls on the PARENT and other family members to teach. That's exhausting.
- The real pain: **"You're tired of doing this shit and not getting the results you want."** The kid is likely disengaged or a little behind (why else would the TOR recommend a tutor, or why else are you considering one?).
- So discovery is about surfacing **homeschool-parent burnout + kid's disengagement (PLUS must-probe: what curriculum? behind on assignments? ideal scope/goal + where the challenges are)**, not academic panic. The parent is carrying the teaching load and it's not working — we lift that weight.
- **CHARTER-SPECIFIC discovery (must-probe, Roman):**
  - **What CURRICULUM are they using?** Charter homeschoolers FREELY SELECT their curriculum — never assume. We need to know which program to tutor effectively and align with the TOR's learning plan. (Different families = totally different materials.)
  - **Are they BEHIND on assignments?** Surfaces both the academic reality and part of the burnout (falling behind = pressure on the parent).
  - **Identify the IDEAL scope of work / a GOAL:** probe to land on what they'd most want us to do with the child — or at minimum a goal and where the specific challenges are. Don't leave the call without a target the tutoring aims at.
- **Objection load is LOW** (they already know they need it — TOR recommended it or they sought it out). The real competition is **other vendors fighting for the same units**, not convincing them tutoring is worth it. Don't over-sell a sold buyer; win the units before another vendor does (free-trial = tiebreaker).
- **SIBLING UPSELL [Roman] — charter families almost ALWAYS have siblings.** Homeschooling families tend to have multiple kids, each with their OWN instructional funds. Once you've won trust with one child, the natural expansion is the sibling(s) — more funds, more sessions, same trusted relationship. Probe for siblings on the call and plant the seed; each sibling is a separate PO/deal. This is a core charter LTV lever (parallels private-pay's multi-sibling pattern, but here EACH kid has their own funded units).

### What winning looks like (the sequence)
1. Consult the family, surface the burnout pain, present how we help.
2. END: capture TOR name + email, mark charter-family = Yes in HubSpot.
3. Parent/teacher creates PO in portal → TOR approves → PO emailed to charter@wetutorathome.com.
4. We create the deal → scheduling team → first session.
- **The stall = "PO purgatory":** the gap between family's "yes" and the PO actually arriving (no status, no clock today). [Existing flagged gap — "Committed–Awaiting PO" status + chase agent.]

## STRATEGIC PLAYS — insider knowledge that builds trust (Roman)

**These are expertise-as-trust-builder: most parents don't know them, and Paola dropping them mid-call signals A+ genuinely knows the landscape. Pure consultation ammunition.**

### Play 1 — Harvard-Westlake 7th-grade entry
H-W has a middle school. Applying for **7th-grade entry is less competitive than the 9th-grade door**. If a family wants H-W, get in at 7th. (H-W still needs very high marks — be cautious with tiger/helicopter parents; don't promise the outcome.)

### Play 2 — LAUSD magnet LOTTERY POINTS game (entrance-exam-free magnets)
Separate from the exam-based programs (IHP/Science Academy/Armstrong). Many LAUSD magnets admit by a **points + lottery** system, NO test. The play is to engineer points over time to win a competitive magnet later. Verified mechanics (LAUSD CHOICES/eChoices, 2026):
- **Waitlist points:** if not selected, the student gets **4 points/year** toward future cycles, up to **12** (waitlist points expire after 3 years). Families often start ~3 years before target matriculation (3rd grade for a 6th-grade magnet; 6th grade for a 9th-grade magnet).
- **Other points:** PHBAO home-school (4), overcrowded home-school (4), sibling (3), matriculation from a magnet elementary/middle (12, one year only). Max possible 23; ~19 typical without overcrowded; 12 is the competitive sweet spot for most magnets.
- **The strategic application:** cross-reference each magnet's openings vs. prior-year applications (published on eChoices) to find **high-waitlist-likelihood schools**, and apply to bank points. Points only attach to your **1st choice**; 2nd/3rd choices go to the bottom of those waitlists.
- **Example target magnets (Roman's list):** Community Magnet (Bel Air), Wonderland gifted, Balboa gifted, Sherman Oaks CES, Los Angeles CES (LACES).
- **THE "FIRST YEAR IS A WASH" LOGIC [Roman, CONFIRMED by official LAUSD docs]:** the first application year has no real downside IF you'd genuinely accept a seat. Get in → you forfeit nothing (you wanted a seat). Don't get in → waitlisted for 1st choice, bank 4 points for next year. The risk only triggers on DECLINING an offer.
- ⚠️ **CRITICAL RISK #1 — declining wipes points [VERBATIM from choices.lausd.net/magnet]:** "If an applicant on a waiting list declines magnet placement, ALL waiting list points are removed." Waitlist offers can come "through the first four weeks of school" — so even an August offer, if declined, zeroes the points. Rule: only apply to schools you'd actually attend.
- ⚠️ **CRITICAL RISK #2 — current-magnet kids get auto-dropped [VERBATIM]:** "Applicants currently enrolled in a magnet program who apply and are selected for another magnet program will automatically be dropped from their current magnet, whether they accept or decline." A happily-enrolled magnet kid who point-farms elsewhere can be yanked from their current school. (That's what MATRICULATION points are for — don't re-apply to stay.)
- **Other verified rules:** max 12 waitlist points (3 consecutive years); applying to the same grade twice forfeits the prior year's points; points only attach to 1st choice (2nd/3rd go to bottom of those waitlists); late applications get NO points. SOURCE: https://choices.lausd.net/magnet (official LAUSD CHOICES, 2026-27).
- **NUANCE on Roman's school list:** some named span schools — **Los Angeles CES, Science Academy, Sherman Oaks CES, Lake Balboa** — do NOT assign matriculation points (multi-level span schools). So they behave differently in a multi-year plan than a standard magnet elementary that graduates kids with 12 matriculation points. Worth knowing when mapping a family's strategy.
- ⚠️ **Gifted-magnet rejection risk:** if you apply ONLY to a gifted magnet and the teacher doesn't verify the child as qualified, the whole application is rejected and NO waitlist points are given. (Some families use a non-gifted K-12 magnet as a backstop to still bank points.)
- **A+'s role [DECIDED — Roman]: CREDIBILITY ONLY, not a service.** Paola references this knowledge to demonstrate A+ knows LAUSD inside-out — builds trust, differentiates, opens the tutoring conversation. We do NOT offer points-strategy consulting as a service line (no staffing/delivery/liability for managing families' multi-year application strategies). It's ammunition, not an offering.

[OPEN — Roman to add more plays as they come up → this becomes a "Strategic Plays" reference card in the hub.]

## TEST-PREP — THREE SUB-MARKETS (Roman, researched Jun 2026)

**Bucket 1 — LAUSD magnet/gifted entrance (MOST business, every year; mostly incoming 6th graders):**
- **Science Academy STEM Magnet** (North Hollywood; grades 6–12, ranked #2 CA middle school): mandatory **MATH + SCIENCE** assessment. Gifted status does NOT exempt — everyone tests. Passing → enters a LOTTERY (be honest: we prep them to pass, lottery is out of anyone's hands). Open to any student in LAUSD boundaries incl. private/non-LAUSD. Occasionally a 7–12 jump applicant, but mostly incoming 6th. → we send **math assessment** (+ science is prereq-dependent; math underlies the science — can't balance a chemical equation while shaky on fractions).
- **Walter Reed IHP** (North Hollywood; oldest LAUSD highly-gifted program, founded 1970/71): mandatory **MATH + WRITING** assessment, taken AT Walter Reed (e.g., Jan 17 2026). Applied via LAUSD CHOICES/eChoices (SAS/IHP tab). Eligibility letter to parent portal ~mid-Feb. Highly gifted, ~2–3 grade levels above peers; math is whole-class Algebra I/Geometry/Algebra II. Roman taught here 9 years = core credibility. → we send **math + writing prompt**.
- **Armstrong Middle School math program**: math entrance assessment. → we send **math assessment**.
- **Feeder pattern:** neighborhood public elementaries — Wonderland, Colfax, Carpenter, others. Parents tour the school, hear about the test, get freaked out, find our webpage on these programs, see we're local + Roman taught at Reed.

**Bucket 2 — Private high school entrance (incoming 9th, abundant private HS near us):**
- **HSPT** (Catholic schools): one test, taken once in **8th grade** for 9th-grade admission. Schools: **Notre Dame, Providence**. (Speed/grammar/vocab heavy, fast-paced.)
- **ISEE** (non-Catholic private): levels by entry grade — **Middle Level = entering 7–8, Upper Level = entering 9–11**. Schools: **Campbell Hall, Harvard-Westlake, Milken**, others. We send ISEE practice tests by level/grade.
- **Chaminade**: has its OWN entrance exam (not HSPT/ISEE).
- → send the practice test matched to the school's exam + the student's entry grade.

**Bucket 2 — DEEPER CONTEXT (Roman):**
- **Same families, matured:** private-HS applicants are often the SAME kids/families who applied to (or considered) the middle-school magnet programs. The driver: LAUSD has FEW quality high school options for the non-super-gifted kid. After middle school, middle-class families look to JUMP to private. So Bucket 1 (magnet 6th) and Bucket 2 (private HS 9th) are often the same household at two life stages — a retention/re-engagement opportunity, not two separate populations.
- **The Harvard-Westlake calculated play (insider tactic to coach):** H-W has a MIDDLE school. Applying for **7th-grade entry** is LESS competitive than applying for 9th-grade entry (far more pressure on the 9th-grade door). If a family wants H-W, the smart play is to get in at 7th. This is exactly the kind of insider knowledge that makes Paola/A+ look like experts and builds trust — most parents don't know it.
- **Implication:** a family in the magnet-6th conversation who's eyeing private long-term might be advised to set up the 7th-grade private jump rather than wait for the brutal 9th-grade funnel. Cross-sell / long-game.

**Bucket 3 — SAT / ACT (kids in 10th–11th):** [STRATEGIC TAILWIND — Roman: "SAT was down post-COVID, schools are making it sexy again, we're down to make money with it"]
- **The test-optional reversal is real and accelerating (verified Jun 2026):** post-COVID test-optional is unwinding fast. For the 2025-26 cycle (fall 2026 admission), most of the Ivy League + Stanford, Georgetown, MIT, Caltech, UPenn, Brown, Cornell, U Miami have reinstated SAT/ACT requirements; Georgia & Florida public university systems mandate scores; Princeton returns ~2026-27. Columbia is the notable permanent-test-optional holdout. Schools publicly argue scores predict college success — so the institutions themselves are re-creating demand. This is a GROWING market, not a seasonal one → worth building the SAT pipeline now (pairs with: existing-family conversion never tried + re-engagement agent).
- Same motion: practice test → review call → tutoring. 
- **Conversion note [CORRECTED]:** existing families seem hard to convert to SAT — BUT Roman confirms we've never actually TRIED. So it's an UNTAPPED opportunity, not a real ceiling. (Pairs with the re-engagement agent: our middle-school families age into SAT years — nobody reaches out.) [ACTION: test converting existing families to SAT before assuming they won't.]
- **How SAT/ACT families typically find us (the funnel):** schools (esp. private) administer tests in person via 3rd-party providers + group programs. Parents start there. When the group does nothing / score doesn't move / Princeton Review disappoints → THEY come to us for **online 1-on-1**. So we're often the "it actually worked this time" upgrade after a group program failed. Position accordingly: 1-on-1, online, targeted from a real diagnostic — the opposite of a group mill.
- These families typically buy a **20-hour package from the get-go** (good initial deal size). They often **start in group programs elsewhere** and come to us when those don't move the score.
- **Test-prep tutoring plan (all buckets):** the plan we build is **2–3 sessions/week, 1 hour each** (≈8–12 hr/mo, so a 20-hr package ≈ a 2-month prep runway — lines up with families calling ~2 months out). Private pay = full-hour sessions.
- **SAT-vs-ACT METHODOLOGY [Roman — a real differentiator, currently INVISIBLE to customers]:** Roman personally meets with SAT/ACT families. Philosophy: "measure twice, cut once." Process: have the student take BOTH the SAT and the ACT up front → cross-reference the **concordance tables** → make projections, including how they'd do on their **lowest-performing section** compared across both tests → rule in the test the kid will do better on FROM THE START. Most families don't know A+ does this. **OPPORTUNITY:** surface it — it's expert, rigorous, and trust-building; it's the SAT/ACT equivalent of the free diagnostic, just deeper. Should be named explicitly in the SAT/ACT call and in marketing.

- **Private HS realistic-expectations [Roman]:** **Harvard-Westlake requires really high marks** — so with the **tiger/helicopter parents** from that world, be CAUTIOUS. Set honest expectations hard (cf. anti-ICP); H-W is a genuine reach that not every kid will clear. Don't get talked into promising the H-W outcome. (The 7th-grade-entry play helps, but the bar is still high.)

**[RESEARCH FLAGS to verify with Roman]:** ISEE standard bands are Lower=5–6, Middle=7–8, Upper=9–12 (Roman said Upper for 9–11 — aligned). Confirm Armstrong's exact test format. Confirm which specific private schools map to HSPT vs ISEE in your actual book of business (researched defaults: Notre Dame/Providence=HSPT; Campbell Hall/Harvard-Westlake/Milken=ISEE; Chaminade=own exam).

## TEST-PREP ICP [Roman] — distinct from private-pay; aspiration not problem

**Core difference: private-pay = a PROBLEM (something's wrong, parent panics, we fix). Test-prep = an ASPIRATION (nothing's wrong, kid often gifted/high-performing, parent reaching for something better). Flips everything: no pain to surface, urgency from a fixed external DATE not a bad report card, parent's state is ambition + competitive anxiety not rescue.**

- **The free diagnostic is the spine of the whole motion:** we ALWAYS give a free diagnostic and promise to tell them HONESTLY what's realistic. It qualifies the family in or out and resets expectations BEFORE we take money. Refusing the diagnostic = the reddest flag.
- **Bullseye:** high-performing / gifted-identified kid, no academic adversity, aiming at a dated competitive gate (IHP / Science Academy / Armstrong / SAT). Realistic, research-driven, self-aware parent (cf. Conor: "am I kidding myself on this IHP?" — that self-awareness = ideal). Lower price sensitivity than problem-driven private pay (chasing a competitive gifted program).
- **ANTI-ICP = the "diagnostic denier" / fantasy parent:** so attached to a fantasy of where their kid is that they REFUSE the diagnostic or cherry-pick it. Two real patterns:
  1. *Cherry-picker:* "my kid knows all the math, just prep the science" for Science Academy — when math is PREREQUISITE to the science (can't balance a chemical equation while struggling with fractions). Insists on skipping the foundation the test actually rests on.
  2. *Impossible delta:* real example — Beata Kharkovsky (contact id 35451): kid took SAT 3×, never above 600 verbal, wants 730+ on a 4th attempt in 2 months. The gap + timeline is not realistic; parent won't hear it.
  - These are CHALLENGING but not always disqualifying — the free diagnostic + honest realism talk is the gate. If they accept the honest read, possibly workable; if they insist on the fantasy and skip/deny the diagnostic, qualify out (set up to fail + blame us).
- **LTV shape:** can be SEASONAL/finite (intense run to a test date, then done) UNLESS converted to ongoing enrichment after. Conversion-to-retained is the key LTV question for test prep (vs private-pay which is durable/multi-sibling by nature).
- [OPEN] do test-prep families convert to ongoing tutoring after the date, or mostly one-and-done? do we want the on-the-bubble kid (~88th %ile push) as well as the gifted kid, or is one much better business?

## PRIVATE-PAY ICP [BUILDING — Roman]

**Anchor insight: the ICP is defined by PERSISTENCE OF NEED, not income or subject.**

- **Early elementary (K–4) = real but FRAGILE.** A single teacher owns the whole year, so the kid's trajectory swings on that one variable. Pattern: we stabilize the kid in 2nd grade → strong new teacher in 3rd → parent feels "we're good" → churn. Or fine in 3rd → new teacher in 4th → things change. Engagement is short, choppy, at the mercy of one teacher resetting every August. Acquire early if we can, but expect volatility.
- **Middle school = the IDEAL.** Multiple teachers, multiple subjects, multiple expectations simultaneously → the need becomes STRUCTURAL and PERSISTENT, not tied to one classroom. No single teacher's arrival "fixes it." Durable complexity = durable need = the long-term client.
- **Implication:** target/qualify for persistence of need. The best private-pay client isn't the highest payer — it's the one whose need doesn't evaporate when one teacher changes. Middle-school multi-subject support is the retention sweet spot.
- **ANTI-ICP [Roman] — the "11th-hour rescuer" / blame-shifter:** the parent who shows up at the LAST MINUTE (≈3 weeks before semester end) with CRAZY-HIGH expectations after having already put the kid through the ringer (sat with them, tried many avenues, exhausted themselves) — and ASSIGNS BLAME to the tutor when miracle results don't materialize. The compounding pattern: (1) late arrival → no runway, (2) prior failed attempts → kid is fried & resistant, (3) compressed timeline → impossible bar, (4) externalized blame → tutor becomes the scapegoat. A pain to deal with and structurally set up to fail.
  - **Detectable on the call:** "semester ends in 3 weeks," "we've tried everything," "I need their grade up from a D to an A by finals" = the warning cluster. Paola should set realistic expectations HARD up front or politely qualify out — taking this client damages tutor morale and generates a bad review even when the work is good.
  - Note the contrast with the GOOD engaged parent (Conor): involved EARLY, realistic, treats it as developmental. The anti-ICP is involved LATE with a rescue fantasy. Timing + expectations separate them, not involvement level.
- **THE SHARP ICP [Roman] — the "coaster hitting the wall":** the kid who had NO academic adversity until now. Coasted through LAUSD elementary on 3s (the soft middle of the 1–4 scale), got by, never learned to struggle. Then middle school hits and TWO things change at once:
  1. **Work gets genuinely harder** (the math/abstraction inflection point).
  2. **Grading flips from forgiving 1–4 → brutal A–F.** LAUSD elementary 1–4 is soft & sticky — teachers rarely give 2s without heavy documentation, CASPP-aligned "above/at/below grade level" smooths everything, so a coaster's cracks stay HIDDEN. Middle-school A–F is subjective, unforgiving, and suddenly VISIBLE — the comfortable "3 kid" gets their first C/D.
  - **Why this is the ideal:** the parent PANICS (this has never happened before, no playbook) → motivated + scared, BUT arriving at the START of a real problem, not 3 weeks before finals (the opposite of the anti-ICP). Fresh, structural, persistent need. First real adversity = the entry point, and the "learning to struggle" work (cf. Conor) becomes the value.
  - Coaching cue: when Paola hears "she's always done fine and suddenly she's struggling" + middle school + first-ever low grade → that's the bullseye private-pay client.
- **Price handled STRUCTURALLY, not by discounting [Roman]:** hourly ($95) is priced HIGH on purpose so nobody picks it — it funnels everyone into packages. The 8-hour package (~$680) = about a month of tutoring at 2×/week, 1 hour each. Packages make the per-hour rate drop and frame the commitment as "a month of support" rather than "a scary hourly number." The package ladder IS the price-objection answer.
- **Private pay = FULL HOUR sessions** (contrast: charter = 45-min sessions, done to stretch the $500 PO efficiently). Private pay isn't constrained by a PO cap, so full hours; the structure difference is deliberate, not arbitrary.
- **LTV & expansion [Roman]:** the best private engagements last MULTIPLE YEARS and span SIBLINGS — families even request the SAME TUTOR back for a younger sibling. Loyalty attaches to the tutor, not just the brand. Implication: a great tutor = a multi-family, multi-year annuity; tutor retention is directly an LTV lever (losing a beloved tutor can lose the families who'd have followed them across kids for years).
- **Best source [Roman]:** these come from families who DID THEIR HOMEWORK on us — researched our many Google/Yelp reviews, or were referred by a friend who used us. They are deliberate, research-driven selectors (NOT impulse/panic-only). Channel = Yelp + Google reviews + word-of-mouth referral. Implication: review volume/quality and referral mechanics are the marketing levers for the bullseye client; protect and feed the review engine.
- **ICP COMPLETE — see standalone artifact `private-pay-ICP.md`.**

## Stage 4 — Commitment → Activation
**What happens:** Private yes → deal same-call (Paola manual) or Get Started Now form (https://meetings.wetutorathome.com/get-started-now-full; in pricing email AND as a standalone page; auto-creates deals that SKIP the consultation — reporting must separate self-serve from consulted deals). Charter yes → TOR email → **PO purgatory** (invisible: no status, no owner, no clock; committed families indistinguishable from cold leads) → PO arrives → Kath creates deal.
**Decided:**
- [SPEC'D] New status **"Committed — Awaiting PO"**, set automatically by the call agent on detecting the joint TOR email/commitment. Bridges the lead-vs-deal gap (charter-only problem; private converts to deal instantly).
- [SPEC'D] PO chase cadence: day 5 no PO → TOR nudge (parent cc'd); day 10 → Paola task; family kept warm in parallel ("Marcus's spot is held, waiting on the school's paperwork").
- [SPEC'D] **Email triage agent Phase 2 (actuator #1):** PO email arrives → agent reads it → extracts student/charter/PO#/amount/term → matches the Awaiting-PO contact → creates the deal in the correct pipeline at Pre-Lesson → stamps dates (purgatory duration becomes measurable per charter) → Slack-pings schedulers (72-hr clock starts) → flips status. **Verify mode first month:** agent stages, Kath one-click approves; graduate to full auto. (Triage agent v2 already spec'd: HubSpot Conversations polling, Sonnet classification, Teachworks enrichment, routing rules locked, SLAs, audit log.)
- Diagnostic chase [UPGRADE — current workflow = 14-day silent timer then ONE text; too slow for hot leads]:
  - ROOT FIX is on the CALL: lock take-by + upload-by dates AND book the results call live before hangup (see Conor call learning below). The timer should rarely need to fire.
  - When it does fire: chase in DAYS not weeks — upload-by date passes → day 1 warm nudge (text+email referencing the kid by name), day 3 second touch, day 5 Paola personal task. NOT a 14-day wait.
  - Agent personalizes the nudge from the call transcript (knows it's Cali, knows it's IHP math) instead of a generic blast.
  - Plus a Kath grading SLA + ungraded-test alert (a family who DID the work then waits = worst leak). KATH GRADES IN 48 HOURS [CONFIRMED].
**[OPEN]:** ~~Kath's grading turnaround~~ = **48 HOURS [CONFIRMED]**; what a PO email looks like per charter (need samples for the extraction spec); the PO process from the school's side (TOR submits to vendor system? approval? portal?); typical PO turnaround days; volume + quality of Get Started self-serve deals vs consulted.

## Stage 5 — Match & first session
**What happens:** Deal at Pre-Lesson → schedulers (Janelle A–L, Yolanda M–Z) match tutor → first session. **KPI: 72 hours in Pre-Lesson [LOCKED].**
**Agents here:**
- [SPEC'D] **Pre-lesson watchdog** — deal exceeds 72h in Pre-Lesson → Slack escalation to scheduler + Mandy. Extends `aplus_weekly_sync`, run daily.
**[OPEN]:** how schedulers actually match (criteria? Teachworks?); how the family learns their tutor (intro email? from whom?); current median time-to-first-session; what happens when no tutor fits.

## Stage 6 — Early retention (days 1–30)
**What happens:** CARE calls — CC1 at 14 days (Paola), CC2 at 45, CC3 at 75. Emily leading a quarter-long retention project. Retention sync script designed (Teachworks → Sheets + Slack).
**Agents here:**
- [SPEC'D] **Early-warning agent** — Teachworks signals (first-session cancel, no session 2 scheduled, missed sessions) → flag BEFORE the family churns instead of after.
- [SPEC'D] CARE-call scheduling automation — CC1/CC2/CC3 tasks generated from the first-session date.
**[OPEN]:** week-1→week-4 survival rate (does anyone know it?); what CC1 actually covers (script? notes captured where?); who acts on an unhappy signal.

## Stage 7 — Renewal & growth
**What happens:** iLEAD monthly PO = every charter family renews every 30 days or silently churns. Private packages deplete (8–100 hrs).
**Agents here:**
- [SPEC'D] **PO renewal agent** — PO expiring / hours depleting, renewal not submitted → alert + TOR/parent nudge. Private: package hours low → renewal prompt to Paola (low package → Paola per triage routing).
- [OPEN] sibling/expansion prompts — families with multiple kids.
**[OPEN]:** current renewal rate; who owns renewal conversations today; does anyone track package depletion proactively.

## Stage 8 — Outcomes & proof
**What happens:** Schools administer assessments; A+ rarely receives post-tutoring results (the data gap). Student Spotlight pipeline [BUILDING] to close it (pseudonymized HubSpot drafts, comic-book asset feature in progress). Proof points: iEM LTEL 7/11 reclassified (63.6%); iLEAD AV Tier 3 81% improvement, 5.2x NWEA norms.
**Agents here:** Spotlight pipeline [BUILDING]; case study agent [EXISTS].
**[OPEN]:** systematic results-request motion (could CC3 at 75 days include a "share Marcus's latest scores" ask feeding Spotlight?).

## Stage 9 — Flywheel
**What happens:** TOR referrals = base business, currently organic/unsystematized. Win-backs: "Check Back Quarterly" + "Past Customer" statuses exist; chase unknown.
**Agents here:**
- [SPEC'D] **Check-back agent** — quarterly statuses get an actual quarterly re-engagement touch.
- [OPEN] referral-ask systematization — where the ask lives (post-first-session? CC2? Spotlight moment?).
- [SPEC'D — high value] **Test-prep re-engagement agent:** today, magnet-6th test-prep families just DISAPPEAR after the season. But they're predictable: a family prepped for a magnet in 6th is a strong candidate for private-HS prep at 7th (Harvard-Westlake middle-school play) or 9th. Agent flags these families on a timer (≈12–24 months post-magnet-season) for a "thinking about private high school?" touch. Same predictable-timing logic as PO renewal. Turns one-and-done test prep into a multi-year relationship. Pairs with the "strategic plays" knowledge (H-W 7th-grade entry, etc.).
- [OPEN] TOR relationship cadence (Paola's TOR call type) — play not yet written.

---

# AGENT MASTER LIST (by priority)

| # | Agent | Stage | Status | Home |
|---|---|---|---|---|
| 1 | Call evaluation + CRM auto-fill | 1,3 | [BUILDING] next | `ops/call-coaching` |
| 1b | AI SMS responder (missed-call + form-reply, 2-way) | 1 | [LOCKED] high pri (30% miss) | `ops/sms-responder` |
| 2 | Lead cadence rebuild + stale-lead watchdog | 2 | [SPEC'D] | HubSpot workflow + `ops/lead-watchdog` |
| 3 | Email triage v2 (incl. Phase 2 PO→deal) | 4 | [SPEC'D] | `ops/email-triage` |
| 4 | Awaiting-PO chase | 4 | [SPEC'D] | workflow + triage agent |
| 5 | Diagnostic chase + grading SLA alert | 3,4 | [SPEC'D] | `ops/diagnostic-chase` |
| 5b | Free-trial conversion tracker | 3 | [SPEC'D] new pipeline | `ops/free-trial` |
| 6 | Pre-lesson 72h watchdog | 5 | [SPEC'D] | extend `aplus_weekly_sync` |
| 7 | Early-warning retention | 6 | [SPEC'D] | `ops/retention` (w/ Emily) |
| 8 | PO renewal / package depletion | 7 | [SPEC'D] | `ops/renewal` |
| 9 | Check-back quarterly re-engagement | 9 | [SPEC'D] | `ops/winback` |
| 10 | Friday coaching rollup | 3 | [SPEC'D] | inside #1 |
| 1c | Promise-keeping / commitment fulfillment | 3 | [SPEC'D] high value | rides on `ops/call-coaching` |
| 11 | School/program cheat-sheet | 3 | [PLANNED] | call companion |
| 12 | Test-prep re-engagement (magnet-6th → private-7th/9th) | 0,9 | [SPEC'D] high value | `ops/winback` |
| — | Blog, case study, spotlight | 0,8 | [LIVE]/[BUILDING] | `/marketing` |

# CHARTER PIPELINE STANDARDIZATION (Jun 19 2026)
3 charter pipelines confirmed: Charter Traditional Vendor Funds (907748, ~4133 deals), Terri iLead Level Up (72281989), Amy iLead Level Up (88841552). All now standardized to **Pre-Lesson → Post-Lesson → Invoice Submitted → Stopped**. The two iLead pipelines had an extra "Hours Reassigned" stage (between Invoice Submitted and Stopped) — REMOVING it; the 14 deals parked there were moved to Stopped (9 Terri, 5 Amy) on Jun 19. [Roman to delete the now-empty stage in HubSpot Settings — connector can't edit pipeline structure.] Baseline-capture gate applies identically across all 3.

# DECISIONS LOG (this session)
Repo → `aplus-agents`, /marketing + /ops · Calls >=60s analyzed · Single #call-coaching channel · Danielle partner calls deferred · First connect = consultation · CONSULTATION = trust-first/money-last, restaurant principle, "what school?" silent qualifier, pricing always emailed as a graphic never read aloud, "be the parent not the salesperson" frame · 3 discovery forks (older-grades / younger-reading / test-prep) · stakes via inflection-point education · charter-we-serve line (social proof + tenure; charter enrollment long = multi-year) · private serves all schools, distinction = area · LAUSD magnet test-prep (Walter Reed IHP / Science Academy / Armstrong; OLSAT = context not product) · TEST-PREP gets most coaching · PRESENT = teaching philosophy concrete (tutor earns trust, delivery>material, rigor for independence, signature back-of-the-set HW method) · online-vs-in-person = objection battleground · in-person scarcity play, steer to online · free trial = earned close after objection (private: beat doubt/online / charter: tiebreaker vs vendor) · free-trial pipeline exists but manual · pricing cards rebuilt (Quiet Ascent) + logo de-boxed · "Committed–Awaiting PO" status to create · PO→deal automation = triage Phase 2, verify-mode first · QTL-CAP status to retire (CAP closed) · Lead vs deal definition confirmed · Kath (not "CAF") creates charter deals · No Google Ads (Yelp only) · 6644 missed-call text 24/7, no contact created (spam) → reply-gated creation · ~30% inbound calls missed · web form fires instant auto text+email · pursuit cadence 3 calls+3 texts+3 emails · PROMISE-KEEPING AGENT spec'd (high value): reads transcript, extracts every commitment, fulfills or flags; staged detect→draft→auto; natural endgame of eval agent · diagnostic email template improved (book results call IN instructions via roman27/test-score-review, upload 2 days before, gender-neutral) · agent can auto-attach grade-specific diagnostic PDFs (HubSpot Files folder 'Math Year End Assessments', files K/1st-7th/Algebra1 + 1 universal ELA diagnostic; RULE CONFIRMED = send student's CURRENT grade + NEXT grade math + ELA, e.g. in 4th→4th+5th, in 5th→5th+6th; ceiling above 7th still TBD; full table in diagnostic-files-table.md) · SCORED FAILS added: prices read aloud, no dated next step locked · diagnostic chase upgrade: lock date on call + chase in days not 14-day silent timer · Conor IHP call ~15/20 (elite discovery; email follow-up FAST & good; but no dated next step in call OR email, diagnostic template says 'no time limit'=kills urgency; FIX: booking link in instructions (book results call BEFORE taking test) = roman27/test-score-review; fix at system level not rep level) · JustCall = Pro Monthly + API key confirmed (transcripts pullable by sid; skip JustCall AI add-on, our rubric is better) · transcripts stored as JustCall links on HubSpot call records, not as text fields

# OPEN QUESTIONS QUEUE
Stage 0–2 done. Stage 3 deep-build IN PROGRESS — remaining: Section 1 exact opener words; logistics-explanation depth before money; then rescore the rubric. Then Stage 4 (PO mechanics), 5, 6, 7, 9.
