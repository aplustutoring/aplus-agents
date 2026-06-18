#!/usr/bin/env python3
"""
build-case-study-textstory.py — animated text-message spotlights per case.

Each spotlight gets several ~30s 9:16 episodes, all from the SAME case arc told
through different relationship dynamics (sender pairings / voices). Shipping
set (DEFAULT_DYNAMICS): parents · grandma · mom_friend · kid_parent.
family_group is also supported (--only family_group) but off by default.

All rendered programmatically (headless Chromium + ffmpeg — NO image/video gen
APIs). Per dynamic the pipeline is:
  1. make_scenes.py  --dynamic D  ->  scenes-D.json  (one Claude call, guardrails
                     in the prompt + hard-validated: no real/pseudonym/school
                     names, no protected classifications, no 6-word verbatim
                     transcript overlap, kid lines kept sparse + non-salesy)
  2. render.py       --dynamic D  ->  {bundle}/textstory/textstory-D.mp4
  3. deliver_textstory.py (only with --deliver) -> #student-spotlight-ready

GUARDRAILS summary (full list in textstory_common.py): invented dialogue only,
generic/role-based contacts, generic messenger UI, our own SFX, end-card
disclosure baked into the template.

Usage:
    python3 scripts/b2c/build-case-study-textstory.py --bundle <bundle>
    python3 scripts/b2c/build-case-study-textstory.py --bundle <bundle> --deliver
    python3 scripts/b2c/build-case-study-textstory.py --bundle <bundle> --only grandma,kid_parent
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "textstory"
sys.path.insert(0, str(HERE))
import textstory_common as tc  # noqa: E402


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"[textstory:{name}] ...")
    return subprocess.run(cmd).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of dynamics "
                         "(default: the 4 shipping dynamics; family_group is "
                         "supported but must be requested explicitly)")
    ap.add_argument("--force-scenes", action="store_true",
                    help="regenerate scene JSON even if it exists")
    ap.add_argument("--keep-work", action="store_true",
                    help="keep render work/ intermediates for debugging")
    ap.add_argument("--deliver", action="store_true",
                    help="post the finished mp4s to Slack")
    ap.add_argument("--channel", default=None, help="override Slack channel")
    ap.add_argument("--thread-ts", default=None,
                    help="nest the delivery under an existing Slack thread")
    args = ap.parse_args()

    if args.only:
        dynamics = [d.strip() for d in args.only.split(",") if d.strip()]
        bad = [d for d in dynamics if d not in tc.DYNAMICS]
        if bad:
            sys.exit(f"unknown dynamic(s): {bad}; valid: {tc.DYNAMICS}")
    else:
        dynamics = list(tc.DEFAULT_DYNAMICS)

    built, failed = [], []
    for d in dynamics:
        print(f"\n=== dynamic: {d} ===")
        scenes_cmd = ["python3", str(HERE / "make_scenes.py"),
                      "--bundle", args.bundle, "--dynamic", d]
        if args.force_scenes:
            scenes_cmd.append("--force")
        if not run_step(f"{d}:scenes", scenes_cmd):
            failed.append(d)
            continue
        render_cmd = ["python3", str(HERE / "render.py"),
                      "--bundle", args.bundle, "--dynamic", d]
        if args.keep_work:
            render_cmd.append("--keep-work")
        if not run_step(f"{d}:render", render_cmd):
            failed.append(d)
            continue
        built.append(d)

    if args.deliver and built:
        dcmd = ["python3", str(HERE / "deliver_textstory.py"),
                "--bundle", args.bundle, "--dynamics", ",".join(built)]
        if args.channel:
            dcmd.extend(["--channel", args.channel])
        if args.thread_ts:
            dcmd.extend(["--thread-ts", args.thread_ts])
        run_step("deliver", dcmd)

    print(f"\ntextstory: built {built or '[]'}"
          + (f", FAILED {failed}" if failed else ""))
    # non-zero only if everything failed (a single dynamic failing is tolerable)
    return 0 if built else 1


if __name__ == "__main__":
    sys.exit(main())
