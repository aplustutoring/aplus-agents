#!/usr/bin/env python3
"""
deliver_textstory.py — post the bundle's text-story episodes into Slack for
Paola's review, reusing the shared Slack delivery helpers (same channel +
upload flow as the rest of the case-study pack; video upload mirrors
scripts/b2c/reel/deliver_reel.py).

Posts one header, then uploads every requested dynamic's mp4 into that thread
(default: all that exist in the bundle).
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
DYNAMIC_LABEL = {
    "parents": "Parents (the war room)",
    "grandma": "Grandma (the voice notes)",
    "mom_friend": "Mom-friend (the referral)",
    "kid_parent": "Kid ↔ Mom (deadpan)",
    "family_group": "Family group chat (the pile-on)",
}


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
    ap.add_argument("--dynamics", default=None,
                    help="comma-separated dynamics to deliver (default: all present)")
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--thread-ts", default=None,
                    help="post into an existing thread (e.g. the case-study delivery)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dynamics:
        wanted = [d.strip() for d in args.dynamics.split(",") if d.strip()]
    else:
        wanted = list(tc.DYNAMICS)
    episodes = [(d, tc.output_path(args.bundle, d)) for d in wanted]
    episodes = [(d, p) for d, p in episodes if p.exists()]
    if not episodes:
        sys.exit(f"no textstory mp4s found in {tc.textstory_dir(args.bundle)} — render first")

    bundle_name = Path(args.bundle).resolve().name
    header = (":speech_balloon: *New text-story spotlights — ready for review*\n"
              f"*{bundle_name}* · {len(episodes)} episodes, same case arc in "
              f"{len(episodes)} relationship dynamics.\n"
              "9:16 vertical, invented archetypal dialogue — no real names, no "
              "transcript quotes. Each ends on the consultation CTA + disclosure. "
              "For Paola's review before posting. :sparkles:")

    print(f"Channel: {args.channel}")
    if args.dry_run:
        print("[dry-run] would post header + upload:")
        print(" header:", header)
        for d, p in episodes:
            print(f"  {d}: {p.name} ({p.stat().st_size} bytes, {dur(p):.0f}s)")
        return 0

    channel_id = sd.resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    thread_ts = args.thread_ts
    if not thread_ts:
        resp = sd.post_message(channel_id, header)
        thread_ts = resp.get("ts")
        print(f"  Header posted (ts={thread_ts})")

    for d, video in episodes:
        scenes = tc.load_scenes(args.bundle, d)
        label = DYNAMIC_LABEL.get(d, d)
        comment = (f"*{label}* — {dur(video):.0f}s · "
                   f"end card: \"{scenes.get('endcard', {}).get('line', '')}\"")
        upload_name = f"{bundle_name}-textstory-{d}.mp4"
        file_id = upload_video(str(video), upload_name)
        sd.complete_upload_to_channel([(file_id, upload_name)], channel_id, comment,
                                      thread_ts=thread_ts)
        print(f"  Uploaded {upload_name} -> thread {thread_ts}")
    print("Done. Open #student-spotlight-ready to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
