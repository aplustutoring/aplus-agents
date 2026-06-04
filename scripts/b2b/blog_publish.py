"""Monday/Wednesday/Friday 8 AM blog publishing flow (decisions #7, #8).

For each publish day:
  Mon  → slot 1
  Wed  → slot 2
  Fri  → slot 3

Steps:
  1. Read state/topic-queue.json; verify the slate is approved (or auto_approved)
  2. Resolve today's slot; skip if .skipped or already published
  3. Generate the blog via aplus-blog-longform skill
  4. Parse out body + SEO metadata block
  5. Run aplus-fact-check skill against the body
  6. Run aplus-brand-check skill against the body
  7. Validate SEO fields against length rules (seo_validators)
  8. If all gates pass: write to aplus-content/<date>-<weekday>/ bundle
  9. Shell out to publish-to-hubspot.py to create the HubSpot draft
 10. Shell out to deliver-to-slack.py to post the bundle delivery message
 11. Mark slot as published in state; append history record

Each quality gate failure aborts the run loudly (decision: fail-fast in
contracts.md). On the first real Mon run, this fires live (decision #17,
no shadow mode).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Ensure shared helpers are importable after restructuring
import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "shared"))
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "b2b"))

from dotenv import load_dotenv

from seo_validators import ValidationIssue, validate_seo_fields
from skills_runner import SkillResult, SkillsRunner
from state import (
    append_history_run,
    read_topic_queue,
    write_topic_queue,
)

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTENT_DIR = REPO_ROOT / "aplus-content"
PLACEHOLDER_HERO = REPO_ROOT / "skills" / "aplus-b2b-brand-kit" / "ilead-outcomes-graphic.png"

PT = timezone(timedelta(hours=-7), name="PT")

WEEKDAY_TO_SLOT = {"Monday": 1, "Wednesday": 2, "Friday": 3}


# ---------- skill orchestration ----------

def build_blog_prompt(topic: dict, week: str) -> str:
    return f"""You are generating one A+ Tutoring B2B blog post for blog.wetutorathome.com.

This call runs from a non-interactive API context — the orchestration sub-skills
referenced in your instructions (`keyword-research`, `serp-analysis`,
`content-gap-analysis`, `geo-content-optimizer`, `meta-tags-optimizer`,
`schema-markup-generator`, `on-page-seo-auditor`) are NOT available here. Silently
use your best SEO judgment in their place. Do NOT mention these sub-skills, and do
NOT add any process notes, status labels, or bracketed markers (e.g.
"[API-mode...]", "[best-effort]", "[SEO Research Notes]") anywhere in the output.
The blog-body must contain ONLY the finished, publish-ready article starting with
the H1 — no preamble, no notes, nothing before the H1.

APPROVED TOPIC for week {week}, slot {topic.get('slot')}:
  Headline: {topic.get('headline')}
  Category: {topic.get('category')}
  Lens: {topic.get('lens')}

Why this matters for A+:
  {topic.get('why_matters', '(none provided)')}

Suggested angle:
  {topic.get('angle', '(none provided)')}

Roman take (for tone reference):
  {topic.get('roman_take', '(none provided)')}

Danielle take (for tone reference):
  {topic.get('danielle_take', '(none provided)')}

OUTPUT FORMAT — produce TWO fenced sections, in this order:

```blog-body
<the full 1,200-1,500 word blog post as markdown, starting with the H1>
```

```blog-meta
h1_title: ...
html_title: ...
meta_description: ...
url_slug: ...
primary_keyword: ...
secondary_keywords:
  - kw1
  - kw2
hero_alt_text: ...
canonical_url: ...
og_title: ...
og_description: ...
twitter_title: ...
twitter_description: ...
featured_image_alt_text: ...
pull_quotes:
  - "First verbatim sentence lifted from the body — one of the 1-2 strongest, most quotable lines (15-25 words)"
  - "Second verbatim strong sentence from the body (15-25 words)"
```

`pull_quotes` MUST be two VERBATIM sentences copied exactly from the blog body
(they become pull-quote graphics). Do not paraphrase; quote real sentences.

Length rules for the meta block (will be machine-validated and the run will FAIL if violated):
  html_title 50-60 chars
  meta_description 130-150 chars (target 140)
  url_slug 3-5 hyphenated lowercase words
  featured_image_alt_text 100-125 chars
  og_title 60-90 chars
  og_description 120-160 chars
  twitter_title 60-70 chars
  twitter_description 120-200 chars

