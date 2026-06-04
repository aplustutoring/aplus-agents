#!/usr/bin/env python3
"""
Embed inline figures (pull-quotes + data-viz graphics) in an existing
HubSpot blog draft.

Uploads inline images (idempotent), fetches the draft's current postBody,
inserts <figure><img></figure> tags after each paragraph that contains
the corresponding anchor text, then PATCHes the draft.

Two figure families are processed:
  1. Pull-quote graphics, sourced from the meta fields:
       pull_quotes:               (list of verbatim quotes)
       inline_pull_quote_images:  (parallel list of image filenames)
  2. Data-viz graphics (added 2026-05-20), sourced from:
       inline_data_viz_images:    (list of image filenames)
       inline_data_viz_anchors:   (parallel list of anchor text snippets)
     This is where preset-stat-graphic and topic-graphic ship inline
     into the blog body per aplus-graphic-prompts v2.1.

Never publishes. State stays DRAFT regardless of source state.

Usage:
    python3 scripts/shared/embed-pull-quotes.py \\
        --bundle aplus-content/2026-05-15-weekly/ \\
        --post-id 213128099969
    python3 scripts/shared/embed-pull-quotes.py \\
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
    """Return {stem}-{bundle-dir-name}.{ext}, unique per case study / weekly
    bundle.

    Using only {stem}-{YYYY-MM-DD} made multiple case studies published on the
    SAME day collide on identical upload names (pull-quote-s1-with-logo-DATE.png,
    hero-DATE.png, ...). HubSpot dedupes uploaded files by name, so studies 2..N
    reused study 1's images and every draft showed the first study's graphics.
    The bundle directory name carries the date AND the pseudonym/slug
    (e.g. 2026-06-04-case-study-valentina), so it is unique per run."""
    p = Path(local_path)
    bundle_name = Path(bundle_path).name or "bundle"
    return f"{p.stem}-{bundle_name}{p.suffix}"

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
            "kind": "pull-quote",
        })
    return pieces


def parse_data_viz_from_meta(meta_path):
    """Parse blog-anchor-meta.md for two parallel lists that ship data-viz
    graphics inline in the blog body (added 2026-05-20 per
    aplus-graphic-prompts v2.1):
    - inline_data_viz_images:  filenames (relative to graphics/)
    - inline_data_viz_anchors: anchor text snippets from the blog body

    Each anchor is an exact (case-insensitive) substring from the prose
    that identifies the paragraph the figure should appear AFTER. The
    preset stat graphic typically anchors on the iLEAD outcomes
    paragraph; the topic graphic typically anchors on the section
    most directly tied to that week's data viz.

    Returns a list of dicts with the same shape pull-quotes return:
    [{"anchor": ..., "file": ..., "alt": ..., "kind": "data-viz"}, ...]

    Returns an empty list if neither field is present (backward
    compatible with bundles created before the v2.1 schema).
    """
    text = Path(meta_path).read_text()

    def extract_list(field_name):
        m = re.search(rf"^{re.escape(field_name)}:\s*$", text, re.MULTILINE)
        if not m:
            return []
        items = []
        for line in text[m.end():].split("\n")[1:]:
            s = line.strip()
            if not s or not s.startswith("-"):
                break
            item = s[1:].strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            items.append(item)
        return items

    images = extract_list("inline_data_viz_images")
    anchors = extract_list("inline_data_viz_anchors")

    if not images and not anchors:
        return []  # backward compatible: pre-v2.1 bundles

    if len(images) != len(anchors):
        raise ValueError(
            f"inline_data_viz_images ({len(images)}) and "
            f"inline_data_viz_anchors ({len(anchors)}) lists must be the "
            f"same length in {meta_path}"
        )

    # Optional human-readable alt text per figure (one-liner mapping)
    alt_map = {}
    for line in text.split("\n"):
        m = re.match(r"^inline_data_viz_alt_(\S+):\s*(.+)$", line.strip())
        if m:
            alt_map[m.group(1)] = m.group(2).strip()

    pieces = []
    for image, anchor in zip(images, anchors):
        # Anchor is used verbatim; trim outer quotes
        anchor_clean = anchor.strip().strip('"').strip("'")
        # Trim to a unique substring length without losing the punctuation
        # that might disambiguate the match
        if len(anchor_clean) > 80:
            anchor_clean = anchor_clean[:80]
        # Pick alt text: explicit override OR a sensible default
        stem = Path(image).stem
        alt = alt_map.get(stem, f"A+ Tutoring data visualization: {stem.replace('-', ' ')}")
        pieces.append({
            "anchor": anchor_clean,
            "file": image,
            "alt": alt,
            "kind": "data-viz",
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

    Bug fix 2026-05-21: HTML-escape both image_url and alt_text before
    interpolating into the attribute values. Without escaping, an alt text
    containing inner double quotes (e.g. `from "pull report this week"`)
    would prematurely terminate the alt attribute and produce malformed
    HTML where the rest of the alt text leaked into invented attributes
    like pull="" report="" this="" week="".

    Returns (new_html, success_bool).
    """
    import html as _html_module
    safe_url = _html_module.escape(image_url, quote=True)
    safe_alt = _html_module.escape(alt_text, quote=True)
    figure_html = (
        '<figure style="margin: 2.5em auto; text-align: center; max-width: 640px;">'
        f'<img src="{safe_url}" alt="{safe_alt}" '
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

    # Bundle layout: B2B weekly uses blog-anchor-meta.md, B2C case-study
    # uses metadata.md. Pick whichever exists; let the parser fail with a
    # specific error if neither does.
    b2b_meta = bundle / "blog-anchor-meta.md"
    b2c_meta = bundle / "metadata.md"
    if b2b_meta.exists():
        meta_path = b2b_meta
    elif b2c_meta.exists():
        meta_path = b2c_meta
    else:
        print(
            f"ERROR: no meta file in {bundle}. "
            f"Expected blog-anchor-meta.md (B2B) or metadata.md (B2C).",
            file=sys.stderr,
        )
        return 1

    # Parse the figure definitions from the meta file
    try:
        pull_quotes = parse_pull_quotes_from_meta(meta_path)
    except ValueError as e:
        print(f"ERROR parsing meta pull_quotes: {e}", file=sys.stderr)
        return 1
    try:
        data_viz = parse_data_viz_from_meta(meta_path)
    except ValueError as e:
        print(f"ERROR parsing meta data viz: {e}", file=sys.stderr)
        return 1

    # Combine into a single list of figures to process
    figures = pull_quotes + data_viz
    print(f"Loaded {len(pull_quotes)} pull-quote(s) + {len(data_viz)} data-viz figure(s) from meta:")
    for fig in figures:
        kind = fig.get("kind", "?")
        print(f"  [{kind}] file={fig['file']}  anchor='{fig['anchor'][:60]}...'")

    # Verify all source files exist locally
    for fig in figures:
        p = bundle / "graphics" / fig["file"]
        if not p.exists():
            print(f"ERROR: missing image: {p}", file=sys.stderr)
            return 1
    print("All inline-figure source files present.")

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
    print("\nUploading / locating inline figure images...")
    if args.dry_run:
        print("  DRY RUN — skipping uploads. Using placeholder URLs.")
        image_urls = {fig["file"]: f"https://example.com/{fig['file']}" for fig in figures}
    else:
        image_urls = {}
        for fig in figures:
            local_path = bundle / "graphics" / fig["file"]
            upload_name = dated_filename(local_path, bundle)
            url = upload_file(local_path, upload_name=upload_name)
            if not url:
                print(f"ERROR: upload returned no URL for {fig['file']}", file=sys.stderr)
                return 1
            image_urls[fig["file"]] = url

    # Phase 3: insert figure tags into the current postBody
    print("\nInserting <figure> tags...")
    new_body = current_body
    inserted = []
    for fig in figures:
        url = image_urls[fig["file"]]
        new_body, ok = insert_figure_after_paragraph(new_body, fig["anchor"], url, fig["alt"])
        if ok:
            print(f"  ✓ [{fig.get('kind','?')}] inserted after anchor: '{fig['anchor'][:60]}...'")
            inserted.append(fig["file"])
        else:
            print(f"  ✗ [{fig.get('kind','?')}] NOT FOUND anchor: '{fig['anchor'][:60]}...'", file=sys.stderr)

    if len(inserted) != len(figures):
        print(f"\nERROR: expected {len(figures)} insertions, got {len(inserted)}", file=sys.stderr)
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

    edit_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{args.post_id}/content"
    print(f"\nDraft updated. Edit URL: {edit_url}")
    log("embed_complete", 200, f"post_id={args.post_id}, inserted={len(inserted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
