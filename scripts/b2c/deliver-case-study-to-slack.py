#!/usr/bin/env python3
"""
A+ Tutoring case study Slack delivery.

Posts a case study bundle to the #student-spotlight-ready channel:

  1. Header: case title + HubSpot draft link + 6 Gate 2 judgment items
  2. Thread reply: Paola feedback (3 sections — kept doing, missing, suggestion)
  3. Thread reply: bundle file list with brief descriptions

Mirrors the pattern from deliver-to-slack.py (weekly bundle) but trimmed for
case studies. Text-only delivery — no graphics until Phase 4 ships the
case-study graphics pipeline.

Usage:
    python3 scripts/b2c/deliver-case-study-to-slack.py \\
        --bundle aplus-content/2026-05-21-case-study-gabriela/ \\
        --post-id 213647971614

    python3 scripts/b2c/deliver-case-study-to-slack.py \\
        --bundle aplus-content/2026-05-21-case-study-gabriela/ \\
        --post-id 213647971614 \\
        --dry-run
"""
import os
import sys
import json
import argparse
import re
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL = "#student-spotlight-ready"
PORTAL_ID = "6312752"
LOG_PATH = Path(__file__).parent / "slack-case-study-usage.log"


def log(action, status, detail=""):
    """Append a JSONL line to the usage log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": status,
        "detail": str(detail)[:500],
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def auth_headers():
    return {"Authorization": f"Bearer {SLACK_TOKEN}"}


def auth_test():
    """Verify the bot token works."""
    r = requests.post(
        "https://slack.com/api/auth.test",
        headers=auth_headers(),
        timeout=20,
    )
    data = r.json()
    if not data.get("ok"):
        print(f"ERROR: Slack auth failed: {data}", file=sys.stderr)
        sys.exit(1)
    return data


def resolve_channel_id(channel_name):
    """Look up a channel ID from a #name."""
    name = channel_name.lstrip("#")
    cursor = ""
    for _ in range(10):  # paginate up to 10 pages
        params = {"limit": 200, "exclude_archived": "true", "types": "public_channel,private_channel"}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            "https://slack.com/api/conversations.list",
            headers=auth_headers(),
            params=params,
            timeout=20,
        )
        data = r.json()
        if not data.get("ok"):
            print(f"ERROR: conversations.list failed: {data}", file=sys.stderr)
            sys.exit(1)
        for ch in data.get("channels", []):
            if ch.get("name") == name:
                return ch.get("id")
        cursor = data.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
    print(f"ERROR: channel #{name} not found in workspace.", file=sys.stderr)
    sys.exit(1)


