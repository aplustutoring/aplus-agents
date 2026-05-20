#!/usr/bin/env python3
"""
A+ Tutoring HubSpot blog publisher.

Reads an A+ weekly bundle (blog markdown + meta + hero image) and creates a
HubSpot CMS Blog Post as a DRAFT. Never publishes. Idempotent on hero image
upload (checks by filename before re-uploading).

Usage:
    python3 scripts/publish-to-hubspot.py --bundle aplus-content/2026-05-15-weekly/
    python3 scripts/publish-to-hubspot.py --bundle aplus-content/2026-05-15-weekly/ --dry-run
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
import markdown


def dated_filename(local_path, bundle_path):
    """Return {stem}-{YYYY-MM-DD}.{ext} derived from the bundle directory name.

    Example:
        dated_filename("graphics/hero.png", "aplus-content/2026-05-18-weekly/")
        -> "hero-2026-05-18.png"
    """
    p = Path(local_path)
    stem, ext = p.stem, p.suffix
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(bundle_path))
    if not m:
        # No date found in bundle path; fall back to undated original name
        return p.name
    return f"{stem}-{m.group(1)}{ext}"

load_dotenv()

TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
PORTAL_ID = "6312752"          # HubSpot account ID (used only for edit URLs)
BLOG_ID = "12422338726"        # content_group_id of the wetutorathome.com blog
HUBSPOT_BASE = "https://api.hubapi.com"
LOG_PATH = Path(__file__).parent / "hubspot-usage.log"


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
    return {"Authorization": f"Bearer {TOKEN}"}


def validate_token():
    """Cheap GET to confirm the token + private app permissions work."""
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
        headers=auth_headers(),
        params={"limit": 1, "contentGroupId": BLOG_ID},
        timeout=30,
    )
    log("validate_token", r.status_code, "OK" if r.status_code == 200 else r.text[:400])
    if r.status_code != 200:
        print(f"ERROR: token validation failed (HTTP {r.status_code}):", file=sys.stderr)
        print(r.text[:1500], file=sys.stderr)
        return False
    return True


def parse_meta(meta_path):
    """Parse the meta markdown file.

    The meta file has a fenced code block containing YAML-style key: value
    lines plus a few standalone fields outside the block (like cta_url).
    Extract the fields the publisher needs.
    """
    text = Path(meta_path).read_text()

    meta = {}

    # Parse the first fenced ```...``` block which holds the bulk of metadata
    block_match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
    if block_match:
        for line in block_match.group(1).split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            if ":" not in stripped:
                continue
            key, _, val = stripped.partition(":")
            meta[key.strip()] = val.strip()

    # cta_url may appear outside the code block as a standalone field
    cta_match = re.search(r"^cta_url:\s*(\S+)", text, re.MULTILINE)
    if cta_match:
        meta["cta_url"] = cta_match.group(1)

    return meta


def markdown_to_html(md_path):
    """Convert blog markdown to HTML. Drop the leading H1 since HubSpot
    renders the post title separately."""
    text = Path(md_path).read_text()
    lines = text.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    body = "\n".join(lines)
    return markdown.markdown(body, extensions=["extra", "tables", "fenced_code"])


def check_existing_file(filename):
    """Exact-name lookup against HubSpot Files. Returns the file record or None.

    HubSpot's name field stores the basename without extension. We compare on
    both the bare stem and the full filename.

    Tries the v3 listing endpoint first; if it returns a non-200 (HubSpot's
    v3 `GET /files/v3/files` has intermittently returned 405 starting 2026-05-19),
    falls back to the v2 filemanager endpoint which is the older API still
    serving valid responses. Both endpoints accept Bearer auth with the
    Private App token.
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
            pass  # fall through to v2

    # v2 fallback (older filemanager endpoint)
    r2 = requests.get(
        f"{HUBSPOT_BASE}/filemanager/api/v2/files",
        headers=auth_headers(),
        params={"name": bare, "limit": 20},
        timeout=30,
    )
    log("check_existing_file_v2", r2.status_code, f"filename={filename}")
    if r2.status_code != 200:
        # Both endpoints failed; let upload proceed without dedup
        return None
    try:
        for obj in r2.json().get("objects", []):
            if obj.get("name") == bare:
                # v2 returns a `url` field that's the canonical public URL —
                # identical to what the v3 upload endpoint returns.
                return {
                    "id": obj.get("id"),
                    "name": obj.get("name"),
                    "url": obj.get("url"),
                }
    except ValueError:
        return None
    return None


