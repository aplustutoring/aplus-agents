#!/bin/bash
# patch-publish-for-case-study.sh
#
# Applies case-study blog support to marketing/scripts/shared/publish-to-hubspot.py.
# All-or-nothing: either all 10 patches succeed and the file is updated,
# or no changes are made and the original file is preserved.
#
# Run ONCE from your repo root:
#     bash patch-publish-for-case-study.sh
#
# Safety: creates a backup at marketing/scripts/shared/publish-to-hubspot.py.bak
# Restore with: mv marketing/scripts/shared/publish-to-hubspot.py.bak marketing/scripts/shared/publish-to-hubspot.py

set -e

SCRIPT_PATH="marketing/scripts/shared/publish-to-hubspot.py"

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "ERROR: $SCRIPT_PATH not found. Run this from your repo root."
  exit 1
fi

# Backup first
cp "$SCRIPT_PATH" "${SCRIPT_PATH}.bak"
echo "Backup: ${SCRIPT_PATH}.bak"

# Apply all patches in memory; only write if every patch succeeds.
python3 << 'PYEOF'
import sys
from pathlib import Path

p = Path("marketing/scripts/shared/publish-to-hubspot.py")
text = p.read_text()
original = text

patches = []

def patch(label, old, new):
    """Register a patch. Asserts old is present exactly once."""
    patches.append((label, old, new))

# --- All patches defined here ---

patch("01 BLOG_IDS dict",
'BLOG_ID = "12422338726"        # content_group_id of the wetutorathome.com blog',
'''# Per-blog content_group_ids and URL bases. Selected at runtime by --blog
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
BLOG_ID = BLOG_IDS["blog"]''')

patch("02 validate_token accepts blog_id",
'''def validate_token():
    """Cheap GET to confirm the token + private app permissions work."""
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
        headers=auth_headers(),
        params={"limit": 1, "contentGroupId": BLOG_ID},
        timeout=30,
    )''',
'''def validate_token(blog_id=None):
    """Cheap GET to confirm the token + private app permissions work."""
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts",
        headers=auth_headers(),
        params={"limit": 1, "contentGroupId": blog_id or BLOG_ID},
        timeout=30,
    )''')

patch("03 create_draft accepts blog_id",
'''def create_draft(
    name,
    slug,
    html,
    meta_description,
    featured_image_url,
    *,
    html_title=None,''',
'''def create_draft(
    name,
    slug,
    html,
    meta_description,
    featured_image_url,
    *,
    blog_id=None,
    html_title=None,''')

patch("04 payload uses blog_id",
'''    payload = {
        "contentGroupId": BLOG_ID,''',
'''    payload = {
        "contentGroupId": blog_id or BLOG_ID,''')

patch("05 featuredImage handles None",
'''        "featuredImage": featured_image_url,
        "useFeaturedImage": True,''',
'''        "featuredImage": featured_image_url or "",
        "useFeaturedImage": bool(featured_image_url),''')

patch("06 --blog flag added to argparse",
'''    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs, parse meta, convert markdown — no HubSpot write calls",
    )
    args = parser.parse_args()''',
'''    parser.add_argument(
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
    args = parser.parse_args()''')

patch("07 smart file detection",
'''    blog_md = bundle / "blog-anchor.md"
    meta_md = bundle / "blog-anchor-meta.md"
    hero_png = bundle / "graphics" / "hero.png"

    for p in (blog_md, meta_md, hero_png):
        if not p.exists():
            print(f"ERROR: missing required file: {p}", file=sys.stderr)
            return 1''',
'''    # Detect bundle layout. B2B uses blog-anchor.md + blog-anchor-meta.md.
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
        hero_png = None''')

patch("08 defer canonical_url default",
'''    html_title = meta.get("html_title") or meta.get("meta_title") or title
    canonical_url = meta.get("canonical_url") or (
        f"https://blog.wetutorathome.com/{slug.lstrip('/')}" if slug else None
    )''',
'''    html_title = meta.get("html_title") or meta.get("meta_title") or title
    canonical_url = meta.get("canonical_url")  # filled in after blog_choice resolves''')

