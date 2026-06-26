#!/usr/bin/env python3
"""
List every HubSpot blog (content_group) on the connected portal and print
each one's name and ID.

Why this exists
---------------
publish-to-hubspot.py needs the content_group_id of each blog it might
publish to. Finding that ID via HubSpot's UI is a multi-click hunt through
settings panels. This script returns the same information in one command.

Usage
-----
Requires HUBSPOT_PRIVATE_APP_TOKEN in environment (same token publish-to-hubspot.py uses).

    python3 scripts/shared/find-blog-ids.py

Output:
    HubSpot blogs on portal NNNNNNN:

    ID                Name                                URL                                          Posts
    12422338726       A+ Tutoring Blog (English)          blog.wetutorathome.com                       47
    NNNNNNNNNNN       A+ Tutoring Case study (English)    blog.wetutorathome.com/case-study            1
    ...

The ID column is what you paste into BLOG_IDS in publish-to-hubspot.py.

Exit codes
----------
0  success
1  no token in environment
2  HubSpot API error (network, auth, rate limit, etc.)
"""
import json
import os
import sys
import urllib.request
import urllib.error


HUBSPOT_API_BASE = "https://api.hubapi.com"


def get_token():
    """Read the HubSpot Private App token from environment."""
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        print(
            "ERROR: HUBSPOT_PRIVATE_APP_TOKEN not set in environment.\n"
            "Either export it in your shell or load it from your .env file before running.\n"
            "Example: export HUBSPOT_PRIVATE_APP_TOKEN=pat-na1-xxxxx",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def fetch_blogs(token):
    """Call HubSpot's /cms/v3/blogs/content-group endpoint and return the list."""
    url = f"{HUBSPOT_API_BASE}/cms/v3/blogs/content-group?limit=100"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: HubSpot API returned HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"ERROR: HubSpot API request failed: {e}", file=sys.stderr)
        sys.exit(2)
    return data.get("results", [])


def fetch_post_count(token, blog_id):
    """Return the published-post count for a given blog ID."""
    url = (
        f"{HUBSPOT_API_BASE}/cms/v3/blogs/posts"
        f"?contentGroupId={blog_id}&state=PUBLISHED&limit=1"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        # If post count fails for one blog, return "?" rather than failing the whole script.
        return "?"
    return data.get("total", "?")


def main():
    token = get_token()
    blogs = fetch_blogs(token)

    if not blogs:
        print("No blogs found on this HubSpot portal. Either the token has no CMS read access, "
              "or no blogs exist yet.", file=sys.stderr)
        return 0

    # Pretty-print a table.
    # Column widths chosen to fit common HubSpot blog names without truncation.
    rows = []
    for blog in blogs:
        blog_id = blog.get("id", "?")
        name = blog.get("name", "(unnamed)")
        root_url = blog.get("rootUrl") or blog.get("publicTitle") or "(no rootUrl set)"
        post_count = fetch_post_count(token, blog_id)
        rows.append((blog_id, name, root_url, str(post_count)))

    # Compute column widths
    headers = ("ID", "Name", "Root URL", "Posts")
    widths = [
        max(len(headers[0]), max(len(r[0]) for r in rows)),
        max(len(headers[1]), max(len(r[1]) for r in rows)),
        max(len(headers[2]), max(len(r[2]) for r in rows)),
        max(len(headers[3]), max(len(r[3]) for r in rows)),
    ]

    print(f"\nHubSpot blogs on portal:\n")
    fmt = f"  {{:<{widths[0]}}}   {{:<{widths[1]}}}   {{:<{widths[2]}}}   {{:>{widths[3]}}}"
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))
    print()
    print(
        "Copy the ID of each blog you want publish-to-hubspot.py to support, "
        "and paste them into the BLOG_IDS dict at the top of that script."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
