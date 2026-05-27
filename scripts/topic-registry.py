#!/usr/bin/env python3
"""Topic registry helper for the A+ weekly content engine.

Reads and writes `state/topic-registry.json` (created 2026-05-22 to stop
candidate topics from being re-proposed week after week without anchoring).

The registry has two key sections:
  - anchors: every published topic with date, slug, title, topic_axis
  - candidates_proposed: every candidate that ever appeared in a brief,
    with date, slot, title, and anchored flag
  - retired_candidates: topics auto-retired after being proposed 3+ times
    without anchoring (resurrectable only with a fresh news hook)

Subcommands:
  list-anchors                       Print all anchored topics
  list-candidates                    Print all proposed candidates
  list-retired                       Print retired candidates
  check TITLE                        Show prior proposals for a title
  is-anchored SLUG                   Exit 0 if slug is in anchors, else 1
  novelty-check FILE                 Read 5 proposed candidates from a text
                                     file (one per line) and report
                                     novelty status (NEW / CARRYOVER /
                                     RETIRED / DUPLICATE-ANCHORED)
  record-candidate DATE SLOT TITLE   Append a candidate to the registry
  record-anchor DATE SLUG TITLE AXIS POST_ID
                                     Mark a topic as anchored
                                     (also flips the candidates_proposed
                                     entry's anchored field to true)

Normalization: title comparison is case-insensitive and strips
punctuation / extra whitespace before matching.

Usage from the weekly engine:
  - Phase 1 (research brief): call `novelty-check` against the brief's
    5 candidates before sending to Slack approval.
  - Phase 2 (approval): call `record-candidate` for each candidate
    after the brief is generated.
  - Phase 3 (anchor approved): call `record-anchor` with the chosen
    slug/title/post_id so future briefs cannot duplicate.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "state" / "topic-registry.json"
RETIRE_THRESHOLD = 3  # candidate proposed 3+ times without anchoring = retired


def _normalize(s):
    """Lowercase, strip punctuation, collapse whitespace."""
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def load():
    if not REGISTRY_PATH.exists():
        return {
            "schema_version": 1,
            "anchors": [],
            "candidates_proposed": [],
            "retired_candidates": [],
        }
    return json.loads(REGISTRY_PATH.read_text())


def save(reg):
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + "\n")


def title_matches(a, b):
    return _normalize(a) == _normalize(b)


def is_anchored_title(reg, title):
    return any(title_matches(a["title"], title) for a in reg.get("anchors", []))


def is_anchored_slug(reg, slug):
    return any(a["slug"] == slug for a in reg.get("anchors", []))


def prior_proposals(reg, title):
    return [c for c in reg.get("candidates_proposed", []) if title_matches(c["title"], title)]


def is_retired_title(reg, title):
    return any(title_matches(r["title"], title) for r in reg.get("retired_candidates", []))


def candidate_status(reg, title):
    """Return one of: ANCHORED-DUPLICATE, RETIRED, CARRYOVER-N, NEW.
    Where N is the count of prior proposals."""
    if is_anchored_title(reg, title):
        return "ANCHORED-DUPLICATE"
    if is_retired_title(reg, title):
        return "RETIRED"
    n = len(prior_proposals(reg, title))
    if n == 0:
        return "NEW"
    return f"CARRYOVER-{n}"


def cmd_list_anchors(_args):
    reg = load()
    for a in reg.get("anchors", []):
        print(f"  {a['date']}  slug={a['slug']:<60}  axis={a.get('topic_axis','?'):<25}  {a['title']}")


def cmd_list_candidates(_args):
    reg = load()
    for c in reg.get("candidates_proposed", []):
        flag = "[ANCHORED]" if c.get("anchored") else "          "
        print(f"  {c['date']} {c['slot']} {flag}  {c['title']}")


def cmd_list_retired(_args):
    reg = load()
    for r in reg.get("retired_candidates", []):
        print(f"  proposed {r.get('proposed_count','?')}x. retired {r.get('retired_on','?')}: {r['title']}")
        if r.get('reason'):
            print(f"    reason: {r['reason']}")


def cmd_check(args):
    reg = load()
    title = args.title
    status = candidate_status(reg, title)
    print(f"Title: {title!r}")
    print(f"Status: {status}")
    priors = prior_proposals(reg, title)
    if priors:
        print(f"Prior proposals ({len(priors)}):")
        for p in priors:
            flag = "[anchored]" if p.get("anchored") else "[rejected]"
            print(f"  {p['date']} slot={p['slot']} {flag}")


def cmd_is_anchored(args):
    reg = load()
    if is_anchored_slug(reg, args.slug):
        print(f"YES: slug {args.slug} is anchored")
        return 0
    print(f"NO: slug {args.slug} is not anchored")
    return 1


def cmd_novelty_check(args):
    """Read titles (one per line) from a file. Report novelty status for each."""
    reg = load()
    titles = [t.strip() for t in Path(args.file).read_text().splitlines() if t.strip() and not t.startswith("#")]
    statuses = []
    for t in titles:
        s = candidate_status(reg, t)
        statuses.append((t, s))
        marker = {
            "NEW": "[OK NEW]",
            "ANCHORED-DUPLICATE": "[FAIL DUPLICATE]",
            "RETIRED": "[FAIL RETIRED]",
        }.get(s, f"[CARRYOVER status={s}]")
        print(f"  {marker:20}  {t}")
    new_count = sum(1 for _, s in statuses if s == "NEW")
    print()
    print(f"Summary: {new_count}/{len(statuses)} truly NEW")
    if new_count < 3:
        print("FAIL: a research brief must include at least 3 NEW candidates.")
        return 1
    return 0


def cmd_record_candidate(args):
    reg = load()
    reg.setdefault("candidates_proposed", []).append({
        "date": args.date,
        "slot": args.slot,
        "title": args.title,
        "anchored": False,
    })
    save(reg)
    print(f"recorded candidate: {args.date} slot={args.slot} title={args.title!r}")


def cmd_record_anchor(args):
    reg = load()
    reg.setdefault("anchors", []).append({
        "date": args.date,
        "slug": args.slug,
        "title": args.title,
        "topic_axis": args.axis,
        "post_id": args.post_id,
    })
    # Flip the candidates_proposed entry for this title and date
    for c in reg.get("candidates_proposed", []):
        if c["date"] == args.date and title_matches(c["title"], args.title):
            c["anchored"] = True
    save(reg)
    print(f"recorded anchor: {args.date} slug={args.slug}")


def main():
    parser = argparse.ArgumentParser(description="Topic registry helper for the A+ weekly content engine.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-anchors").set_defaults(func=cmd_list_anchors)
    sub.add_parser("list-candidates").set_defaults(func=cmd_list_candidates)
    sub.add_parser("list-retired").set_defaults(func=cmd_list_retired)

    p = sub.add_parser("check")
    p.add_argument("title")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("is-anchored")
    p.add_argument("slug")
    p.set_defaults(func=cmd_is_anchored)

    p = sub.add_parser("novelty-check")
    p.add_argument("file", help="Text file with one candidate title per line")
    p.set_defaults(func=cmd_novelty_check)

    p = sub.add_parser("record-candidate")
    p.add_argument("date")
    p.add_argument("slot")
    p.add_argument("title")
    p.set_defaults(func=cmd_record_candidate)

    p = sub.add_parser("record-anchor")
    p.add_argument("date")
    p.add_argument("slug")
    p.add_argument("title")
    p.add_argument("axis")
    p.add_argument("post_id")
    p.set_defaults(func=cmd_record_anchor)

    args = parser.parse_args()
    rc = args.func(args)
    sys.exit(0 if rc is None else rc)


if __name__ == "__main__":
    main()
