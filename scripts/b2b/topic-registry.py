#!/usr/bin/env python3
"""Topic registry helper for the A+ weekly content engine + case-study engine.

Reads and writes `state/topic-registry.json` (created 2026-05-22 to stop
candidate topics from being re-proposed week after week without anchoring;
extended 2026-05-27 to also track student case studies so the same student
is never featured twice).

The registry has four key sections:
  - anchors                  (B2B weekly) every published topic with date,
                             slug, title, topic_axis
  - candidates_proposed      (B2B weekly) every candidate that ever appeared
                             in a brief, with date, slot, title, anchored flag
  - retired_candidates       (B2B weekly) topics auto-retired after being
                             proposed 3+ times without anchoring
  - case_studies             (B2C case study) every student case study ever
                             drafted/published, keyed by REAL student name
                             (not pseudonym) for true duplicate protection

B2B weekly subcommands:
  list-anchors                       Print all anchored topics
  list-candidates                    Print all proposed candidates
  list-retired                       Print retired candidates
  check TITLE                        Show prior proposals for a title
  is-anchored SLUG                   Exit 0 if slug is in anchors, else 1
  novelty-check FILE                 Read N proposed candidates from a text
                                     file (one per line) and report
                                     novelty status (NEW / CARRYOVER /
                                     RETIRED / DUPLICATE-ANCHORED)
  record-candidate DATE SLOT TITLE   Append a candidate to the registry
  record-anchor DATE SLUG TITLE AXIS POST_ID
                                     Mark a topic as anchored

Case-study subcommands (added v1.1, 2026-05-27):
  list-case-studies                  Print all case studies
  check-student REAL_NAME            Exit 0 if NEW student (safe to feature),
                                     exit 1 if student has already been
                                     featured (DUPLICATE)
  record-case-study DATE REAL_NAME PSEUDONYM SLUG [SCHOOL] [POST_ID]
                                     Register a new case study. REAL_NAME is
                                     the un-anonymized full name from the
                                     archive file; aliases (other surnames,
                                     nicknames) can be added separately.

Normalization: title and name comparisons are case-insensitive and strip
punctuation / extra whitespace before matching.

Usage from the weekly engine:
  - Phase 1 (research brief): call `novelty-check` against the brief's
    5 candidates before sending to Slack approval.
  - Phase 2 (approval): call `record-candidate` for each candidate
    after the brief is generated.
  - Phase 3 (anchor approved): call `record-anchor` with the chosen
    slug/title/post_id so future briefs cannot duplicate.

Usage from the case-study engine:
  - Before drafting (intake): call `check-student REAL_NAME` to verify
    the student has not been featured. Exit code 1 means DUPLICATE
    -- abort the run and confirm with Paola.
  - After draft + Document 1 anonymization passes: call
    `record-case-study DATE REAL_NAME PSEUDONYM SLUG SCHOOL POST_ID`
    to register the case in the registry. This is the canonical
    duplicate guard going forward.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "state" / "topic-registry.json"
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


# ----- Case-study tracking (v1.1, 2026-05-27) -----
def _name_matches(a, b):
    """Case-insensitive normalized comparison for student names. Tighter
    than title_matches because we want 'Lehyana Keys' and 'lehyana keys'
    to match but 'Lehyana' and 'Lehyana Estrada' to NOT match (different
    student in principle, even if same first name)."""
    return _normalize(a) == _normalize(b)


def find_case_study_by_real_name(reg, real_name):
    """Return the case_studies entry that matches real_name (by canonical
    name OR any alias), or None."""
    for cs in reg.get("case_studies", []):
        if _name_matches(cs.get("real_student_name", ""), real_name):
            return cs
        for alias in cs.get("real_student_aliases", []):
            if _name_matches(alias, real_name):
                return cs
    return None


def cmd_list_case_studies(_args):
    reg = load()
    cases = reg.get("case_studies", [])
    if not cases:
        print("(no case studies registered yet)")
        return
    for cs in cases:
        aliases = cs.get("real_student_aliases", [])
        alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
        post = cs.get("hubspot_post_id") or "no-post-id"
        print(
            f"  {cs['date']}  real={cs['real_student_name']}{alias_str}  "
            f"-> published={cs['published_pseudonym']}  slug={cs['slug']}  "
            f"school={cs.get('school','?')}  post={post}  status={cs.get('status','?')}"
        )


def cmd_check_student(args):
    """Exit 0 if NEW (safe to feature), exit 1 if DUPLICATE (already featured)."""
    reg = load()
    real_name = args.real_name
    match = find_case_study_by_real_name(reg, real_name)
    if match:
        print(f"DUPLICATE: {real_name!r} matches existing case study")
        print(f"  date:        {match['date']}")
        print(f"  real:        {match['real_student_name']}")
        if match.get("real_student_aliases"):
            print(f"  aliases:     {', '.join(match['real_student_aliases'])}")
        print(f"  published:   {match['published_pseudonym']}")
        print(f"  slug:        {match['slug']}")
        print(f"  school:      {match.get('school','?')}")
        print(f"  post_id:     {match.get('hubspot_post_id','?')}")
        print(f"  status:      {match.get('status','?')}")
        print()
        print("This student has already been featured. Abort the new case study or confirm with Paola.")
        return 1
    print(f"NEW: {real_name!r} not found in case_studies registry. Safe to feature.")
    return 0


def cmd_record_case_study(args):
    reg = load()
    # If this student is already registered, refuse to add a duplicate row
    existing = find_case_study_by_real_name(reg, args.real_name)
    if existing and not args.force:
        print(
            f"ERROR: case study for {args.real_name!r} already exists "
            f"(published as {existing['published_pseudonym']}, slug {existing['slug']}). "
            f"Use --force to add anyway (rare; only if intentional re-feature with new content).",
            file=sys.stderr,
        )
        return 1
    aliases = [a.strip() for a in args.aliases.split(",") if a.strip()] if args.aliases else []
    entry = {
        "date": args.date,
        "real_student_name": args.real_name,
        "real_student_aliases": aliases,
        "published_pseudonym": args.pseudonym,
        "slug": args.slug,
        "school": args.school,
        "hubspot_post_id": args.post_id,
        "status": args.status,
    }
    reg.setdefault("case_studies", []).append(entry)
    save(reg)
    print(
        f"recorded case study: {args.date}  real={args.real_name}  "
        f"-> published={args.pseudonym}  slug={args.slug}"
    )


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

    # Case-study subcommands (v1.1)
    sub.add_parser("list-case-studies").set_defaults(func=cmd_list_case_studies)

    p = sub.add_parser("check-student", help="Check whether a real student name has already been featured")
    p.add_argument("real_name", help="Real student name (full, as in the archive document)")
    p.set_defaults(func=cmd_check_student)

    p = sub.add_parser("record-case-study", help="Register a new student case study in the registry")
    p.add_argument("date", help="YYYY-MM-DD")
    p.add_argument("real_name", help="Real full student name (canonical, e.g. 'Lehyana Keys')")
    p.add_argument("pseudonym", help="Published pseudonym (e.g. 'Gabriela')")
    p.add_argument("slug", help="URL slug (e.g. 'gabriela-ilead')")
    p.add_argument("school", nargs="?", default="", help="School name (optional)")
    p.add_argument("post_id", nargs="?", default=None, help="HubSpot post ID (optional)")
    p.add_argument("--aliases", default="", help="Comma-separated aliases / alternate spellings (e.g. 'Lehyana Estrada,Leanna')")
    p.add_argument("--status", default="drafted", help="One of: drafted / published / archived (default: drafted)")
    p.add_argument("--force", action="store_true", help="Add even if duplicate exists (rare)")
    p.set_defaults(func=cmd_record_case_study)

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
