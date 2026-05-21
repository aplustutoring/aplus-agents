---
name: aplus-research
description: Research the web for LinkedIn-worthy topics relevant to A+ Tutoring's B2B audience (charter directors, special programs coordinators, district leaders). Watches five topic categories (federal/state K-12 funding, K-12 problem stories, target school news, industry/competitor moves, education research) plus a defined keyword set. Surfaces a weekly topic queue ranked by relevance to A+'s positioning. Use whenever the LinkedIn content engine needs new topics, when running the weekly Monday research routine, or when Danielle/Roman want to see what's worth posting about this week.
---

# A+ Tutoring Research Agent

## Purpose

Surface the 3-10 most relevant K-12 education topics from the past 7 days that A+ Tutoring should post about on LinkedIn, ranked by relevance to A+'s positioning and audience.

This is the fuel for the LinkedIn content engine. Without good topic input, the rest of the system writes about the wrong things.

## When to apply

- Monday morning weekly research routine (default cadence)
- Ad-hoc when Danielle or Roman ask "what's worth posting about this week?"
- When a specific event happens (CARS deadline, state policy announcement, major K-12 news) and we need to react fast
- When the content queue runs low

## Five topic categories (watchlist)

The agent monitors all five categories every research run. Findings are tagged by category in the output.

