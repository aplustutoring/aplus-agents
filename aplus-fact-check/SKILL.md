---
name: aplus-fact-check
description: Verify the factual accuracy of any A+ content containing specific claims about legislation, statistics, dates, studies, officials, or organizational data before it reaches the approval queue. Catches what brand-check misses (brand-check verifies WORDS, fact-check verifies CLAIMS). Use on every piece of content that contains a verifiable factual assertion. Triggered automatically on research briefs, op-eds, company posts, and case studies before brand-check runs.
---

# A+ Fact-Check Agent

## Purpose

Verify factual claims in A+ content against authoritative sources before content reaches Danielle's approval queue.

This skill exists because of a specific failure mode: the `aplus-research` skill can produce factually shaky content that passes `aplus-brand-check` (because brand-check catches words, not facts). On May 11, 2026, the research agent surfaced SB 414 as "moving through legislature" when it had already been vetoed by Governor Newsom in December 2025. Brand-check would have passed that content. A school admin reading it would have lost trust in A+ instantly.

**Fact-check runs BEFORE brand-check in the pipeline.** Wrong facts can't be polished into right facts.

## When to apply

Fact-check is mandatory on every piece of content that contains:

- **Legislative claims** (bill numbers, bill status, bill provisions, signing dates, veto dates)
- **Statistics** (percentages, dollar amounts, student counts, growth rates)
- **Study citations** (study names, publication dates, sample sizes, findings)
- **Named officials** (governors, legislators, superintendents, charter directors)
- **Organizational data** (school enrollments, district sizes, network affiliations)
- **Dates** (event dates, deadline dates, conference dates)
- **Direct quotes** (anything in quotation marks attributed to a person)
- **A+ internal data** (case study figures, partnership claims, outcome data)

Skip fact-check ONLY when content is:
- Pure opinion or interpretation with no specific claims
- A direct quote from Paola's intake brief that Paola already verified
- Boilerplate marketing copy with no specific assertions

## When fact-check runs in the pipeline

Order of operations for any content generation:

1. Voice skill (roman-voice, danielle-voice) OR brand-kit skill produces draft
2. **fact-check runs FIRST** (catches factual errors)
3. **brand-check runs SECOND** (catches word/voice violations)
4. If both pass, content goes to Danielle approval queue
5. If either fails, content goes back to writer agent with specific issues flagged

## What fact-check verifies (by claim type)

### Legislative claims

