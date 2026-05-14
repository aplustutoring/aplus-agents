# Blog Anchor — SEO Metadata + Schema (HubSpot Publication Ready)

## Pre-Draft SEO Research Findings (captured from v1.1 pipeline)

**keyword-research output:**
- Primary keyword: `Title III funding deadline California charter schools`
- Search volume: Low (estimated 50-200/mo). High-intent commercial investigation query.
- Difficulty score: 28/100 (low, SERP dominated by CDE bureaucratic pages with no charter-specific framing)
- Intent classification: Informational + commercial investigation (charter directors looking for what the deadline requires and what to do)
- Related cluster terms: "Title III obligation deadline," "Title III Immigrant funds California," "Title III unspent funds charter," "EL intervention funding deadline," "supplemental-not-supplant Title III"

**serp-analysis output:**
- Top 5 ranking pages: (1) cde.ca.gov Title III categorical programs page; (2) cde.ca.gov Title III preliminary allocations 2024-25; (3) cde.ca.gov Title III FAQs; (4) ed.gov Title III, Part A overview; (5) EdSource Title III analysis
- SERP features present: AI Overview likely, People Also Ask box highly likely, Featured Snippet possible
- Content type/length of winners: Bureaucratic pages averaging 600-1,200 words. None written for charter-school operational use. No partner-school proof points.

**content-gap-analysis output:**
- Queries A+ does not currently cover but competitors do: "what counts as Title III obligation," "Title III monitoring documentation," "supplemental-not-supplant examples"
- Topic clusters where A+ has thin coverage: Charter-LEA specific Title III operational guidance
- Question phrasings competitors answer: "What is the Title III deadline?", "What can Title III funds be used for?", "What happens if Title III funds are not spent?"

**Decision before drafting:** Topic angle revised to address the operational gap. Primary keyword retained. Added structured "what counts vs. what doesn't" comparison list to compete for AI Overview citation.

---

## SEO METADATA BLOCK (HUBSPOT PUBLICATION READY v1.1)

```
url_slug: /title-iii-funding-deadline-2026-california-charter-schools
h1_title: Title III Funding Deadline 2026: What California Charter Schools Need to Do Before September 30
meta_title: Title III Funding Deadline 2026: California Charter Guide
meta_description: California charter schools must obligate 2024-25 Title III funds by September 30, 2026. Learn what counts as a valid obligation and where the dollars go.

primary_keyword: Title III funding deadline California charter schools
keyword_search_volume: Low (50-200/mo estimated, high-intent commercial investigation)
keyword_difficulty: 28/100
keyword_intent: Informational + commercial investigation
secondary_keywords: Title III obligation deadline, Title III Immigrant funds California, Title III unspent funds charter, EL intervention funding deadline, supplemental-not-supplant Title III

serp_features_targeted: AI Overview, People Also Ask, Featured Snippet
serp_top_competitors: cde.ca.gov Title III categorical programs page, cde.ca.gov Title III preliminary allocations 2024-25, EdSource Title III analysis
content_gaps_addressed: Charter-LEA specific operational framing, valid-obligation comparison list, partner-school proof points (iLEAD Tier 3 outcomes), supplemental-not-supplant practical examples

internal_links_recommended:
  - /case-study-ilead-math-tier3
  - /results/ilead-tier-3-english
  - /services
  - /consultation

external_links_cited:
  - https://www.cde.ca.gov/fg/aa/co/ca24winst3immytdexp6mo.asp
  - https://www.cde.ca.gov/fg/fo/profile.asp?id=6249
  - https://nssa.stanford.edu/news/early-findings-show-evidence-high-impact-tutoring-increases-student-attendance-dc-schools

schema_type: Article
schema_author: A+ Tutoring Team
schema_publisher: A+ Tutoring
schema_date_published: 2026-05-14

hero_image_alt_text: California charter school administrator reviewing Title III expenditure report on laptop with September 30, 2026 deadline highlighted on calendar
pull_quotes:
  - "The deadline is not a budget question. It is a clock."
  - "Spending zero never gets flagged in a monitoring visit. The unintended consequence is that the EL students Title III was designed to serve get nothing."
  - "$6,295 sitting in an account with a four-and-a-half-month clock on it."
reading_time: 7 minutes
target_publish_date: 2026-05-20 (Wednesday AM)
target_promotion: LinkedIn company post Wednesday PM, Roman op-ed Thursday AM, Danielle op-ed Friday AM
on_page_audit_score: 88/100
```

