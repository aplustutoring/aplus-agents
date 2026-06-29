#!/usr/bin/env python3
"""Verify that a published case study contains NO real-name tokens.

For a case-study bundle, the archive file `archive-{realname}.md` holds
a `## Name-mapping table` that pairs every real-name token with its
published pseudonym (or `(dropped)` marker). This script:

  1. Parses the name-mapping table from the archive
  2. Reads the published document (`case-study-{pseudonym}.md`)
  3. Searches the published doc for any real-name token (case-insensitive,
     word-boundary regex)
  4. Reports FAIL with line numbers for each leak, PASS if clean
  5. Exits non-zero on FAIL so it can gate the QA workflow

Mapping-table semantics:
  | Real | Published |
  |------|-----------|
  | Lehyana | Gabriela           ← real "Lehyana" must NOT appear in published
  | Leanna | (nickname, dropped) ← real "Leanna" must NOT appear (dropped marker)
  | iLEAD Exploration | iLEAD Exploration  ← Real == Published, allowed inline

Usage:
    python3 scripts/b2c/check-anonymization.py --bundle aplus-content/2026-05-21-case-study-gabriela/
    python3 scripts/b2c/check-anonymization.py --bundle <bundle> --verbose

Referenced by `aplus-content/{date}-case-study-{name}/bundle-summary.md`
as the automated anonymization gate before Document 1 is approved.
"""
import argparse
import re
import sys
from pathlib import Path


def find_archive_file(bundle_dir):
    """Return the archive-*.md file in the bundle. Fail if none / >1."""
    candidates = sorted(bundle_dir.glob("archive-*.md"))
    if not candidates:
        raise FileNotFoundError(
            f"No archive-*.md found in {bundle_dir}. Expected exactly one."
        )
    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple archive-*.md files found in {bundle_dir}: "
            f"{[p.name for p in candidates]}. Expected exactly one."
        )
    return candidates[0]


def find_case_study_file(bundle_dir):
    """Return the case-study-*.md file in the bundle. Fail if none / >1."""
    candidates = sorted(bundle_dir.glob("case-study-*.md"))
    if not candidates:
        raise FileNotFoundError(
            f"No case-study-*.md found in {bundle_dir}. Expected exactly one."
        )
    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple case-study-*.md files found in {bundle_dir}: "
            f"{[p.name for p in candidates]}. Expected exactly one."
        )
    return candidates[0]


def parse_name_mapping_table(archive_text):
    """Extract (real_token, published_token) pairs from the
    `## Name-mapping table` section of the archive.

    Returns a list of tuples preserving table order.
    """
    # Find the section
    m = re.search(r"^##\s+Name-mapping table\s*$", archive_text, re.MULTILINE | re.IGNORECASE)
    if not m:
        raise ValueError(
            "Archive is missing the '## Name-mapping table' section. "
            "Add the table with rows like '| Real | Published |' before running this check."
        )
    # Walk forward, collect table rows until we hit a blank line + non-table line
    pairs = []
    in_table = False
    for line in archive_text[m.end():].split("\n"):
        stripped = line.strip()
        # End of table: next heading
        if stripped.startswith("##"):
            break
        # Skip header row ("| Real | Published |") and separator ("|-----|")
        if "real" in stripped.lower() and "published" in stripped.lower():
            in_table = True
            continue
        if re.match(r"^\|\s*-+\s*\|", stripped):
            in_table = True
            continue
        if not in_table:
            continue
        # Stop at blank line after we've seen rows
        if not stripped:
            if pairs:
                break
            continue
        # Parse "| Real | Published |"
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 2:
            continue
        real_tok, published_tok = cells
        if not real_tok:
            continue
        pairs.append((real_tok, published_tok))
    if not pairs:
        raise ValueError(
            "Found '## Name-mapping table' but parsed zero rows. "
            "Check that the table uses the format '| Real | Published |'."
        )
    return pairs


