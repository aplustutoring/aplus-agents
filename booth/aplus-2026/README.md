# booth/aplus-2026 — APLUS+ Network 23rd Annual Conference (Anaheim, Oct 21-23, 2026)

Home for the conference booth. Today it holds the school list; the booth build
(group selfie, one print per contact entered, print queue, HubSpot) lands here
next to it.

| File | What |
| --- | --- |
| `schools.yml` | Every APLUS+ member school (95, from theaplus.org/member-schools on 2026-09-11) with region, network, website, staff email domains, and whether we already hold teacher contacts for that domain in HubSpot. Plus 13 A+ Tutoring partner schools that are NOT APLUS+ members. |
| `schools-dropdown.json` | Flat list the booth loads for the school picker: `label`, `region`, `domains`, `known`. Typing an email whose domain matches auto-selects the school; the picker is the fallback. |

## How the list was built

1. Member names and regions scraped from the APLUS+ member page.
2. Website and staff email domain per school found by web search (four parallel
   research passes), confidence marked high / medium / low per row.
3. Cross-referenced against 1,084 Teacher of Record contacts in HubSpot
   (persona = Teacher of Record/EF/ES, grouped by email domain and the
   `[Agent] School` stamp). Where HubSpot already holds a verified domain for
   the school or its network (iLEAD, Compass, IEM, Springs, Pacific Charter
   Institute, Sage Oak, Excel, Gorman, Granite Mountain, Forest, Cottonwood,
   Epic), that domain is included and the row is `known`.
   `in_hubspot_tor_contacts` is the count for the domains on the row, so
   network schools (three IEM schools, six Springs schools) repeat the network
   total; it is a "we already work with these people" flag, not a per-school
   count.

## Things to verify before the booth goes live

- 26 rows are medium or low confidence, mostly the Learn4Life "II" schools in
  the Central Valley (staff email likely `cvcharter.org`), Options for Youth and
  Opportunities for Learning campus domains, and Northern Summit Academy
  (`ns-academy.org` site vs `nsa-academy.org` email).
- Diego Hills Central is still listed by APLUS+ but appears to have closed
  June 2024; keep the row, expect no one.
- Gorman: web says `gormanlcn.org`, HubSpot holds 15 teachers on `gormanlc.org`.
  Both are in the row.
- Learn4Life campuses each have their own site but staff mail is
  `learn4life.org`; the row carries both.

## The attendee list nobody asked for

Jeff Rice (APLUS+ founder, jeff@theaplus.org) tracks registrations "for planning
purposes" and sent Roman the full exhibitor table in 2024 the day he asked. In
the 2026 thread with Danielle (Aug 24 to Sep 3) nobody asked which schools are
registered. The member list above is the superset; the registered list is the
one that matters for the dropdown order and for pre-conference outreach. The
ask goes from the sales seat (Danielle), email only, per the teacher-contact
rules. Roman also sees Jeff in person at the Upper South regional meeting at
iLEAD HQ on 2026-09-17.
