"""Draft feedback loop — the team's edits ARE the training signal.

Tier 1 (automatic): every agent-created draft is registered here with the
exact text the agent wrote. Each sweep checks Gmail: draft still there →
pending; gone → find what was SENT on that thread and compare:
  sent as-is        → good
  edited then sent  → needs improvement (the diff shows exactly what)
  nothing sent      → discarded / rewritten
Tier 2 (automatic): edits + discards land in corrections/email-drafts/ AND in a
compact style-rules file the drafting prompts load at runtime, so tomorrow's
drafts carry yesterday's edits. Weekly one-liner to the visionary seat.
Tier 3 (people): a reply to the aplus bot in #agent-feedback becomes a style
rule via the same corrections path (feedback agent, unchanged).

State: state/draft_registry.jsonl (append-only events, committed like the
audit log). Read-only against Gmail; writes only repo files + one Slack DM.
"""
from __future__ import annotations

import base64
import difflib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import gmail_client as gm, slack_client
from .business_hours import now_la
from .config import DRY_RUN, ROOT, cfg, staff

REGISTRY = ROOT / "state" / "draft_registry.jsonl"
STYLE_RULES = ROOT.parent / "corrections" / "email-drafts" / "STYLE-RULES.md"
CORR_DIR = ROOT.parent / "corrections" / "email-drafts"

# ── registry ────────────────────────────────────────────────────────────────

