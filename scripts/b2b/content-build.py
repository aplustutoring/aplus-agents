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
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

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


SUMMARY_CHANNEL = os.environ.get("TOPIC_REVIEW_CHANNEL", "#weekly-content-ready")
HUBSPOT_EDIT_URL = "https://app.hubspot.com/pages/6312752/editor/blog/{post_id}"


def _extract_issues(report_text: str, limit: int = 900) -> str:
    """Pull the 'Issues Found' section from a fact/brand-check report (the
    specific, actionable findings) so the reviewer sees exactly what to fix."""
    m = re.search(r"#+\s*Issues?\s+Found.*", report_text or "", re.IGNORECASE | re.DOTALL)
    snippet = (m.group(0) if m else (report_text or "")).strip()
    return snippet[:limit].rstrip()


def _slack_post(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set; skipping draft-summary post")
        return
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": SUMMARY_CHANNEL, "text": text, "mrkdwn": True, "unfurl_links": False},
            timeout=30,
        )
        if not r.json().get("ok"):
            logger.warning("slack summary post failed: %s", r.json().get("error"))
    except Exception as e:  # non-fatal — the drafts still exist in HubSpot
        logger.warning("slack summary post error: %s", e)


def _post_summary(results: list[dict]) -> None:
    """One Slack message: each ready draft + HubSpot link + its specific flags."""
    staged = [r for r in results if r.get("status") == "staged"]
    if not staged:
        return
    lines = [":memo: *This week's blog drafts are ready in HubSpot* — review, fix any flags, then post Mon/Wed/Fri.\n"]
    for r in staged:
        pid = r.get("hubspot_post_id")
        url = HUBSPOT_EDIT_URL.format(post_id=pid) if pid else ""
        head = (r.get("headline") or "")[:90]
        lines.append(f"*Slot {r['slot']} — {r.get('post_date','')}:* <{url}|{head}>")
        qa = ["fact :white_check_mark:" if r.get("fact_pass") else "fact :x:",
              "brand :white_check_mark:" if r.get("brand_pass") else "brand :x:"]
        if r.get("seo_issues"):
            qa.append(f"seo:{r['seo_issues']}")
        lines.append("  " + " · ".join(qa))
        for fd in r.get("flag_details", []):
            lines.append(f"  :warning: {' '.join(fd.split())[:300]}")
        lines.append("")
    _slack_post("\n".join(lines).rstrip())


