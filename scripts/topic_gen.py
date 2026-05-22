"""Thursday 5 PM topic generation orchestrator.

Run flow:
  1. Run 3 lens variants (lens_runs.run_all_lenses) → 3 candidate topics
  2. Filter each through lens 0 redundancy check (lens_zero), unless refresh mode
  3. Post the surviving candidates to Slack as a single message in the
     weekly-content-ready channel, with instructions for approval/edit
  4. Save state/topic-queue.json with message ts + approval deadline
  5. approval_deadline.py (run Mon 7 AM) polls the message and resolves approval

The Slack message format follows the polling pattern already used by
await-slack-approval.py — no webhook endpoint needed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from lens_runs import LENSES, LensRunResult, Topic, run_all_lenses
from lens_zero import check_many, RedundancyVerdict
from refresh_mode import is_refresh_mode
from skills_runner import SkillsRunner
from state import topic_queue_transaction, append_history_run

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_SCHOOLS_PATH = REPO_ROOT / "skills" / "aplus-research" / "target-schools.md"

SLACK_BASE = "https://slack.com/api"
DEFAULT_CHANNEL = os.environ.get("TOPIC_REVIEW_CHANNEL", "#weekly-content-ready")

# Pacific Time hardcoded — A+ runs on PT (Roman + Danielle both in CA).
# datetime.timezone has no DST awareness; use offsets matching the operating period.
# May is PDT (-7); we'll switch if the architecture needs cross-year ops.
PT = timezone(timedelta(hours=-7), name="PT")


def _slack_token() -> str:
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    return tok


def _slack_call(method: str, endpoint: str, **kwargs) -> dict:
    url = f"{SLACK_BASE}/{endpoint}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_slack_token()}"
    r = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack API error on {endpoint}: {body.get('error', body)}")
    return body


def _load_target_schools_context() -> str:
    if TARGET_SCHOOLS_PATH.is_file():
        return TARGET_SCHOOLS_PATH.read_text(encoding="utf-8")
    return "(No target-schools.md present; HOT 13 list unavailable for this run.)"


def _format_topic_for_slack(slot: int, topic: Topic, verdict: Optional[RedundancyVerdict]) -> str:
    lines = [
        f"*{slot}. {topic.headline}*",
        f"_Lens: {topic.source_lens} | Category: {topic.category}_",
    ]
    if topic.why_matters:
        lines.append(f"*Why this matters:* {topic.why_matters}")
    if topic.angle:
        lines.append(f"*Suggested angle:* {topic.angle}")
    if topic.roman_take:
        lines.append(f"*Roman take:* {topic.roman_take}")
    if topic.danielle_take:
        lines.append(f"*Danielle take:* {topic.danielle_take}")
    if topic.sources:
        lines.append("*Sources:* " + " ".join(f"<{s}|link>" for s in topic.sources[:3]))
    if verdict is not None and not verdict.bypassed:
        lines.append(
            f"_Redundancy check: max similarity {verdict.max_similarity:.2f} "
            f"(threshold {verdict.threshold})_"
        )
    return "\n".join(lines)


def build_slack_message(
    current_week: str,
    candidates: list[tuple[Topic, Optional[RedundancyVerdict]]],
    refresh_mode: bool,
    approval_deadline: datetime,
) -> str:
    header = (
        f":newspaper: *A+ Weekly Topic Slate — {current_week}*\n"
        f"Three topics → publishes Mon (slot 1), Wed (slot 2), Fri (slot 3) at 8 AM PT.\n"
        f"*Approve the slate:* react :white_check_mark: (Roman or Danielle, whoever sees first).\n"
        f"*Edit a slot:* reply in thread `EDIT 1: replacement headline` (also works for 2 or 3).\n"
        f"*Skip a slot:* reply in thread `SKIP 2` (slot 2 won't publish that day).\n"
        f"Auto-approve the slate at *{approval_deadline.strftime('%a %b %d, %I:%M %p %Z')}* if no action."
    )
    if refresh_mode:
        header += "\n:recycle: *Refresh mode ON* — redundancy check bypassed for this run."

    sections = [
        _format_topic_for_slack(idx + 1, topic, verdict)
        for idx, (topic, verdict) in enumerate(candidates)
    ]
    return header + "\n\n" + "\n\n---\n\n".join(sections)


def run(
    *,
    channel: str = DEFAULT_CHANNEL,
    refresh: Optional[bool] = None,
    dry_run: bool = False,
) -> dict:
    """Execute the Thursday topic-gen flow end-to-end."""
    refresh_active = is_refresh_mode() if refresh is None else refresh
    now = datetime.now(PT)
    current_week = now.strftime("%Y-%m-%d")

    # Approval deadline = next Monday 7 AM PT
    days_until_mon = (7 - now.weekday()) % 7 or 7
    monday = (now + timedelta(days=days_until_mon)).replace(
        hour=7, minute=0, second=0, microsecond=0
    )

    logger.info(
        "topic_gen_start week=%s refresh=%s channel=%s deadline=%s",
        current_week, refresh_active, channel, monday.isoformat(),
    )

    context = _load_target_schools_context()
    runner = SkillsRunner()

    lens_results: list[LensRunResult] = run_all_lenses(runner, context)
    topics: list[Topic] = [r.topic for r in lens_results if r.topic is not None]

    if not topics:
        raise RuntimeError("all 3 lenses failed to produce a parseable Topic 1")

    if len(topics) < 3:
        logger.warning("only %d of 3 lenses produced parseable topics", len(topics))

    # Redundancy filter (lens 0)
    verdicts: list[Optional[RedundancyVerdict]] = []
    if refresh_active:
        verdicts = [None] * len(topics)
    else:
        verdicts = check_many([t.headline for t in topics], bypass=False)

    surviving: list[tuple[Topic, Optional[RedundancyVerdict]]] = []
    rejected: list[tuple[Topic, RedundancyVerdict]] = []
    for topic, verdict in zip(topics, verdicts):
        if verdict is not None and verdict.is_redundant:
            rejected.append((topic, verdict))
            logger.warning(
                "topic_rejected_redundant lens=%s headline=%r sim=%.3f matched=%r",
                topic.source_lens, topic.headline[:80], verdict.max_similarity,
                verdict.matched_post.title if verdict.matched_post else None,
            )
        else:
            surviving.append((topic, verdict))

    if not surviving:
        raise RuntimeError(
            "all candidates rejected by lens 0 redundancy check; "
            "enable refresh mode (APLUS_REFRESH_MODE=1) if you want to re-cover an old topic"
        )

    message_text = build_slack_message(current_week, surviving, refresh_active, monday)

    if dry_run:
        print("=== DRY RUN: would post to", channel, "===")
        print(message_text)
        print("=== END DRY RUN ===")
        return {"dry_run": True, "topics": [asdict(t) for t, _ in surviving]}

    post = _slack_call(
        "POST",
        "chat.postMessage",
        json={"channel": channel, "text": message_text, "unfurl_links": False, "unfurl_media": False},
    )
    message_ts = post["ts"]
    channel_id = post["channel"]
    logger.info("slack_posted channel=%s ts=%s", channel_id, message_ts)

    # Persist state
    with topic_queue_transaction() as queue:
        queue.current_week = current_week
        queue.topics = [
            {
                "slot": idx + 1,
                "lens": topic.source_lens,
                "headline": topic.headline,
                "category": topic.category,
                "sources": topic.sources,
                "why_matters": topic.why_matters,
                "angle": topic.angle,
                "roman_take": topic.roman_take,
                "danielle_take": topic.danielle_take,
                "redundancy_max_similarity": (
                    verdict.max_similarity if verdict and not verdict.bypassed else None
                ),
            }
            for idx, (topic, verdict) in enumerate(surviving)
        ]
        queue.slack = {
            "channel_id": channel_id,
            "message_ts": message_ts,
            "posted_at": now.isoformat(),
            "approval_deadline": monday.isoformat(),
            "refresh_mode": refresh_active,
        }
        queue.approval = {
            "status": "pending",
            "approved_slot": None,
            "approved_by": None,
            "approved_at": None,
            "edit_note": None,
        }

    append_history_run({
        "ts": now.isoformat(),
        "kind": "topic_gen",
        "week": current_week,
        "lenses": [r.lens.name for r in lens_results],
        "topics_produced": len(topics),
        "topics_rejected_redundant": len(rejected),
        "topics_posted": len(surviving),
        "refresh_mode": refresh_active,
        "slack_channel": channel_id,
        "slack_ts": message_ts,
    })

    return {
        "channel_id": channel_id,
        "message_ts": message_ts,
        "topics_posted": len(surviving),
        "topics_rejected_redundant": len(rejected),
        "refresh_mode": refresh_active,
        "approval_deadline": monday.isoformat(),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Run Thursday topic generation")
    p.add_argument("--channel", default=DEFAULT_CHANNEL)
    p.add_argument("--refresh", action="store_true", help="enable refresh mode (skip lens 0)")
    p.add_argument("--dry-run", action="store_true", help="print Slack message instead of posting")
    args = p.parse_args()

    try:
        # --refresh CLI flag forces True; absence falls through to APLUS_REFRESH_MODE env var
        refresh_arg = True if args.refresh else None
        result = run(channel=args.channel, refresh=refresh_arg, dry_run=args.dry_run)
    except Exception as e:
        logger.exception("topic_gen_failed: %s", e)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
