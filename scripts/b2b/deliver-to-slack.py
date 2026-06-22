#!/usr/bin/env python3
"""
A+ Tutoring weekly bundle Slack delivery (v2 — 14-graphic edition).

Posts a header message to a Slack channel, then 8 threaded reply messages
covering every asset in the bundle:

  1. Blog assets gallery   (hero, social-card, creative-graphic, 3 pull-quotes)
  2. LinkedIn company post (text + carousel slide 1)
  3. LinkedIn carousel     (all 5 carousel slides as a gallery)
  4. Roman op-ed           (text + pull-quote s2 standalone)
  5. Danielle op-ed        (text + pull-quote s3 standalone)
  6. Instagram post        (text from instagram-post.md + image)
  7. Instagram story       (image only, no caption)
  8. Facebook post         (text + image)

Delivery only. The bot never publishes to LinkedIn, Facebook, or Instagram —
Danielle / Roman copy-paste each block from Slack into the destination
platform manually.
"""
import os
import sys
import json
import argparse
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
CHANNEL = "#weekly-content-ready"
PORTAL_ID = "6312752"
MAX_IMAGE_BYTES = 1_500_000  # resize anything larger so Slack uploads don't time out
LOG_PATH = Path(__file__).parent / "slack-usage.log"


def dated_filename(local_path, bundle_path):
    """Return {stem}-{YYYY-MM-DD}.{ext} derived from the bundle directory name."""
    p = Path(local_path)
    stem, ext = p.stem, p.suffix
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return p.name
    return f"{stem}-{m.group(1)}{ext}"


# ---------- Delivery structure ----------

# Each piece is one thread reply. The first body line is the title; the
# rest is the body content. "image_files" are paths relative to the bundle.
# Body sources: explicit text OR a path to a .md file in the bundle root.
# All graphic image_files paths are relative to {bundle}/graphics/.

# One main message per post (short header, NO images) + one threaded reply per
# deliverable, IN THIS ORDER. Every image lives in a reply, never the main message.
PIECES = [
    {
        "name": "Reply 1 — LinkedIn company post",
        "publish_window": "company page — after the blog is published",
        "destination": "A+ Tutoring LinkedIn company page",
        "body_file": "linkedin-company.md",
        "image_files": ["graphics/linkedin-carousel-slide-1-with-logo.png"],
    },
    {
        "name": "Reply 2 — Roman op-ed",
        "publish_window": "Roman's personal LinkedIn",
        "destination": "Roman's LinkedIn (personal)",
        "body_file": "roman-oped.md",
        "image_files": ["graphics/pull-quote-s1-with-logo.png"],
    },
    {
        "name": "Reply 3 — Danielle op-ed",
        "publish_window": "Danielle's personal LinkedIn",
        "destination": "Danielle's LinkedIn (personal)",
        "body_file": "danielle-oped.md",
        "image_files": ["graphics/pull-quote-s2-with-logo.png"],
    },
    {
        "name": "Reply 4 — LinkedIn carousel (PDF + 5 slides)",
        "publish_window": "attach to the company post (Reply 1)",
        "destination": "A+ Tutoring LinkedIn company page",
        "body_text": (
            ":clipboard: *LinkedIn carousel.* Upload the *PDF* (first file) as a document "
            "post on the company page — that's how LinkedIn renders a swipeable carousel. "
            "The 5 PNGs below are the same slides for preview.\n"
            ":bulb: Put the blog link in the *first comment*, not the post body — LinkedIn "
            "gives 2-3x more reach that way (same trick for the op-eds)."
        ),
        "extra_files": ["graphics/linkedin-carousel.pdf"],
        "image_files": [
            "graphics/linkedin-carousel-slide-1-with-logo.png",
            "graphics/linkedin-carousel-slide-2-with-logo.png",
            "graphics/linkedin-carousel-slide-3-with-logo.png",
            "graphics/linkedin-carousel-slide-4-with-logo.png",
            "graphics/linkedin-carousel-slide-5-with-logo.png",
        ],
    },
    {
        "name": "Reply 5 — Facebook + Instagram post",
        "publish_window": "post the SAME caption + image to both",
        "destination": "Facebook page + Instagram",
        "body_file": "fb-ig-post.md",
        "image_files": ["graphics/fb-ig-card-with-logo.png"],
    },
    {
        "name": "Reply 6 — Blog assets (reference)",
        "publish_window": "reference — already embedded in the HubSpot draft",
        "destination": "the HubSpot blog draft (link above)",
        "body_text": (
            ":clipboard: *Blog assets* — hero, social card, and the 2 inline pull-quotes. "
            "Already embedded in the HubSpot draft; here for reference."
        ),
        "image_files": [
            "graphics/hero.png",
            "graphics/social-card-with-logo.png",
            "graphics/pull-quote-s1-with-logo.png",
            "graphics/pull-quote-s2-with-logo.png",
        ],
    },
]
# B2B lives on LinkedIn — Instagram Story and Facebook (B2C/parents) pieces removed.


