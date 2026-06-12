#!/usr/bin/env python3
"""
deliver_textstory.py — post {bundle}/textstory/textstory.mp4 into Slack for
Paola's review, reusing the shared Slack delivery helpers (same channel +
upload flow as the rest of the case-study pack; video upload mirrors
scripts/b2c/reel/deliver_reel.py).
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textstory_common as tc  # noqa: E402

sys.path.insert(0, str(tc.REPO / "scripts" / "shared"))
import requests  # noqa: E402
import slack_delivery_common as sd  # noqa: E402

CHANNEL = "#student-spotlight-ready"


def dur(path) -> float:
    out = subprocess.run(
        [tc.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def upload_video(path, name):
    """Slack external-upload flow, skipping the image-only resize in
    slack_delivery_common.upload_one_file."""
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

    video = tc.output_path(args.bundle)
    if not video.exists():
        sys.exit(f"textstory not found: {video} — render it first")

    bundle_name = Path(args.bundle).resolve().name
    scenes = tc.load_scenes(args.bundle)
    secs = dur(video)
    header = ":speech_balloon: *New text-story spotlight — ready for review*"
    comment = (f"Animated text-message spotlight for *{bundle_name}* "
               f"({secs:.0f}s, 9:16 vertical, invented archetypal dialogue — "
               f"no real names, no transcript quotes).\n"
               f"Contact variant: {scenes.get('contact', {}).get('name', '?')} · "
               f"End card: \"{scenes.get('endcard', {}).get('line', '')}\" + "
               f"consultation CTA + outcomes disclosure.\n"
               f"For Paola's review before posting. :sparkles:")
    upload_name = f"{bundle_name}-textstory.mp4"

    print(f"Textstory: {video}\nChannel: {args.channel}")
    if args.dry_run:
        print("[dry-run] would post header + upload:")
        print(" header:", header)
        print(" comment:", comment)
        print(" file:", upload_name, f"({video.stat().st_size} bytes)")
        return 0

    channel_id = sd.resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    thread_ts = args.thread_ts
    if not thread_ts:
        resp = sd.post_message(channel_id, header)
        thread_ts = resp.get("ts")
        print(f"  Header posted (ts={thread_ts})")

    file_id = upload_video(str(video), upload_name)
    sd.complete_upload_to_channel([(file_id, upload_name)], channel_id, comment,
                                  thread_ts=thread_ts)
    print(f"  Uploaded {upload_name} -> thread {thread_ts}")
    print("Done. Open #student-spotlight-ready to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
