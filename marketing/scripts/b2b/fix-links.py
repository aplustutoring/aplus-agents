#!/usr/bin/env python3
"""Verify and repair source-article hyperlinks in B2B blog drafts.

Fact-check verifies CLAIMS; this verifies the LINKS resolve to the right source.
For every <a href> in a HubSpot blog post body:
  - HTTP-check it (follow redirects, browser UA).
  - dead (4xx/5xx, excluding bot-block codes) OR generic (bare domain / landing
    word like /research/) -> ask the model (web search) for the correct, specific,
    currently-live source URL, HTTP-verify it (must 200 + be specific), and replace.
  - dead with no good replacement -> UNLINK (keep the claim text, drop the href).
  - generic with no better option -> keep (it at least resolves).
  - 401/403/429/timeout (bot-blocked / uncertain) -> leave as-is.

Usage:
  python3 scripts/b2b/fix-links.py --post-id 214363657790 [--apply]
  python3 scripts/b2b/fix-links.py --all-staged [--apply]
Default is dry-run; --apply patches the HubSpot postBody.
"""
import os, re, sys, json, argparse, time, html as htmllib
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv
load_dotenv(override=True)
import anthropic

HUBSPOT = "https://api.hubapi.com"
HHEAD = {"Authorization": f"Bearer {os.environ['HUBSPOT_PRIVATE_APP_TOKEN']}"}
MODEL = "claude-opus-4-7"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
GENERIC_WORDS = {"research", "blog", "about", "home", "index", "news", "resources", "articles", "publications"}
KEEP_CODES = {401, 403, 429}  # bot-block / auth -> uncertain, never touch
LINK_RE = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*?>(.*?)</a>', re.I | re.S)


