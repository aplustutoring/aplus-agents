#!/usr/bin/env python3
"""Weekend batch build — generate all 3 approved blogs into HubSpot DRAFTS.

Runs after the Friday approval (single decision point). For each non-skipped,
lens_status=ok slot it:
  1. generates the blog (reuses blog_publish: aplus-blog-longform -> SEO -> fact/brand)
  2. writes a post-date-named bundle  (aplus-content/<post-date>-<url_slug>/)
  3. creates a HubSpot DRAFT          (publish-to-hubspot.py; never publishes live)
  4. delivers the bundle to Slack and marks the slot `staged`

By Monday all 3 drafts are ready in HubSpot; a human reviews and POSTS each one
Mon/Wed/Fri. Nothing here auto-publishes.

Naming (post date = the day the blog goes live): slot 1 -> that week's Monday,
slot 2 -> Wednesday, slot 3 -> Friday.

Deferred follow-ons (tracked separately):
  - full social-graphics pipeline (currently a placeholder hero only)
  - uploading every bundle graphic to HubSpot File Manager (2c)
  - one combined Slack "bundle" message instead of one per blog
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "shared"))
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "b2b"))

from dotenv import load_dotenv

from state import read_topic_queue, write_topic_queue, append_history_run
from skills_runner import SkillsRunner
import blog_publish as bp

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# slot -> offset in days from the publish-week Monday
SLOT_DAY_OFFSET = {1: 0, 2: 2, 3: 4}  # Mon, Wed, Fri
APPROVED_STATUSES = ("approved", "auto_approved")


def post_date_for_slot(week: str, slot: int) -> "datetime.date":
    """Publish date for a slot: the Mon/Wed/Fri of the week AFTER the slate week.

    `week` is the topic-gen date (a Thursday). The blogs go live the following
    Mon (slot 1), Wed (slot 2), Fri (slot 3).
    """
    wd = datetime.strptime(week, "%Y-%m-%d").date()
    days_to_monday = (0 - wd.weekday()) % 7 or 7  # the FOLLOWING Monday
    monday = wd + timedelta(days=days_to_monday)
    return monday + timedelta(days=SLOT_DAY_OFFSET[slot])


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def build_slot(slot: int, topic: dict, week: str, runner: SkillsRunner, *, dry_run: bool) -> dict:
    post_date = post_date_for_slot(week, slot)
    logger.info(
        "build_slot start slot=%s post_date=%s headline=%r",
        slot, post_date, topic.get("headline", "")[:70],
    )

    # --- generate (reuse blog_publish) ---
    blog_prompt = bp.build_blog_prompt(topic, week)
    blog_result = runner.run_skill("aplus-blog-longform", blog_prompt, max_tokens=24000)
    body, meta = bp.parse_blog_output(blog_result.text)
    if body is None or not meta:
        raise RuntimeError(f"slot {slot}: failed to parse blog-body/blog-meta fences")

    seo_issues = bp.validate_seo_fields({k: v for k, v in meta.items() if isinstance(v, str)})
    if seo_issues:
        for issue in seo_issues:
            logger.error("seo_validation slot=%s %s", slot, issue)
        raise RuntimeError(f"slot {slot}: SEO validation failed ({len(seo_issues)} issue(s))")

    fact_pass, fact_result = bp.run_fact_check(runner, body)
    brand_pass, brand_result = bp.run_brand_check(runner, body)

    slug = _slugify(str(meta.get("url_slug", "")), f"slot-{slot}")
    bundle_dir = bp.CONTENT_DIR / f"{post_date}-{slug}"
    bp.write_bundle(
        bundle_dir, body, bp.format_meta_for_hubspot_script(meta, topic),
        {"fact-check": fact_result, "brand-check": brand_result},
    )
    logger.info("bundle_written slot=%s path=%s", slot, bundle_dir)

    if not (fact_pass and brand_pass):
        logger.warning(
            "slot %s gated (fact=%s brand=%s) — bundle written for review, NOT drafted",
            slot, fact_pass, brand_pass,
        )
        return {"slot": slot, "status": "gated", "bundle_dir": str(bundle_dir),
                "fact_pass": fact_pass, "brand_pass": brand_pass, "post_date": str(post_date)}

    if dry_run:
        return {"slot": slot, "status": "generated", "bundle_dir": str(bundle_dir),
                "post_date": str(post_date), "dry_run": True}

    publish_rc = bp.shell_out_to_publish(bundle_dir, dry_run=False)
    if publish_rc != 0:
        raise RuntimeError(f"slot {slot}: publish-to-hubspot.py exited {publish_rc}")

    slack_rc = bp.shell_out_to_slack(bundle_dir, dry_run=False)
    if slack_rc != 0:
        logger.warning("slot %s deliver-to-slack.py rc=%s (continuing)", slot, slack_rc)

    # --- mark staged (re-read to avoid clobbering concurrent writes) ---
    q = read_topic_queue()
    if q.topics and slot - 1 < len(q.topics):
        t = dict(q.topics[slot - 1])
        t["staged"] = True
        t["staged_at"] = datetime.now().astimezone().isoformat()
        t["post_date"] = str(post_date)
        t["bundle_dir"] = str(bundle_dir.relative_to(bp.REPO_ROOT))
        q.topics[slot - 1] = t
        write_topic_queue(q)

    append_history_run({
        "ts": datetime.now().astimezone().isoformat(),
        "kind": "content_build",
        "week": week,
        "slot": slot,
        "post_date": str(post_date),
        "headline": topic.get("headline"),
        "bundle_dir": str(bundle_dir.relative_to(bp.REPO_ROOT)),
        "publish_rc": publish_rc,
        "slack_rc": slack_rc,
    })
    return {"slot": slot, "status": "staged", "bundle_dir": str(bundle_dir),
            "post_date": str(post_date), "publish_rc": publish_rc, "slack_rc": slack_rc}


def build(*, dry_run: bool = False, only_slot: int | None = None) -> list[dict]:
    queue = read_topic_queue()
    if not queue.approval or queue.approval.get("status") not in APPROVED_STATUSES:
        raise RuntimeError(
            f"slate not approved (status={queue.approval.get('status') if queue.approval else 'none'})"
        )
    week = queue.current_week or "unknown-week"
    topics = queue.topics or []
    runner = SkillsRunner()

    results: list[dict] = []
    for slot in ([only_slot] if only_slot else [1, 2, 3]):
        if slot > len(topics):
            results.append({"slot": slot, "status": "skipped", "reason": "missing from queue"})
            continue
        topic = topics[slot - 1]
        if topic.get("skipped"):
            results.append({"slot": slot, "status": "skipped", "reason": "skipped flag"})
            continue
        if topic.get("lens_status") != "ok":
            results.append({"slot": slot, "status": "skipped", "reason": f"lens_status={topic.get('lens_status')}"})
            continue
        if topic.get("staged"):
            results.append({"slot": slot, "status": "skipped", "reason": f"already staged at {topic.get('staged_at')}"})
            continue
        results.append(build_slot(slot, topic, week, runner, dry_run=dry_run))
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Weekend batch build: 3 approved blogs -> HubSpot drafts")
    p.add_argument("--slot", type=int, choices=[1, 2, 3], help="build a single slot (testing)")
    p.add_argument("--dry-run", action="store_true", help="generate + write bundles, skip HubSpot/Slack/state")
    args = p.parse_args()
    try:
        results = build(dry_run=args.dry_run, only_slot=args.slot)
    except Exception as e:
        logger.exception("content_build_failed: %s", e)
        return 1
    import json
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
