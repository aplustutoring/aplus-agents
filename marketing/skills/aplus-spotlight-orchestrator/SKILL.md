---
name: aplus-spotlight-orchestrator
description: >
  End-to-end orchestrator for A+ Tutoring B2C student spotlight case studies. Takes a single Drive folder (or local bundle path) of raw intake source documents and runs the COMPLETE pipeline: draft + anonymize the case study, write metadata, generate all 13 graphics, publish to HubSpot as a draft, research Instagram hashtags + write platform captions, and deliver the full pack to Paola in Slack. Use this when Roman says "run the spotlight for [student]", "build the case study for [folder]", "process the new spotlight", or points at an intake folder and asks to run the whole thing. This is the master runbook; it calls the aplus-spotlight-case-study skill for drafting and the aplus-b2c-hashtag-analyst skill for hashtags, then shells out to the Python graphics + publish + delivery scripts.
---

# A+ Spotlight Orchestrator

## CRITICAL: This is a multi-step pipeline. Work top to bottom. Stop at any gate that fails.

This skill runs the entire B2C case study pipeline end to end. It coordinates
two other skills (drafting, hashtags) and six Python scripts (graphics,
publish, delivery). Run the phases in order. After each phase, confirm it
succeeded before moving to the next.

### Spotlight reel (auto, after Slack delivery)
Full runs (`--stop-after complete`) now also generate and deliver an animated
9:16 **spotlight reel** via the `reel` stage (`marketing/scripts/b2c/reel/`, see the
`aplus-spotlight-reel` skill). It reads the same `metadata.md` + case study,
produces its own stills/voice/Veo animation/captions, and posts the video into
`#student-spotlight-ready`. The stage is **non-fatal** — a Veo quota or ffmpeg
error is logged and the run still completes. Costs ~$5 (Veo) per run; disable
with env `SPOTLIGHT_REEL=0`. Requires `ffmpeg` on the runner (CI installs it).

## Prerequisites check (run first)

