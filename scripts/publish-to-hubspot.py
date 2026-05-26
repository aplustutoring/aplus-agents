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
# Per-blog content_group_ids and URL bases. Selected at runtime by --blog
# flag or by the bundle metadata `hubspot_blog:` field.
BLOG_IDS = {
    "blog": "12422338726",        # A+ Tutoring Blog (English) — B2B
    "case-study": "81499394054",  # A+ Tutoring Case study (English) — B2C
}
BLOG_URL_BASES = {
    "blog": "https://blog.wetutorathome.com",
    "case-study": "https://blog.wetutorathome.com/case-study",
}
# Kept for any legacy import of BLOG_ID.
BLOG_ID = BLOG_IDS["blog"]
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


def validate_token(blog_id=None):
    """Cheap GET to confirm the token + private app permissions work."""
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
        headers=auth_headers(),
        params={"limit": 1, "contentGroupId": blog_id or BLOG_ID},
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

    v1.7 (2026-05-20) also extracts:
      - Scalar SEO fields: html_title, canonical_url, hero_alt_text,
        language, campaign_uuid, category_id
      - List fields: keywords, secondary_keywords, tag_ids
      - Multi-line schema_markup: raw HTML / JSON-LD for HubSpot headHtml
    """
    text = Path(meta_path).read_text()

    meta = {}

    # Parse the FIRST fenced ```...``` block (holds the bulk of scalar metadata)
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

    # v1.7 list fields. Use the same parallel-list pattern as
    # embed-pull-quotes.py: `field:` on its own line, then `  - item` lines.
    def _extract_list(field):
        m = re.search(rf"^{re.escape(field)}:\s*$", text, re.MULTILINE)
        if not m:
            return []
        items = []
        for line in text[m.end():].split("\n")[1:]:
            stripped = line.strip()
            if not stripped or not stripped.startswith("-"):
                break
            item = stripped[1:].strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            elif item.startswith("'") and item.endswith("'"):
                item = item[1:-1]
            items.append(item)
        return items

    meta["_keywords_list"] = _extract_list("keywords")
    meta["_secondary_keywords_list"] = _extract_list("secondary_keywords")
    meta["_tag_ids_list"] = _extract_list("tag_ids")

    # v1.7 schema_markup: raw HTML block to inject into <head>. Two sources
    # are accepted:
    #  1. Explicit YAML literal block:
    #       schema_markup: |
    #         <script type="application/ld+json">...</script>
    #     We accept the indented-under-pipe form (used in skill docs)
    #  2. Existing ```json fenced blocks under a section heading like
    #     "## JSON-LD schema block" or "## Schema markup". The publisher
    #     wraps each JSON object in <script type="application/ld+json">.
    #
    # Backward compatible: bundles created before v1.7 had JSON-LD as
    # ```json blocks in the meta file with no explicit schema_markup
    # field. The publisher still extracts and uses them.
    schema_html = _extract_schema_markup(text)
    if schema_html:
        meta["_schema_markup_html"] = schema_html

    return meta


def _extract_schema_markup(text):
    """Return concatenated <script type='application/ld+json'>...</script>
    HTML ready to inject into HubSpot headHtml.

    Looks for, in priority order:
      1. An explicit `schema_markup: |` YAML literal block (raw HTML kept
         verbatim).
      2. Any number of ```json fenced blocks, each wrapped in <script
         type="application/ld+json">...</script>.
    """
    # 1. Explicit `schema_markup: |` block (literal style)
    m = re.search(r"^schema_markup:\s*\|\s*\n", text, re.MULTILINE)
    if m:
        lines = text[m.end():].split("\n")
        body_lines = []
        for line in lines:
            # Continue while the line is indented (any whitespace) OR blank
            if line.startswith("  ") or line.startswith("\t") or line.strip() == "":
                body_lines.append(line.lstrip())
            else:
                break
        block = "\n".join(body_lines).strip()
        if block:
            return block

    # 2. ```json fenced blocks (auto-wrap)
    json_blocks = re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if json_blocks:
        wrapped = []
        for b in json_blocks:
            b = b.strip()
            if not b:
                continue
            wrapped.append(
                '<script type="application/ld+json">\n' + b + "\n</script>"
            )
        return "\n".join(wrapped)

    return ""


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