def should_check(real_tok, published_tok):
    """Return True if the real_tok must NOT appear in Document 1.

    Skip the check ONLY when Real == Published (e.g., a school name kept
    inline by design). All other cases — including `(dropped)` markers,
    pseudonyms, and shortened forms like `M.` — must enforce non-appearance
    of the real token.
    """
    return real_tok.strip().lower() != published_tok.strip().lower()


def _doubled_letter_variant(token):
    """Regex source matching `token` with any letter allowed to repeat, so a
    doubled-consonant spelling variant (Johny <-> Johnny) is still caught.
    Non-letters are escaped literally. This only ADDS matches alongside the
    exact token — it never removes a match, so the gate cannot get weaker."""
    return "".join(
        (re.escape(ch) + "+") if ch.isalpha() else re.escape(ch)
        for ch in token
    )


def find_leaks(text, real_token, line_offsets):
    """Find case-insensitive word-boundary matches of real_token in text,
    including doubled-consonant spelling variants.
    Returns list of (line_no, line_text_snippet) tuples."""
    # Match the exact token OR any doubled-letter variant, both at word
    # boundaries. Escape the literal token in case it has regex metachars.
    pattern = re.compile(
        rf"\b(?:{re.escape(real_token)}|{_doubled_letter_variant(real_token)})\b",
        re.IGNORECASE,
    )
    leaks = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        if pattern.search(line):
            leaks.append((line_no, line.strip()[:140]))
    return leaks


def main():
    parser = argparse.ArgumentParser(
        description="Verify that a published case study contains no real-name tokens."
    )
    parser.add_argument("--bundle", required=True, help="Path to case-study bundle directory")
    parser.add_argument("--verbose", action="store_true", help="Print every checked token, even passes")
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    if not bundle.is_dir():
        print(f"ERROR: bundle dir not found: {bundle}", file=sys.stderr)
        return 2

    try:
        archive_path = find_archive_file(bundle)
        case_study_path = find_case_study_file(bundle)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        pairs = parse_name_mapping_table(archive_path.read_text())
    except ValueError as e:
        print(f"ERROR parsing archive: {e}", file=sys.stderr)
        return 2

    case_study_text = case_study_path.read_text()
    line_offsets = [m.start() for m in re.finditer(r"^", case_study_text, re.MULTILINE)]

    print(f"Bundle:      {bundle.name}")
    print(f"Archive:     {archive_path.name}")
    print(f"Case study:  {case_study_path.name}")
    print(f"Mapping rows: {len(pairs)}")
    print()

    failures = []
    checked = 0
    skipped = []
    for real_tok, published_tok in pairs:
        if not should_check(real_tok, published_tok):
            skipped.append((real_tok, published_tok))
            if args.verbose:
                print(f"  [SKIP] {real_tok!r} == {published_tok!r} (kept inline by design)")
            continue
        leaks = find_leaks(case_study_text, real_tok, line_offsets)
        checked += 1
        if leaks:
            failures.append((real_tok, published_tok, leaks))
            print(f"  [FAIL] real={real_tok!r} should appear as {published_tok!r} but FOUND in published doc:")
            for line_no, snippet in leaks:
                print(f"           line {line_no}: {snippet!r}")
        else:
            if args.verbose:
                print(f"  [OK]   {real_tok!r} -> {published_tok!r}")

    print()
    print(f"Checked: {checked}    Skipped (Real==Published): {len(skipped)}    Failed: {len(failures)}")

    if failures:
        print()
        print("ANONYMIZATION FAILURE. Document 1 contains real-name tokens that must be replaced before publish.")
        for real_tok, published_tok, leaks in failures:
            print(f"  - {real_tok!r} -> should be {published_tok!r} (appears {len(leaks)}x)")
        return 1

    print()
    print("ANONYMIZATION PASS. Document 1 contains no real-name tokens from the archive mapping table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