Confirm these exist before starting:
- The intake source folder (Drive or local) with the student's raw documents
- Repo at `~/Desktop/aplus-marketing-skills`
- `.env` with `GEMINI_API_KEY`, `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `HUBSPOT_PRIVATE_APP_TOKEN`
- The two sibling skills present: `aplus-spotlight-case-study`, `aplus-b2c-hashtag-analyst`

If any are missing, stop and tell Roman which one.

## Phase 0: Gather inputs

Ask Roman (once, batched) for anything not obvious from the folder:
- Path to the intake source folder
- Real student first name (for anonymization input)
- School name (drives URL slug + demographics for hero)
- Confirm bundle output date (defaults to today)

The bundle directory is:
`marketing/aplus-content/{YYYY-MM-DD}-case-study-{pseudonym}/`

## Phase 1: Draft the case study (uses aplus-spotlight-case-study skill)

Read the source documents. Apply the `aplus-spotlight-case-study` skill to
produce Document 1 (published, anonymized) and Document 2 (archive, real
names). Follow ALL of that skill's rules: 8-section structure, 1,200-1,500
words, pseudonym matching cultural background, grammar gate on every quote.

Write these files into the bundle directory:
- `case-study-{pseudonym}.md` (Document 1, anonymized)
- `archive-{realname}.md` (Document 2, NEVER published)

Run the anonymization checker before proceeding:
```
python3 marketing/scripts/b2c/check-anonymization.py --bundle marketing/aplus-content/{bundle}/
```
If it flags a real name in Document 1, FIX before continuing. Hard gate.

## Phase 2: Write metadata.md

Produce `metadata.md` in the bundle. Include the fenced block with:
```
h1_title: [title]
subject: [math|reading|writing|science]
grade: [number]
student_gender: [girl|boy]
student_ethnicity: [derived from school demographics — see note below]
url_slug: [pseudonym]-[school-short-slug]
meta_title: [...]
meta_description: [...]
hero_alt_text: [...]
```
Plus `pull_quotes:` (2, both passing the grammar gate).

### Deriving student_ethnicity (IMPORTANT)
Look up the school's dominant demographics. Check `marketing/data/partner-schools.md`
first for a demographics field. If absent, web-search the school's CA
DataQuest / enrollment demographics and pick the representation that matches
the actual student population (most A+ charter schools are minority-majority,
heavily Latino and Black). Set `student_ethnicity` to reflect the real
population. Never default to white. When the pseudonym implies a background
(e.g., Latinate name), align ethnicity with it.

## Phase 3: Bundle support files

Generate into the bundle:
- `bundle-summary.md` (one-page index + "Items needing Gate 2" section with numbered **bold** items)
- `qa-checklist.md`
- `paola-feedback.md` (3 sections: what worked, what was missing, one process suggestion)
- `seo-research-notes.md`

## Phase 4: Generate graphics

All six graphics builders are generalized scripts in scripts/ that take
--bundle and read everything from metadata.md. No per-bundle copies, no
path editing. Run from repo root, replacing {bundle} with the new bundle dir:

   python3 marketing/scripts/b2c/build-case-study-hero-card.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/b2c/build-case-study-topic-graphic.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/b2c/build-case-study-pull-quotes.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/b2c/build-case-study-ig-carousel.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/b2c/build-instagram-stories.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/b2c/build-case-study-facebook.py --bundle marketing/aplus-content/{bundle}/
   python3 marketing/scripts/shared/composite-logo.py --bundle marketing/aplus-content/{bundle}/

Notes:
- Hero auto-varies by subject/grade/gender/ethnicity via marketing/scripts/b2c/hero_scene.py. No manual prompt editing.
- The topic graphic reads its milestones list from metadata.md. Phase 2 must write that list (month | topic | verbatim_phrase per line) from the student's actual lesson-note progression.
- After generation, visually spot-check the hero and pull quotes. Grammar gate + ethnicity + face-partial rules must hold.

## Phase 5: Publish to HubSpot (draft)

```
python3 marketing/scripts/shared/publish-to-hubspot.py --bundle marketing/aplus-content/{bundle}/
```
Record the returned `post_id`. The post is a DRAFT — never auto-published.
HubSpot publish is Roman + Danielle's Gate 2 decision.

## Phase 6: Hashtags + captions (uses aplus-b2c-hashtag-analyst skill)

Apply the `aplus-b2c-hashtag-analyst` skill to this bundle. It researches
trending IG hashtags fresh for this case, writes `instagram_caption`,
`facebook_caption`, and `hashtag_research_notes` into `metadata.md`. Confirm
all 5 hashtags follow the schema (3 trending + 1 brand voice + 1 Roman voice)
and every caption passes the grammar gate.

## Phase 7: Deliver to Slack

Two scripts, in order. First the text bundle (header + Paola feedback +
file list), then the graphics + captions pack.

```
python3 marketing/scripts/b2c/deliver-case-study-to-slack.py --bundle marketing/aplus-content/{bundle}/ --post-id {post_id}
python3 marketing/scripts/b2c/deliver-case-study-graphics-to-slack.py --bundle marketing/aplus-content/{bundle}/
```

Both post to `#student-spotlight-ready`. The graphics script @mentions Paola.

Run each with `--dry-run` first to preview, then for real.

## Phase 8: Confirm + report

Tell Roman:
- Bundle path
- HubSpot draft post_id + edit URL
- Confirmation the Slack pack landed in #student-spotlight-ready
- The 5 hashtags chosen (so Roman can spot-check)
- Any Gate 2 items that need his + Danielle's judgment before publish

## Hard gates (never skip)

1. **Anonymization gate** (Phase 1): real name must NOT appear in Document 1.
2. **Grammar gate** (Phases 2, 6): every quote/caption reads as a complete grammatical sentence. A tutoring company never ships broken grammar.
3. **Ethnicity gate** (Phase 2): hero reflects the school's real demographics, never defaults to white.
4. **Face-partial gate** (Phase 4): the child in the hero is never a clear front-facing portrait. Representative, not identifiable.
5. **Draft-only gate** (Phase 5): HubSpot post is always a draft. Publish is a human decision.
6. **No auto-posting gate** (Phase 7): Slack delivery only. The bot never posts to Instagram, Facebook, or any external platform. Paola posts manually.

## What this skill does NOT do

- Does NOT publish the HubSpot draft live (Gate 2 human decision)
- Does NOT post to social platforms (Paola posts from the Slack pack)
- Does NOT pull intake data automatically (Paola drops the folder)
- Does NOT invent data or quotes (uses only what's in the source docs)

## Version

v1.0 (2026-05-27). Initial orchestrator. Chains aplus-spotlight-case-study (drafting) + aplus-b2c-hashtag-analyst (hashtags) + the graphics/publish/delivery scripts into one end-to-end pipeline. Built after the Gabriela case proved every individual piece. Next iteration should generalize the per-bundle graphics scripts into shared scripts/ versions so Phase 4 stops requiring per-bundle copies.