### A. Federal/state K-12 funding
- Title I, Title II, Title III funding news, allocations, deadlines
- ESSA reauthorization or amendments
- CARS (California's Comprehensive Accountability Reporting System) updates
- State budget allocations affecting K-12
- Charter funding policy changes
- Any news about funds returned, deadlines missed, allocation problems

### B. K-12 problem stories
- LTEL (Long-Term English Learner) crisis stories and reclassification data
- Learning loss reports (post-COVID and ongoing)
- Achievement gap studies (ELA, math)
- Teacher shortage articles
- Chronic absenteeism reporting
- Reading and math score drops at any level (state, district, national)
- Equity gap research
- IEP / special education service delivery problems

### C. Specific charter / district news (target school list)
- News about specific schools on A+'s HOT 13 target list and expansion targets
- Charter renewals, new charter approvals, charter closures
- District leadership changes at target schools
- Press coverage of programs at target schools
- Hiring announcements at target schools (especially intervention coordinators, special programs)
- Awards or recognition received by target schools

The HOT 13 list and expansion targets should be provided to the agent at runtime as context.

### D. Industry / competitor moves
- Major moves by other intervention companies (Varsity Tutors, Tutor Doctor, Sylvan, K12, IXL, Carnegie Learning, etc.)
- New entrants to K-12 intervention space
- Acquisitions, funding rounds, leadership changes in edtech
- Studies or reports comparing intervention models
- Emerging methodologies (AI tutoring, peer tutoring at scale, etc.)

### E. Research / academic
- New ESSA Tier 1/2/3/4 evidence designations
- NWEA data releases and MAP Growth reports
- University research on tutoring effectiveness
- Reports from EdResearch, RAND, MDRC, AIR, NCEE, AERA
- Evidence reviews on high-impact tutoring (HIT) and high-dosage tutoring
- Publications from NSSA (National Student Support Accelerator)

## Keyword set (mandatory monitoring)

Every research run searches for these terms specifically. They signal A+-relevant content even when the topic doesn't fall cleanly into A through E.

### Tier 1 keywords (always check)
- "high-impact tutoring" / "HIT"
- "high-dosage tutoring"
- "Long-Term English Learner" / "LTEL"
- "Title III"
- "Title I"
- "reclassification"
- "ESSA evidence"
- "Tier 2 intervention" / "Tier 3 intervention"
- "MTSS" / "Multi-tiered system of supports"
- "NWEA" / "MAP Growth"
- "intervention tutoring"

### Tier 2 keywords (check if time allows)
- "learning recovery" / "learning acceleration"
- "chronic absenteeism"
- "reading gap" / "math gap"
- "achievement gap"
- "ELL services" / "English Learner services"
- "charter accountability"
- "NSSA" / "National Student Support Accelerator"
- "funded intervention"

### Forbidden / noise terms
The agent does NOT surface results focused on:
- General tutoring marketing content (parent-facing how-tos)
- Test prep marketing (SAT/ACT prep companies)
- College admissions content
- Homeschool curriculum debates
- Generic edtech product reviews
- AI replacing teachers debates (overdone, low signal)

## Output format

Each research run produces a markdown file with the following structure:

```markdown
# A+ Research Brief . [Date]

## Summary
[2-3 sentence summary of the week's most relevant signals]

## Top 3 recommended topics for next week's content

### Topic 1: [Headline]
- **Category:** [A/B/C/D/E]
- **Source(s):** [URLs]
- **Why this matters for A+:** [1-2 sentences]
- **Suggested angle for company post:** [1 sentence]
- **Roman take suggestion:** [1 sentence . what conviction angle]
- **Danielle take suggestion:** [1 sentence . what implementation angle]

### Topic 2: [...]
### Topic 3: [...]

## Additional topics worth knowing about (not recommended for posting)
- [3-5 items, brief one-liners]

## Watchlist updates
- [Anything new on HOT 13 schools]
- [Any keyword spikes worth flagging]
```

## Source quality rules

The agent prefers sources in this order:

1. **Primary research** . peer-reviewed studies, government reports (USDE, CDE), NWEA, NSSA, university research centers
2. **Trade press** . EdWeek, The 74, Chalkbeat, EdSurge, K-12 Dive
3. **Major media** . NYT Education, WaPo Education, AP Education
4. **Local press** . only when directly relevant to a HOT 13 target school

The agent AVOIDS:
- Listicle aggregators
- AI-generated content farms
- Vendor blogs disguised as research (other tutoring companies promoting themselves)
- LinkedIn thought-leadership posts as primary sources
- Reddit threads (use as signal of conversation, never as a source claim)

## Ranking criteria for topic recommendations

The agent ranks topics by these factors, in order:

1. **A+ positioning fit** . Does this topic let A+ say something only A+ can say? (Highest weight)
2. **Audience relevance** . Will charter directors and special programs coordinators care?
3. **Differentiation potential** . Can Roman AND Danielle each take a distinct angle on it?
4. **Recency** . Past 7 days strongly preferred; past 14 days acceptable for slow-moving research
5. **Evidence strength** . Is there real data behind the topic, or is it just opinion?

## Coordination with other skills

- Output feeds into `roman-voice` and `danielle-voice` (each topic comes with a suggested angle for each)
- Output feeds into the company post writer (using `social-content` from Charlie Hills's repo or similar)
- Topic recommendations should reference relevant A+ case study data when applicable (`aplus-case-study`)
- All output passes through `aplus-brand-check` before content is generated from it

## Approval gate

Roman and Danielle review the research brief together (or Danielle alone if Roman is unavailable). They approve 3 topics for the week's content production. Topics not approved go to the "additional topics" backlog.

## Frequency

- **Default:** Once per week, Monday morning
- **Reactive:** Ad-hoc when major K-12 news breaks
- **Pre-conference:** Bonus run before any major conference Danielle is attending (CARS, All Titles, etc.)

## What this skill does NOT do

- Does NOT write the actual LinkedIn posts (that's `social-content` + voice skills)
- Does NOT generate graphics
- Does NOT post to LinkedIn directly
- Does NOT track engagement metrics (that's `analytics-dashboard` from Charlie Hills's repo)
- Does NOT replace Danielle's professional judgment on what to pitch to schools

## Related skills

- `roman-voice` . uses topic suggestions to draft Roman's op-eds
- `danielle-voice` . uses topic suggestions to draft Danielle's op-eds
- `aplus-brand-check` . QA filter applied to research output before writers consume it
- `aplus-case-study` . provides evidence base when topics call for case study citations
- `aplus-b2b-brand-kit` . visual brand layer applied to any content generated from research

## Version

v1.0 . Created May 8, 2026
Foundation: Topic categories A-E and keyword set defined in conversation with Roman May 8, 2026