def _append(rec: dict) -> None:
    rec.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    if DRY_RUN:
        print(f"[DRY_RUN] draft_registry << {json.dumps(rec, default=str)[:200]}")
        return
    REGISTRY.parent.mkdir(exist_ok=True)
    with open(REGISTRY, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _iter():
    if not REGISTRY.exists():
        return
    with open(REGISTRY) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def register(draft: dict, kind: str, body: str, to_addr: str, source: str,
             thread_id: str = "", meta: dict | None = None) -> None:
    """Call right after any create_draft*(): remember what the agent wrote."""
    d_msg = (draft or {}).get("message") or {}
    if not (draft or {}).get("id"):
        return
    _append({"event": "created", "draft_id": draft["id"],
             "message_id": d_msg.get("id"), "thread_id": d_msg.get("threadId") or thread_id,
             "kind": kind, "source": source, "to": to_addr,
             "body": body, **(meta or {})})


def _open_drafts() -> list[dict]:
    created, closed = {}, set()
    for r in _iter():
        if r.get("event") == "created":
            created[r["draft_id"]] = r
        elif r.get("event") in ("outcome",):
            closed.add(r.get("draft_id"))
    return [r for did, r in created.items() if did not in closed]


# ── outcome detection ───────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _sent_on_thread(thread_id: str, since_iso: str) -> dict | None:
    """The most recent SENT message on the thread after the draft was created."""
    if not thread_id:
        return None
    try:
        th = gm._get(f"/threads/{thread_id}", {"format": "full"})
    except Exception:  # noqa: BLE001
        return None
    best = None
    for m in th.get("messages", []):
        if "SENT" not in (m.get("labelIds") or []):
            continue
        internal = int(m.get("internalDate") or 0) / 1000
        if datetime.fromtimestamp(internal, tz=timezone.utc).isoformat() < since_iso:
            continue
        # body text
        def _text(part) -> str:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
            return "".join(_text(p) for p in part.get("parts", []) or [])
        body = _text(m.get("payload", {})) or m.get("snippet", "")
        if not best or internal > best["ts"]:
            best = {"ts": internal, "body": body, "id": m.get("id")}
    return best


def _classify(agent_body: str, sent_body: str) -> tuple[str, float, str]:
    """(verdict, similarity, unified diff). Quoted-reply tails are stripped
    before comparing so a Gmail-appended quote doesn't read as an edit."""
    sent_clean = re.split(r"\n\s*On .+?wrote:|\n>+ ", sent_body, maxsplit=1,
                          flags=re.S)[0]
    a, b = _norm(agent_body), _norm(sent_clean)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.97:
        return "sent_as_is", ratio, ""
    diff = "\n".join(difflib.unified_diff(
        agent_body.splitlines(), sent_clean.splitlines(),
        fromfile="agent draft", tofile="as sent", lineterm="", n=1))
    if ratio >= 0.5:
        return "edited", ratio, diff
    return "rewritten", ratio, diff


def sweep() -> None:
    """Every 15-min run: settle any agent draft that has left Gmail Drafts."""
    settled = 0
    for r in _open_drafts():
        if gm.get_draft(r["draft_id"]) is not None:
            continue                                   # still pending
        sent = _sent_on_thread(r.get("thread_id"), r.get("timestamp") or "")
        if sent:
            verdict, ratio, diff = _classify(r.get("body") or "", sent["body"])
        else:
            verdict, ratio, diff = "discarded", 0.0, ""
        _append({"event": "outcome", "draft_id": r["draft_id"], "kind": r.get("kind"),
                 "source": r.get("source"), "to": r.get("to"), "verdict": verdict,
                 "similarity": round(ratio, 3), "diff": diff[:4000],
                 "sent_message_id": (sent or {}).get("id")})
        # Gmail label flip on the sent message
        try:
            if sent and sent.get("id"):
                gm.apply_labels(sent["id"], ["A+ Agent/Sent"])
        except Exception:  # noqa: BLE001
            pass
        if verdict in ("edited", "rewritten", "discarded"):
            _record_correction(r, verdict, diff, (sent or {}).get("body", ""))
        settled += 1
    if settled:
        print(f"draft_feedback: {settled} draft(s) settled")


# ── Tier 2: corrections + runtime style rules ───────────────────────────────

def _record_correction(created: dict, verdict: str, diff: str, sent_body: str) -> None:
    """One file per edited/discarded draft in corrections/email-drafts/ (the
    fleet's standard feedback format), plus a distilled line in STYLE-RULES.md
    that the drafting prompts load at runtime."""
    if DRY_RUN:
        return
    CORR_DIR.mkdir(parents=True, exist_ok=True)
    day = now_la().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", f"{created.get('kind')}-{verdict}-"
                  f"{(created.get('to') or '').split('@')[0]}").strip("-")[:60]
    path = CORR_DIR / f"{day}-{slug}.md"
    n = 2
    while path.exists():
        path = CORR_DIR / f"{day}-{slug}-{n}.md"; n += 1
    path.write_text(
        f"---\nreporter: gmail (draft outcome)\ndate: {day}\nagent: email-{created.get('source')}\n"
        f"agent_label: Email drafts\ntype: ANNOYING\nseverity: low\n"
        f"kind: {created.get('kind')}\nverdict: {verdict}\ndraft_id: {created.get('draft_id')}\n"
        f"status: open\n---\n\n## Agent draft\n\n```\n{created.get('body') or ''}\n```\n\n"
        + (f"## As sent\n\n```\n{sent_body[:3000]}\n```\n\n## Diff\n\n```diff\n{diff}\n```\n"
           if verdict != "discarded" else "## Outcome\n\nDraft discarded — no message sent on the thread.\n"))
    # distilled rule: the human's version of changed lines is the guidance
    if verdict in ("edited", "rewritten") and diff:
        added = [l[1:].strip() for l in diff.splitlines()
                 if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
        removed = [l[1:].strip() for l in diff.splitlines()
                   if l.startswith("-") and not l.startswith("---") and l[1:].strip()]
        if added or removed:
            STYLE_RULES.parent.mkdir(parents=True, exist_ok=True)
            hdr = ("# Email draft style rules (learned from the team's edits)\n\n"
                   "Loaded into the drafting prompts at runtime. Newest last; "
                   "the drafter sees the most recent 25.\n\n")
            if not STYLE_RULES.exists():
                STYLE_RULES.write_text(hdr)
            with open(STYLE_RULES, "a") as f:
                f.write(f"- ({day}, {created.get('kind')}) team changed "
                        f"{' / '.join(repr(x[:80]) for x in removed[:2]) or '(added text)'} → "
                        f"{' / '.join(repr(x[:80]) for x in added[:2]) or '(removed text)'}\n")


def style_rules_prompt(max_rules: int = 25) -> str:
    """The learned rules, formatted for a system prompt. Empty until edits exist."""
    if not STYLE_RULES.exists():
        return ""
    rules = [l for l in STYLE_RULES.read_text().splitlines() if l.startswith("- ")]
    if not rules:
        return ""
    return ("\n\nSTYLE RULES learned from how the team edited earlier drafts — write the "
            "way the team ended up sending, not the way earlier drafts read:\n"
            + "\n".join(rules[-max_rules:]))


# ── weekly one-liner ────────────────────────────────────────────────────────

def weekly_report() -> None:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    outcomes = [r for r in _iter() if r.get("event") == "outcome"
                and (r.get("timestamp") or "") >= since]
    if not outcomes:
        return
    c = {k: sum(1 for r in outcomes if r["verdict"] == k)
         for k in ("sent_as_is", "edited", "rewritten", "discarded")}
    n = len(outcomes)
    lines = [f"✍️ *Agent drafts — last 7 days:* {n} settled — "
             f"{c['sent_as_is']} sent as-is ({round(100 * c['sent_as_is'] / n)}%), "
             f"{c['edited']} edited, {c['rewritten']} rewritten, {c['discarded']} discarded."]
    ex = [r for r in outcomes if r["verdict"] in ("edited", "rewritten")][:3]
    for r in ex:
        added = [l[1:].strip() for l in (r.get("diff") or "").splitlines()
                 if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
        if added:
            lines.append(f"  • {r.get('kind')} → team wrote: \"{added[0][:90]}\"")
    slack_client.dm(staff("visionary").get("slack_user_id"), "\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    import sys
    weekly_report() if "--weekly" in sys.argv else sweep()
