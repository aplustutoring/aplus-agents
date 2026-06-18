#!/usr/bin/env python3
"""
A+ Tutoring Student Spotlight — UNIFIED Slack delivery (B2C).

Posts a single thread to #student-spotlight-ready, structured exactly like the
B2B weekly delivery (deliver-to-slack.py):

  HEADER (one short message, no images):
    - spotlight title + date
    - student pseudonym @ school + case pattern
    - HubSpot draft link (Review & publish)
    - predicted public blog URL
    - Gate 2 review items
    - a :thread: numbered index of every reply

  THREAD REPLIES (one per deliverable, IN ORDER), each with its copy + images:
    Reply 1 — Instagram carousel (5 slides)
    Reply 2 — Instagram Story (3 frames)
    Reply 3 — Facebook post (parents)
    Reply 4 — Comic (5 feed posts, 4:5)
    Reply 5 — Comic (5 Story frames, 9:16)
    Reply 6 — Blog assets (reference — already in HubSpot draft)
    Reply 7 — Paola intake feedback (internal — not for posting)

This is the ONLY Slack delivery script the spotlight orchestrator calls. It
replaces the former two-thread split (deliver-case-study-to-slack.py for text +
this script for graphics). Both B2B and B2C import scripts/shared/
slack_delivery_common.py so the two channels look identical.

Usage:
    cd ~/Desktop/aplus-marketing-skills
    python3 scripts/b2c/deliver-case-study-graphics-to-slack.py \\
        --bundle aplus-content/2026-05-21-case-study-gabriela/ \\
        --post-id 213647971614 \\
        [--dry-run]
"""
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

_REPO = Path(__file__).resolve().parents[2]
# Ensure shared helpers are importable from scripts/shared
sys.path.insert(0, str(_REPO / "scripts" / "shared"))
import slack_delivery_common as sd

CHANNEL = "#student-spotlight-ready"
PORTAL_ID = "6312752"
PAOLA_USER_ID = "U094B5DRZBR"  # @-mention on the header so Paola gets a ping


# ---------- Case metadata + Gate 2 extraction (ported from text delivery) ----------

def extract_case_metadata(bundle_path):
    """Pull case study metadata for the header summary."""
    meta = {"pseudonym": "", "school": "", "title": "", "slug": "", "case_pattern": ""}
    metadata_path = bundle_path / "metadata.md"
    if metadata_path.exists():
        text = metadata_path.read_text()
        block = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
        if block:
            for line in block.group(1).split("\n"):
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "h1_title":
                    meta["title"] = val
                elif key == "url_slug":
                    meta["slug"] = val
                elif key == "case_pattern":
                    meta["case_pattern"] = val
                elif key == "school_named":
                    meta["school"] = val
        if meta["slug"] and "-" in meta["slug"]:
            meta["pseudonym"] = meta["slug"].split("-")[0].capitalize()
        elif meta["slug"]:
            meta["pseudonym"] = meta["slug"].capitalize()
    return meta


