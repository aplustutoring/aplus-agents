"""Thursday 5 PM topic generation orchestrator.

Run flow (single-touchpoint engine — no approval gate as of 2026-06-08):
  1. Run 3 lens variants (lens_runs.run_all_lenses) → 3 candidate topics
  2. Filter each through lens 0 redundancy check (lens_zero), unless refresh mode
  3. Post the slate to Slack as an FYI (not an approval ask) in the
     weekly-content-ready channel, with the full pitch per slot in-thread
  4. Save state/topic-queue.json with the slate AUTO-APPROVED
     (approval.status="auto_approved")
  5. content-build (weekend) builds all 3 into HubSpot drafts and posts the
     finished drafts; the human's only gate is publishing each draft.

The old approval poll + Friday deadline workflows are retired — the human
reviews and publishes the finished HubSpot drafts instead of approving topics.
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
import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "shared"))
_sys.path.insert(0, str(_REPO_ROOT / "scripts" / "b2b"))

import requests
from dotenv import load_dotenv

from lens_runs import LENSES, LensRunResult, Topic, run_all_lenses, run_lens
from lens_zero import check_many, RedundancyVerdict
from refresh_mode import is_refresh_mode
from skills_runner import SkillsRunner
from state import topic_queue_transaction, append_history_run, read_topic_queue

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_SCHOOLS_PATH = REPO_ROOT / "skills" / "aplus-research" / "target-schools.md"

SLACK_BASE = "https://slack.com/api"
DEFAULT_CHANNEL = os.environ.get("TOPIC_REVIEW_CHANNEL", "#weekly-content-ready")
# Danielle (Director of School Partnerships) — @-mentioned on each slate so she
# gets a ping to review. Member IDs are not secret (same convention as PAOLA_USER_ID).
DANIELLE_USER_ID = "U05NMABF3B2"

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


def _slot_summary_line(slot: int, entry: dict) -> str:
    if entry["lens_status"] == "ok":
        return f"*Slot {slot}:* {entry['headline']}"
    if entry["lens_status"] == "redundant":
        return (
            f"*Slot {slot}:* ⚠️ Candidate removed by redundancy check — "
            f"this slot will be skipped this week"
        )
    return (
        f"*Slot {slot}:* ⚠️ Lens {slot} failed to produce a topic — "
        f"this slot will be skipped this week"
    )


def _build_slot_entry(
    slot: int,
    lens: object,
    topic: Optional[Topic],
    verdict: Optional[RedundancyVerdict],
    refresh_mode: bool,
) -> dict:
    entry = {
        "slot": slot,
        "lens": lens.name,
        "lens_status": "failed",
        "headline": "",
        "category": "",
        "sources": [],
        "why_matters": "",
        "angle": "",
        "roman_take": "",
        "danielle_take": "",
        "redundancy_max_similarity": None,
        "redundancy_bypassed": False,
    }
    if topic is None:
        return entry

    entry.update(
        {
            "headline": topic.headline,
            "category": topic.category,
            "sources": topic.sources,
            "why_matters": topic.why_matters,
            "angle": topic.angle,
            "roman_take": topic.roman_take,
            "danielle_take": topic.danielle_take,
        }
    )

    if verdict is not None and verdict.is_redundant:
        entry["lens_status"] = "redundant"
        entry["redundancy_max_similarity"] = verdict.max_similarity
        entry["original_headline"] = topic.headline
        return entry

    entry["lens_status"] = "ok"
    entry["redundancy_bypassed"] = bool(refresh_mode)
    if verdict is not None:
        entry["redundancy_max_similarity"] = verdict.max_similarity
    return entry


def _format_slot_thread_reply(slot: int, entry: dict) -> str:
    if entry["lens_status"] != "ok":
        status_text = "Lens failed to produce a topic — this slot is skipped this week."
        if entry["lens_status"] == "redundant":
            status_text = (
                "Candidate removed by redundancy check (too close to a recent post) — "
                "this slot is skipped this week."
            )
        return f"*Slot {slot} — skipped*\n{status_text}"

    lines = [
        f"*Slot {slot} — full pitch*",
        f"*Headline:* {entry['headline']}",
    ]
    if entry.get("category"):
        lines.append(f"*Category:* {entry['category']}")
    if entry.get("why_matters"):
        lines.append(f"*Why it matters:* {entry['why_matters']}")
    if entry.get("angle"):
        lines.append(f"*Angle:* {entry['angle']}")
    if entry.get("roman_take"):
        lines.append(f"*Roman take:* {entry['roman_take']}")
    if entry.get("danielle_take"):
        lines.append(f"*Danielle take:* {entry['danielle_take']}")
    if entry.get("sources"):
        lines.append("*Sources:* " + " ".join(f"<{s}|link>" for s in entry["sources"][:3]))
    if entry.get("redundancy_max_similarity") is not None:
        lines.append(
            f"*Redundancy similarity:* {entry['redundancy_max_similarity']:.2f}"
        )
    elif entry.get("redundancy_bypassed"):
        lines.append("*Redundancy similarity:* bypassed (refresh mode)")
    return "\n".join(lines)


def build_slack_message(
    current_week: str,
    slots: list[dict],
    refresh_mode: bool,
) -> tuple[str, list[str]]:
    header = (
        f":newspaper: <@{DANIELLE_USER_ID}> *A+ Weekly Topic Slate — {current_week}*\n"
        f"Three topics → one blog each, posting Mon (slot 1) / Wed (slot 2) / Fri (slot 3).\n\n"
        f":gear: *Building all three into HubSpot drafts now — drafts ready Monday* in this channel.\n"
        f"No approval step: I'll post the finished drafts with working links; you review each and "
        f"publish it on its day. Don't like one? Just don't publish it.\n\n"
        f"Full pitch for each slot is in the thread below 👇"
    )
    if refresh_mode:
        header += "\n:recycle: *Refresh mode ON* — redundancy check bypassed for this run."

    lines = [_slot_summary_line(slot["slot"], slot) for slot in slots]
    thread_replies = [_format_slot_thread_reply(slot["slot"], slot) for slot in slots]
    return header + "\n\n" + "\n".join(lines), thread_replies


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

    # Guard: never regenerate/overwrite a slate already posted for THIS week (a
    # duplicate PDT/PST cron, or any out-of-band run, would otherwise clobber an
    # approved+staged slate already built into HubSpot drafts — which is exactly
    # what happened on 2026-06-04). A genuinely new week (different current_week)
    # proceeds normally; --refresh forces regeneration.
    if not refresh_active:
        existing = read_topic_queue()
        if existing.current_week == current_week and existing.slack and existing.slack.get("message_ts"):
            status = (existing.approval or {}).get("status", "pending")
            logger.warning(
                "slate for %s already posted (approval=%s) — refusing to regenerate and "
                "clobber it; use --refresh to force.", current_week, status,
            )
            return {"status": "skipped", "reason": f"{current_week} slate already posted (approval={status})"}

    # No approval gate (single touchpoint removed 2026-06-08): the slate is
    # auto-approved on generation and content-build builds all 3 into HubSpot
    # drafts straight away. The human's only gate is publishing each draft.
    logger.info(
        "topic_gen_start week=%s refresh=%s channel=%s (auto-approve, no gate)",
        current_week, refresh_active, channel,
    )

    context = _load_target_schools_context()
    runner = SkillsRunner()

    lens_results: list[LensRunResult] = run_all_lenses(runner, context)
    for idx, result in enumerate(lens_results):
        if result.topic is not None:
            continue
        logger.warning(
            "lens_failed_first_pass slot=%s name=%s — retrying once",
            idx + 1,
            result.lens.name,
        )
        retry_result = run_lens(result.lens, runner, context)
        if retry_result.topic is not None:
            logger.info(
                "lens_retry_ok slot=%s name=%s",
                idx + 1,
                result.lens.name,
            )
        else:
            logger.warning(
                "lens_failed_second_pass slot=%s name=%s",
                idx + 1,
                result.lens.name,
            )
        lens_results[idx] = retry_result

    parseable_results = [r for r in lens_results if r.topic is not None]
    if not parseable_results:
        raise RuntimeError("all 3 lenses failed to produce a parseable Topic 1")

    if len(parseable_results) < 3:
        logger.warning("only %d of 3 lenses produced parseable topics", len(parseable_results))

    if refresh_active:
        verdicts = [None] * len(parseable_results)
    else:
        verdicts = check_many([r.topic.headline for r in parseable_results], bypass=False)

    slots: list[dict] = []
    rejected: list[tuple[Topic, RedundancyVerdict]] = []
    verdict_iter = iter(verdicts)
    ok_slots = 0
    for idx, result in enumerate(lens_results):
        verdict = None
        if result.topic is not None:
            verdict = next(verdict_iter)
        slot_entry = _build_slot_entry(idx + 1, result.lens, result.topic, verdict, refresh_active)
        if slot_entry["lens_status"] == "ok":
            ok_slots += 1
        elif slot_entry["lens_status"] == "redundant" and result.topic is not None and verdict is not None:
            rejected.append((result.topic, verdict))
            logger.warning(
                "topic_rejected_redundant lens=%s headline=%r sim=%.3f matched=%r",
                result.topic.source_lens,
                result.topic.headline[:80],
                verdict.max_similarity,
                verdict.matched_post.title if verdict.matched_post else None,
            )
        slots.append(slot_entry)

    if ok_slots == 0:
        raise RuntimeError(
            "all candidates rejected by lens 0 redundancy check; "
            "enable refresh mode (APLUS_REFRESH_MODE=1) if you want to re-cover an old topic"
        )

    parent_text, thread_replies = build_slack_message(current_week, slots, refresh_active)

    if dry_run:
        print("=== DRY RUN: would post to", channel, "===")
        print(parent_text)
        print("=== DRY RUN: would post thread replies ===")
        for idx, reply in enumerate(thread_replies, start=1):
            print("---")
            print(f"Thread reply for slot {idx}:")
            print(reply)
        print("=== END DRY RUN ===")
        return {"dry_run": True, "slots": slots}

    post = _slack_call(
        "POST",
        "chat.postMessage",
        json={"channel": channel, "text": parent_text, "unfurl_links": False, "unfurl_media": False},
    )
    message_ts = post["ts"]
    channel_id = post["channel"]
    logger.info("slack_posted channel=%s ts=%s", channel_id, message_ts)

    thread_replies_ts: list[dict] = []
    for slot_entry, reply_text in zip(slots, thread_replies):
        thread_post = _slack_call(
            "POST",
            "chat.postMessage",
            json={
                "channel": channel,
                "text": reply_text,
                "thread_ts": message_ts,
                "unfurl_links": False,
                "unfurl_media": False,
            },
        )
        thread_replies_ts.append({"slot": slot_entry["slot"], "ts": thread_post["ts"]})

    with topic_queue_transaction() as queue:
        queue.current_week = current_week
        queue.topics = slots
        queue.slack = {
            "channel_id": channel_id,
            "message_ts": message_ts,
            "posted_at": now.isoformat(),
            "approval_deadline": None,
            "refresh_mode": refresh_active,
            "thread_replies": thread_replies_ts,
            "processed_reply_ts": [],
        }
        # Auto-approved on generation — no approval poll / deadline anymore.
        # content-build's gate accepts "auto_approved" and proceeds.
        queue.approval = {
            "status": "auto_approved",
            "approved_slot": None,
            "approved_by": "auto (no approval gate)",
            "approved_at": now.isoformat(),
            "denied_by": None,
            "denied_at": None,
            "edit_note": None,
        }

    append_history_run({
        "ts": now.isoformat(),
        "kind": "topic_gen",
        "week": current_week,
        "lenses": [r.lens.name for r in lens_results],
        "topics_produced": len(parseable_results),
        "topics_rejected_redundant": len(rejected),
        "topics_posted": ok_slots,
        "refresh_mode": refresh_active,
        "slack_channel": channel_id,
        "slack_ts": message_ts,
    })

    return {
        "channel_id": channel_id,
        "message_ts": message_ts,
        "topics_posted": ok_slots,
        "topics_rejected_redundant": len(rejected),
        "refresh_mode": refresh_active,
        "approval": "auto_approved",
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
