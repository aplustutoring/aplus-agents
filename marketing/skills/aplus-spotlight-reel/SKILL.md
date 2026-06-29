---
name: aplus-spotlight-reel
description: >
  Produce a narrated, captioned animated SPOTLIGHT REEL (9:16 vertical video) for an
  A+ Tutoring B2C student spotlight, from a bundle's metadata + case study. Generates
  its own comic-style storyboard script, scene stills, Veo animation, Gemini voiceover,
  and word-by-word karaoke captions, then assembles spotlight-reel.mp4. Use when Roman
  or Paola says "make a reel for [student]", "video version of the spotlight",
  "animated spotlight", or points at a processed case-study bundle and asks for a video.
  This skill is INDEPENDENT of the comic storyboard: both read the same upstream
  metadata; neither reads the other. Runs on direct APIs only (Gemini + OpenAI keys in
  .env) — no Higgsfield, no Canva, headless-friendly.
---

# A+ Spotlight Reel

## Single responsibility

Turn a processed case-study bundle into ONE narrated, captioned 9:16 reel.
It does NOT draft the case study, generate the comic, publish, or deliver —
those are other skills. It reads the same upstream data the comic reads
(`metadata.md` + the case study) and renders its own independent video. Run it
in parallel with the comic; the two never depend on each other and may use
different art (the reel and comic are posted on different days by design).

## Why a separate skill (not coupled to the comic)

The student's story is authored ONCE upstream, in the case study + `metadata.md`.
The comic and the reel are each just a renderer of that source. Keeping them
independent means: run either alone, run both at once, and neither breaks if the
other changes. The only thing they share is the source data — which is what keeps
them consistent in substance while free to differ in look.

## Prerequisites

- Repo at `~/code/aplus-agents`
- `.env` with `GEMINI_API_KEY` (stills, video, voice) and `OPENAI_API_KEY` (caption word-timing)
- `ffmpeg` / `ffprobe` (Homebrew). Install: `brew install ffmpeg`
- A bundle with `metadata.md` (produced by the case-study / orchestrator phase),
  containing `subject`, `grade`, `student_gender`, and ideally `result_stat`/`comic_stat`.
- Python deps: `Pillow`, `python-dotenv`, `openai`, `google-genai` (in requirements.txt)

If `metadata.md` is missing, stop — the bundle hasn't been processed yet.

## Guardrails (non-negotiable — same as the comic/case-study skills)

- The hero is a FICTIONAL archetype typed only by subject (power/emblem) and grade
  (age band). NEVER the real child, no name, no likeness, no photo.
- NO student name in narration or captions — not even the published pseudonym.
  Refer to the student generically ("a fourth grader", "he"/"she", "this student").
  Names read as identifying and are not wanted on the reel.
- Captions/narration surface ONLY non-sensitive axes: subject, grade band, the arc,
  and a non-sensitive outcome. NEVER IEP / 504 / disability / EL / LTEL / low-income /
  foster in any spoken line or caption.
- Captions render the SCRIPTED `vo` text (correct punctuation/caps), timed by
  Whisper — never the raw transcript (which drops punctuation and reads as poor
  grammar).
- Image/video models render NO text — all caption text is composited by the pipeline.
- After authoring the script, run the gates (Phase 2) before rendering.

## Pipeline — run phases in order from the repo root

### Phase 0: Baseline script
Generate the deterministic baseline storyboard script from metadata:
```
python3 marketing/scripts/b2c/reel/make_script.py --bundle marketing/aplus-content/{bundle}/ [--voice Achird]
```
Writes `{bundle}/reel/script.json` — 5 beats (struggle → sidekick → breakthrough →
win → end card), each with `scene` (image prompt), `motion` (Veo prompt), `vo`
(narration = caption text), and `delivery` (TTS tone). Hero archetype is derived
from subject/grade/gender.

