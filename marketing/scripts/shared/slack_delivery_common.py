#!/usr/bin/env python3
"""
Shared Slack delivery module for A+ Tutoring content engine.

Both the B2B weekly bundle delivery (deliver-to-slack.py) and the B2C case
study graphics delivery (deliver-case-study-graphics-to-slack.py) import from
here so the two channels look identical: same piece structure, same runbook
formatting, same upload flow.

PIECE SCHEMA (used by both B2B and B2C):
    {
        "name": "Instagram carousel",          # piece title
        "publish_window": "post this week",     # WHEN
        "destination": "instagram.com/aplustutoring",  # WHERE
        "body_text": "...",                      # OR
        "body_file": "linkedin-company.md",      # path relative to bundle
        "image_files": ["graphics/foo.png", ...],  # relative to bundle
    }

deliver_pieces() renders every piece identically: a header, then one
thread reply per piece with the runbook text + the graphics attached.
"""
import os
import sys
import json
import re
import tempfile
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
MAX_IMAGE_BYTES = 5_000_000
LOG_PATH = Path(__file__).parent / "slack-usage.log"


# ---------- Logging ----------

def log(action, status, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": str(status),
        "detail": str(detail)[:500],
    }
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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
    log(endpoint, r.status_code,
        body.get("error", "ok") if isinstance(body, dict) else "non-json")
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


def resolve_channel_id(channel_name_or_id):
    """Accept either a channel ID (C/G/D... 9-11 chars) or a #name and return the ID."""
    if re.fullmatch(r"[CGD][A-Z0-9]{8,10}", channel_name_or_id):
        return channel_name_or_id
    name = channel_name_or_id.lstrip("#")
    cursor = None
    while True:
        params = {"limit": 200, "exclude_archived": True,
                  "types": "public_channel,private_channel"}
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


# ---------- File handling ----------

def dated_filename(local_path, bundle_path):
    """Return {stem}-{YYYY-MM-DD}.{ext} derived from the bundle directory name."""
    p = Path(local_path)
    stem, ext = p.stem, p.suffix
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return p.name
    return f"{stem}-{m.group(1)}{ext}"


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


def upload_one_file(image_path, upload_name):
    """Upload a single file to Slack via the modern files API. Returns file_id."""
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
    """Finalize a multi-file upload, sharing to channel with one comment."""
    files_payload = json.dumps([{"id": fid, "title": title} for fid, title in file_ids_and_titles])
    payload = {
        "files": files_payload,
        "channel_id": channel,
        "initial_comment": initial_comment,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return slack_call("POST", "files.completeUploadExternal", data=payload)


# ---------- Markdown helpers ----------

def extract_body(md_path):
    """Strip frontmatter (everything before a `\\n---\\n`) and return the body."""
    text = Path(md_path).read_text()
    parts = text.split("\n---\n", 1)
    return (parts[1].strip() if len(parts) == 2 else text.strip())


def md_to_slack_mrkdwn(md):
    """Convert a small subset of markdown to Slack mrkdwn."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", md)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    text = re.sub(r"^##+ (.+)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text


def extract_block_scalar(text, field):
    """Extract a YAML block-scalar (field: | ...) handling 2-space indentation."""
    pat = rf"^{re.escape(field)}:\s*\|\s*\n((?:(?:  |\t).*\n?|\n)*)"
    m = re.search(pat, text, re.MULTILINE)
    if not m:
        return ""
    raw = m.group(1)
    lines = [re.sub(r"^(    |  )", "", line) for line in raw.split("\n")]
    return "\n".join(lines).strip()


# ---------- The unified piece renderer ----------

def resolve_pieces(pieces, bundle):
    """Filter PIECES down to deliverable pieces, attaching _present_images.

    A piece is deliverable if it has body_text OR a present body_file OR
    at least one present image.
    """
    effective = []
    for p in pieces:
        image_files = p.get("image_files", [])
        present = [bundle / f for f in image_files if (bundle / f).exists()]
        missing = [f for f in image_files if not (bundle / f).exists()]
        if missing:
            print(f"NOTE: {p['name']} — missing {len(missing)} image(s): {missing}",
                  file=sys.stderr)
        if "body_file" in p and not (bundle / p["body_file"]).exists():
            print(f"NOTE: {p['name']} — missing body file {p['body_file']}; skipping piece",
                  file=sys.stderr)
            continue
        if not present and "body_text" not in p and "body_file" not in p:
            print(f"NOTE: {p['name']} — no images and no body; skipping piece",
                  file=sys.stderr)
            continue
        effective.append({**p, "_present_images": present})
    return effective


def render_piece_comment(piece, bundle):
    """Build the runbook comment text for one piece, identical format B2B + B2C."""
    if "body_file" in piece:
        body = md_to_slack_mrkdwn(extract_body(bundle / piece["body_file"]))
    else:
        body = piece.get("body_text", "")
    intro_lines = [
        f":clipboard: *{piece['name']}*  _({piece['publish_window']})_",
        f"_Paste to: `{piece['destination']}`_",
        "",
        body,
    ]
    return "\n".join(intro_lines)


def deliver_pieces(channel_id, header_text, pieces, bundle, header_blocks=None):
    """Post the header, then each piece as a thread reply. Shared by B2B + B2C.

    Returns the header thread_ts.
    """
    if header_blocks is None:
        header_blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
            {"type": "divider"},
        ]
    print("\nPosting header...")
    header_resp = post_message(channel_id, header_text, blocks=header_blocks)
    header_ts = header_resp.get("ts")
    print(f"  Header ts: {header_ts}")

    for p in pieces:
        print(f"\nDelivering: {p['name']}")
        comment = render_piece_comment(p, bundle)
        present_images = p.get("_present_images", [])

        if not present_images:
            post_message(channel_id, comment, thread_ts=header_ts)
            print(f"  Posted text-only ({len(comment)} chars)")
            continue

        file_ids_titles = []
        for img_path in present_images:
            upload_name = dated_filename(img_path, bundle)
            file_id = upload_one_file(str(img_path), upload_name)
            file_ids_titles.append((file_id, upload_name))
            print(f"  Uploaded: {upload_name}")

        complete_upload_to_channel(file_ids_titles, channel_id, comment, thread_ts=header_ts)
        print(f"  Posted: {len(file_ids_titles)} image(s) + {len(comment)} chars")

    return header_ts