def upload_file(image_path, upload_name=None):
    """Upload to /files/v3/files. Returns the file's CDN URL.

    Idempotent: if a file with the same dated name is already present in
    HubSpot Files, returns that URL instead of re-uploading.

    image_path is the local path; upload_name (if given) is what HubSpot
    sees. Used to apply the dated-filename convention on upload.
    """
    filename = upload_name or Path(image_path).name
    existing = check_existing_file(filename)
    if existing:
        url = existing.get("url")
        print(f"  Existing file in HubSpot: {filename} -> reusing {url}")
        log("upload_file_skipped", 200, f"existing url={url}")
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

    log("upload_file", r.status_code, r.text[:500])
    if r.status_code not in (200, 201):
        print(f"ERROR: file upload failed (HTTP {r.status_code}):", file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)
    url = r.json().get("url")
    print(f"  Uploaded: {filename} -> {url}")
    return url


def create_draft(name, slug, html, meta_description, featured_image_url):
    """POST /cms/v3/blogs/posts. State is hardcoded to DRAFT."""
    slug_clean = slug.lstrip("/")

    payload = {
        "contentGroupId": BLOG_ID,
        "name": name,
        "slug": slug_clean,
        "metaDescription": meta_description,
        "postBody": html,
        "featuredImage": featured_image_url,
        "useFeaturedImage": True,
        "authorName": "A+ Tutoring",
        "state": "DRAFT",
    }

    r = requests.post(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    log("create_draft", r.status_code, r.text[:1000])
    if r.status_code not in (200, 201):
        print(f"ERROR: draft creation failed (HTTP {r.status_code}):", file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)
    return r.json()


def main():
    parser = argparse.ArgumentParser(
        description="Publish an A+ weekly bundle to HubSpot as a DRAFT (never published)."
    )
    parser.add_argument(
        "--bundle",
        required=True,
        help="Path to weekly bundle directory (e.g., aplus-content/2026-05-15-weekly/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs, parse meta, convert markdown — no HubSpot write calls",
    )
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 1

    blog_md = bundle / "blog-anchor.md"
    meta_md = bundle / "blog-anchor-meta.md"
    hero_png = bundle / "graphics" / "hero.png"

    for p in (blog_md, meta_md, hero_png):
        if not p.exists():
            print(f"ERROR: missing required file: {p}", file=sys.stderr)
            return 1

    if not TOKEN:
        print("ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set in .env", file=sys.stderr)
        return 1

    # Parse meta
    meta = parse_meta(meta_md)
    title = meta.get("h1_title") or meta.get("meta_title")
    slug = meta.get("url_slug", "")
    description = meta.get("meta_description", "")
    keywords = meta.get("primary_keyword", "")
    cta_url = meta.get("cta_url", "(not found)")

    if not title:
        print(
            "ERROR: title not found in meta (looked for h1_title or meta_title)",
            file=sys.stderr,
        )
        return 1

    print("=== PARSED INPUTS ===")
    print(f"Title:            {title}")
    print(f"Slug:             {slug}")
    print(f"Meta description: {description}  ({len(description)} chars)")
    print(f"Primary keyword:  {keywords}")
    print(f"CTA URL (meta):   {cta_url}")
    print(f"Hero image:       {hero_png}  ({hero_png.stat().st_size:,} bytes)")

    # Convert markdown
    html = markdown_to_html(blog_md)
    print(f"HTML body length: {len(html):,} chars")

    if args.dry_run:
        print("\n=== DRY RUN — no HubSpot API calls will be made ===\n")
        print(
            f"Would validate token: GET {HUBSPOT_BASE}/cms/v3/blogs/posts"
            f"?contentGroupId={BLOG_ID}&limit=1"
        )
        print(
            f"Would check existing files: GET {HUBSPOT_BASE}/files/v3/files"
            f"?name={hero_png.name}"
        )
        print(f"Would upload {hero_png.name} if not already present")
        print(f"Would POST {HUBSPOT_BASE}/cms/v3/blogs/posts with state=DRAFT")
        print(f"contentGroupId={BLOG_ID}, authorName='A+ Tutoring'")
        print("\n--- First 600 chars of generated HTML ---")
        print(html[:600])
        print("\n--- Last 400 chars of generated HTML ---")
        print(html[-400:])
        return 0

    print("\n=== EXECUTING ===")
    print("\nValidating HubSpot token...")
    if not validate_token():
        return 1
    print("Token OK.")

    hero_upload_name = dated_filename(hero_png, bundle)
    print(f"\nUploading hero image as: {hero_upload_name}")
    hero_url = upload_file(hero_png, upload_name=hero_upload_name)
    print(f"Hero image URL: {hero_url}")

    print("\nCreating draft post...")
    post = create_draft(title, slug, html, description, hero_url)
    post_id = post.get("id")
    edit_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{post_id}/content"

    print(f"\nDraft created. Post ID: {post_id}")
    print(f"Edit URL: {edit_url}")
    log("publish_complete", 200, f"post_id={post_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