### Phase 1: Refine the script (this is the creative step)
Open `script.json` and REWRITE the `vo` lines so they're student-specific and in
**B2C brand voice** (apply `aplus-b2c-brand-kit`): address the parent ("your child"),
warm/hopeful, outcome-led, plain language. Weave in the real, non-sensitive outcome
(e.g., a grade-level jump or score gain from the case study) where it strengthens the
win or breakthrough line. Keep each line short enough to read in ~3–6s. Leave `scene`
and `motion` unless you want to adjust the visuals. Captions are auto-derived from the
spoken `vo`, so editing `vo` updates both voice and captions.

### Phase 2: Gates (hard)
- `python3 marketing/scripts/b2c/check-anonymization.py --bundle marketing/aplus-content/{bundle}/` — must pass; no real name leaks.
- Apply `aplus-brand-check` to every `vo` line (banned words: empower, unlock potential,
  transform, leverage, delve, harness, foster, "all students", game-changer; no em-dash tics
  if narrated oddly). Apply `aplus-fact-check` to any outcome claim you added.
- Confirm no sensitive classification appears in any `vo`/caption.

### Phase 3: Render media (direct APIs — costs ~$5 on the Google account)
```
python3 marketing/scripts/b2c/reel/make_stills.py --bundle marketing/aplus-content/{bundle}/   # Gemini images (anchor + 4 beats)
python3 marketing/scripts/b2c/reel/make_vo.py     --bundle marketing/aplus-content/{bundle}/   # Gemini TTS (5 lines)
python3 marketing/scripts/b2c/reel/make_clips.py  --bundle marketing/aplus-content/{bundle}/   # Veo 3.1 Fast (4 clips, ~8s each)
```
All three are resumable (existing outputs are reused; pass `--force` to regenerate).
Verify the stills look on-brand and artifact-free before spending on video.

### Phase 4: Assemble
```
python3 marketing/scripts/b2c/reel/build_reel.py  --bundle marketing/aplus-content/{bundle}/
```
Trims each clip to its narration length, strips clip audio, overlays the top-left A+
watermark + karaoke captions, appends the 4s end card, and muxes the voiceover.
Output: `{bundle}/reel/spotlight-reel.mp4` (9:16, h264 + AAC). Open it to review.

## Cost & timing
- Stills: ~free-ish (Gemini image, 5 calls). Voice: cheap (Gemini TTS, 5 calls).
- Video: Veo 3.1 Fast, 4 clips ≈ **$4–5** on the Google account. (Swap tier via
  `make_clips.py --model veo-3.1-generate-preview` for higher fidelity at higher cost.)
- Wall time: a few minutes (Veo is the long pole).

## Tuning
- Voice: `make_script.py --voice {Sulafat|Achird|...}` (Gemini voices), or edit `voice` in script.json + rerun `make_vo.py --force`.
- Captions / watermark / timing: constants at the top of `build_reel.py` and `reel_common.py`.
- Per-beat copy or visuals: edit `script.json` and rerun the affected phase.

## Delivery & automation
- **Deliver to Slack:** `python3 marketing/scripts/b2c/reel/deliver_reel.py --bundle marketing/aplus-content/{bundle}/`
  posts the reel into `#student-spotlight-ready` (header + video upload) for review.
  Pass `--thread-ts` to attach it to an existing spotlight thread.
- **Automatic:** the `aplus-spotlight-orchestrator` runs this whole pipeline as its
  `reel` stage on full runs (after Slack delivery). It's **non-fatal** (a Veo quota
  or ffmpeg error is logged, the run still completes) and gated by env
  `SPOTLIGHT_REEL` (default on; set `SPOTLIGHT_REEL=0` to skip). CI installs `ffmpeg`.
  The auto path uses the deterministic baseline script (no name, on-brand); run the
  manual Phase 1 refinement when a hero spotlight deserves a bespoke script.

## Approval gate
Like all B2C content, the finished reel goes to Paola for review before publishing.

## Related
- `aplus-spotlight-orchestrator` — the master case-study pipeline (drafts the data this reads)
- `aplus-b2c-brand-kit` — voice/colors applied in Phase 1
- `aplus-brand-check`, `aplus-fact-check` — Phase 2 gates
- `build-case-study-comic.py` — the independent static comic renderer (parallel sibling)
