"""SEO field validators (architecture decisions #15 and #16).

Every published blog post must pass these checks before reaching HubSpot.
Validators return a list of ValidationIssue; an empty list means pass.

Decision #15: meta description target 140 chars, pass band 130-150
Decision #16: length bounds for html_title, slug, featured_image_alt_text,
              og_title, og_description, twitter_title, twitter_description
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationIssue:
    field: str
    value: str
    actual_length: int
    rule: str
    severity: str = "fail"

    def __str__(self) -> str:
        v = self.value[:40] + "..." if len(self.value) > 40 else self.value
        return f"[{self.severity}] {self.field}={v!r} (len={self.actual_length}): {self.rule}"


# (field, min_len, max_len, rule_description, severity)
LENGTH_RULES = [
    # Decision #16
    ("html_title", 50, 60, "html_title must be 50-60 chars", "fail"),
    ("featured_image_alt_text", 100, 125, "featured_image_alt_text must be 100-125 chars", "fail"),
    ("og_title", 60, 90, "og_title must be 60-90 chars", "fail"),
    ("og_description", 120, 160, "og_description must be 120-160 chars", "fail"),
    ("twitter_title", 60, 70, "twitter_title must be 60-70 chars", "fail"),
    ("twitter_description", 120, 200, "twitter_description must be 120-200 chars", "fail"),
    # Decision #15
    ("meta_description", 130, 150, "meta_description must be 130-150 chars (target 140)", "fail"),
]


def validate_length(field: str, value: Optional[str], min_len: int, max_len: int, rule: str, severity: str = "fail") -> Optional[ValidationIssue]:
    if value is None:
        return ValidationIssue(field, "", 0, f"{field} is missing", severity)
    actual = len(value)
    if actual < min_len or actual > max_len:
        return ValidationIssue(field, value, actual, rule, severity)
    return None


def validate_slug(value: Optional[str]) -> Optional[ValidationIssue]:
    """Slug must be 3-5 hyphenated words (decision #16)."""
    if value is None:
        return ValidationIssue("slug", "", 0, "slug is missing", "fail")
    parts = [p for p in value.split("-") if p]
    word_count = len(parts)
    if word_count < 3 or word_count > 5:
        return ValidationIssue(
            "slug",
            value,
            word_count,
            f"slug must be 3-5 hyphenated words (got {word_count})",
            "fail",
        )
    if any(not p.replace("_", "").isalnum() for p in parts):
        return ValidationIssue(
            "slug",
            value,
            len(value),
            "slug parts must be alphanumeric (lowercase, hyphen-separated)",
            "fail",
        )
    if value != value.lower():
        return ValidationIssue(
            "slug",
            value,
            len(value),
            "slug must be lowercase",
            "fail",
        )
    return None


def validate_seo_fields(fields: dict) -> list[ValidationIssue]:
    """Run all checks. Returns empty list if everything passes."""
    issues: list[ValidationIssue] = []

    for field, min_len, max_len, rule, severity in LENGTH_RULES:
        issue = validate_length(field, fields.get(field), min_len, max_len, rule, severity)
        if issue:
            issues.append(issue)

    slug_issue = validate_slug(fields.get("slug"))
    if slug_issue:
        issues.append(slug_issue)

    return issues


if __name__ == "__main__":
    print("=== valid payload (should PASS) ===")
    good = {
        "html_title": "Charter School Tutoring Roi: A Districts Practical Guide",
        "slug": "charter-school-tutoring-roi",
        "meta_description": "Charter school directors weighing tutoring spend can use this short guide to evaluate ROI by program design, attendance, and growth.",
        "featured_image_alt_text": "Charter school student receiving virtual tutoring on laptop with teacher visible on screen via webcam interface",
        "og_title": "Charter School Tutoring ROI: A Director's Practical Guide for 2026",
        "og_description": "Charter school directors weighing tutoring spend can use this short guide to evaluate ROI by program design, attendance, and growth.",
        "twitter_title": "Charter School Tutoring ROI: A Director's Practical Guide 2026",
        "twitter_description": "Charter school directors weighing tutoring spend can use this short guide to evaluate ROI by program design, attendance, and growth metrics.",
    }
    issues = validate_seo_fields(good)
    if issues:
        for i in issues:
            print(" ", i)
        raise SystemExit("sanity test FAILED — valid payload reported issues")
    print("no issues — OK")

    print("\n=== invalid payload (should FAIL on every field) ===")
    bad = {
        "html_title": "Too short",
        "slug": "way-too-many-words-in-this-slug-here",
        "meta_description": "Way too short.",
        "featured_image_alt_text": "Short alt",
        "og_title": "Tiny",
        "og_description": "Short.",
        "twitter_title": "Tiny",
        "twitter_description": "Short twitter desc.",
    }
    issues = validate_seo_fields(bad)
    for i in issues:
        print(" ", i)
    if not issues:
        raise SystemExit("sanity test FAILED — invalid payload reported no issues")
    print(f"\nfound {len(issues)} issues — OK")

    print("\n=== missing payload (every field None) ===")
    missing_issues = validate_seo_fields({})
    print(f"missing fields reported: {len(missing_issues)}")
    assert len(missing_issues) == len(LENGTH_RULES) + 1, "expected one issue per rule + slug"
    print("OK")

    print("\nALL ASSERTIONS PASSED")
