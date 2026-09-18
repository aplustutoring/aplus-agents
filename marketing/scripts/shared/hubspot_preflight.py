#!/usr/bin/env python3
"""Preflight checks on a HubSpot blog post body + meta, before a human publishes.

Why this file exists
--------------------
publish-to-hubspot.py only ever writes DRAFTS, and HubSpot happily accepts a
draft write for a body it will later refuse to RENDER. So the first person to
find out is the human clicking "Publish" in the HubSpot UI, and all they get
back is "Error Something went wrong. Please try refreshing."

Danielle filed that exact report three times (2026-08-24, 2026-09-02,
2026-09-10) and each investigation had nothing to work with: the agent exited
0, the Slack summary said the drafts were ready, and the only API trail
(hubspot-usage.log) is gitignored and dies with the CI runner. The failure was
never in our scripts, so no amount of logging inside publish-to-hubspot.py's
create-draft call would have caught it.

These checks close that gap. They are deterministic and offline, and they run
twice:
  1. in publish-to-hubspot.py, over the body + meta about to be written;
  2. in content-build.py, over the LIVE draft body AFTER embed-pull-quotes.py
     and fix-links.py have patched it. That patched body is the one a human
     actually publishes, and until now nothing ever looked at it.

Findings ride the bundle's review flags into the weekly Slack summary, so a
body that cannot publish is visible before someone hits a dead publish button.

Advisory by default: a finding never blocks the draft, because a flagged draft
a human can fix beats no draft at all. Pass --strict to make `fail` findings
exit non-zero.

Usage:
    python3 scripts/shared/hubspot_preflight.py --post-id 221200515332
    python3 scripts/shared/hubspot_preflight.py --post-id 221200515332 --json
    python3 scripts/shared/hubspot_preflight.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict

HUBSPOT_BASE = "https://api.hubapi.com"

# Elements with no end tag. A stack-based balance check must not expect one.
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# Heuristic ceilings, not HubSpot-documented limits. They exist to catch the
# runaway cases (a data-URI image inlined into the body, a body that ballooned
# across re-runs) rather than to police normal posts, so they are `warn`.
MAX_BODY_CHARS = 400_000
MAX_INLINE_IMAGES = 12
# HubSpot stores metaDescription in a bounded column; past ~300 chars the CMS
# truncates or rejects. The 130-150 house band is seo_validators.py's job.
MAX_META_DESCRIPTION = 300


@dataclass
class PreflightIssue:
    field: str
    rule: str
    detail: str = ""
    severity: str = "fail"

    def __str__(self) -> str:
        d = f" — {self.detail}" if self.detail else ""
        return f"[{self.severity}] {self.field}: {self.rule}{d}"


def _excerpt(html: str, pos: int, width: int = 70) -> str:
    """A one-line window around `pos`, for pointing a human at the bad markup."""
    start = max(0, pos - width // 2)
    snippet = html[start:start + width].replace("\n", " ")
    return f"...{snippet}..." if start else f"{snippet}..."


@dataclass
class _Tag:
    name: str
    is_close: bool
    attrs: str
    start: int
    self_closing: bool


_TAG_START_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9:-]*)")
_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"""
)


def _scan_tags(html: str) -> "tuple[list[_Tag], list[PreflightIssue]]":
    """Tokenize the HTML tags in `html`.

    Quote-aware on purpose: an attribute value may legitimately contain '>'
    (embed-pull-quotes.py escapes its alt text, but a drafted body carrying
    hand-written HTML might not), so the scanner tracks quote state instead of
    stopping at the first '>'. A tag whose quote or '>' never arrives is the
    single most likely way to hand HubSpot markup it cannot parse, so it is
    reported rather than silently skipped.
    """
    tags: list[_Tag] = []
    issues: list[PreflightIssue] = []
    i, n = 0, len(html)
    while i < n:
        lt = html.find("<", i)
        if lt == -1:
            break
        if html.startswith("<!--", lt):
            close = html.find("-->", lt)
            if close == -1:
                issues.append(PreflightIssue(
                    "postBody", "unterminated HTML comment", _excerpt(html, lt)))
                break
            i = close + 3
            continue
        m = _TAG_START_RE.match(html, lt)
        if not m:
            # A literal '<' in prose. python-markdown escapes these to &lt;,
            # so it is not by itself a problem.
            i = lt + 1
            continue
        j, quote = m.end(), ""
        while j < n:
            c = html[j]
            if quote:
                if c == quote:
                    quote = ""
            elif c in "\"'":
                quote = c
            elif c == ">":
                break
            j += 1
        if j >= n:
            issues.append(PreflightIssue(
                "postBody",
                "unterminated tag or unclosed attribute quote",
                _excerpt(html, lt)))
            break
        attrs = html[m.end():j]
        tags.append(_Tag(
            name=m.group(2).lower(),
            is_close=bool(m.group(1)),
            attrs=attrs,
            start=lt,
            self_closing=attrs.rstrip().endswith("/"),
        ))
        i = j + 1
    return tags, issues


