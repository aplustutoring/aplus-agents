#!/usr/bin/env python3
"""
A+ Tutoring case study GRAPHICS + captions Slack delivery (B2C).

Posts the full B2C social pack to #student-spotlight-ready for Paola, using
the SAME piece structure and formatting as the B2B weekly delivery
(deliver-to-slack.py). Both scripts import scripts/shared/slack_delivery_common.py
so the two channels look identical.

Pieces:
  1. Blog assets (reference — already in HubSpot draft)
  2. Instagram carousel (5 slides + caption + hashtags)
  3. Instagram Story (3 frames + posting steps)
  4. Facebook post (1 image + caption)

Companion to deliver-case-study-to-slack.py, which posts the header / Paola
feedback / bundle file list. Run that first, then this for the graphics.

Usage:
    cd ~/Desktop/aplus-marketing-skills
    python3 scripts/b2c/deliver-case-study-graphics-to-slack.py \\
        --bundle aplus-content/2026-05-21-case-study-gabriela/ \\
        [--dry-run]
"""
import sys
import re
import argparse
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
# Ensure shared helpers are importable from scripts/shared
sys.path.insert(0, str(_REPO / "scripts" / "shared"))
import slack_delivery_common as sd

CHANNEL = "#student-spotlight-ready"
PAOLA_USER_ID = "U094B5DRZBR"  # @-mention on the header so Paola gets a ping


def build_pieces(bundle, meta_text):
    """Build the B2C PIECES list, injecting captions from metadata.md."""
    ig_caption = sd.extract_block_scalar(meta_text, "instagram_caption")
    fb_caption = sd.extract_block_scalar(meta_text, "facebook_caption")

    slug_m = re.search(r"^\s*url_slug:\s*(.+)$", meta_text, re.MULTILINE)
    slug = slug_m.group(1).strip().lstrip("/") if slug_m else "gabriela-ilead"
    blog_url = f"https://blog.wetutorathome.com/case-study/{slug}"

    pieces = [
        {
            "name": "Blog assets (reference only)",
            "publish_window": "already in HubSpot draft",
            "destination": "blog.wetutorathome.com",
            "body_text": (
                ":clipboard: *Blog assets* — hero, social card, topic data viz, "
                "2 pull-quotes. These are already in the HubSpot draft. Shown "
                "here for reference only. No action needed unless Roman asks."
            ),
            "image_files": [
                "graphics/hero.png",
                "graphics/social-card-with-logo.png",
                "graphics/topic-graphic-with-logo.png",
                "graphics/pull-quote-s1-with-logo.png",
                "graphics/pull-quote-s2-with-logo.png",
            ],
        },
        {
            "name": "Instagram carousel (5 slides)",
            "publish_window": "post this week",
            "destination": "instagram.com/aplustutoring",
            "body_text": (
                ":clipboard: *Instagram carousel — 5 slides.*\n\n"
                "*How to post:*\n"
                "1. Open Instagram, tap + for a new post\n"
                "2. Select all 5 slides IN ORDER (slide 1 first)\n"
                "3. Paste the caption below exactly as written\n"
                "4. Make sure the blog link is in your bio (link in bio)\n"
                "5. Post\n\n"
                "*Caption (copy everything below this line):*\n\n"
                + (ig_caption or "_(no instagram_caption found in metadata.md)_")
            ),
            "image_files": [
                "graphics/instagram-carousel-slide-1-with-logo.png",
                "graphics/instagram-carousel-slide-2-with-logo.png",
                "graphics/instagram-carousel-slide-3-with-logo.png",
                "graphics/instagram-carousel-slide-4-with-logo.png",
                "graphics/instagram-carousel-slide-5-with-logo.png",
            ],
        },
        {
            "name": "Instagram Story (3 frames)",
            "publish_window": "post same day as carousel",
            "destination": "instagram.com/aplustutoring (story)",
            "body_text": (
                ":clipboard: *Instagram Story — 3-frame sequence.*\n\n"
                "*How to post:*\n"
                "1. Open Instagram Stories, upload the 3 frames IN ORDER\n"
                "2. On Frame 3 (the CTA frame): tap the sticker icon, choose Link sticker\n"
                f"3. Paste this link: {blog_url}\n"
                "4. Drag the link sticker to the upper third of Frame 3\n"
                "5. Post all 3 frames"
            ),
            "image_files": [
                "graphics/instagram-story-1.png",
                "graphics/instagram-story-2.png",
                "graphics/instagram-story-3.png",
            ],
        },
        {
            "name": "Facebook post (parents)",
            "publish_window": "post within 2 days",
            "destination": "facebook.com/WeTutorAtHome",
            "body_text": (
                ":clipboard: *Facebook post.*\n\n"
                "*How to post:*\n"
                "1. Open Facebook, create a new post on the A+ Tutoring page\n"
                "2. Upload the single image below\n"
                "3. Paste the caption below exactly as written\n"
                "4. Post (no hashtags on Facebook — they hurt reach)\n\n"
                "*Caption (copy everything below this line):*\n\n"
                + (fb_caption or "_(no facebook_caption found in metadata.md)_")
            ),
            "image_files": ["graphics/facebook-with-logo.png"],
        },
    ]
    return pieces


def main():
    ap = argparse.ArgumentParser(description="Deliver case study graphics + captions to Slack.")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    meta_path = bundle / "metadata.md"
    if not meta_path.exists():
        print(f"ERROR: metadata.md not found in {bundle}", file=sys.stderr)
        return 1
    meta_text = meta_path.read_text()

    pieces = build_pieces(bundle, meta_text)
    effective = sd.resolve_pieces(pieces, bundle)
    if not effective:
        print("ERROR: nothing deliverable.", file=sys.stderr)
        return 1

    header_text = (
        f":art: <@{PAOLA_USER_ID}> case study graphics + captions are ready.\n\n"
        "Each piece below has copy-paste-ready text and the images attached. "
        "Post them on your own schedule. No editing needed."
    )

    if args.dry_run:
        print("=== DRY RUN — no Slack calls ===\n")
        print(f"Channel: {args.channel}\n")
        print("HEADER:")
        print("=" * 60)
        print(header_text)
        print("=" * 60)
        for p in effective:
            print()
            print("=" * 60)
            print(sd.render_piece_comment(p, bundle))
            print("\nFILES:")
            for img in p["_present_images"]:
                print(f"  [OK] {img.name}")
        return 0

    if not sd.SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set in .env", file=sys.stderr)
        return 1

    print("Verifying Slack token...")
    me = sd.auth_test()
    print(f"  Authed as: {me.get('user')} in workspace: {me.get('team')}")
    print(f"Resolving channel {args.channel}...")
    channel_id = sd.resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    sd.deliver_pieces(channel_id, header_text, effective, bundle)

    print(f"\nDone. Open {args.channel} in Slack to review the graphics thread.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
