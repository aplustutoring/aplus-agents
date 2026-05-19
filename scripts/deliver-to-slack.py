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

SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
CHANNEL = "#weekly-content-ready"
PORTAL_ID = "6312752"
MAX_IMAGE_BYTES = 5_000_000
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

PIECES = [
    {
        "name": "Blog assets gallery",
        "publish_window": "Thursday AM publish",
        "destination": "blog.wetutorathome.com",
        "body_text": (
            ":clipboard: *Blog assets* — hero, social card, data-viz graphic, "
            "3 inline pull-quotes. All 6 below."
        ),
        "image_files": [
            "graphics/hero.png",
            "graphics/social-card-with-logo.png",
            "graphics/creative-graphic-with-logo.png",
            "graphics/pull-quote-s1-with-logo.png",
            "graphics/pull-quote-s2-with-logo.png",
            "graphics/pull-quote-s3-with-logo.png",
        ],
    },
    {
        "name": "LinkedIn company post",
        "publish_window": "Thursday PM",
        "destination": "linkedin.com/company/aplus-tutoring",
        "body_file": "linkedin-company.md",
        "image_files": ["graphics/linkedin-carousel-slide-1-with-logo.png"],
    },
    {
        "name": "LinkedIn carousel (5 slides)",
        "publish_window": "Thursday PM (attach to company post above)",
        "destination": "linkedin.com/company/aplus-tutoring",
        "body_text": (
            ":clipboard: *Full LinkedIn carousel* — 5 slides, upload as a single "
            "PDF or sequential image carousel in the LinkedIn composer."
        ),
        "image_files": [
            "graphics/linkedin-carousel-slide-1-with-logo.png",
            "graphics/linkedin-carousel-slide-2-with-logo.png",
            "graphics/linkedin-carousel-slide-3-with-logo.png",
            "graphics/linkedin-carousel-slide-4-with-logo.png",
            "graphics/linkedin-carousel-slide-5-with-logo.png",
        ],
    },
    {
        "name": "Roman op-ed",
        "publish_window": "Friday AM",
        "destination": "linkedin.com/in/romanslavinsky",
        "body_file": "roman-oped.md",
        "image_files": ["graphics/pull-quote-s2-with-logo.png"],
    },
    {
        "name": "Danielle op-ed",
        "publish_window": "Monday AM (post-Memorial Day)",
        "destination": "Danielle's personal LinkedIn",
        "body_file": "danielle-oped.md",
        "image_files": ["graphics/pull-quote-s3-with-logo.png"],
    },
    {
        "name": "Instagram post",
        "publish_window": "Monday PM",
        "destination": "instagram.com/aplustutoring",
        "body_file": "instagram-post.md",
        "image_files": ["graphics/instagram-post.png"],
    },
    {
        "name": "Instagram story",
        "publish_window": "Monday or Tuesday — story is 24hr",
        "destination": "instagram.com/aplustutoring (story)",
        "body_text": (
            ":clipboard: *Instagram Story image* — Stories take no caption in the "
            "composer; add stickers / link / poll in Instagram itself."
        ),
        "image_files": ["graphics/instagram-story.png"],
    },
    {
        "name": "Facebook post (B2C, parents)",
        "publish_window": "Monday PM",
        "destination": "facebook.com/aplustutoring",
        "body_file": "facebook.md",
        "image_files": ["graphics/facebook.png"],
    },
]


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
    """Downsize image to a temp file if over max_bytes."""
    src = Path(image_path)
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
    headers["Authorization"] = f"Bearer {SLACK_TOKEN}"
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
    image_path = ensure_under_size(image_path)
    file_size = Path(image_path).stat().st_size

    step1 = slack_call("GET", "files.getUploadURLExternal",
                       params={"filename": upload_name, "length": file_size})
    upload_url = step1["upload_url"]
    file_id = step1["file_id"]

    with open(image_path, "rb") as f:
        r = requests.post(upload_url, files={"file": (upload_name, f)}, timeout=120)
    log("upload_bytes", r.status_code, upload_name)
    if r.status_code != 200:
        raise RuntimeError(f"Upload bytes failed for {upload_name}: HTTP {r.status_code} {r.text[:300]}")
    return file_id


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
        missing = [f for f in p["image_files"] if not (bundle / f).exists()]
        if missing:
            print(f"NOTE: {p['name']} — missing {len(missing)} image(s): {missing}", file=sys.stderr)
        if "body_file" in p and not (bundle / p["body_file"]).exists():
            print(f"NOTE: {p['name']} — missing body file {p['body_file']}; skipping piece", file=sys.stderr)
            continue
        if not present and "body_text" not in p:
            print(f"NOTE: {p['name']} — no images and no body_text; skipping piece", file=sys.stderr)
            continue
        effective_pieces.append({**p, "_present_images": present})

    if not effective_pieces:
        print("ERROR: nothing deliverable in this bundle.", file=sys.stderr)
        return 1

    if not SLACK_TOKEN and not args.dry_run:
        print("ERROR: SLACK_BOT_TOKEN not set in .env. Run /mcp or add the token first.", file=sys.stderr)
        return 1

    date_str = extract_date_human(bundle) or "?"
    print(f"=== Bundle: {bundle} ({date_str}) ===")

    # Header
    header_lines = [f":package: *Weekly content bundle ready  -  {date_str}*"]
    if args.post_id:
        url = f"https://app.hubspot.com/blog/{PORTAL_ID}/edit/{args.post_id}"
        header_lines.append(f":memo: HubSpot blog draft: <{url}|Review and publish>")
    else:
        header_lines.append(":memo: HubSpot blog draft: (no --post-id provided)")
    header_lines.append("")
    header_lines.append(
        f":pushpin: {len(effective_pieces)} deliveries below — copy each block into the destination platform at the suggested time."
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

    # Each piece as thread reply
    for p in effective_pieces:
        print(f"\nDelivering: {p['name']}")
        # Build initial_comment
        if "body_file" in p:
            body = md_to_slack_mrkdwn(extract_body(bundle / p["body_file"]))
        else:
            body = p["body_text"]

        intro_lines = [
            f":clipboard: *{p['name']}*  _({p['publish_window']})_",
            f"_Paste to: `{p['destination']}`_",
            "",
            body,
        ]
        comment = "\n".join(intro_lines)

        if not p["_present_images"]:
            # No images — just a chat message
            post_message(channel_id, body, thread_ts=header_ts)
            print(f"  Posted text-only ({len(body)} chars)")
            continue

        # Upload each image first, collect file IDs
        file_ids_titles = []
        for img_path in p["_present_images"]:
            upload_name = dated_filename(img_path, bundle)
            file_id = upload_one_file(str(img_path), upload_name)
            file_ids_titles.append((file_id, upload_name))
            print(f"  Uploaded: {upload_name}")

        # Complete upload, sharing all files to channel/thread with one comment
        complete_upload_to_channel(file_ids_titles, channel_id, comment, thread_ts=header_ts)
        print(f"  Posted: {len(file_ids_titles)} image(s) + {len(body)} chars of body")

    print("\nDone. Open the channel in Slack to review.")
    log("delivery_complete", "ok", f"channel={args.channel} bundle={bundle} pieces={len(effective_pieces)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