# ---------- Logging ----------

def log(action, status, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": str(status),
        "detail": str(detail)[:500],
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- Helpers ----------

def extract_body(md_path):
    """Each derivative file has a frontmatter block, then a `---` line,
    then the body. Return just the body."""
    text = Path(md_path).read_text()
    parts = text.split("\n---\n", 1)
    return (parts[1].strip() if len(parts) == 2 else text.strip())


def md_to_slack_mrkdwn(md):
    """Convert a small subset of markdown to Slack mrkdwn."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", md)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    return text


def ensure_under_size(image_path, max_bytes=MAX_IMAGE_BYTES):
    """Downsize image to a temp file if over max_bytes. Non-image files (e.g. the
    carousel PDF) pass through untouched."""
    src = Path(image_path)
    if src.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        return str(src)
    if src.stat().st_size <= max_bytes:
        return str(src)
    from PIL import Image
    img = Image.open(src)
    scale = 0.8
    tmp_path = Path(tempfile.gettempdir()) / f"slack-{src.name}"
    while True:
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        resized = img.resize(new_size, Image.LANCZOS)
        resized.save(tmp_path, format="PNG", optimize=True)
        if tmp_path.stat().st_size <= max_bytes or scale < 0.15:
            return str(tmp_path)
        scale *= 0.8


def extract_date_human(bundle_path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return m.group(1)


# ---------- Slack API ----------

def slack_call(method, endpoint, **kwargs):
    url = f"https://slack.com/api/{endpoint}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {SLACK_BOT_TOKEN}"
    r = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    try:
        body = r.json()
    except ValueError:
        body = {"raw_text": r.text}
    log(endpoint, r.status_code, body.get("error", "ok") if isinstance(body, dict) else "non-json")
    if r.status_code >= 400 or (isinstance(body, dict) and body.get("ok") is False):
        print(f"\nERROR Slack {endpoint} -> HTTP {r.status_code}: {body}", file=sys.stderr)
        raise RuntimeError(f"Slack API call failed: {endpoint}")
    return body


def auth_test():
    return slack_call("POST", "auth.test")


def post_message(channel, text, blocks=None, thread_ts=None):
    payload = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return slack_call("POST", "chat.postMessage",
                      json=payload,
                      headers={"Content-Type": "application/json; charset=utf-8"})


def upload_one_file(image_path, upload_name):
    """Upload a single file to Slack via the modern files API. Returns file_id.
    Does NOT share to a channel yet — caller does that via completeUploadExternal.
    """
    import time
    image_path = ensure_under_size(image_path)
    file_size = Path(image_path).stat().st_size

    # Retry transient upload timeouts. Each attempt gets a FRESH upload URL
    # (Slack upload URLs are single-use), so a timed-out POST can be re-driven.
    last_err = None
    for attempt in range(3):
        try:
            step1 = slack_call("GET", "files.getUploadURLExternal",
                               params={"filename": upload_name, "length": file_size})
            upload_url = step1["upload_url"]
            file_id = step1["file_id"]
            with open(image_path, "rb") as f:
                r = requests.post(upload_url, files={"file": (upload_name, f)}, timeout=180)
            if r.status_code == 200:
                log("upload_bytes", 200, upload_name)
                return file_id
            last_err = f"HTTP {r.status_code} {r.text[:200]}"
        except Exception as e:
            last_err = str(e)
        log("upload_retry", "warn", f"{upload_name} attempt {attempt + 1}: {last_err}")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Upload bytes failed for {upload_name} after 3 attempts: {last_err}")


def complete_upload_to_channel(file_ids_and_titles, channel, initial_comment, thread_ts=None):
    """Finalize a multi-file upload, sharing to channel with one comment.

    file_ids_and_titles: list of (file_id, title) tuples
    """
    files_payload = json.dumps([{"id": fid, "title": title} for fid, title in file_ids_and_titles])
    payload = {
        "files": files_payload,
        "channel_id": channel,
        "initial_comment": initial_comment,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return slack_call("POST", "files.completeUploadExternal", data=payload)


def resolve_channel_id(channel_name_or_id):
    """Accept either a channel ID (C/G/D... 9-11 chars) or a name and return the ID."""
    if re.fullmatch(r"[CGD][A-Z0-9]{8,10}", channel_name_or_id):
        return channel_name_or_id
    name = channel_name_or_id.lstrip("#")
    cursor = None
    while True:
        params = {"limit": 200, "exclude_archived": True, "types": "public_channel,private_channel"}
        if cursor:
            params["cursor"] = cursor
        body = slack_call("GET", "conversations.list", params=params)
        for ch in body.get("channels", []):
            if ch.get("name") == name:
                return ch["id"]
        cursor = body.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    # Fallback: probe via chat.postMessage
    probe = slack_call("POST", "chat.postMessage",
                       json={"channel": f"#{name}", "text": ":mag: probe"},
                       headers={"Content-Type": "application/json; charset=utf-8"})
    channel_id = probe.get("channel")
    if channel_id:
        ts = probe.get("ts")
        if ts:
            try:
                slack_call("POST", "chat.delete",
                           json={"channel": channel_id, "ts": ts},
                           headers={"Content-Type": "application/json; charset=utf-8"})
            except Exception:
                pass
        return channel_id
    raise RuntimeError(f"Channel {channel_name_or_id} not found.")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="Deliver an A+ weekly bundle (14-graphic edition) to Slack.")
    parser.add_argument("--bundle", required=True, help="Weekly bundle directory")
    parser.add_argument("--post-id", help="HubSpot post_id for the header link. Optional.")
    parser.add_argument("--channel", default=CHANNEL, help=f"Slack channel (default: {CHANNEL})")
    parser.add_argument("--dry-run", action="store_true", help="Validate everything, do not call Slack")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    # Resolve effective image_files for each piece — handle missing files gracefully
    # so we deliver what exists rather than failing on a missing carousel slide
    effective_pieces = []
    for p in PIECES:
        present = [bundle / f for f in p["image_files"] if (bundle / f).exists()]
        extra = [bundle / f for f in p.get("extra_files", []) if (bundle / f).exists()]
        missing = [f for f in p["image_files"] if not (bundle / f).exists()]
        if missing:
            print(f"NOTE: {p['name']} — missing {len(missing)} image(s): {missing}", file=sys.stderr)
        if "body_file" in p and not (bundle / p["body_file"]).exists():
            print(f"NOTE: {p['name']} — missing body file {p['body_file']}; skipping piece", file=sys.stderr)
            continue
        if not present and not extra and "body_text" not in p:
            print(f"NOTE: {p['name']} — no images and no body_text; skipping piece", file=sys.stderr)
            continue
        effective_pieces.append({**p, "_present_images": present, "_present_extra": extra})

    if not effective_pieces:
        print("ERROR: nothing deliverable in this bundle.", file=sys.stderr)
        return 1

    if not SLACK_BOT_TOKEN and not args.dry_run:
        print("ERROR: SLACK_BOT_TOKEN not set in .env. Run /mcp or add the token first.", file=sys.stderr)
        return 1

    date_str = extract_date_human(bundle) or "?"
    print(f"=== Bundle: {bundle} ({date_str}) ===")

    # Construct predicted blog URL deterministically from the slug in meta.
    # Available BEFORE HubSpot publish so Roman/Danielle can use it for the
    # Instagram link sticker and for any pre-publish references.
    predicted_blog_url = None
    headline = None
    meta_path = bundle / "blog-anchor-meta.md"
    if meta_path.exists():
        _meta = meta_path.read_text()
        m = re.search(r"^\s*url_slug:\s*(.+)$", _meta, re.MULTILINE)
        if m:
            predicted_blog_url = f"https://blog.wetutorathome.com/{m.group(1).strip().lstrip('/')}"
        hm = (re.search(r"^\s*h1_title:\s*(.+)$", _meta, re.MULTILINE)
              or re.search(r"^\s*html_title:\s*(.+)$", _meta, re.MULTILINE))
        if hm:
            headline = hm.group(1).strip().strip('"').strip("'")

    # Substitute {predicted_blog_url} placeholders in piece body_text strings
    # so the IG Story piece can reference the URL directly.
    if predicted_blog_url:
        for p in effective_pieces:
            if "body_text" in p:
                p["body_text"] = p["body_text"].replace("{predicted_blog_url}", predicted_blog_url)

    # Header — two clearly separated lanes so the reviewer never confuses the
    # blog (published FROM HubSpot, graphics embedded) with the LinkedIn pieces
    # (which need the actual image files DOWNLOADED + copy pasted into LinkedIn).
    # Short main message: title + the draft link + a one-line index of the thread.
    # NO images and no long copy here — every deliverable (with its images + text)
    # is a separate threaded reply below.
    title = headline or f"This week's content — {date_str}"
    header_lines = [f":newspaper: *{title}*  _({date_str})_", ""]
    if args.post_id:
        url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{args.post_id}/content"
        header_lines.append(f":memo: <{url}|Review &amp; publish the draft in HubSpot>")
    header_lines.append(
        f":thread: Everything to post is in the *thread below* — {len(effective_pieces)} replies, "
        "each with its copy + images:"
    )
    header_lines.append(
        "   " + "   ".join(
            f"*{i + 1})* {p['name'].split('— ', 1)[-1]}" for i, p in enumerate(effective_pieces)
        )
    )
    header_text = "\n".join(header_lines)

    # Dry-run preview
    print("\n=== Pieces ===")
    for p in effective_pieces:
        body_preview = ""
        if "body_file" in p:
            body_preview = md_to_slack_mrkdwn(extract_body(bundle / p["body_file"]))
        else:
            body_preview = p["body_text"]
        n_images = len(p["_present_images"])
        print(f"  - {p['name']}  ({n_images} images, {len(body_preview)} chars, -> {p['destination']})")

    if args.dry_run:
        print("\n=== DRY RUN — no Slack calls ===")
        print("\nHeader:\n" + header_text)
        return 0

    # Auth + channel
    print("\nVerifying Slack token...")
    me = auth_test()
    print(f"  Authed as bot: {me.get('user')} in workspace: {me.get('team')}")

    print(f"Resolving channel {args.channel}...")
    channel_id = resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    print("\nPosting header...")
    header_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "divider"},
    ]
    header_resp = post_message(channel_id, header_text, blocks=header_blocks)
    header_ts = header_resp.get("ts")
    print(f"  Header ts: {header_ts}")

    # Each piece as a thread reply — EXCEPT pieces flagged in_channel (e.g. the blog
    # assets gallery), which post to the channel so the visuals are visible at a glance.
    for p in effective_pieces:
        print(f"\nDelivering: {p['name']}")
        tt = None if p.get("in_channel") else header_ts
        # Build initial_comment
        if "body_file" in p:
            body = md_to_slack_mrkdwn(extract_body(bundle / p["body_file"]))
        else:
            body = p["body_text"]

        intro_lines = [
            f":clipboard: *{p['name']}*  _({p['publish_window']})_",
            f"_Paste to:_ `{p['destination']}`",
            "",
            body,
        ]
        comment = "\n".join(intro_lines)

        # Non-image extras (e.g. the LinkedIn carousel PDF) upload FIRST so they
        # sit at the top of the reply — that's the file the user actually uploads.
        attachments = list(p.get("_present_extra", [])) + p["_present_images"]
        if not attachments:
            # No files — just a chat message
            post_message(channel_id, body, thread_ts=tt)
            print(f"  Posted text-only ({len(body)} chars)")
            continue

        # Upload each file first, collect file IDs
        file_ids_titles = []
        for fpath in attachments:
            upload_name = dated_filename(fpath, bundle)
            file_id = upload_one_file(str(fpath), upload_name)
            file_ids_titles.append((file_id, upload_name))
            print(f"  Uploaded: {upload_name}")

        # Complete upload, sharing all files to channel/thread with one comment
        complete_upload_to_channel(file_ids_titles, channel_id, comment, thread_ts=tt)
        print(f"  Posted: {len(file_ids_titles)} file(s) + {len(body)} chars of body")

    print("\nDone. Open the channel in Slack to review.")
    log("delivery_complete", "ok", f"channel={args.channel} bundle={bundle} pieces={len(effective_pieces)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
