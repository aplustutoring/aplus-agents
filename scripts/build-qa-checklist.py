#!/usr/bin/env python3
"""
Build the human-sign-off QA checklist for a weekly content bundle.

Outputs aplus-content/{bundle}/qa-checklist.md — a markdown file with all
the gates Danielle and Roman should walk through before publishing.

Usage:
    python3 scripts/build-qa-checklist.py --bundle aplus-content/2026-05-18-weekly/

Per the v1.4 master weekly run prompt, this runs at the end of every
bundle generation so the team has a single canonical checklist to work
from.
"""
import argparse
import re
import sys
from pathlib import Path


CHECKLIST_TEMPLATE = """# Content QA Checklist: {date}

> Bundle is NOT marked ready-to-publish until ALL boxes checked.

## Blog post

- [ ] Word count between 1,200 and 1,500
- [ ] All quality gates pass (aplus-fact-check, aplus-brand-check, humanize-writing, on-page SEO audit ≥ 80)
- [ ] No em dashes anywhere in body
- [ ] No AI vocabulary (leverage, delve, harness, foster in corporate sense, etc.)
- [ ] Both iLEAD case study URLs present in body (Math + ELA)
- [ ] Danielle's HubSpot booking link in CTA (no generic /consultation)
- [ ] All 3-5 internal links present (case studies + partner + service pages)
- [ ] Linda Darling-Hammond attribution correct (CA SBE President; NOT Stanford)
- [ ] Susanna Loeb attribution correct (Stanford GSE)
- [ ] iLEAD numbers exact (75 percent, 87.5 percent, 80 percent)
- [ ] No "81 percent" appearance anywhere (retired figure)
- [ ] No "21 students" appearance anywhere (retired figure)

## Topic graphic (AI-generated, this week's data viz)

- [ ] Visual content matches blog topic
- [ ] Any numerical claims in the graphic match the blog body exactly
- [ ] No fabricated data points
- [ ] A+ logo present (bottom-right, real logo not AI-rendered)
- [ ] Brand colors correct (navy + orange)
- [ ] Text rendering clean (no garbled letters, no hallucinated tokens)
- [ ] Approved by: ___________

## Preset stat graphic (canonical iLEAD outcomes)

- [ ] File is a verbatim copy of `skills/aplus-b2b-brand-kit/ilead-outcomes-graphic.png`
- [ ] Numbers verified (75 percent, 87.5 percent, 80 percent)
- [ ] Student counts verified (12, 8, 20)
- [ ] Ring fills proportional to percentages (75 percent ring is visibly 3/4 filled, 87.5 percent ring nearly full, 80 percent ring 4/5 filled)
- [ ] If any of the above fails: regenerate via `scripts/build-ilead-outcomes-graphic.py` and re-copy

## Pull-quote graphics (3)

- [ ] All quote text is VERBATIM from blog body (no paraphrasing)
- [ ] No date line at bottom
- [ ] No "A+ Tutoring blog" subtitle
- [ ] Logo correctly placed (bottom-right, white variant on orange background)

## LinkedIn carousel (5 slides)

- [ ] Slide content matches blog
- [ ] No factual errors across slides
- [ ] Brand colors consistent across all 5 slides
- [ ] Slide 1 (hook) reads as the blog's opening claim
- [ ] Slide 5 (CTA) points to the blog URL or Danielle's booking

## Hero image (homeschool spec)

- [ ] Home-based learning setting (kitchen, home office, bedroom desk, etc.)
- [ ] NO traditional classroom signifiers (rows of desks, chalkboard, school lockers, etc.)
- [ ] Documentary photography aesthetic (candid, not staged)
- [ ] Natural lighting

## Instagram post + Facebook + LinkedIn company text

- [ ] B2C voice for Instagram/Facebook (warm, parent-relatable)
- [ ] B2B voice for LinkedIn company (institutional, educator-peer)
- [ ] Hashtags present on Instagram caption
- [ ] No overlap between Roman and Danielle op-eds (paired-differentiation check)

## Slack delivery

- [ ] Bundle delivered to #weekly-content-ready
- [ ] All graphics visible in Slack thread
- [ ] HubSpot draft link present in header
- [ ] Posting schedule clear in bundle-summary.md

## Human sign-off

- [ ] Roman approved: ___________
- [ ] Danielle approved (for any charter-school audience content): ___________

---

When all boxes are checked, the bundle is ready to publish.
"""


def extract_date(bundle_path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return "(unknown date)"
    return m.group(1)


def main():
    parser = argparse.ArgumentParser(description="Emit qa-checklist.md for a weekly content bundle.")
    parser.add_argument("--bundle", required=True, help="Bundle directory")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    date_str = extract_date(bundle)
    out_path = bundle / "qa-checklist.md"
    out_path.write_text(CHECKLIST_TEMPLATE.format(date=date_str))
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
