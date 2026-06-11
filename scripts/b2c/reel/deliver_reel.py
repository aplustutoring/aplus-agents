#!/usr/bin/env python3
"""
deliver_reel.py — post a finished spotlight reel to #student-spotlight-ready for
Paola's review, reusing the shared Slack delivery helpers (same channel + upload
flow as the case study / graphics deliveries).

Usage:
  python3 scripts/b2c/reel/deliver_reel.py --bundle aplus-content/{bundle}/ \
      [--channel '#student-spotlight-ready'] [--thread-ts TS] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[3]
load_dotenv(REPO / ".env")
sys.path.insert(0, str(REPO / "scripts" / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import slack_delivery_common as sd          # noqa: E402
import reel_common as rc                      # noqa: E402

CHANNEL = "#student-spotlight-ready"


def upload_video(path, name):
    """Upload a video via Slack's external-upload flow, skipping the image-only
    resize in slack_delivery_common.upload_one_file."""
    size = Path(path).stat().st_size
    step1 = sd.slack_call("GET", "files.getUploadURLExternal",
                          params={"filename": name, "length": size})
    with open(path, "rb") as f:
        r = requests.post(step1["upload_url"], files={"file": (name, f)}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"upload bytes failed: HTTP {r.status_code} {r.text[:200]}")
    return step1["file_id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--thread-ts", default=None,
                    help="post into an existing thread (e.g. the case-study delivery)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reel = rc.output_path(args.bundle)
    if not reel.exists():
        sys.exit(f"reel not found: {reel} — build it first")

    bundle_name = Path(args.bundle).resolve().name
    secs = rc.dur(reel)
    header = ":movie_camera: *New animated Student Spotlight reel — ready for review*"
    comment = (f"Animated spotlight reel for *{bundle_name}* "
               f"({secs:.0f}s, 9:16 vertical, voiceover + captions, no student name).\n"
               f"CTA: *Book a consultation*, with a gentle link to more success stories.\n"
               f"For Paola's review before posting. :sparkles:")
    upload_name = f"{bundle_name}-spotlight-reel.mp4"

    print(f"Reel: {reel}\nChannel: {args.channel}")
    if args.dry_run:
        print("[dry-run] would post header + upload:")
        print(" header:", header)
        print(" comment:", comment)
        print(" file:", upload_name, f"({reel.stat().st_size} bytes)")
        return 0

    channel_id = sd.resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    thread_ts = args.thread_ts
    if not thread_ts:
        resp = sd.post_message(channel_id, header)
        thread_ts = resp.get("ts")
        print(f"  Header posted (ts={thread_ts})")

    file_id = upload_video(str(reel), upload_name)
    sd.complete_upload_to_channel([(file_id, upload_name)], channel_id, comment,
                                  thread_ts=thread_ts)
    print(f"  Uploaded {upload_name} -> thread {thread_ts}")
    print("Done. Open #student-spotlight-ready to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