def _parse_attrs(attrs: str) -> "dict[str, str]":
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attrs):
        value = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else (m.group(4) or ""))
        out[m.group(1).lower()] = value
    return out


def check_tag_balance(html: str) -> "list[PreflightIssue]":
    """Stack-based balance check over the body's tags.

    Unbalanced markup is the failure mode that matters here: HubSpot stores a
    draft verbatim, but publishing renders it through the blog template, and a
    tag that never closes takes the render (and the publish) down with it.

    On a mismatch we pop down to the matching open tag when there is one, so
    each genuinely unclosed element is reported once instead of cascading.
    """
    issues: list[PreflightIssue] = []
    tags, issues_scan = _scan_tags(html)
    issues.extend(issues_scan)

    stack: list[_Tag] = []
    for tag in tags:
        if tag.name in VOID_ELEMENTS or tag.self_closing:
            continue
        if not tag.is_close:
            stack.append(tag)
            continue
        if not any(t.name == tag.name for t in stack):
            issues.append(PreflightIssue(
                "postBody",
                f"stray closing </{tag.name}> with no matching open tag",
                _excerpt(html, tag.start)))
            continue
        while stack:
            open_tag = stack.pop()
            if open_tag.name == tag.name:
                break
            issues.append(PreflightIssue(
                "postBody",
                f"unclosed <{open_tag.name}>",
                _excerpt(html, open_tag.start)))
    for open_tag in reversed(stack):
        issues.append(PreflightIssue(
            "postBody",
            f"unclosed <{open_tag.name}> at end of body",
            _excerpt(html, open_tag.start)))
    return issues


def check_links_and_images(html: str) -> "list[PreflightIssue]":
    """Validate every <a> and <img> the body ships.

    fix-links.py rewrites hrefs and embed-pull-quotes.py injects <img> tags, so
    both families are machine-written after the draft exists and neither is
    checked anywhere else.
    """
    issues: list[PreflightIssue] = []
    tags, _ = _scan_tags(html)
    inline_images = 0

    for tag in tags:
        if tag.is_close:
            continue
        attrs = _parse_attrs(tag.attrs)

        if tag.name == "a":
            href = attrs.get("href")
            if href is None or not href.strip():
                issues.append(PreflightIssue(
                    "postBody", "anchor with empty or missing href",
                    _excerpt(html, tag.start)))
                continue
            if href.lower().startswith("javascript:"):
                issues.append(PreflightIssue(
                    "postBody", "anchor with a javascript: href", href[:80]))
            elif re.search(r"\s", href):
                issues.append(PreflightIssue(
                    "postBody", "anchor href contains whitespace", href[:80]))
            if "&amp;amp;" in href:
                # A double-escaped ampersand means something rewrote an href
                # that was already HTML-escaped. The resulting URL is wrong.
                issues.append(PreflightIssue(
                    "postBody", "anchor href is double-escaped (&amp;amp;)", href[:80]))

        elif tag.name == "img":
            inline_images += 1
            src = attrs.get("src")
            if src is None or not src.strip():
                issues.append(PreflightIssue(
                    "postBody", "image with empty or missing src",
                    _excerpt(html, tag.start)))
                continue
            if src.lower().startswith("data:"):
                issues.append(PreflightIssue(
                    "postBody",
                    "inline data-URI image in body (upload to HubSpot Files instead)",
                    f"{len(src):,} chars of data URI"))
            elif not re.match(r"(https?:)?//|^/", src):
                issues.append(PreflightIssue(
                    "postBody", "image src is not an absolute or root-relative URL",
                    src[:80], severity="warn"))
            if not attrs.get("alt", "").strip():
                issues.append(PreflightIssue(
                    "postBody", "image without alt text", src[:80], severity="warn"))

    if inline_images > MAX_INLINE_IMAGES:
        issues.append(PreflightIssue(
            "postBody",
            f"unusually many inline images (>{MAX_INLINE_IMAGES})",
            f"{inline_images} <img> tags — figures may have stacked across re-runs",
            severity="warn"))
    return issues