def extract_gate_2_items(bundle_path):
    """Pull the Gate 2 judgment items from bundle-summary.md."""
    summary_path = bundle_path / "bundle-summary.md"
    if not summary_path.exists():
        return []
    text = summary_path.read_text()
    section = re.search(
        r"##\s+Items needing Gate 2.*?\n(.*?)(?=\n##\s|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return []
    items = re.findall(r"^\d+\.\s+\*\*([^*]+?)\*\*", section.group(1), re.MULTILINE)
    cleaned, seen = [], set()
    for it in items:
        it = it.strip()
        if it and it not in seen:
            seen.add(it)
            cleaned.append(it)
    return cleaned


def extract_date_human(bundle_path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return "?"
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return m.group(1)


# ---------- Pieces ----------

def build_pieces(bundle, meta_text, blog_url):
    """Build the numbered B2C PIECES list, injecting captions from metadata.md.

    Social-first order: the things Paola actually posts come first, reference
    material (blog assets) and internal notes (Paola feedback) come last.
    """
    ig_caption = sd.extract_block_scalar(meta_text, "instagram_caption")
    fb_caption = sd.extract_block_scalar(meta_text, "facebook_caption")

    pieces = [
        {
            "name": "Reply 1 — Instagram carousel (5 slides)",
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
            "name": "Reply 2 — Instagram Story (3 frames)",
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
            "name": "Reply 3 — Facebook post (parents)",
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
        {
            "name": "Reply 4 — Comic (5 feed posts, 4:5)",
            "publish_window": "post this week",
            "destination": "instagram.com/aplustutoring (feed)",
            "body_text": (
                ":comic: *Comic — 5-beat hero story (feed, 4:5).*\n\n"
                "A fictional hero version of the student's journey (struggle -> "
                "help -> breakthrough -> win -> CTA). Post as 5 individual posts "
                "or a carousel, in order.\n"
                "_Hero is a generic archetype, not the real child._"
            ),
            "image_files": [
                "graphics/comic-1-struggle.png",
                "graphics/comic-2-sidekick.png",
                "graphics/comic-3-breakthrough.png",
                "graphics/comic-4-win.png",
                "graphics/comic-5-cta.png",
            ],
        },
        {
            "name": "Reply 5 — Comic (5 Story frames, 9:16)",
            "publish_window": "post same week",
            "destination": "instagram.com/aplustutoring (story)",
            "body_text": (
                ":comic: *Comic — Story version (9:16, 5 frames.)*\n\n"
                "*How to post:*\n"
                "1. Open Instagram Stories, upload the 5 frames IN ORDER\n"
                "2. On Frame 5 (the CTA): add a Link sticker to the consultation "
                "page, dragged to the upper third\n"
                "3. Post all 5"
            ),
            "image_files": [
                "graphics/comic-story-1-struggle.png",
                "graphics/comic-story-2-sidekick.png",
                "graphics/comic-story-3-breakthrough.png",
                "graphics/comic-story-4-win.png",
                "graphics/comic-story-5-cta.png",
            ],
        },
        {
            "name": "Reply 6 — Blog assets (reference only)",
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
            "name": "Reply 7 — Paola intake feedback",
            "publish_window": "internal — for the next case study",
            "destination": "internal — not for posting",
            "body_file": "paola-feedback.md",
            "image_files": [],
        },
    ]
    return pieces


def build_header(bundle, meta, gate_2, post_id, blog_url, n_pieces, piece_names):
    """B2B-style header: title + student + draft link + Gate 2 + thread index."""
    date_str = extract_date_human(bundle)
    title = meta["title"] or f"New Student Spotlight — {date_str}"

    lines = [f":star: <@{PAOLA_USER_ID}> *New Student Spotlight — {title}*  _({date_str})_", ""]

    student_line = ":bust_in_silhouette: *Student:* "
    student_line += f"{meta['pseudonym'] or '(pseudonym)'} (pseudonym)"
    if meta["school"]:
        student_line += f" at {meta['school']}"
    lines.append(student_line)
    if meta["case_pattern"]:
        lines.append(f":memo: *Case pattern:* {meta['case_pattern']}")

    if post_id:
        url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{post_id}/content"
        lines.append(f":pencil2: <{url}|Review &amp; publish the draft in HubSpot>")
    else:
        lines.append(":pencil2: *HubSpot draft:* (no post-id provided)")
    if blog_url:
        lines.append(f":link: *URL when published:* <{blog_url}|{blog_url}>")

    lines.append("")
    lines.append(":pushpin: *Gate 2 — items needing Roman + Danielle review:*")
    if gate_2:
        for i, item in enumerate(gate_2, 1):
            lines.append(f"{i}. {item.strip()}")
    else:
        lines.append("_(no Gate 2 items extracted from bundle-summary.md)_")

    lines.append("")
    lines.append(
        f":thread: Everything to post is in the *thread below* — {n_pieces} replies, "
        "each with its copy + images:"
    )
    lines.append(
        "   " + "   ".join(
            f"*{i + 1})* {name.split('— ', 1)[-1]}" for i, name in enumerate(piece_names)
        )
    )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Deliver a Student Spotlight bundle to Slack (unified B2B-style thread).")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--post-id", help="HubSpot post_id for the header draft link.")
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

    case_meta = extract_case_metadata(bundle)
    gate_2 = extract_gate_2_items(bundle)

    blog_url = None
    if case_meta["slug"]:
        blog_url = f"https://blog.wetutorathome.com/case-study/{case_meta['slug'].lstrip('/')}"

    pieces = build_pieces(bundle, meta_text, blog_url or "https://blog.wetutorathome.com/case-study/")
    effective = sd.resolve_pieces(pieces, bundle)
    if not effective:
        print("ERROR: nothing deliverable.", file=sys.stderr)
        return 1

    header_text = build_header(
        bundle, case_meta, gate_2, args.post_id, blog_url,
        len(effective), [p["name"] for p in effective],
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
            if not p["_present_images"]:
                print("  (text-only)")
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

    header_ts = sd.deliver_pieces(channel_id, header_text, effective, bundle)

    print(f"\nDone. Open {args.channel} in Slack to review the spotlight thread.")
    # Emit the thread ts so the orchestrator can nest the reel + text-stories
    # under this same per-student thread.
    if header_ts:
        print(f"THREAD_TS={header_ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