def create_draft(
    name,
    slug,
    html,
    meta_description,
    featured_image_url,
    *,
    blog_id=None,
    html_title=None,
    canonical_url=None,
    featured_image_alt_text=None,
    tag_ids=None,
    campaign=None,
    head_html=None,
    meta_keywords=None,
    language="en",
    category_id=None,
):
    """POST /cms/v3/blogs/posts. State is hardcoded to DRAFT.

    v1.7 (2026-05-20): added 9 HubSpot SEO properties:
      htmlTitle, linkRelCanonicalUrl, featuredImageAltText, tagIds,
      campaign, headHtml, metaKeywords, language, categoryId.

    featured_image_alt_text is REQUIRED by the caller (no more empty
    alt text). All other extended properties are optional.
    """
    slug_clean = slug.lstrip("/")

    payload = {
        "contentGroupId": blog_id or BLOG_ID,
        "name": name,
        "slug": slug_clean,
        "metaDescription": meta_description,
        "postBody": html,
        "featuredImage": featured_image_url or "",
        "useFeaturedImage": bool(featured_image_url),
        "authorName": "A+ Tutoring",
        "state": "DRAFT",
    }

    # v1.7 SEO properties — only include when non-empty so we never set
    # a HubSpot field to a literal empty string (HubSpot treats "" as a
    # real override that hides the inherited default).
    if html_title:
        payload["htmlTitle"] = html_title
    if canonical_url:
        payload["linkRelCanonicalUrl"] = canonical_url
    if featured_image_alt_text:
        payload["featuredImageAltText"] = featured_image_alt_text
    if tag_ids:
        # HubSpot wants integer IDs. Coerce numeric strings to int.
        coerced = []
        for t in tag_ids:
            try:
                coerced.append(int(t))
            except (TypeError, ValueError):
                coerced.append(t)
        payload["tagIds"] = coerced
    if campaign:
        payload["campaign"] = campaign
    if head_html:
        payload["headHtml"] = head_html
    if meta_keywords:
        payload["metaKeywords"] = meta_keywords
    if language:
        payload["language"] = language
    if category_id is not None:
        try:
            payload["categoryId"] = int(category_id)
        except (TypeError, ValueError):
            payload["categoryId"] = category_id

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
        "--blog",
        choices=list(BLOG_IDS.keys()),
        default=None,
        help=(
            "Which HubSpot blog to publish to. If omitted, reads `hubspot_blog:` "
            "from the bundle's meta file. Falls back to 'blog' (B2B). "
            "Options: " + ", ".join(BLOG_IDS.keys())
        ),
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

    # Detect bundle layout. B2B uses blog-anchor.md + blog-anchor-meta.md.
    # Case-study uses case-study-*.md + metadata.md.
    if (bundle / "blog-anchor.md").exists():
        blog_md = bundle / "blog-anchor.md"
        meta_md = bundle / "blog-anchor-meta.md"
    else:
        candidates = sorted(bundle.glob("case-study-*.md"))
        if not candidates:
            print(
                f"ERROR: no body markdown found in {bundle}. "
                f"Expected blog-anchor.md (B2B) or case-study-*.md.",
                file=sys.stderr,
            )
            return 1
        blog_md = candidates[0]
        meta_md = bundle / "metadata.md"

    hero_png = bundle / "graphics" / "hero.png"
    # Hero optional for early case-study runs (no graphics pipeline yet).
    # B2B requires hero.
    hero_required = (blog_md.name == "blog-anchor.md")
    for p_check in (blog_md, meta_md):
        if not p_check.exists():
            print(f"ERROR: missing required file: {p_check}", file=sys.stderr)
            return 1
    if hero_required and not hero_png.exists():
        print(f"ERROR: missing required file: {hero_png}", file=sys.stderr)
        return 1
    if not hero_png.exists():
        print(f"NOTE: no hero image at {hero_png} — publishing without featured image.")
        hero_png = None

    if not TOKEN:
        print("ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set in .env", file=sys.stderr)
        return 1

    # Parse meta
    meta = parse_meta(meta_md)
    title = meta.get("h1_title") or meta.get("meta_title")
    slug = meta.get("url_slug", "")
    description = meta.get("meta_description", "")
    primary_keyword = meta.get("primary_keyword", "")
    cta_url = meta.get("cta_url", "(not found)")

    if not title:
        print(
            "ERROR: title not found in meta (looked for h1_title or meta_title)",
            file=sys.stderr,
        )
        return 1

    # v1.7 extended SEO fields with sensible fallbacks
    html_title = meta.get("html_title") or meta.get("meta_title") or title
    canonical_url = meta.get("canonical_url")  # filled in after blog_choice resolves

    # featuredImageAltText is REQUIRED. Accept either new (hero_alt_text)
    # or legacy (hero_image_alt_text) field name.
    hero_alt = (
        meta.get("hero_alt_text")
        or meta.get("hero_image_alt_text")
        or ""
    )
    if hero_png is not None and (not hero_alt or len(hero_alt) < 10):
        print(
            "ERROR: hero_alt_text is REQUIRED when a hero image is present and "
            "must be a descriptive sentence (>=10 chars). Looked for hero_alt_text "
            "or hero_image_alt_text in meta.",
            file=sys.stderr,
        )
        return 1

    # Keywords list -> comma-joined string for HubSpot metaKeywords
    keywords_list = list(meta.get("_keywords_list", []))
    if not keywords_list:
        # Fall back to primary_keyword + secondary_keywords
        sk = meta.get("_secondary_keywords_list", [])
        if primary_keyword:
            keywords_list = [primary_keyword] + sk
    meta_keywords_string = ", ".join(k for k in keywords_list if k)

    tag_ids = meta.get("_tag_ids_list", [])
    language = meta.get("language", "en")
    campaign_uuid = meta.get("campaign_uuid")
    if campaign_uuid and campaign_uuid.lower() in ("null", "none", ""):
        campaign_uuid = None
    category_id = meta.get("category_id")
    if category_id and category_id.lower() in ("null", "none", ""):
        category_id = None

    head_html = meta.get("_schema_markup_html", "")
    if not head_html:
        print(
            "WARNING: no schema_markup found in meta (looked for "
            "`schema_markup:` field or ```json blocks). headHtml will be empty.",
            file=sys.stderr,
        )

    # HubSpot CMS v3 Blog Posts API silently drops `metaKeywords` (confirmed
    # 2026-05-20: the GET response no longer includes that property). Modern
    # SEO doesn't use meta keywords for ranking anyway, but we still inject
    # the <meta name="keywords"> tag into headHtml so the keywords land in
    # the rendered HTML for any legacy crawler that reads it.
    if meta_keywords_string and head_html is not None:
        # Escape double-quotes in the content
        kw_escaped = meta_keywords_string.replace('"', "&quot;")
        kw_tag = f'<meta name="keywords" content="{kw_escaped}">'
        # Prepend so it lands at the top of headHtml
        head_html = kw_tag + ("\n" + head_html if head_html else "")

    # Resolve blog choice. Precedence: --blog flag > meta hubspot_blog > "blog".
    blog_choice = args.blog or meta.get("hubspot_blog") or "blog"
    if blog_choice not in BLOG_IDS:
        print(f"ERROR: unknown blog choice {blog_choice!r}. Valid: {', '.join(BLOG_IDS.keys())}", file=sys.stderr)
        return 1
    blog_id = BLOG_IDS[blog_choice]
    blog_url_base = BLOG_URL_BASES[blog_choice]
    print(f"Publishing to blog: {blog_choice} (id={blog_id})")

    # Now that blog_url_base is known, fill in canonical_url default
    if not canonical_url and slug:
        canonical_url = f"{blog_url_base}/{slug.lstrip('/')}"

    # Predicted blog URL (deterministic from slug). Available BEFORE publish
    # so downstream steps (Slack delivery, IG link sticker) can reference it.
    predicted_blog_url = f"{blog_url_base}/{slug.lstrip('/')}" if slug else None

    print("=== PARSED INPUTS ===")
    print(f"Display title:    {title}")
    print(f"HTML title:       {html_title}")
    print(f"Slug:             {slug}")
    print(f"Canonical URL:    {canonical_url}")
    print(f"Predicted URL:    {predicted_blog_url}")
    print(f"Meta description: {description}  ({len(description)} chars)")
    print(f"Hero alt text:    {hero_alt[:80]}...  ({len(hero_alt)} chars)")
    print(f"Keywords:         {meta_keywords_string!r}  ({len(keywords_list)} terms)")
    print(f"Tag IDs:          {tag_ids}")
    print(f"Campaign UUID:    {campaign_uuid}")
    print(f"Language:         {language}")
    print(f"Category ID:      {category_id}")
    print(f"Schema markup:    {len(head_html):,} chars of headHtml")
    print(f"CTA URL (meta):   {cta_url}")
    print(f"Hero image:       {hero_png}" + (f"  ({hero_png.stat().st_size:,} bytes)" if hero_png else " (none — case study mode)"))

    # Convert markdown
    html = markdown_to_html(blog_md)
    print(f"HTML body length: {len(html):,} chars")

    if args.dry_run:
        print("\n=== DRY RUN — no HubSpot API calls will be made ===\n")
        print(
            f"Would validate token: GET {HUBSPOT_BASE}/cms/v3/blogs/posts"
            f"?contentGroupId={blog_id}&limit=1"
        )
        print(
            f"Would check existing files: GET {HUBSPOT_BASE}/files/v3/files"
            f"?name={hero_png.name if hero_png else '(no hero)'}"
        )
        if hero_png:
            print(f"Would upload {hero_png.name} if not already present")
        else:
            print("Would skip hero upload (no hero image)")
        print(f"Would POST {HUBSPOT_BASE}/cms/v3/blogs/posts with state=DRAFT")
        print(f"contentGroupId={blog_id}, authorName='A+ Tutoring'")
        print("\n--- v1.7 SEO payload preview ---")
        preview = {
            "name": title,
            "htmlTitle": html_title,
            "slug": slug,
            "linkRelCanonicalUrl": canonical_url,
            "metaDescription": description,
            "featuredImageAltText": hero_alt,
            "tagIds": tag_ids,
            "campaign": campaign_uuid,
            "metaKeywords": meta_keywords_string,
            "language": language,
            "categoryId": category_id,
            "headHtml_len": len(head_html),
            "headHtml_preview": head_html[:240] + ("..." if len(head_html) > 240 else ""),
        }
        for k, v in preview.items():
            print(f"  {k}: {v}")
        print("\n--- First 600 chars of generated HTML body ---")
        print(html[:600])
        print("\n--- Last 400 chars of generated HTML body ---")
        print(html[-400:])
        return 0

    print("\n=== EXECUTING ===")
    print("\nValidating HubSpot token...")
    if not validate_token(blog_id):
        return 1
    print("Token OK.")

    if hero_png is not None:
        hero_upload_name = dated_filename(hero_png, bundle)
        print(f"\nUploading hero image as: {hero_upload_name}")
        hero_url = upload_file(hero_png, upload_name=hero_upload_name)
        print(f"Hero image URL: {hero_url}")
    else:
        hero_url = None
        print("\nNo hero image — publishing without featured image.")

    print("\nCreating draft post...")
    post = create_draft(
        title,
        slug,
        html,
        description,
        hero_url,
        blog_id=blog_id,
        html_title=html_title,
        canonical_url=canonical_url,
        featured_image_alt_text=hero_alt,
        tag_ids=tag_ids,
        campaign=campaign_uuid,
        head_html=head_html,
        meta_keywords=meta_keywords_string,
        language=language,
        category_id=category_id,
    )
    post_id = post.get("id")
    edit_url = f"https://app.hubspot.com/blog/{PORTAL_ID}/editor/{post_id}/content"

    print(f"\nDraft created. Post ID: {post_id}")
    print(f"Edit URL: {edit_url}")
    log("publish_complete", 200, f"post_id={post_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
