#!/usr/bin/env python3
"""
build-case-study-textstory.py — one-shot animated text-message spotlight.

Each spotlight gets its OWN ~30s 9:16 episode: an invented, archetypal
Mom<->Dad text thread telling the case study's emotional arc, rendered
programmatically (headless Chromium + ffmpeg — NO image/video gen APIs).

Pipeline (each step is its own script under scripts/b2c/textstory/):
  1. make_scenes.py   bundle metadata + anonymized case study -> one Claude
                      call -> scenes.json (guardrails in the prompt, then
                      hard-validated: no real/pseudonym/school names, no
                      protected classifications, no 6-word verbatim overlap
                      with raw transcripts)
  2. render.py        scenes.json -> {bundle}/textstory/textstory.mp4
  3. deliver_textstory.py  (only with --deliver) -> #student-spotlight-ready

GUARDRAILS summary (full list in textstory_common.py): invented dialogue
only, generic contacts, generic messenger UI, our own SFX, end-card
disclosure baked into the template.

Usage:
    python3 scripts/b2c/build-case-study-textstory.py --bundle aplus-content/{bundle}/
    python3 scripts/b2c/build-case-study-textstory.py --bundle ... --deliver
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "textstory"


def run_step(name: str, cmd: list[str]) -> None:
    print(f"[textstory:{name}] ...")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"textstory {name} failed (exit {r.returncode})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--force-scenes", action="store_true",
                    help="regenerate scenes.json even if it exists")
    ap.add_argument("--deliver", action="store_true",
                    help="post the finished mp4 to Slack")
    ap.add_argument("--channel", default=None, help="override Slack channel")
    args = ap.parse_args()

    scenes_cmd = ["python3", str(HERE / "make_scenes.py"), "--bundle", args.bundle]
    if args.force_scenes:
        scenes_cmd.append("--force")
    run_step("scenes", scenes_cmd)
    run_step("render", ["python3", str(HERE / "render.py"), "--bundle", args.bundle])

    if args.deliver:
        dcmd = ["python3", str(HERE / "deliver_textstory.py"), "--bundle", args.bundle]
        if args.channel:
            dcmd.extend(["--channel", args.channel])
        run_step("deliver", dcmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