def http_kind(url):
    """Return (status_code, kind) where kind in ok/dead/generic/keep.

    `url` arrives straight out of the HTML, so its ampersands are entity-encoded
    (`?a=1&amp;b=2`). Requesting that literally sends the server a parameter
    named `amp;b`, which is a different URL than the one the post links to: a
    live source with a query string could come back 404 and get UNLINKED as
    "dead". Unescape before the check, keep the escaped form as the key.
    """
    try:
        r = requests.get(htmllib.unescape(url), headers=UA, allow_redirects=True, timeout=15)
        code = r.status_code
        final = r.url
    except Exception:
        return (0, "keep")
    if code in KEEP_CODES:
        return (code, "keep")
    if code >= 400:
        return (code, "dead")
    segs = [s for s in urlparse(final).path.split("/") if s]
    if len(segs) == 0 or segs[-1].lower() in GENERIC_WORDS:
        return (code, "generic")
    return (code, "ok")


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def find_replacement(anchor, context, old_url, client, same_domain=False):
    old_url = htmllib.unescape(old_url)  # show the model the real URL, not the escaped one
    prompt = (
        f"A hyperlink in an A+ Tutoring blog post is broken or too generic and must be replaced.\n"
        f'Anchor text: "{anchor}"\nClaim/context: "{context}"\nOld (bad) URL: {old_url}\n\n'
        f"Find the SINGLE best, currently-live source URL that directly supports this claim. "
        f"It MUST be a specific article/report/page (NOT a site homepage or generic landing page), "
        f"from an authoritative source (gov, .edu, established news org, or the original publisher). "
        f"Reply with ONLY the URL on one line, or exactly NONE if you cannot find a reliable live source."
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print("     web_search error:", e)
        return None
    text = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    m = re.search(r'https?://[^\s)>"\]]+', text)
    if not m:
        return None
    cand = m.group(0).rstrip(".,);'\"")
    if cand == old_url:
        return None
    # For generic-homepage links the author intended THIS source — only accept a
    # deeper page on the SAME domain (prevents swapping "FCMAT" for an unrelated
    # article). Dead links are broken anyway, so any verified domain is allowed.
    if same_domain and urlparse(cand).netloc.replace("www.", "") != urlparse(old_url).netloc.replace("www.", ""):
        return None
    code, kind = http_kind(cand)
    return cand if kind == "ok" else None


def process_post(pid, apply, client):
    """Returns (changes, ok). ok=False means the run could not be trusted."""
    g = requests.get(f"{HUBSPOT}/cms/v3/blogs/posts/{pid}", headers=HHEAD, timeout=30)
    if g.status_code != 200:
        # An unchecked GET used to leave html="" here, which found zero links and
        # printed "all links ok" — a clean bill of health for a post we never read.
        print(f"\n=== {pid} ===", file=sys.stderr)
        print(f"   ERROR fetching post (HTTP {g.status_code}): {g.text[:800]}", file=sys.stderr)
        return [], False
    d = g.json()
    html = d.get("postBody", "") or ""
    print(f"\n=== {pid}  {d.get('name','')[:64]} ===")
    decided = {}
    for m in LINK_RE.finditer(html):
        url = m.group(1)
        if url in decided:
            continue
        anchor = strip_tags(m.group(2))
        ctx = strip_tags(html[max(0, m.start() - 200): m.end() + 60])
        code, kind = http_kind(url)
        if kind in ("ok", "keep"):
            decided[url] = ("keep", None, code, kind)
            continue
        repl = find_replacement(anchor, ctx, url, client, same_domain=(kind == "generic"))
        if repl:
            decided[url] = ("replace", repl, code, kind)
        elif kind == "dead":
            decided[url] = ("unlink", None, code, kind)
        else:  # generic, nothing better -> keep the working link
            decided[url] = ("keep", None, code, kind)
        time.sleep(0.4)

    new_html = html
    changes = []
    for url, (action, repl, code, kind) in decided.items():
        if action == "replace":
            # Escape on the way back in. A replacement URL with a bare "&" in a
            # query string is not valid in an href attribute, and a bare quote
            # would terminate the attribute early and leave a malformed <a>.
            safe = htmllib.escape(repl, quote=True)
            new_html = new_html.replace(f'href="{url}"', f'href="{safe}"')
            changes.append(f"[{kind} {code}] REPLACE\n        {url}\n     -> {repl}")
        elif action == "unlink":
            new_html = LINK_RE.sub(lambda mm: strip_tags(mm.group(2)) if mm.group(1) == url else mm.group(0), new_html)
            changes.append(f"[{kind} {code}] UNLINK (kept text)\n        {url}")

    total = len(decided)
    print(f"  {total} unique links — {len(changes)} to change")
    for c in changes:
        print("   " + c)
    if not changes:
        print("   all links ok")
    if apply and changes:
        r = requests.patch(f"{HUBSPOT}/cms/v3/blogs/posts/{pid}", headers=HHEAD, json={"postBody": new_html}, timeout=60)
        print("   PATCH postBody:", r.status_code)
        if r.status_code not in (200, 201):
            # This used to be printed and forgotten: the status was never checked,
            # main() always returned 0, and content-build.py only looks at the
            # return code. A rejected patch left the draft half-repaired with
            # nobody told. Surface HubSpot's own message and fail the run.
            print(f"   ERROR: HubSpot rejected the postBody patch (HTTP {r.status_code}):",
                  file=sys.stderr)
            print("   " + r.text[:1500], file=sys.stderr)
            return changes, False
    return changes, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post-id", action="append", default=[])
    ap.add_argument("--all-staged", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    pids = list(a.post_id)
    if a.all_staged:
        q = json.load(open("state/topic-queue.json"))
        pids += [t["hubspot_post_id"] for t in q.get("topics", []) if t.get("hubspot_post_id")]
    if not pids:
        print("no post ids (use --post-id or --all-staged)")
        return 1
    client = anthropic.Anthropic()
    failed = []
    for pid in pids:
        _, ok = process_post(pid, a.apply, client)
        if not ok:
            failed.append(pid)
    print("\nDONE", "(applied)" if a.apply else "(dry-run)")
    if failed:
        print(f"FAILED on {len(failed)} post(s): {', '.join(map(str, failed))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