---

## A/B Variants (for future testing)

**meta_title variants (not chosen as primary):**
- B: "Title III Deadline Sept 30, 2026: What Charter LEAs Must Do" (60 chars)
- C: "California Title III Deadline: Charter Schools' 2026 Clock" (58 chars)

**meta_description variants (not chosen as primary):**
- B: "Title III Immigrant funds pay $125.90 per newcomer. Unspent dollars revert to CDE after Sept 30. A+ Tutoring's guide for charter directors and coordinators." (158 chars)
- C: "Charter LEAs have 4.5 months to obligate 2024-25 Title III ELL and Immigrant funds before Sept 30, 2026. Practical guide with supplemental-not-supplant rules." (159 chars)

---

## JSON-LD Schema Block (paste into HubSpot structured data field)

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "Title III Funding Deadline 2026: What California Charter Schools Need to Do Before September 30",
  "description": "California charter schools must obligate 2024-25 Title III funds by September 30, 2026. Learn what counts as a valid obligation and where the dollars go.",
  "image": "https://blog.wetutorathome.com/hubfs/title-iii-deadline-2026-hero.jpg",
  "datePublished": "2026-05-20T08:00:00-07:00",
  "dateModified": "2026-05-20T08:00:00-07:00",
  "author": {
    "@type": "Organization",
    "name": "A+ Tutoring Team",
    "url": "https://wetutorathome.com"
  },
  "publisher": {
    "@type": "Organization",
    "name": "A+ Tutoring",
    "logo": {
      "@type": "ImageObject",
      "url": "https://wetutorathome.com/hubfs/aplus-logo.png"
    }
  },
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "https://blog.wetutorathome.com/title-iii-funding-deadline-2026-california-charter-schools"
  },
  "keywords": "Title III funding deadline, California charter schools, Title III Immigrant funds, supplemental-not-supplant, EL intervention"
}
```

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What does the September 30, 2026 Title III deadline actually require?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "The Title III subgrant period for 2024-25 funds runs from July 1, 2024 to September 30, 2026, giving LEAs 27 months to obligate the funds. Obligate means entering into a binding contract or commitment that creates a liability against the funds. After September 30, 2026, LEAs have 90 additional days to liquidate any encumbrances, with December 30, 2026 as the final cash-out date. Funds neither obligated nor liquidated by those dates must be returned to the California Department of Education."
      }
    },
    {
      "@type": "Question",
      "name": "What does the research say about how Title III dollars should be spent?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Stanford's National Student Support Accelerator (NSSA), led by Susanna Loeb at the Stanford Graduate School of Education, found that scheduled high-impact tutoring sessions decreased the probability of student absence by 11.4 percent for middle schoolers, about 3.1 additional days of school per student per year when tutoring is part of the school day. NSSA defines high-impact tutoring as at least three sessions per week, small group size of one to four students, sessions delivered during the school day, and the same tutor across the cycle."
      }
    }
  ]
}
```

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "A+ Tutoring",
  "alternateName": "A+ Tutoring (We Tutor At Home)",
  "url": "https://wetutorathome.com",
  "logo": "https://wetutorathome.com/hubfs/aplus-logo.png",
  "description": "A+ Tutoring is a California K-12 virtual tutoring company serving charter schools and intervention programs with synchronous online Tier 2 and Tier 3 small-group instruction in ELA and math.",
  "areaServed": {
    "@type": "State",
    "name": "California"
  },
  "knowsAbout": [
    "Tier 3 intervention",
    "High-impact tutoring",
    "Title III funding",
    "Long-Term English Learner reclassification",
    "Charter school intervention programs",
    "NWEA MAP Growth aligned instruction"
  ]
}
```