def post_message(channel_id, text, thread_ts=None, blocks=None):
    """Post a chat message; optionally as a thread reply."""
    payload = {
        "channel": channel_id,
        "text": text,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    if blocks:
        payload["blocks"] = blocks
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    data = r.json()
    if not data.get("ok"):
        print(f"ERROR: chat.postMessage failed: {data}", file=sys.stderr)
        log("post_message", "fail", json.dumps(data)[:400])
        sys.exit(1)
    log("post_message", "ok", f"channel={channel_id} ts={data.get('ts')}")
    return data


def extract_case_metadata(bundle_path):
    """Pull case study metadata for the header summary."""
    meta = {
        "pseudonym": "",
        "school": "",
        "title": "",
        "slug": "",
        "case_pattern": "",
    }
    metadata_path = bundle_path / "metadata.md"
    if metadata_path.exists():
        text = metadata_path.read_text()
        # Look for fenced block
        block = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
        if block:
            for line in block.group(1).split("\n"):
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "h1_title":
                    meta["title"] = val
                elif key == "url_slug":
                    meta["slug"] = val
                elif key == "case_pattern":
                    meta["case_pattern"] = val
                elif key == "school_named":
                    meta["school"] = val
        # Pseudonym is the first word of the slug
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
    # Find the section that lists Gate 2 items
    section = re.search(
        r"##\s+Items needing Gate 2.*?\n(.*?)(?=\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section:
        return []
    # Each item is a numbered list line starting with "1. ", "2. ", etc.
    # Each item is a numbered list line. Bundle-summary uses bold titles
    # ("**...**") OR plain numbered items. Capture either.
    items = re.findall(
        r"^\d+\.\s+\*\*([^*]+?)\*\*",
        section.group(1),
        re.MULTILINE,
    )
    # Strip and dedupe while preserving order
    cleaned = []
    seen = set()
    for it in items:
        it = it.strip()
        if it and it not in seen:
            seen.add(it)
            cleaned.append(it)
    return cleaned


def extract_paola_feedback(bundle_path):
    """Read paola-feedback.md and return the body text."""
    fb_path = bundle_path / "paola-feedback.md"
    if not fb_path.exists():
        return None
    return fb_path.read_text()


def md_to_slack(text):
    """Simple markdown to Slack mrkdwn. Headings -> bold lines, **bold** -> *bold*."""
    # Slack uses *bold* not **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # ## Heading -> *Heading*
    text = re.sub(r"^##+ (.+)$", r"*\1*", text, flags=re.MULTILINE)
    # # Heading -> *Heading*
    text = re.sub(r"^# (.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text


def list_bundle_files(bundle_path):
    """Return a list of (filename, size) tuples for files in the bundle."""
    files = []
    for f in sorted(bundle_path.iterdir()):
        if f.is_file() and f.suffix == ".md":
            files.append((f.name, f.stat().st_size))
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Deliver a case study bundle to Slack."
    )
    parser.add_argument("--bundle", required=True, help="Case study bundle directory")
    parser.add_argument("--post-id", help="HubSpot post_id for the draft link")
    parser.add_argument("--channel", default=CHANNEL, help=f"Slack channel (default: {CHANNEL})")
    parser.add_argument("--dry-run", action="store_true", help="Validate, don't post to Slack")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    if not SLACK_TOKEN and not args.dry_run:
        print("ERROR: SLACK_BOT_TOKEN not set in .env", file=sys.stderr)
        return 1

    # Gather all the content
    case_meta = extract_case_metadata(bundle)
    gate_2 = extract_gate_2_items(bundle)
    paola_feedback = extract_paola_feedback(bundle)
    bundle_files = list_bundle_files(bundle)

    # Predicted blog URL
    predicted_blog_url = None
    if case_meta["slug"]:
        predicted_blog_url = f"https://blog.wetutorathome.com/case-study/{case_meta['slug']}"

    # HubSpot draft URL
    hubspot_url = None
    if args.post_id:
        hubspot_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{args.post_id}/content"

    # Date string
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle))
    date_str = m.group(1) if m else "?"

    # --- Build header ---
    header_lines = [
        f":star: *New Student Spotlight Case Study Ready  -  {date_str}*",
        "",
        f":bust_in_silhouette: *Student:* {case_meta['pseudonym']} (pseudonym) at {case_meta['school']}",
        f":memo: *Case pattern:* {case_meta['case_pattern']}",
        f":page_facing_up: *Title:* {case_meta['title']}",
    ]
    if hubspot_url:
        header_lines.append(f":pencil2: *HubSpot draft:* <{hubspot_url}|Review and publish>")
    else:
        header_lines.append(":pencil2: *HubSpot draft:* (no post-id provided)")
    if predicted_blog_url:
        header_lines.append(f":link: *URL when published:* <{predicted_blog_url}|{predicted_blog_url}>")
    header_lines.append("")
    header_lines.append(":pushpin: *Gate 2 — items needing Roman + Danielle review:*")
    if gate_2:
        for i, item in enumerate(gate_2, 1):
            header_lines.append(f"{i}. {item.strip()}")
    else:
        header_lines.append("_(no Gate 2 items extracted from bundle-summary.md)_")
    header_lines.append("")
    header_lines.append(":speech_balloon: Replies below: Paola intake feedback + bundle file list")
    header_text = "\n".join(header_lines)

    # --- Dry run preview ---
    if args.dry_run:
        print("=== DRY RUN — no Slack calls ===\n")
        print(f"Channel: {args.channel}\n")
        print("HEADER:")
        print("=" * 60)
        print(header_text)
        print("=" * 60)
        print("\n\nPAOLA FEEDBACK (thread reply 1):")
        print("=" * 60)
        if paola_feedback:
            print(md_to_slack(paola_feedback)[:1200] + "..." if len(paola_feedback) > 1200 else md_to_slack(paola_feedback))
        else:
            print("(no paola-feedback.md found in bundle)")
        print("=" * 60)
        print("\n\nBUNDLE FILES (thread reply 2):")
        print("=" * 60)
        for fname, size in bundle_files:
            print(f"  - {fname}  ({size:,} bytes)")
        return 0

    # --- Real delivery ---
    print(f"Verifying Slack token...")
    me = auth_test()
    print(f"  Authed as: {me.get('user')} in workspace: {me.get('team')}")

    print(f"Resolving channel {args.channel}...")
    channel_id = resolve_channel_id(args.channel)
    print(f"  Channel ID: {channel_id}")

    # 1. Post the header
    print("\nPosting header message...")
    header_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "divider"},
    ]
    header_resp = post_message(channel_id, header_text, blocks=header_blocks)
    header_ts = header_resp.get("ts")
    print(f"  Header posted (ts={header_ts})")

    # 2. Post Paola feedback as thread reply
    if paola_feedback:
        print("\nPosting Paola feedback as thread reply...")
        feedback_intro = (
            ":memo: *Paola intake feedback — for the next case study*\n"
            "_3 sections: what worked, what was missing, one process suggestion._\n\n"
        )
        feedback_text = feedback_intro + md_to_slack(paola_feedback)
        # Slack message limit is 4000 chars; truncate if needed
        if len(feedback_text) > 38000:
            feedback_text = feedback_text[:37500] + "\n\n_(truncated — read full feedback in paola-feedback.md)_"
        post_message(channel_id, feedback_text, thread_ts=header_ts)
        print(f"  Posted Paola feedback ({len(feedback_text)} chars)")
    else:
        print("\nNo paola-feedback.md found — skipping feedback thread")

    # 3. Post bundle file list as thread reply
    print("\nPosting bundle file list as thread reply...")
    file_lines = [":file_folder: *Bundle files (all in the case study Drive folder + repo):*", ""]
    descriptions = {
        "case-study-gabriela.md": "Published case study (Doc 1, anonymized)",
        "archive-lehyana.md": "Un-anonymized archive (Doc 2, NEVER published)",
        "metadata.md": "SEO metadata, JSON-LD schema, A/B variants",
        "qa-checklist.md": "QA walkthrough (133 checkboxes)",
        "bundle-summary.md": "One-page index of automated checks + Gate 2 items",
        "seo-research-notes.md": "Pre-draft SEO research (keyword/SERP/gap analysis)",
        "paola-feedback.md": "Intake feedback for Paola",
    }
    for fname, size in bundle_files:
        # Look up description by stem prefix (handles case-study-{any-name}.md and archive-{any-name}.md)
        desc = descriptions.get(fname, "")
        if not desc:
            for prefix, d in descriptions.items():
                stem_prefix = prefix.rsplit("-", 1)[0] if "-" in prefix else prefix.rstrip(".md")
                if fname.startswith(stem_prefix.split(".")[0]):
                    desc = d
                    break
        file_lines.append(f"  *{fname}* ({size:,} bytes) — {desc}")
    file_text = "\n".join(file_lines)
    post_message(channel_id, file_text, thread_ts=header_ts)
    print(f"  Posted bundle file list ({len(bundle_files)} files)")

    print("\nDone. Open #student-spotlight-ready in Slack to review.")
    log("case_study_delivery_complete", "ok", f"bundle={bundle} channel={args.channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