def check_post_body(html: "str | None") -> "list[PreflightIssue]":
    """All body-level checks."""
    if html is None or not html.strip():
        return [PreflightIssue("postBody", "post body is empty")]
    issues = check_tag_balance(html)
    issues += check_links_and_images(html)
    if len(html) > MAX_BODY_CHARS:
        issues.append(PreflightIssue(
            "postBody", f"body exceeds {MAX_BODY_CHARS:,} chars",
            f"{len(html):,} chars", severity="warn"))
    return issues


def check_meta(*, name=None, slug=None, meta_description=None,
               featured_image_url=None, use_featured_image=False) -> "list[PreflightIssue]":
    """Meta fields HubSpot needs in order to render and route the post."""
    issues: list[PreflightIssue] = []

    if not (name or "").strip():
        issues.append(PreflightIssue("name", "post title is empty"))

    s = slug or ""
    if not s.strip():
        issues.append(PreflightIssue("slug", "slug is empty"))
    else:
        if re.search(r"\s", s):
            issues.append(PreflightIssue("slug", "slug contains whitespace", s[:80]))
        if s != s.lower():
            issues.append(PreflightIssue("slug", "slug is not lowercase", s[:80]))
        if s.startswith("/") or "//" in s:
            issues.append(PreflightIssue("slug", "slug has a leading or doubled slash", s[:80]))

    md = meta_description or ""
    if not md.strip():
        issues.append(PreflightIssue("metaDescription", "meta description is empty"))
    elif len(md) > MAX_META_DESCRIPTION:
        issues.append(PreflightIssue(
            "metaDescription", f"meta description exceeds {MAX_META_DESCRIPTION} chars",
            f"{len(md)} chars"))

    if use_featured_image or featured_image_url:
        url = featured_image_url or ""
        if not url.strip():
            issues.append(PreflightIssue(
                "featuredImage", "useFeaturedImage is set but featuredImage is empty"))
        elif url.lower().startswith("data:"):
            issues.append(PreflightIssue(
                "featuredImage", "featured image is a data URI, not a hosted URL",
                f"{len(url):,} chars"))
        elif not re.match(r"https?://", url, re.I):
            issues.append(PreflightIssue(
                "featuredImage", "featured image URL is not http(s)", url[:80]))
    return issues


def run_checks(*, post_body=None, name=None, slug=None, meta_description=None,
               featured_image_url=None, use_featured_image=False) -> "list[PreflightIssue]":
    """Every offline check, in one call. Empty list means nothing found."""
    return check_post_body(post_body) + check_meta(
        name=name, slug=slug, meta_description=meta_description,
        featured_image_url=featured_image_url, use_featured_image=use_featured_image,
    )


def report(issues: "list[PreflightIssue]", label: str = "PREFLIGHT", stream=None) -> None:
    """Print findings in the shape the other scripts in this pipeline print."""
    stream = stream or sys.stdout
    fails = [i for i in issues if i.severity == "fail"]
    warns = [i for i in issues if i.severity != "fail"]
    if not issues:
        print(f"{label}: clean (0 issues)", file=stream)
        return
    print(f"{label}: {len(fails)} fail, {len(warns)} warn", file=stream)
    for issue in fails + warns:
        print(f"  {issue}", file=stream)


# ---------- live-draft mode ----------