def _publish_draft(bundle_dir: Path, update_post_id: "str | None" = None) -> "tuple[int, str | None]":
    """Run publish-to-hubspot.py, capturing the HubSpot post id it prints.

    If update_post_id is given, PATCHes that existing draft (no duplicate);
    otherwise creates a new draft. Returns (return_code, post_id).
    """
    cmd = ["python3", str(bp.REPO_ROOT / "scripts" / "shared" / "publish-to-hubspot.py"), "--bundle", str(bundle_dir)]
    if update_post_id:
        cmd += ["--update-existing", str(update_post_id)]
    logger.info("invoking: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(bp.REPO_ROOT), capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    m = re.search(r"Post ID:\s*(\S+)", r.stdout)
    return r.returncode, (m.group(1) if m else update_post_id)


def _build_graphics(bundle_dir: Path) -> None:
    """Generate the blog graphics (distinct hero + pull-quotes + social card) and
    composite logos. Best-effort: image-gen failures log and leave the placeholder
    hero in place — they never crash the content build."""
    steps = [
        (bp.REPO_ROOT / "scripts" / "b2b" / "build-graphics.py", ["--bundle", str(bundle_dir)]),
        (bp.REPO_ROOT / "scripts" / "shared" / "composite-logo.py", ["--bundle", str(bundle_dir)]),
    ]
    for script, extra in steps:
        try:
            r = subprocess.run(
                ["python3", str(script), *extra], cwd=str(bp.REPO_ROOT),
                capture_output=True, text=True, timeout=900,
            )
            sys.stdout.write(r.stdout)
            if r.returncode != 0:
                logger.warning("%s rc=%s: %s", script.name, r.returncode, (r.stderr or "")[:300])
        except Exception as e:
            logger.warning("%s error: %s", script.name, e)


def _generate_oped_assets(runner: SkillsRunner, bundle_dir: Path, topic: dict, body: str) -> None:
    """Generate the LinkedIn assets that ride alongside the blog: a Roman op-ed, a
    Danielle op-ed, and an A+ company-page post. Best-effort; em dashes stripped."""
    headline = topic.get("headline", "")
    excerpt = body[:1500]
    jobs = [
        ("roman-voice", "roman-oped.md",
         f"Write a LinkedIn op-ed in Roman's founder voice reacting to this week's A+ blog.\n"
         f"Topic: {headline}\nAngle: {topic.get('angle','')}\nRoman's take: {topic.get('roman_take','')}\n"
         f"180-260 words, first person, personal conviction. Do NOT use em dashes. "
         f"Output ONLY the op-ed text.\n\nBlog excerpt:\n{excerpt}"),
        ("danielle-voice", "danielle-oped.md",
         f"Write a LinkedIn op-ed in Danielle's voice (Director of School Partnerships) on this week's A+ blog.\n"
         f"Topic: {headline}\nAngle: {topic.get('angle','')}\nDanielle's take: {topic.get('danielle_take','')}\n"
         f"180-260 words, practical implementation lens. Do NOT use em dashes. "
         f"Output ONLY the op-ed text.\n\nBlog excerpt:\n{excerpt}"),
        ("aplus-b2b-brand-kit", "linkedin-company.md",
         f"Write a LinkedIn COMPANY post for the A+ Tutoring company page promoting this week's blog.\n"
         f"Topic: {headline}\n120-180 words: a hook, 2-3 insight lines, and a soft CTA to read the blog. "
         f"B2B brand voice. Do NOT use em dashes. Output ONLY the post text."),
    ]
    for skill, fname, prompt in jobs:
        try:
            res = runner.run_skill(skill, prompt, max_tokens=2000)
            (bundle_dir / fname).write_text(bp.strip_em_dashes(res.text.strip()) + "\n", encoding="utf-8")
            logger.info("oped_asset written: %s", fname)
        except Exception as e:
            logger.warning("oped asset %s failed: %s", fname, e)


def _deliver_to_slack(bundle_dir: Path, post_id: "str | None") -> int:
    """Deliver the bundle to Slack, passing the HubSpot post id so the header carries
    a WORKING draft link (the editor URL; the live URL 404s until published)."""
    cmd = ["python3", str(bp.REPO_ROOT / "scripts" / "b2b" / "deliver-to-slack.py"), "--bundle", str(bundle_dir)]
    if post_id:
        cmd += ["--post-id", str(post_id)]
    try:
        r = subprocess.run(cmd, cwd=str(bp.REPO_ROOT), capture_output=True, text=True, timeout=600)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            logger.warning("deliver-to-slack rc=%s: %s", r.returncode, (r.stderr or "")[:300])
        return r.returncode
    except Exception as e:
        logger.warning("deliver-to-slack error: %s", e)
        return 1


def _apply_mechanical_fixes(body: str, meta: dict) -> "tuple[str, dict]":
    """Deterministic backstops the LLM keeps missing: strip em/en dashes (brand
    auto-reject) and normalize the slug. Guaranteed, not best-effort."""
    body = bp.strip_em_dashes(body)
    if isinstance(meta.get("url_slug"), str):
        meta["url_slug"] = bp.normalize_slug(meta["url_slug"])
    return body, meta


def _run_checks(runner: SkillsRunner, body: str, meta: dict):
    """Run SEO + fact + brand. Returns (seo_issues, fact_pass, fact_result, brand_pass, brand_result)."""
    seo_fields = {k: v for k, v in meta.items() if isinstance(v, str)}
    seo_fields.setdefault("slug", str(meta.get("url_slug", "")))  # validator keys on `slug`
    seo_issues = bp.validate_seo_fields(seo_fields)
    fact_pass, fact_result = bp.run_fact_check(runner, body)
    brand_pass, brand_result = bp.run_brand_check(runner, body)
    return seo_issues, fact_pass, fact_result, brand_pass, brand_result


def build_slot(slot: int, topic: dict, week: str, runner: SkillsRunner, *, dry_run: bool, existing_post_id: "str | None" = None) -> dict:
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

    body, meta = _apply_mechanical_fixes(body, meta)
    seo_issues, fact_pass, fact_result, brand_pass, brand_result = _run_checks(runner, body, meta)

    # --- automatic correction LOOP: feed the QA findings to aplus-content-corrector,
    # which rewrites the post to fix them; re-check and repeat until everything passes
    # or MAX_CORRECTION_PASSES is hit. The draft you review is the corrected version.
    MAX_CORRECTION_PASSES = 5

    def _score(seo, fp, bp_):  # fewer failures = better; 0 = fully clean
        return (0 if fp else 1) + (0 if bp_ else 1) + (1 if seo else 0)

    def _snapshot():
        return {"score": _score(seo_issues, fact_pass, brand_pass), "body": body, "meta": meta,
                "seo": seo_issues, "fp": fact_pass, "fr": fact_result, "bp": brand_pass, "br": brand_result}

    best = _snapshot()
    passes = 0
    while best["score"] > 0 and passes < MAX_CORRECTION_PASSES:
        passes += 1
        logger.info("slot=%s correction pass %d/%d (fact=%s brand=%s seo=%d)",
                    slot, passes, MAX_CORRECTION_PASSES, fact_pass, brand_pass, len(seo_issues))
        new_body, new_meta = bp.run_corrections(
            runner, body, bp.format_meta_for_hubspot_script(meta, topic),
            fact_report=("" if fact_pass else fact_result.text),
            brand_report=("" if brand_pass else brand_result.text),
            seo_issues=seo_issues,
        )
        if not (new_body and new_meta):
            logger.warning("slot=%s corrector output unparseable on pass %d; stopping", slot, passes)
            break
        # Carry carousel_slides forward if the corrector dropped them (graphics need it).
        if not new_meta.get("carousel_slides") and meta.get("carousel_slides"):
            new_meta["carousel_slides"] = meta["carousel_slides"]
        body, meta = _apply_mechanical_fixes(new_body, new_meta)
        seo_issues, fact_pass, fact_result, brand_pass, brand_result = _run_checks(runner, body, meta)
        sc = _score(seo_issues, fact_pass, brand_pass)
        logger.info("slot=%s after pass %d: fact=%s brand=%s seo=%d (score=%d, best=%d)",
                    slot, passes, fact_pass, brand_pass, len(seo_issues), sc, best["score"])
        if sc < best["score"]:
            best = _snapshot()
    if passes:
        # Ship the BEST version seen across passes, never a regressed final pass.
        body, meta = best["body"], best["meta"]
        seo_issues, fact_pass, fact_result, brand_pass, brand_result = (
            best["seo"], best["fp"], best["fr"], best["bp"], best["br"])
        logger.info("slot=%s corrections done after %d pass(es), shipping best: fact=%s brand=%s seo=%d",
                    slot, passes, fact_pass, brand_pass, len(seo_issues))

    for issue in seo_issues:
        logger.warning("seo_issue slot=%s %s", slot, issue)

    # Remaining gates after the correction pass are ADVISORY — a human reviews every
    # draft in HubSpot before posting. Failures are flagged on the bundle, never block.
    flags: list[str] = []
    if not fact_pass:
        flags.append("FACT-CHECK — " + (_extract_issues(fact_result.text) or "see fact-check-report.md"))
    if not brand_pass:
        flags.append("BRAND-CHECK — " + (_extract_issues(brand_result.text) or "see brand-check-report.md"))
    flags += [f"SEO — {issue}" for issue in seo_issues]

    slug = _slugify(str(meta.get("url_slug", "")), f"slot-{slot}")
    bundle_dir = bp.CONTENT_DIR / f"{post_date}-{slug}"
    bp.write_bundle(
        bundle_dir, body, bp.format_meta_for_hubspot_script(meta, topic),
        {"fact-check": fact_result, "brand-check": brand_result},
    )
    if flags:
        (bundle_dir / "review-flags.md").write_text(
            "# Review flags — check/fix in HubSpot before posting\n\n"
            + "\n".join(f"- {f}" for f in flags) + "\n",
            encoding="utf-8",
        )
    logger.info(
        "bundle_written slot=%s path=%s flags=%d (fact=%s brand=%s seo=%d)",
        slot, bundle_dir, len(flags), fact_pass, brand_pass, len(seo_issues),
    )

    # Distinct hero + pull-quotes + social card (best-effort) before the draft.
    _build_graphics(bundle_dir)
    # Roman + Danielle LinkedIn op-eds + company post (best-effort).
    _generate_oped_assets(runner, bundle_dir, topic, body)

    if dry_run:
        return {"slot": slot, "status": "generated", "headline": topic.get("headline"),
                "bundle_dir": str(bundle_dir), "post_date": str(post_date),
                "fact_pass": fact_pass, "brand_pass": brand_pass,
                "seo_issues": len(seo_issues), "flags": len(flags), "flag_details": flags, "dry_run": True}

    publish_rc, post_id = _publish_draft(bundle_dir, update_post_id=existing_post_id)
    if publish_rc != 0:
        raise RuntimeError(f"slot {slot}: publish-to-hubspot.py exited {publish_rc}")
    action = "updated" if existing_post_id else "created"
    logger.info("hubspot_draft_%s slot=%s post_id=%s", action, slot, post_id)

    # Embed pull-quote figures inline in the draft body (best-effort). --reset-figures
    # makes it idempotent so re-runs refresh figures instead of stacking duplicates.
    if post_id:
        try:
            r = subprocess.run(
                ["python3", str(bp.REPO_ROOT / "scripts" / "shared" / "embed-pull-quotes.py"),
                 "--bundle", str(bundle_dir), "--post-id", str(post_id), "--reset-figures"],
                cwd=str(bp.REPO_ROOT), capture_output=True, text=True, timeout=300,
            )
            sys.stdout.write(r.stdout)
            if r.returncode != 0:
                logger.warning("embed-pull-quotes slot=%s rc=%s: %s", slot, r.returncode, (r.stderr or "")[:300])
        except Exception as e:
            logger.warning("embed-pull-quotes slot=%s error: %s", slot, e)

    slack_rc = _deliver_to_slack(bundle_dir, post_id)
    if slack_rc != 0:
        logger.warning("slot %s deliver-to-slack rc=%s (continuing)", slot, slack_rc)

    # --- mark staged (re-read to avoid clobbering concurrent writes) ---
    q = read_topic_queue()
    if q.topics and slot - 1 < len(q.topics):
        t = dict(q.topics[slot - 1])
        t["staged"] = True
        t["staged_at"] = datetime.now().astimezone().isoformat()
        t["post_date"] = str(post_date)
        t["bundle_dir"] = str(bundle_dir.relative_to(bp.REPO_ROOT))
        if post_id:
            t["hubspot_post_id"] = post_id
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
        "hubspot_post_id": post_id,
        "action": action,
        "fact_pass": fact_pass,
        "brand_pass": brand_pass,
        "seo_issues": len(seo_issues),
        "flags": flags,
    })
    return {"slot": slot, "status": "staged", "action": action, "headline": topic.get("headline"),
            "bundle_dir": str(bundle_dir), "post_date": str(post_date), "hubspot_post_id": post_id,
            "fact_pass": fact_pass, "brand_pass": brand_pass,
            "seo_issues": len(seo_issues), "flags": len(flags), "flag_details": flags,
            "publish_rc": publish_rc, "slack_rc": slack_rc}


