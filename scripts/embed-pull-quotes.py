#!/usr/bin/env python3
"""
Embed pull-quote graphics inline in an existing HubSpot blog draft.

Uploads pull-quote images (idempotent), fetches the draft's current postBody,
inserts <figure><img></figure> tags after each paragraph containing the anchor
quote text, then PATCHes the draft.

Never publishes. State stays DRAFT regardless of source state.

Usage:
    python3 scripts/embed-pull-quotes.py \\
        --bundle aplus-content/2026-05-15-weekly/ \\
        --post-id 213128099969
    python3 scripts/embed-pull-quotes.py \\
        --bundle aplus-content/2026-05-15-weekly/ \\
        --post-id 213128099969 --dry-run
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


def dated_filename(local_path, bundle_path):
    """Return {stem}-{YYYY-MM-DD}.{ext} derived from the bundle directory name."""
    p = Path(local_path)
    stem, ext = p.stem, p.suffix
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        return p.name
    return f"{stem}-{m.group(1)}{ext}"

load_dotenv()

TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
PORTAL_ID = "6312752"
BLOG_ID = "12422338726"
HUBSPOT_BASE = "https://api.hubapi.com"
LOG_PATH = Path(__file__).parent / "hubspot-usage.log"

def parse_pull_quotes_from_meta(meta_path):
    """Parse blog-anchor-meta.md for two parallel lists:
    - pull_quotes: the verbatim quotes (used as alt text and to derive anchors)
    - inline_pull_quote_images: the corresponding image filenames

    Returns a list of dicts: [{"anchor": ..., "file": ..., "alt": ...}, ...]
    Anchor matching is case-insensitive at insertion time, so a quote that
    appears mid-sentence in the blog prose (lowercase first letter) still
    matches a quote rendered as a standalone graphic (capitalized first
    letter).
    """
    text = Path(meta_path).read_text()

    def extract_list(field_name):
        # Match `field_name:` followed by lines beginning with `  - `
        m = re.search(rf"^{re.escape(field_name)}:\s*$", text, re.MULTILINE)
        if not m:
            return []
        items = []
        # Walk lines after the field header
        lines = text[m.end():].split("\n")
        for line in lines[1:]:  # skip the first empty line after the header
            stripped = line.strip()
            if not stripped:
                # blank line ends the list
                break
            if not stripped.startswith("-"):
                # any non-bullet line ends the list
                break
            item = stripped[1:].strip()
            # strip surrounding quotes if present
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            items.append(item)
        return items

    quotes = extract_list("pull_quotes")
    images = extract_list("inline_pull_quote_images")

    if not quotes:
        raise ValueError(f"No 'pull_quotes:' list found in {meta_path}")
    if not images:
        raise ValueError(f"No 'inline_pull_quote_images:' list found in {meta_path}")
    if len(quotes) != len(images):
        raise ValueError(
            f"pull_quotes ({len(quotes)}) and inline_pull_quote_images "
            f"({len(images)}) lists must be the same length in {meta_path}"
        )

    pieces = []
    for quote, image in zip(quotes, images):
        # Derive an anchor: the first 60 characters of the quote, stripped of
        # surrounding punctuation. The case-insensitive matcher in
        # insert_figure_after_paragraph handles capitalization differences
        # between standalone quote (capitalized) and mid-sentence body
        # appearance (lowercase).
        anchor = quote.strip().strip('"').strip("'").rstrip(".,;:")
        if len(anchor) > 60:
            anchor = anchor[:60]
        pieces.append({
            "anchor": anchor,
            "file": image,
            "alt": f"Pull quote: {quote}",
        })
    return pieces


def log(action, status, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": status,
        "detail": str(detail)[:500],
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def check_existing_file(filename):
    """Exact-name lookup against HubSpot Files with v3 -> v2 fallback.

    HubSpot's v3 `GET /files/v3/files` started returning 405 intermittently
    around 2026-05-19. When the v3 lookup fails, we fall back to the older
    v2 filemanager endpoint which still serves valid responses.
    """
    bare = Path(filename).stem

    # v3 attempt
    r = requests.get(
        f"{HUBSPOT_BASE}/files/v3/files",
        headers=auth_headers(),
        params={"name": bare, "limit": 20},
        timeout=30,
    )
    log("check_existing_file_v3", r.status_code, f"filename={filename}")
    if r.status_code == 200:
        try:
            for record in r.json().get("results", []):
                record_name = record.get("name", "")
                if record_name == bare or record_name == filename:
                    return record
            return None
        except ValueError:
            pass

    # v2 fallback
    r2 = requests.get(
        f"{HUBSPOT_BASE}/filemanager/api/v2/files",
        headers=auth_headers(),
        params={"name": bare, "limit": 20},
        timeout=30,
    )
    log("check_existing_file_v2", r2.status_code, f"filename={filename}")
    if r2.status_code != 200:
        return None
    try:
        for obj in r2.json().get("objects", []):
            if obj.get("name") == bare:
                # v2 returns a `url` field that's the canonical public URL.
                return {
                    "id": obj.get("id"),
                    "name": obj.get("name"),
                    "url": obj.get("url"),
                }
    except ValueError:
        return None
    return None


def upload_file(image_path, upload_name=None):
    """Upload to HubSpot Files. Idempotent by exact filename.

    image_path is the local path; upload_name (if given) is the dated name
    the file should have inside HubSpot Files.
    """
    filename = upload_name or Path(image_path).name
    existing = check_existing_file(filename)
    if existing:
        url = existing.get("url")
        print(f"  Existing in HubSpot: {filename} -> reusing {url}")
        log("upload_skipped", 200, f"existing url={url}")
        return url

    with open(image_path, "rb") as f:
        files = {"file": (filename, f, "image/png")}
        data = {
            "options": json.dumps({"access": "PUBLIC_INDEXABLE"}),
            "folderPath": "/aplus-blog-images",
        }
        r = requests.post(
            f"{HUBSPOT_BASE}/files/v3/files",
            headers=auth_headers(),
            files=files,
            data=data,
            timeout=120,
        )
    log("upload_file", r.status_code, r.text[:400])
    if r.status_code not in (200, 201):
        print(f"  ERROR upload {filename} (HTTP {r.status_code}): {r.text[:400]}", file=sys.stderr)
        return None
    url = r.json().get("url")
    print(f"  Uploaded: {filename} -> {url}")
    return url


def get_post(post_id):
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts/{post_id}",
        headers=auth_headers(),
        timeout=30,
    )
    log("get_post", r.status_code, f"post_id={post_id}")
    if r.status_code != 200:
        print(f"ERROR fetching post {post_id}: HTTP {r.status_code}", file=sys.stderr)
        print(r.text[:1500], file=sys.stderr)
        return None
    return r.json()


def insert_figure_after_paragraph(html, anchor, image_url, alt_text):
    """Find the </p> that closes the paragraph containing `anchor`, then
    insert a <figure> with the image right after it.

    Matching is case-insensitive on the anchor. This handles the common case
    where a pull-quote graphic is capitalized (standalone) but the quote
    appears mid-sentence in the body prose with a lowercase first letter.

    Returns (new_html, success_bool).
    """
    figure_html = (
        '<figure style="margin: 2.5em auto; text-align: center; max-width: 640px;">'
        f'<img src="{image_url}" alt="{alt_text}" '
        'style="max-width: 100%; height: auto; display: block; margin: 0 auto;" />'
        "</figure>"
    )

    pos = html.lower().find(anchor.lower())
    if pos == -1:
        return html, False
    end_pos = html.find("</p>", pos)
    if end_pos == -1:
        return html, False
    insert_pos = end_pos + len("</p>")
    new_html = html[:insert_pos] + "\n" + figure_html + html[insert_pos:]
    return new_html, True


def patch_post(post_id, post_body):
    """PATCH the post with just the updated postBody. State is not changed."""
    payload = {"postBody": post_body}
    r = requests.patch(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts/{post_id}",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    log("patch_post", r.status_code, f"post_id={post_id}, body_len={len(post_body)}")
    if r.status_code not in (200, 201):
        print(f"ERROR patching post (HTTP {r.status_code}):", file=sys.stderr)
        print(r.text[:1500], file=sys.stderr)
        return False
    return True


def strip_existing_figures(html):
    """Remove any <figure>...</figure> blocks from the HTML.

    Used with --reset-figures when re-embedding pull-quotes on a draft that
    already has them, so we don't accumulate duplicate figures.
    """
    new_html, count = re.subn(r"\n?<figure[^>]*>.*?</figure>\n?", "", html, flags=re.DOTALL)
    return new_html, count


def main():
    parser = argparse.ArgumentParser(
        description="Embed pull-quote graphics into an existing HubSpot blog draft"
    )
    parser.add_argument("--bundle", required=True, help="Weekly bundle dir")
    parser.add_argument("--post-id", required=True, help="HubSpot post ID to PATCH")
    parser.add_argument("--dry-run", action="store_true", help="No HubSpot writes")
    parser.add_argument(
        "--reset-figures",
        action="store_true",
        help="Strip any existing <figure> tags from postBody before inserting fresh ones. Use when re-running embed on a draft that already has pull-quotes.",
    )
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set", file=sys.stderr)
        return 1

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    meta_path = bundle / "blog-anchor-meta.md"
    if not meta_path.exists():
        print(f"ERROR: meta file not found: {meta_path}", file=sys.stderr)
        return 1

    # Parse the pull-quote definitions from the meta file
    try:
        pull_quotes = parse_pull_quotes_from_meta(meta_path)
    except ValueError as e:
        print(f"ERROR parsing meta: {e}", file=sys.stderr)
        return 1
    print(f"Loaded {len(pull_quotes)} pull-quote definitions from meta:")
    for pq in pull_quotes:
        print(f"  - file={pq['file']}  anchor='{pq['anchor'][:50]}...'")

    # Verify the pull-quote image files exist locally
    for pq in pull_quotes:
        p = bundle / "graphics" / pq["file"]
        if not p.exists():
            print(f"ERROR: missing pull-quote image: {p}", file=sys.stderr)
            return 1
    print("All pull-quote source files present.")

    # Phase 1: fetch the existing draft so we know its current postBody
    print(f"\nFetching post {args.post_id}...")
    post = get_post(args.post_id)
    if not post:
        return 1
    current_body = post.get("postBody", "")
    current_state = post.get("state", "?")
    print(f"  State: {current_state}")
    print(f"  postBody length: {len(current_body):,} chars")

    if args.reset_figures:
        current_body, n_stripped = strip_existing_figures(current_body)
        print(f"  Stripped {n_stripped} existing <figure> tag(s) ({len(current_body):,} chars after strip)")

    # Phase 2: upload images (idempotent) or get existing URLs
    print("\nUploading / locating pull-quote images...")
    if args.dry_run:
        print("  DRY RUN — skipping uploads. Using placeholder URLs.")
        image_urls = {pq["file"]: f"https://example.com/{pq['file']}" for pq in pull_quotes}
    else:
        image_urls = {}
        for pq in pull_quotes:
            local_path = bundle / "graphics" / pq["file"]
            upload_name = dated_filename(local_path, bundle)
            url = upload_file(local_path, upload_name=upload_name)
            if not url:
                print(f"ERROR: upload returned no URL for {pq['file']}", file=sys.stderr)
                return 1
            image_urls[pq["file"]] = url

    # Phase 3: insert figure tags into the current postBody
    print("\nInserting <figure> tags...")
    new_body = current_body
    inserted = []
    for pq in pull_quotes:
        url = image_urls[pq["file"]]
        new_body, ok = insert_figure_after_paragraph(new_body, pq["anchor"], url, pq["alt"])
        if ok:
            print(f"  ✓ inserted after anchor: '{pq['anchor'][:60]}...'")
            inserted.append(pq["file"])
        else:
            print(f"  ✗ NOT FOUND anchor: '{pq['anchor'][:60]}...'", file=sys.stderr)

    if len(inserted) != len(pull_quotes):
        print(f"\nERROR: expected {len(pull_quotes)} insertions, got {len(inserted)}", file=sys.stderr)
        print("Aborting before PATCH to avoid a partial state.", file=sys.stderr)
        return 1

    print(f"\nNew postBody length: {len(new_body):,} chars (was {len(current_body):,}, delta +{len(new_body) - len(current_body):,})")

    # Phase 4: PATCH
    if args.dry_run:
        print("\nDRY RUN — skipping PATCH. Would send PATCH /cms/v3/blogs/posts/{post_id}")
        return 0

    print(f"\nPATCHing post {args.post_id}...")
    if not patch_post(args.post_id, new_body):
        return 1

    edit_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/edit/{args.post_id}"
    print(f"\nDraft updated. Edit URL: {edit_url}")
    log("embed_complete", 200, f"post_id={args.post_id}, inserted={len(inserted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