For any mention of a California bill (SB ###, AB ###):

1. **Verify bill exists.** Search LegiScan or leginfo.legislature.ca.gov for the bill number.
2. **Verify current status.** Is the bill: Introduced / In Committee / Passed Senate / Passed Assembly / Vetoed / Signed into Law / Chaptered? Status MUST be current as of today.
3. **Verify author.** Is the named senator/assembly member actually the author?
4. **Verify provisions.** Does the bill actually contain what the content claims?
5. **Verify effective dates.** If the content claims a date, verify against the bill text.

For federal legislation (HR ###, S ###):
- Same checks against congress.gov

### Statistics

For any percentage, dollar amount, count, or growth rate:

1. **Verify the source.** Is the cited source real?
2. **Verify the number.** Does the cited source actually contain that number?
3. **Verify the context.** Is the number being used in the same context the source intended? (Common failure: stat is real, application is wrong)
4. **Verify recency.** When was the data collected? Is it still current enough to cite?

### Study citations

For any "according to [Stanford/Harvard/Brookings/NWEA/etc.]":

1. **Verify the study exists.** Search the cited institution's research page.
2. **Verify the publication date.** Is the study as recent as claimed?
3. **Verify the finding.** Does the study actually say what the content claims?
4. **Verify the sample size and methodology.** Is the citation responsible?

### Named officials

For any named person:

1. **Verify the person holds the role claimed.** (e.g., "Superintendent of XYZ Unified") . check official site
2. **Verify spelling.** Names must be spelled correctly.
3. **For elected officials:** Confirm they're still in office.

### Organizational data

For any claim about a school, district, or network:

1. **Verify enrollment figures.** Check CDE Public School Directory or DataQuest.
2. **Verify ESSA designation status.** Check CDE accountability data.
3. **Verify network affiliations.** Confirm the school is part of the claimed network.
4. **Verify Title funding status.** Check CDE Title program data if claimed.

### Direct quotes

For any quoted statement:

1. **Verify the source said it.** Search for the quote.
2. **Verify the context.** Is the quote being represented faithfully?
3. **For partner quotes:** Confirm Paola/Danielle has consent to publish.

### A+ internal data

For any claim about A+ outcomes, partnerships, or methods:

1. **Verify A+ outcome data against the correct source for each cut.** The fact-check skill caught a real failure mode on May 11, 2026 where 81% was being cited as a real figure. Investigation revealed 81% was based on incorrect headcount (one student was improperly labeled). The verified figures are below.

**iLEAD AV Tier 3 data . 2024-25 school year . correct attributions:**

| Program | Students | Improved | Rate | Avg RIT | Avg %ile | Source |
|---|---|---|---|---|---|---|
| Math Tier 3 (PUBLISHED) | 12 | 9 | 75% | +18.7 | +20.8 | https://wetutorathome.com/case-study-ilead-math-tier3 |
| ELA Tier 3 (PUBLISHED) | 8 | 7 | 87.5% | +20.1 | +17.8 | https://wetutorathome.com/results/ilead-tier-3-english |
| Combined (both programs together) | 20 | 16 | 80% | ~+19.4 | ~+19.5 | Sum of both published case studies |

All three figures are valid. Use the one that matches your context:
- Citing the published Math case study URL → use 75%, 12 students
- Citing the published ELA case study URL → use 87.5%, 8 students
- Making a general claim about the full Tier 3 program → use 80%, 20 students

**Retired figure:** 81% / 21 students. This was based on incorrect headcount. Do NOT use this figure in any content. If found in existing content, flag for revision.

**Dosage details (both programs):** 17 hours per student, one-to-one synchronous delivery, same tutor across the cycle.
2. **Verify against other A+ published case studies** for other cohort claims
3. **Flag any claim that doesn't appear in published or internally documented sources** . A+ should not invent outcome data
4. **Verify partner relationships** against target-schools.md before claiming a school as a partner

## Output format

### PASS

```
✅ FACT CHECK PASSED

Content: [first 50 chars]
Claims verified: [N]
Sources checked: [list]
Notes: [any close calls or context worth flagging to writer]

Routing to brand-check.
```

### FAIL . single issue

```
❌ FACT CHECK FAILED

Content: [first 50 chars]

CLAIM IN CONTENT: "[exact quote from content]"
ACTUAL FACT: "[what the verified source says]"
SOURCE: [URL of authoritative source]
SEVERITY: [Critical / Important / Minor]

Recommended fix: [How to rewrite the claim correctly OR drop it]

Returning to writer for revision.
```

### FAIL . multiple issues

```
❌ FACT CHECK FAILED . MULTIPLE ISSUES

Content: [first 50 chars]

Issues found:
1. [Claim type]: "[quote]" → ACTUAL: "[fact]" → SOURCE: [URL] → SEVERITY: [level] → FIX: [recommendation]
2. [Claim type]: "[quote]" → ACTUAL: "[fact]" → SOURCE: [URL] → SEVERITY: [level] → FIX: [recommendation]
3. ...

Returning to writer for revision. Address all critical and important issues before resubmitting. Minor issues can be addressed but are not blocking.
```

## Severity levels

**Critical** (auto-fail, never publishes):
- Bill cited with wrong status (e.g., vetoed bill cited as "moving through legislature")
- Statistic that doesn't appear in the cited source
- Quote attributed to wrong person
- Named partner that isn't actually a partner
- A+ outcome data that doesn't match published case studies

**Important** (auto-fail unless writer justifies):
- Slightly outdated statistic (data is 2+ years old when newer data exists)
- Source cited at the wrong level (citing Brookings when actually cited by EdSource)
- Date imprecision (Q1 2026 when actually February 2026)

**Minor** (flag but allow publication):
- Spelling of less common names
- Acronym expansion preference (LTEL vs. Long-Term English Learner)
- Verb tense around recent events ("just passed" vs "passed last month")

## Authoritative source priority

For each claim type, fact-check uses these sources in priority order:

### California legislation
1. leginfo.legislature.ca.gov (official bill text + status)
2. LegiScan.com (status tracking + voting records)
3. EdSource (analysis + context)
4. CalMatters (analysis + context)
5. CSBA / CASBO (school-side analysis)

### Federal legislation
1. congress.gov
2. K-12 Dive (education-specific federal coverage)
3. Education Week

### Statistics
1. CDE DataQuest (California school data)
2. NCES (federal education data)
3. NWEA research publications (assessment data)
4. The primary research source cited (not summaries)

### California schools and districts
1. CDE Public School Directory
2. The school's official website
3. The authorizing district's website
4. CDE accountability data (ESSA flags, Dashboard)

### Education research
1. The publishing institution's website directly
2. Peer-reviewed journals if applicable
3. EdResearch / RAND / MDRC / AIR for replication studies

## What fact-check does NOT do

- Does NOT verify whether a claim is strategically wise (that's human judgment)
- Does NOT verify tone or voice (that's brand-check)
- Does NOT verify spelling/grammar except for proper names
- Does NOT replace Danielle's professional knowledge of the charter ecosystem
- Does NOT replace Roman's institutional knowledge of A+'s history
- Does NOT make up sources if it can't find one . flags as "unable to verify" and routes back

## When fact-check cannot verify

If a claim cannot be verified within reasonable effort (3-5 source searches):

```
⚠️ FACT CHECK UNABLE TO VERIFY

Content: [first 50 chars]

UNVERIFIABLE CLAIM: "[exact quote]"
SEARCHES ATTEMPTED: [list]
RECOMMENDATION: [Drop the claim / Rewrite without specific number / Request human verification from Danielle or Roman]

This is NOT a fail. This requires human decision before publication.
```

## Iteration protocol

If the same writer agent or research agent produces 3+ factual errors in a row:

1. Log the pattern
2. Flag for skill audit (the upstream skill may need stricter source rules)
3. Recommend updating the upstream SKILL.md to prevent the recurring failure

## Coordination with other skills

- Receives content from: aplus-research, roman-voice, danielle-voice, aplus-b2b-brand-kit, aplus-b2c-brand-kit, aplus-spotlight-case-study, any blog/email writer
- Sends verified content to: aplus-brand-check (next gate in pipeline)
- Sends failed content to: original writer agent for revision
- Reads from: target-schools.md (for partner status verification), published case studies, A+ Master Document if accessible

## Frequency

- Runs on EVERY piece of content that contains verifiable claims
- Mandatory step in every content generation workflow
- Cannot be skipped . bypassing fact-check is the failure mode that destroyed credibility on SB 414

## What this skill costs (worth knowing)

Fact-check adds 30 seconds to 5 minutes per piece of content depending on claim count. For a typical Roman op-ed (100 words, 2-3 claims): about 2 minutes of agent time. For a research brief with 10+ claims: 10-15 minutes.

This is real time, not theoretical. Build it into pipeline timing expectations.

## Related skills

- `aplus-research` . upstream skill that surfaces topics with claims requiring verification
- `aplus-brand-check` . downstream skill that runs AFTER fact-check passes
- `roman-voice` . upstream skill whose drafts must be fact-checked
- `danielle-voice` . upstream skill whose drafts must be fact-checked
- `aplus-spotlight-case-study` . upstream skill whose drafts must be fact-checked (especially outcome data)

## Failure log

Document any errors caught by this skill in a `fact-check-failures.md` file in the same folder. This builds institutional memory and helps tune upstream skills.

Format:

```
## [Date] . [Content type] . [Writer agent]

CLAIM: "[what was wrong]"
ACTUAL: "[what was right]"
SOURCE: [URL]
ROOT CAUSE: [Why the writer agent produced this . outdated training data, missing source priority, etc.]
ACTION TAKEN: [Returned for revision / Skill updated / Pattern flagged]
```

## Version

v1.2 . Updated May 13, 2026 . Corrected iLEAD AV figure from 81%/21 students (incorrect headcount) to 80%/20 students (verified). Added ELA case study URL and attribution. Retired 81% figure permanently.
v1.1 . Updated May 11, 2026 (added correct attribution table for iLEAD AV data after first real run flagged 81% misattribution against published case study URL)
v1.0 . Created May 11, 2026
Foundation: SB 414 incident on May 11, 2026 surfaced the factual accuracy gap that brand-check cannot catch. Built specifically to prevent shipping content with wrong bill statuses, fabricated statistics, or invented A+ outcome data. iLEAD AV data correction added same day after first real run validated the skill.