Output ONLY the two fenced sections. No commentary before or after.
""".strip()


_FENCE_RE = re.compile(r"```(?P<tag>[a-zA-Z0-9_-]+)\n(?P<body>.*?)\n```", re.DOTALL)


_PROCESS_NOTE_RE = re.compile(
    r"^\s*\[?\s*(?:API-mode|best-effort|sub-skill unavailable|SEO Research Notes)[^\n]*\]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_process_notes(body: str) -> str:
    """Remove any process/status notes the model leaked (e.g. '[API-mode: ...]')
    so the published body starts cleanly at the H1."""
    body = _PROCESS_NOTE_RE.sub("", body)
    lines = body.splitlines()
    # Drop blank lines / stray bracketed notes that precede the first H1.
    while lines and not lines[0].lstrip().startswith("#"):
        first = lines[0].strip()
        if first == "" or (first.startswith("[") and first.endswith("]")):
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()


def parse_blog_output(text: str) -> tuple[Optional[str], dict[str, object]]:
    """Extract the ```blog-body``` and ```blog-meta``` fences."""
    body: Optional[str] = None
    meta: dict[str, object] = {}
    for m in _FENCE_RE.finditer(text):
        tag = m.group("tag")
        content = m.group("body")
        if tag == "blog-body":
            body = _strip_process_notes(content.strip())
        elif tag == "blog-meta":
            meta = _parse_meta_block(content)
    return body, meta


def _parse_meta_block(block: str) -> dict[str, object]:
    """Lightweight YAML-ish parser: `key: value` lines and `key:` followed by `- item` lists."""
    out: dict[str, object] = {}
    current_list_key: Optional[str] = None
    for line in block.splitlines():
        raw = line.rstrip()
        if not raw or raw.lstrip().startswith("#"):
            continue
        if raw.lstrip().startswith("-") and current_list_key:
            item = raw.lstrip()[1:].strip()
            out.setdefault(current_list_key, []).append(item)  # type: ignore[union-attr]
            continue
        if ":" in raw and not raw.startswith(" "):
            key, _, val = raw.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                current_list_key = key
                out[key] = []
            else:
                current_list_key = None
                out[key] = val
    return out


def format_meta_for_hubspot_script(meta: dict[str, object], topic: dict) -> str:
    """Render meta as the markdown format publish-to-hubspot.py expects.

    publish-to-hubspot.py reads a fenced ```...``` block of key:value lines,
    plus standalone cta_url. We re-emit our parsed meta in that shape.
    """
    lines = ["# Blog Meta", "", "```"]
    for key in (
        "h1_title", "html_title", "meta_title", "url_slug", "meta_description",
        "primary_keyword", "hero_alt_text", "canonical_url",
        "og_title", "og_description", "twitter_title", "twitter_description",
        "featured_image_alt_text", "language", "campaign_uuid", "category_id",
    ):
        if key in meta and isinstance(meta[key], str):
            lines.append(f"{key}: {meta[key]}")
    # h1_title fallback
    if "h1_title" not in meta and "html_title" in meta:
        lines.append(f"h1_title: {meta['html_title']}")
    lines.append("```")
    for list_key in ("secondary_keywords", "keywords", "tag_ids", "pull_quotes"):
        if list_key in meta and isinstance(meta[list_key], list):
            lines.append("")
            lines.append(f"{list_key}:")
            for item in meta[list_key]:
                lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


# ---------- quality gates ----------

def _check_skill_verdict(skill_result: SkillResult, skill_name: str) -> bool:
    """Naive PASS/FAIL check based on skill output text.
    aplus-fact-check and aplus-brand-check emit reports — look for explicit FAIL signals.
    """
    text = skill_result.text.upper()
    # Explicit overall-verdict phrases, in priority order. The skills emit their
    # native format ("❌ FACT CHECK FAILED" / "✅ FACT CHECK PASSED",
    # "BRAND CHECK FAILED/PASSED"); the run_* prompts also request "VERDICT: PASS/FAIL".
    # Match these BEFORE any heuristic — a report naturally says "fail" many times
    # while describing checks, which used to cause false negatives.
    fail_markers = ("VERDICT: FAIL", "OVERALL: FAIL", "FACT CHECK FAILED", "BRAND CHECK FAILED")
    pass_markers = ("VERDICT: PASS", "OVERALL: PASS", "FACT CHECK PASSED", "BRAND CHECK PASSED")
    for m in fail_markers:
        if m in text:
            logger.error("%s returned FAIL verdict (marker=%r)", skill_name, m)
            return False
    for m in pass_markers:
        if m in text:
            logger.info("%s returned PASS verdict (marker=%r)", skill_name, m)
            return True
    # Heuristic fallback only when no explicit verdict phrase is present
    fails = text.count("FAIL")
    passes = text.count("PASS")
    if fails > passes:
        logger.warning("%s: no explicit verdict; %d FAIL vs %d PASS mentions — treating as FAIL", skill_name, fails, passes)
        return False
    logger.warning("%s: no explicit verdict; defaulting to PASS (%d FAIL/%d PASS)", skill_name, fails, passes)
    return True


def run_fact_check(runner: SkillsRunner, body: str) -> tuple[bool, SkillResult]:
    prompt = (
        "Run a fact-check pass on the blog content below. Verify all factual claims "
        "(legislation, statistics, dates, studies, officials, organizational data). "
        "Conclude with a clear `VERDICT: PASS` or `VERDICT: FAIL` line.\n\n"
        f"---\n{body}\n---"
    )
    # web search lets fact-check actually verify claims against live sources
    result = runner.run_skill("aplus-fact-check", prompt, web_search=True)
    passed = _check_skill_verdict(result, "fact-check")
    if not passed:
        logger.warning("fact-check findings (first 3500 chars):\n%s", result.text[:3500])
    return passed, result


def run_brand_check(runner: SkillsRunner, body: str) -> tuple[bool, SkillResult]:
    prompt = (
        "Run a brand-check pass on the blog content below. Flag banned words, AI fingerprints "
        "(em dashes, 'leverage/delve/harness'), voice violations, brand inconsistencies, "
        "missing voice differentiation, and profanity. "
        "Conclude with a clear `VERDICT: PASS` or `VERDICT: FAIL` line.\n\n"
        f"---\n{body}\n---"
    )
    result = runner.run_skill("aplus-brand-check", prompt)
    return _check_skill_verdict(result, "brand-check"), result


# ---------- bundle assembly ----------

def write_bundle(bundle_dir: Path, body: str, meta_block_text: str, skill_results: dict[str, SkillResult]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "blog-anchor.md").write_text(body, encoding="utf-8")
    (bundle_dir / "blog-anchor-meta.md").write_text(meta_block_text, encoding="utf-8")
    # Quality gate transcripts for audit
    for name, sr in skill_results.items():
        (bundle_dir / f"{name}-report.md").write_text(sr.text, encoding="utf-8")
    # Hero placeholder (publish-to-hubspot.py requires graphics/hero.png exists)
    graphics_dir = bundle_dir / "graphics"
    graphics_dir.mkdir(exist_ok=True)
    hero_target = graphics_dir / "hero.png"
    if not hero_target.exists():
        if PLACEHOLDER_HERO.exists():
            shutil.copy2(PLACEHOLDER_HERO, hero_target)
        else:
            logger.warning("no placeholder hero.png available; HubSpot publish will fail")


def shell_out_to_publish(bundle_dir: Path, dry_run: bool) -> int:
    cmd = ["python3", str(REPO_ROOT / "scripts" / "shared" / "publish-to-hubspot.py"), "--bundle", str(bundle_dir)]
    if dry_run:
        cmd.append("--dry-run")
    logger.info("invoking: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return r.returncode


def shell_out_to_slack(bundle_dir: Path, dry_run: bool) -> int:
    cmd = ["python3", str(REPO_ROOT / "scripts" / "b2b" / "deliver-to-slack.py"), "--bundle", str(bundle_dir)]
    if dry_run:
        cmd.append("--dry-run")
    logger.info("invoking: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return r.returncode


# ---------- main flow ----------

def run(*, slot_override: Optional[int] = None, dry_run: bool = False) -> dict:
    now = datetime.now(PT)
    weekday = now.strftime("%A")
    if slot_override is not None:
        slot = slot_override
    elif weekday in WEEKDAY_TO_SLOT:
        slot = WEEKDAY_TO_SLOT[weekday]
    else:
        return {"status": "skipped", "reason": f"{weekday} is not a publish day"}

    queue = read_topic_queue()
    if not queue.approval or queue.approval.get("status") not in ("approved", "auto_approved"):
        raise RuntimeError(
            f"slate not approved (status={queue.approval.get('status') if queue.approval else 'none'})"
        )

    if not queue.topics or slot > len(queue.topics):
        return {"status": "skipped", "reason": f"slot {slot} missing from queue"}

    topic = queue.topics[slot - 1]
    if topic.get("lens_status") != "ok":
        return {
            "status": "skipped",
            "reason": f"slot {slot} has lens_status={topic.get('lens_status')}"
        }
    if topic.get("skipped"):
        return {"status": "skipped", "reason": f"slot {slot} flagged as skipped"}
    if topic.get("published"):
        return {"status": "skipped", "reason": f"slot {slot} already published at {topic.get('published_at')}"}

    logger.info("blog_publish_start slot=%s headline=%r", slot, topic.get("headline", "")[:80])

    runner = SkillsRunner()
    blog_prompt = build_blog_prompt(topic, queue.current_week or "unknown-week")
    blog_result = runner.run_skill("aplus-blog-longform", blog_prompt, max_tokens=24000)

    body, meta = parse_blog_output(blog_result.text)
    if body is None or not meta:
        raise RuntimeError("blog generation: failed to parse blog-body or blog-meta fences from skill output")

    # SEO validation BEFORE QA gates so we fail fast on the simplest checks
    seo_issues: list[ValidationIssue] = validate_seo_fields({k: v for k, v in meta.items() if isinstance(v, str)})
    if seo_issues:
        for issue in seo_issues:
            logger.error("seo_validation %s", issue)
        raise RuntimeError(f"SEO validation failed with {len(seo_issues)} issue(s)")

    # Quality gates
    fact_pass, fact_result = run_fact_check(runner, body)
    brand_pass, brand_result = run_brand_check(runner, body)

    quality_gates_passed = fact_pass and brand_pass
    if not quality_gates_passed:
        # Still write the bundle for human review
        bundle_dir = CONTENT_DIR / f"{now.date()}-{weekday.lower()}"
        write_bundle(
            bundle_dir, body, format_meta_for_hubspot_script(meta, topic),
            {"fact-check": fact_result, "brand-check": brand_result},
        )
        raise RuntimeError(
            f"quality gates failed (fact-check={fact_pass}, brand-check={brand_pass}); "
            f"bundle written to {bundle_dir} for review"
        )

    # Assemble bundle
    bundle_dir = CONTENT_DIR / f"{now.date()}-{weekday.lower()}"
    meta_text = format_meta_for_hubspot_script(meta, topic)
    write_bundle(bundle_dir, body, meta_text, {"fact-check": fact_result, "brand-check": brand_result})
    logger.info("bundle_written path=%s", bundle_dir)

    if dry_run:
        return {
            "dry_run": True,
            "slot": slot,
            "bundle_dir": str(bundle_dir),
            "fact_check_pass": fact_pass,
            "brand_check_pass": brand_pass,
            "seo_issues": 0,
        }

    publish_rc = shell_out_to_publish(bundle_dir, dry_run=False)
    if publish_rc != 0:
        raise RuntimeError(f"publish-to-hubspot.py exited with code {publish_rc}")

    slack_rc = shell_out_to_slack(bundle_dir, dry_run=False)
    if slack_rc != 0:
        logger.warning("deliver-to-slack.py exited with code %d (continuing)", slack_rc)

    # Mark slot published
    queue = read_topic_queue()  # re-read in case anyone else mutated
    if queue.topics and slot - 1 < len(queue.topics):
        t = dict(queue.topics[slot - 1])
        t["published"] = True
        t["published_at"] = now.isoformat()
        t["bundle_dir"] = str(bundle_dir.relative_to(REPO_ROOT))
        queue.topics[slot - 1] = t
        write_topic_queue(queue)

    append_history_run({
        "ts": now.isoformat(),
        "kind": "blog_publish",
        "week": queue.current_week,
        "slot": slot,
        "weekday": weekday,
        "headline": topic.get("headline"),
        "bundle_dir": str(bundle_dir.relative_to(REPO_ROOT)),
        "publish_rc": publish_rc,
        "slack_rc": slack_rc,
    })

    return {
        "status": "published",
        "slot": slot,
        "bundle_dir": str(bundle_dir),
        "publish_rc": publish_rc,
        "slack_rc": slack_rc,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Blog publishing flow (Mon/Wed/Fri 8 AM)")
    p.add_argument("--slot", type=int, choices=[1, 2, 3], help="override slot (for testing)")
    p.add_argument("--dry-run", action="store_true", help="skip HubSpot + Slack calls")
    args = p.parse_args()

    try:
        result = run(slot_override=args.slot, dry_run=args.dry_run)
    except Exception as e:
        logger.exception("blog_publish_failed: %s", e)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