def fetch_post(post_id: str) -> "dict | None":
    """GET the live draft so we can check the body a human will actually publish."""
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        print("ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set", file=sys.stderr)
        return None
    r = requests.get(
        f"{HUBSPOT_BASE}/cms/v3/blogs/posts/{post_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"ERROR fetching post {post_id}: HTTP {r.status_code}", file=sys.stderr)
        print(r.text[:1500], file=sys.stderr)
        return None
    return r.json()


def check_live_post(post_id: str) -> "tuple[list[PreflightIssue], bool]":
    """Run the checks against a live HubSpot draft. Returns (issues, fetched_ok)."""
    post = fetch_post(post_id)
    if post is None:
        return [], False
    return run_checks(
        post_body=post.get("postBody"),
        name=post.get("name"),
        slug=post.get("slug"),
        meta_description=post.get("metaDescription"),
        featured_image_url=post.get("featuredImage"),
        use_featured_image=bool(post.get("useFeaturedImage")),
    ), True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Preflight a HubSpot blog draft before a human publishes it.")
    p.add_argument("--post-id", help="Check this live HubSpot draft")
    p.add_argument("--json", action="store_true",
                   help="Emit findings as JSON on stdout (for content-build.py)")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero when any fail-severity finding is present")
    p.add_argument("--self-test", action="store_true", help="Run the built-in assertions")
    args = p.parse_args()

    if args.self_test or not args.post_id:
        return _self_test()

    issues, ok = check_live_post(args.post_id)
    if not ok:
        if args.json:
            print(json.dumps({"post_id": args.post_id, "fetched": False, "issues": []}))
        return 1
    if args.json:
        print(json.dumps({
            "post_id": args.post_id,
            "fetched": True,
            "issues": [asdict(i) for i in issues],
        }))
    else:
        report(issues, label=f"PREFLIGHT {args.post_id}")
    if args.strict and any(i.severity == "fail" for i in issues):
        return 1
    return 0


def _self_test() -> int:
    """Offline assertions — no HubSpot calls. Mirrors seo_validators.py's shape."""
    print("=== clean body (should PASS) ===")
    clean = (
        "<p>Varsity Tutors for Schools shut down, and the reason cited was evidence.</p>\n"
        '<figure style="margin: 2.5em auto;">'
        '<img src="https://cdn.hubspot.net/hero.png" alt="A+ Tutoring data visualization" />'
        "</figure>\n"
        '<p>See <a href="https://www.cde.ca.gov/fg/fo/r14/el23.asp?a=1&amp;b=2">the RFA</a>.</p>'
    )
    issues = run_checks(
        post_body=clean,
        name="Varsity Tutors For Schools Shut Down. What Directors Take From It",
        slug="varsity-tutors-schools-shutdown",
        meta_description="Varsity Tutors walked away from K-12 schools. Here is what "
                         "charter directors should take from the shutdown and the evidence bar.",
        featured_image_url="https://cdn.hubspot.net/hero.png",
        use_featured_image=True,
    )
    for i in issues:
        print(" ", i)
    if any(i.severity == "fail" for i in issues):
        raise SystemExit("sanity test FAILED — clean payload reported a fail-severity issue")
    print("no fail-severity issues — OK")

    print("\n=== unclosed tag (the publish-render killer) ===")
    issues = check_post_body("<p>Use the <blockquote> pattern when quoting a director.</p>")
    for i in issues:
        print(" ", i)
    assert any("unclosed <blockquote>" in i.rule for i in issues), "expected unclosed blockquote"

    print("\n=== unterminated attribute quote ===")
    issues = check_post_body('<p>Read <a href="https://example.com/report>the report</a></p>')
    for i in issues:
        print(" ", i)
    assert any("unterminated" in i.rule for i in issues), "expected unterminated tag"

    print("\n=== data-URI image in body ===")
    issues = check_post_body('<p>x</p><img src="data:image/png;base64,AAAA" alt="chart" />')
    for i in issues:
        print(" ", i)
    assert any("data-URI" in i.rule for i in issues), "expected data-URI finding"

    print("\n=== broken anchors ===")
    issues = check_post_body(
        '<p><a href="">empty</a> <a href="https://x.com/a?b=1&amp;amp;c=2">dbl</a></p>')
    for i in issues:
        print(" ", i)
    assert any("empty or missing href" in i.rule for i in issues), "expected empty href"
    assert any("double-escaped" in i.rule for i in issues), "expected double-escape finding"

    print("\n=== stray closing tag ===")
    issues = check_post_body("<p>orphan</p></div>")
    for i in issues:
        print(" ", i)
    assert any("stray closing" in i.rule for i in issues), "expected stray close finding"

    print("\n=== bad meta ===")
    issues = check_meta(name="", slug="Not A Slug", meta_description="",
                        featured_image_url="data:image/png;base64,AAAA",
                        use_featured_image=True)
    for i in issues:
        print(" ", i)
    assert any(i.field == "name" for i in issues)
    assert any(i.field == "slug" and "whitespace" in i.rule for i in issues)
    assert any(i.field == "metaDescription" for i in issues)
    assert any(i.field == "featuredImage" and "data URI" in i.rule for i in issues)

    print("\n=== empty body ===")
    issues = check_post_body("")
    assert len(issues) == 1 and issues[0].rule == "post body is empty"
    print("  ", issues[0])

    print("\nALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