def build(*, dry_run: bool = False, only_slot: int | None = None, rebuild: bool = False) -> list[dict]:
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
        if topic.get("staged") and not rebuild:
            results.append({"slot": slot, "status": "skipped", "reason": f"already staged at {topic.get('staged_at')}"})
            continue
        results.append(build_slot(
            slot, topic, week, runner,
            dry_run=dry_run, existing_post_id=topic.get("hubspot_post_id"),
        ))
    # One consolidated Slack message: the 3 drafts + links + their specific flags,
    # so Danielle sees exactly what to fix (only on a full real build).
    if not dry_run and not only_slot:
        _post_summary(results)
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Weekend batch build: 3 approved blogs -> HubSpot drafts")
    p.add_argument("--slot", type=int, choices=[1, 2, 3], help="build a single slot (testing)")
    p.add_argument("--dry-run", action="store_true", help="generate + write bundles, skip HubSpot/Slack/state")
    p.add_argument("--rebuild", action="store_true", help="rebuild already-staged slots, updating their existing HubSpot drafts in place")
    args = p.parse_args()
    try:
        results = build(dry_run=args.dry_run, only_slot=args.slot, rebuild=args.rebuild)
    except Exception as e:
        logger.exception("content_build_failed: %s", e)
        return 1
    import json
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