patch("09 hero_alt only required when hero exists",
'''    if not hero_alt or len(hero_alt) < 10:
        print(
            "ERROR: hero_alt_text is REQUIRED and must be a descriptive sentence "
            "(>=10 chars). Looked for hero_alt_text or hero_image_alt_text in meta.",
            file=sys.stderr,
        )
        return 1''',
'''    if hero_png is not None and (not hero_alt or len(hero_alt) < 10):
        print(
            "ERROR: hero_alt_text is REQUIRED when a hero image is present and "
            "must be a descriptive sentence (>=10 chars). Looked for hero_alt_text "
            "or hero_image_alt_text in meta.",
            file=sys.stderr,
        )
        return 1''')

patch("10 resolve blog_choice + predicted URL + canonical default",
'''    # Predicted blog URL (deterministic from slug). Available BEFORE publish
    # so downstream steps (Slack delivery, IG link sticker) can reference it.
    predicted_blog_url = f"https://blog.wetutorathome.com/{slug.lstrip('/')}" if slug else None''',
'''    # Resolve blog choice. Precedence: --blog flag > meta hubspot_blog > "blog".
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
    predicted_blog_url = f"{blog_url_base}/{slug.lstrip('/')}" if slug else None''')

patch("11 validate_token call passes blog_id",
'''    print("\\nValidating HubSpot token...")
    if not validate_token():
        return 1''',
'''    print("\\nValidating HubSpot token...")
    if not validate_token(blog_id):
        return 1''')

patch("12 hero upload guarded by hero_png is not None",
'''    hero_upload_name = dated_filename(hero_png, bundle)
    print(f"\\nUploading hero image as: {hero_upload_name}")
    hero_url = upload_file(hero_png, upload_name=hero_upload_name)
    print(f"Hero image URL: {hero_url}")''',
'''    if hero_png is not None:
        hero_upload_name = dated_filename(hero_png, bundle)
        print(f"\\nUploading hero image as: {hero_upload_name}")
        hero_url = upload_file(hero_png, upload_name=hero_upload_name)
        print(f"Hero image URL: {hero_url}")
    else:
        hero_url = None
        print("\\nNo hero image — publishing without featured image.")''')

patch("13 create_draft call passes blog_id",
'''    print("\\nCreating draft post...")
    post = create_draft(
        title,
        slug,
        html,
        description,
        hero_url,
        html_title=html_title,''',
'''    print("\\nCreating draft post...")
    post = create_draft(
        title,
        slug,
        html,
        description,
        hero_url,
        blog_id=blog_id,
        html_title=html_title,''')

# --- Validate all patches before applying ---
failures = []
for label, old, new in patches:
    count = text.count(old)
    if count == 0:
        failures.append(f"  [{label}] target text NOT FOUND in file")
    elif count > 1:
        failures.append(f"  [{label}] target text matches {count} times (must be unique)")

if failures:
    print("\n*** PATCH FAILURES — NO CHANGES MADE ***\n", file=sys.stderr)
    for f in failures:
        print(f, file=sys.stderr)
    print("\nYour publish-to-hubspot.py is unchanged.", file=sys.stderr)
    sys.exit(1)

# All patches validated; apply them in order
for label, old, new in patches:
    text = text.replace(old, new, 1)
    print(f"  [{label}] applied")

# Write the patched file
p.write_text(text)
print(f"\nAll {len(patches)} patches applied successfully.")
PYEOF

PATCH_EXIT=$?
if [ $PATCH_EXIT -ne 0 ]; then
  echo "Patch script failed; restoring backup."
  mv "${SCRIPT_PATH}.bak" "$SCRIPT_PATH"
  exit 1
fi

# Syntax-check the patched file
if python3 -c "import ast; ast.parse(open('$SCRIPT_PATH').read())" 2>/dev/null; then
  echo "Syntax check: OK"
  echo ""
  echo "Patched file is ready. Test with:"
  echo "    python3 marketing/scripts/shared/publish-to-hubspot.py --bundle marketing/aplus-content/2026-05-21-case-study-gabriela/ --dry-run"
else
  echo "ERROR: patched file has syntax errors. Restoring backup."
  mv "${SCRIPT_PATH}.bak" "$SCRIPT_PATH"
  exit 1
fi
