#!/usr/bin/env python3
"""
make_clips.py — animate the reel's stills into clips via the DIRECT Gemini API
(Veo). Reads each beat's still + motion prompt from {bundle}/reel/script.json.
Veo returns ~8s clips; the assembler trims each to its narration length and
strips audio. Output -> {bundle}/reel/work/<key>.veo.mp4

Usage:  python3 scripts/b2c/reel/make_clips.py --bundle aplus-content/{bundle}/
                 [--only key ...] [--force] [--model veo-3.1-fast-generate-preview]
"""
import argparse
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from google.genai import errors

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel_common as rc

DEFAULT_MODEL = "veo-3.1-fast-generate-preview"
ASPECT, RESOLUTION, PERSON = "9:16", "720p", "allow_adult"
NEGATIVE = ("caption box, speech bubble, empty white banner, text, words, "
            "watermark, logo, letterbox, black bars, borders, style drift, "
            "morphing face, photorealistic, extra limbs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--only", nargs="*", help="subset of beat keys")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not rc.GEMINI_KEY:
        sys.exit("GEMINI_API_KEY not set")

    script = rc.load_script(args.bundle)
    sdir, work = rc.stills_dir(args.bundle), rc.work_dir(args.bundle)
    work.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=rc.GEMINI_KEY)
    cfg = types.GenerateVideosConfig(
        aspect_ratio=ASPECT, number_of_videos=1, resolution=RESOLUTION,
        negative_prompt=NEGATIVE, person_generation=PERSON)

    beats = [b for b in script["beats"]
             if (not args.only or b["key"] in args.only)
             and (args.force or not (work / f"{b['key']}.veo.mp4").exists())]
    if not beats:
        print("nothing to generate (all clips present)")
        return 0

    def submit(model, prompt, img):
        # Veo has tight rate limits; retry on 429 with backoff instead of
        # crashing (which would orphan already-submitted jobs).
        for attempt in range(6):
            try:
                return client.models.generate_videos(model=model, prompt=prompt,
                                                      image=img, config=cfg)
            except errors.ClientError as e:
                if getattr(e, "status_code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e):
                    wait = min(90, 20 * (attempt + 1))
                    print(f"  429 rate-limited; waiting {wait}s (attempt {attempt+1}/6)...", flush=True)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError("Veo submit failed after 6 retries (429). Try later.")

    ops = {}
    for i, b in enumerate(beats):
        still = sdir / f"{b['key']}.png"
        if not still.exists():
            sys.exit(f"missing still {still} — run make_stills.py")
        if i:
            time.sleep(8)   # space submissions to stay under the per-minute cap
        img = types.Image(image_bytes=still.read_bytes(), mime_type="image/png")
        op = submit(args.model, b["motion"], img)
        ops[b["key"]] = op
        print(f"submitted {b['key']}: {op.name}", flush=True)

    pending, fails = set(ops), []
    while pending:
        time.sleep(10)
        for key in list(pending):
            op = client.operations.get(ops[key]); ops[key] = op
            if not op.done:
                continue
            pending.discard(key)
            if getattr(op, "error", None):
                print(f"{key}: ERROR {op.error}", flush=True); fails.append(key); continue
            vids = getattr(op.response, "generated_videos", None) or []
            if not vids:
                print(f"{key}: NO VIDEO (safety/RAI). {op.response}", flush=True); fails.append(key); continue
            v = vids[0].video
            client.files.download(file=v)
            out = work / f"{key}.veo.mp4"
            v.save(str(out))
            print(f"{key}: saved {out.name} ({out.stat().st_size} bytes)", flush=True)
        if pending:
            print(f"  ...waiting on {sorted(pending)}", flush=True)
    print("clips done" + (f" WITH FAILURES {fails}" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
