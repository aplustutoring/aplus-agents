#!/usr/bin/env python3
"""
Feedback Agent v1 — "the doorbell for demotions"

One Slack channel (#agent-feedback) where anyone on the team tells the fleet
what's not working. Every top-level message is a report; this script is what
happens when the doorbell rings:

  intake      classify a report -> thread ack (by name) -> correction PR
              (+ ticket draft for BROKEN/critical, fast-path for DEMOTE)
  digest      Friday PM counts by agent/type, unresolved aging, demotion-
              review candidates -> Slack + state/digest-latest.md
  close-loop  a correction PR merged -> reply in the original thread

Mechanism behind two standing promises: the /corrections feedback loop
(#AP008) and "anyone affected can demote an agent instantly" (#AP011).

Probation: ships at Draft. Thread replies are live; correction files open as
PRs Roman merges; tickets are drafted into the thread for Roman to execute;
the DEMOTE registry flip is opened as a one-click PR, never merged by the
agent. All operational pings route per config slack.alerts_to (2026-07-31:
everything goes through Roman). See README.md for the graduation plan.

Fleet conventions honored here:
  - PT for everything human-facing (workflow sets TZ=America/Los_Angeles);
    machine-facing timestamps stay explicit UTC.
  - Labels, never internal names, in anything the team sees (#AP014).
  - Never argue with a reporter, never defend an agent in-thread.
  - FERPA: reports quoting student/family specifics store the thread link
    in the correction file, not the quoted content (#AP008).
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("feedback-agent")

REPO_ROOT = Path(__file__).resolve().parents[2]

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SLACK_BOT_TOKEN   = os.getenv("SLACK_BOT_TOKEN", "")
HUBSPOT_API_KEY   = os.getenv("HUBSPOT_API_KEY", "") or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
GH_TOKEN          = os.getenv("GH_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")

REPORT_TYPES = ["BROKEN", "WRONG", "ANNOYING", "IDEA", "DEMOTE"]
SEVERITIES = ["critical", "normal", "low"]


# ─── Config / state ───────────────────────────────────────────────────────────

def load_config():
    with open(Path(__file__).parent / "config.yml") as f:
        return yaml.safe_load(f)


def load_state(path):
    p = REPO_ROOT / path
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {"processed": [], "awaiting": {}, "reports": [], "graduation": {"clean_merges": 0}}


def save_state(state, path, max_ids):
    state["processed"] = state["processed"][-max_ids:]
    p = REPO_ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ─── Registry (the manifest is the vocabulary) ────────────────────────────────

def load_registry_agents(cfg):
    """id -> {name, status, zaps} for every registered agent. If a described
    behavior maps to none of these, it's UNKNOWN — possible shadow automation,
    which feeds the Zapier census."""
    with open(REPO_ROOT / cfg["registry_path"]) as f:
        reg = yaml.safe_load(f)
    agents = {}
    for a in reg.get("agents", []):
        agents[a["id"]] = {
            "name": a.get("name", a["id"]),
            "status": a.get("status", "unverified"),
            "zaps": a.get("zaps", []),
        }
    return agents


def flip_registry_probation(cfg, agent_id, date_pt):
    """Text-level edit of registry.yml (preserves comments): set
    `probation: draft` inside the agent's block. Returns True on success."""
    path = REPO_ROOT / cfg["registry_path"]
    lines = path.read_text().splitlines(keepends=True)
    # Pass 1: the agent's block = its "- id:" line up to the next "- id:".
    start = end = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*- id:\s*(\S+)\s*$", line):
            if start is not None:
                end = i
                break
            if re.match(rf"^\s*- id:\s*{re.escape(agent_id)}\s*$", line):
                start = i
    if start is None:
        return False
    end = end if end is not None else len(lines)
    # Pass 2: replace an existing probation line, else insert after status.
    new_line = None
    for i in range(start, end):
        if re.match(r"^\s+probation:", lines[i]):
            indent = re.match(r"^(\s+)", lines[i]).group(1)
            lines[i] = f"{indent}probation: draft   # DEMOTED {date_pt} via #agent-feedback\n"
            new_line = i
            break
    if new_line is None:
        for i in range(start, end):
            sm = re.match(r"^(\s+)status:", lines[i])
            if sm:
                lines.insert(i + 1, f"{sm.group(1)}probation: draft   # DEMOTED {date_pt} via #agent-feedback\n")
                new_line = i + 1
                break
    if new_line is None:
        return False
    path.write_text("".join(lines))
    return True


# ─── Slack ────────────────────────────────────────────────────────────────────

def slack_api(method, payload):
    r = requests.post(
        f"https://slack.com/api/{method}",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                 "Content-Type": "application/json; charset=utf-8"},
        json=payload, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack {method} error: {data.get('error')}")
    return data


def post_reply(channel, thread_ts, text, dry_run):
    if dry_run:
        log.info(f"[dry-run] would reply in {channel}/{thread_ts}:\n{text}\n")
        return
    slack_api("chat.postMessage",
              {"channel": channel, "thread_ts": thread_ts, "text": text, "unfurl_links": False})


def post_channel(channel, text, dry_run):
    if dry_run:
        log.info(f"[dry-run] would post to {channel}:\n{text}\n")
        return
    slack_api("chat.postMessage", {"channel": channel, "text": text, "unfurl_links": False})


def get_permalink(channel, ts):
    try:
        r = requests.get(
            "https://slack.com/api/chat.getPermalink",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"channel": channel, "message_ts": ts}, timeout=15,
        )
        data = r.json()
        return data.get("permalink") if data.get("ok") else None
    except requests.RequestException:
        return None


def get_first_name(user_id):
    """Reporter's first name from their Slack profile. A report to the fleet
    is a person talking; the fleet answers like one."""
    try:
        r = requests.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"user": user_id}, timeout=15,
        )
        data = r.json()
        if not data.get("ok"):
            return None
        prof = data["user"].get("profile", {})
        first = prof.get("first_name") or (prof.get("real_name") or "").split(" ")[0]
        return first or data["user"].get("name")
    except requests.RequestException:
        return None


def mention(cfg, person):
    """<@Uxxx> when the member ID is configured, plain name otherwise."""
    uid = (cfg["slack"].get("people") or {}).get(person, "")
    return f"<@{uid}>" if uid.startswith("U") else person.capitalize()


def alert_mentions(cfg):
    """Everyone who receives operational pings (ticket drafts, DEMOTE alerts,
    digest flags) — config slack.alerts_to. 2026-07-31: Roman, who runs
    everything through himself."""
    people = cfg["slack"].get("alerts_to") or ["roman"]
    return " ".join(mention(cfg, p) for p in people)


# ─── Classification (Claude) ──────────────────────────────────────────────────

CLASSIFY_PROMPT = """\
You are @Fleet, the intake for #agent-feedback — the Slack channel where the \
A+ Tutoring team reports problems with the automation fleet. A team member \
named {first_name} posted this report:

<report>
{text}
</report>
{clarification_block}
The registered agents (the ONLY valid vocabulary — if the described behavior \
maps to none of them, use "UNKNOWN"):

{vocabulary}

Classify the report:

- agent_id: which registered agent the report is about. "UNKNOWN" if it maps
  to no registered agent (possible shadow automation).
- type: BROKEN (errored/failed to run) · WRONG (ran fine, bad judgment or
  output) · ANNOYING (noisy, mistimed, tone-off) · IDEA (improvement request)
  · DEMOTE (explicit loss of trust — "turn it off", "stop it", "demote", or
  clear equivalent sentiment; when in doubt between DEMOTE and ANNOYING,
  DEMOTE requires clear turn-it-off intent).
- severity: critical (agent is touching families/schools wrongly RIGHT NOW) ·
  normal · low.
- needs_clarification: true ONLY if you genuinely cannot tell which agent or
  what went wrong. One question max — otherwise proceed with your best read.
- ack_message: your reply in the thread. Rules: open with "{first_name} — ",
  then brief and human — no corporate filler, no "thank you for your
  feedback". Name what you understood and what happens next (correction filed
  for review / ticket drafted). Use the agent's human label, never its
  internal id. NEVER argue with the reporter or defend the agent — corrections
  are data, not litigation. 1–3 sentences.
- slug: 3–6 kebab-case words naming the issue (for the correction filename).
- contains_student_or_family_specifics: true if the report quotes or names a
  specific student, family, or school situation (FERPA — the correction file
  will store the thread link instead of the content).
- summary: one neutral sentence describing the issue, safe to store even when
  the FERPA flag is true (no student/family names or specifics).
"""


def build_schema(agent_ids):
    return {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "enum": agent_ids + ["UNKNOWN"]},
            "type": {"type": "string", "enum": REPORT_TYPES},
            "severity": {"type": "string", "enum": SEVERITIES},
            "needs_clarification": {"type": "boolean"},
            "clarifying_question": {"type": "string"},
            "ack_message": {"type": "string"},
            "slug": {"type": "string"},
            "contains_student_or_family_specifics": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["agent_id", "type", "severity", "needs_clarification",
                     "clarifying_question", "ack_message", "slug",
                     "contains_student_or_family_specifics", "summary"],
        "additionalProperties": False,
    }


def classify_report(text, first_name, agents, cfg, clarification=None):
    import anthropic

    vocabulary = "\n".join(
        f"- {aid}: {meta['name']} (status: {meta['status']})"
        for aid, meta in agents.items()
    )
    clarification_block = ""
    if clarification:
        clarification_block = (
            f"\nYou already asked a clarifying question and {first_name} answered:\n"
            f"<answer>\n{clarification}\n</answer>\n"
            "Do NOT ask again — classify with what you have.\n"
        )
    prompt = CLASSIFY_PROMPT.format(
        first_name=first_name, text=text,
        clarification_block=clarification_block, vocabulary=vocabulary,
    )
    ccfg = cfg["claude"]
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)
    resp = client.messages.create(
        model=ccfg["model"],
        max_tokens=ccfg["max_tokens"],
        output_config={"format": {"type": "json_schema", "schema": build_schema(list(agents))}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise ValueError("Claude refused to classify this report")
    result = json.loads(next(b.text for b in resp.content if b.type == "text"))
    if clarification:
        result["needs_clarification"] = False   # one question max, enforced
    # Belt-and-braces: the ack must open with the reporter's name.
    if not result["ack_message"].startswith(first_name):
        result["ack_message"] = f"{first_name} — {result['ack_message']}"
    result["slug"] = re.sub(r"[^a-z0-9-]", "", result["slug"].lower().replace(" ", "-"))[:40] or "report"
    return result


# ─── Correction files + PRs ───────────────────────────────────────────────────

def agent_label(agents, agent_id):
    if agent_id == "UNKNOWN":
        return "unregistered automation"
    return agents[agent_id]["name"]


def build_correction(cls, payload, first_name, permalink, agents, date_pt):
    """The correction record — the fleet's training diet. FERPA rule: if the
    report quotes student/family specifics, store the thread link, not the
    quoted content (#AP008 channel rules)."""
    ferpa = cls["contains_student_or_family_specifics"]
    front = "\n".join([
        "---",
        f"reporter: {first_name}",
        f"reporter_slack_id: {payload['user']}",
        f"date: {date_pt}",
        f"agent: {cls['agent_id']}",
        f"agent_label: {agent_label(agents, cls['agent_id'])}",
        f"type: {cls['type']}",
        f"severity: {cls['severity']}",
        f"channel: {payload['channel']}",
        f'thread_ts: "{payload["ts"]}"',
        f"permalink: {permalink or 'unavailable'}",
        "status: open",
        "---",
    ])
    if ferpa:
        body = (
            "Report contains student/family specifics — content withheld per the\n"
            f"FERPA channel rule (#AP008). Read it in the thread: {permalink or '(permalink unavailable)'}\n\n"
            f"Neutral summary: {cls['summary']}\n"
        )
    else:
        quoted = "\n".join(f"> {line}" for line in payload["text"].splitlines())
        body = f"## Report ({first_name})\n\n{quoted}\n\n## Classification\n\n{cls['summary']}\n"
    return front + "\n\n" + body


def run_git(args, check=True):
    return subprocess.run(args, cwd=REPO_ROOT, check=check,
                          capture_output=True, text=True)


def open_pr(branch, files, commit_msg, pr_title, pr_body, dry_run):
    """Commit `files` on a fresh branch off origin/main and open a PR.
    Returns the PR URL (or None). Restores the original branch either way."""
    if dry_run:
        log.info(f"[dry-run] would open PR '{pr_title}' on branch {branch} with {files}")
        return None
    orig = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if orig == "HEAD":   # detached (repository_dispatch checkout) — return by SHA
        orig = run_git(["git", "rev-parse", "HEAD"]).stdout.strip()
    try:
        run_git(["git", "checkout", "-b", branch])
        run_git(["git", "add"] + files)
        run_git(["git", "commit", "-m", commit_msg])
        run_git(["git", "push", "-u", "origin", branch])
        r = run_git(["gh", "pr", "create", "--base", "main", "--head", branch,
                     "--title", pr_title, "--body", pr_body])
        url = r.stdout.strip().splitlines()[-1]
        log.info(f"PR opened: {url}")
        return url
    finally:
        run_git(["git", "checkout", orig], check=False)


# ─── HubSpot ticket (per #AP007 conventions) ──────────────────────────────────

def build_ticket_payload(cls, first_name, permalink, agents, cfg, date_pt):
    tcfg = cfg["hubspot"]["ticket"]
    label = agent_label(agents, cls["agent_id"])
    return {
        "properties": {
            "subject": f"[AGENT] {label}: {cls['summary'][:120]}",
            "content": (f"Reported by {first_name} in #agent-feedback ({date_pt}).\n\n"
                        f"{cls['summary']}\n\nThread: {permalink or 'unavailable'}\n"
                        f"Type: {cls['type']} · Severity: {cls['severity']}"),
            "hs_pipeline": tcfg["pipeline"],
            "hs_pipeline_stage": tcfg["stage"],
            "hs_ticket_priority": "HIGH" if cls["severity"] == "critical" else tcfg["priority"],
            "ticket_source": "agent_feedback",
            "source_agent": cls["agent_id"],
        },
    }


def create_ticket(payload):
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/tickets",
        headers={"Authorization": f"Bearer {HUBSPOT_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=20,
    )
    r.raise_for_status()
    return r.json().get("id")


# ─── Intake ───────────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)


def intake(cfg, payload, dry_run):
    state = load_state(cfg["state"]["path"])
    event_key = payload.get("event_id") or f"{payload['channel']}/{payload['ts']}"
    if event_key in state["processed"] or payload["ts"] in state["processed"]:
        log.info(f"already processed {event_key} (Slack retry?) — skipping")
        return
    if payload.get("bot_id"):
        log.info("bot message — ignoring")
        return

    thread_ts = payload.get("thread_ts") or ""
    is_reply = bool(thread_ts) and thread_ts != payload["ts"]
    clarification = None
    if is_reply:
        # Thread replies are conversation, not new reports — except answers in
        # threads @Fleet started with a clarifying question.
        pending = state["awaiting"].get(thread_ts)
        if not pending or pending.get("user") != payload["user"]:
            log.info("thread reply outside a pending clarification — ignoring")
            return
        clarification = payload["text"]
        original_text = pending["text"]
        root_ts = thread_ts
    else:
        original_text = payload["text"]
        root_ts = payload["ts"]

    first_name = get_first_name(payload["user"]) or "there"
    agents = load_registry_agents(cfg)
    cls = classify_report(original_text, first_name, agents, cfg, clarification=clarification)
    label = agent_label(agents, cls["agent_id"])
    log.info(f"classified: agent={cls['agent_id']} type={cls['type']} severity={cls['severity']}")

    # Ambiguous -> ONE clarifying question max, then we proceed regardless.
    if cls["needs_clarification"] and not clarification:
        q = cls["clarifying_question"].strip() or "which agent was this about?"
        if not q.startswith(first_name):
            q = f"{first_name} — quick question so I file this right: {q}"
        post_reply(payload["channel"], root_ts, q, dry_run)
        state["awaiting"][root_ts] = {"user": payload["user"], "text": original_text,
                                      "asked_utc": now_utc().isoformat()}
        state["processed"].append(event_key)
        if not dry_run:
            save_state(state, cfg["state"]["path"], cfg["state"]["max_processed_ids"])
        return

    state["awaiting"].pop(root_ts, None)
    date_pt = datetime.now().strftime("%Y-%m-%d")   # TZ=America/Los_Angeles (fleet convention)
    permalink = get_permalink(payload["channel"], root_ts) if not dry_run else None

    # 1. Ack in thread, by name. DEMOTE gets its confirmation wording — the
    #    demotion is honored FIRST and reviewed after (#AP011); the reporter is
    #    never asked to justify.
    if cls["type"] == "DEMOTE":
        ack = (f"{first_name} — done. *{label}* dropped to Draft — nothing goes out "
               f"without human approval until further notice. "
               f"{alert_mentions(cfg)} pinged with the registry change ready to execute.")
    else:
        ack = cls["ack_message"]
    post_reply(payload["channel"], root_ts, ack, dry_run)

    # 2. Correction file -> PR (draft mode: Roman merges).
    corr_dir = Path(cfg["corrections_dir"]) / cls["agent_id"]
    corr_path = corr_dir / f"{date_pt}-{cls['slug']}.md"
    (REPO_ROOT / corr_dir).mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / corr_path).write_text(
        build_correction(cls, {**payload, "ts": root_ts}, first_name, permalink, agents, date_pt))
    short_ts = root_ts.replace(".", "")[-6:]
    pr_url = open_pr(
        branch=f"corrections/{cls['agent_id']}-{date_pt}-{cls['slug']}-{short_ts}",
        files=[str(corr_path)],
        commit_msg=f"correction({cls['agent_id']}): {cls['slug']} [{cls['type']}]",
        pr_title=f"[correction] {label}: {cls['slug'].replace('-', ' ')}",
        pr_body=(f"{cls['type']} / {cls['severity']} — reported by {first_name} in #agent-feedback.\n\n"
                 f"{cls['summary']}\n\nThread: {permalink or 'n/a'}\n\n"
                 f"Filed by the Feedback Agent (Draft probation — merge to accept into the training diet)."),
        dry_run=dry_run,
    )
    if dry_run:
        (REPO_ROOT / corr_path).unlink(missing_ok=True)

    # 3. BROKEN or critical -> HubSpot ticket, so it enters the re-ping ladder
    #    with a human name attached (#AP007). Draft probation: the payload is
    #    posted for the approver (slack.alerts_to) to execute; graduated: created directly.
    ticket_status = None
    if cls["type"] == "BROKEN" or cls["severity"] == "critical":
        tpayload = build_ticket_payload(cls, first_name, permalink, agents, cfg, date_pt)
        if cfg["probation"]["stage"] == "draft":
            post_reply(payload["channel"], root_ts,
                       f"{alert_mentions(cfg)} — ticket drafted for this one "
                       f"({cls['type']}/{cls['severity']}), ready to create:\n"
                       f"```{json.dumps(tpayload, indent=2)}```", dry_run)
            ticket_status = "drafted"
        else:
            ticket_id = None if dry_run else create_ticket(tpayload)
            ticket_status = f"created:{ticket_id}"

    # 4. DEMOTE fast path — no debate, no triage.
    if cls["type"] == "DEMOTE":
        demote_pr = None
        if cls["agent_id"] != "UNKNOWN":
            flipped = flip_registry_probation(cfg, cls["agent_id"], date_pt)
            if flipped:
                demote_pr = open_pr(
                    branch=f"demote/{cls['agent_id']}-{date_pt}-{short_ts}",
                    files=[cfg["registry_path"]],
                    commit_msg=f"registry: demote {cls['agent_id']} to draft (via #agent-feedback)",
                    pr_title=f"[DEMOTE] {label} -> Draft probation",
                    pr_body=(f"Demotion reported by {first_name} in #agent-feedback. Per #AP011 the "
                             f"demotion is honored first and reviewed after.\n\nThread: {permalink or 'n/a'}\n\n"
                             f"One click: merge to flip `{cls['agent_id']}` to `probation: draft`."),
                    dry_run=dry_run,
                )
                if dry_run:
                    run_git(["git", "checkout", "--", cfg["registry_path"]], check=False)
            zaps = agents[cls["agent_id"]]["zaps"]
            zap_note = (f"Zaps to pause: {', '.join(zaps)}" if zaps
                        else "No zaps registered to this agent in registry.yml — cross-check the Zapier census.")
        else:
            zap_note = "Agent is UNKNOWN — possible shadow automation; check the Zapier census before pausing anything."
        post_reply(payload["channel"], root_ts,
                   f"{alert_mentions(cfg)} — DEMOTE on *{label}* "
                   f"from {first_name}. Registry PR ready: {demote_pr or '(see run log — PR not opened)'}. "
                   f"{zap_note}", dry_run)

    if cls["agent_id"] == "UNKNOWN":
        log.info("UNKNOWN agent — flagged as possible shadow automation (Zapier census input)")

    # 5. Log for the digest + close-the-loop.
    state["reports"].append({
        "date": date_pt, "ts": root_ts, "channel": payload["channel"],
        "reporter": first_name, "reporter_slack_id": payload["user"],
        "agent": cls["agent_id"], "type": cls["type"], "severity": cls["severity"],
        "correction_path": str(corr_path), "pr_url": pr_url,
        "ticket": ticket_status, "status": "open", "permalink": permalink,
    })
    state["processed"].append(event_key)
    if not dry_run:
        save_state(state, cfg["state"]["path"], cfg["state"]["max_processed_ids"])
    log.info("intake complete")


# ─── Digest (Friday PM) ───────────────────────────────────────────────────────

def digest(cfg, dry_run):
    state = load_state(cfg["state"]["path"])
    today = datetime.now().date()   # PT via workflow TZ
    week_ago = today - timedelta(days=7)
    window = today - timedelta(days=cfg["digest"]["review_window_days"])

    def d(r):
        return datetime.strptime(r["date"], "%Y-%m-%d").date()

    weekly = [r for r in state["reports"] if d(r) >= week_ago]
    recent = [r for r in state["reports"] if d(r) >= window]
    unresolved = [r for r in state["reports"] if r["status"] == "open" and r["type"] != "IDEA"]

    counts = {}
    for r in weekly:
        counts.setdefault(r["agent"], {}).setdefault(r["type"], 0)
        counts[r["agent"]][r["type"]] += 1

    # Demotion-review candidates: >=N WRONG/ANNOYING in the review window.
    # The scoreboard tracks agents, not humans — aggregate by agent only.
    flagged = {}
    for r in recent:
        if r["type"] in ("WRONG", "ANNOYING"):
            flagged[r["agent"]] = flagged.get(r["agent"], 0) + 1
    candidates = {a: n for a, n in flagged.items() if n >= cfg["digest"]["review_threshold"]}

    agents = load_registry_agents(cfg)
    lines = [f"*Fleet feedback — week ending {today.strftime('%b %-d')}*"]
    if counts:
        lines.append("")
        for aid, by_type in sorted(counts.items(), key=lambda kv: -sum(kv[1].values())):
            parts = " · ".join(f"{n} {t}" for t, n in sorted(by_type.items()))
            lines.append(f"• *{agent_label(agents, aid) if aid == 'UNKNOWN' or aid in agents else aid}* — {parts}")
    else:
        lines.append("\nNo reports this week. Either the fleet behaved or nobody rang the doorbell.")
    if unresolved:
        lines.append("\n*Unresolved corrections:*")
        for r in sorted(unresolved, key=lambda r: r["date"])[:10]:
            age = (today - d(r)).days
            lines.append(f"• {agent_label(agents, r['agent']) if r['agent'] in agents or r['agent'] == 'UNKNOWN' else r['agent']}"
                         f" — {r['type']}, {age}d old ({r['pr_url'] or 'no PR'})")
    if candidates:
        lines.append(f"\n*Demotion-review candidates* (≥{cfg['digest']['review_threshold']} "
                     f"WRONG/ANNOYING in {cfg['digest']['review_window_days']}d — for "
                     f"{alert_mentions(cfg)}'s ledger):")
        for aid, n in sorted(candidates.items(), key=lambda kv: -kv[1]):
            lines.append(f"• *{agent_label(agents, aid) if aid in agents or aid == 'UNKNOWN' else aid}* — {n} reports")
    clean = state["graduation"]["clean_merges"]
    target = cfg["probation"]["clean_reports_target"]
    lines.append(f"\n_Feedback Agent probation: {clean}/{target} clean reports toward autonomous filing._")

    text = "\n".join(lines)
    post_channel(cfg["slack"]["channel"], text, dry_run)

    # Written copy feeds the Integrator's Monday brief.
    md_path = REPO_ROOT / cfg["state"]["digest_path"]
    if not dry_run:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(f"# Fleet feedback digest — {today}\n\n" +
                           text.replace("*", "**") + "\n")
    log.info("digest complete")


# ─── Close the loop ───────────────────────────────────────────────────────────

def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm


def close_loop(cfg, pr_number, dry_run):
    """A correction PR merged -> tell the reporter in the original thread what
    changed and when. Feedback that vanishes into a void kills the channel;
    the reply-back is the feature."""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    pr = json.loads(run_git(["gh", "api", f"repos/{repo}/pulls/{pr_number}"]).stdout)
    if not pr.get("merged_at"):
        log.info("PR not merged — nothing to close")
        return
    files = json.loads(run_git(["gh", "api", f"repos/{repo}/pulls/{pr_number}/files", "--paginate"]).stdout)
    corr_files = [f["filename"] for f in files
                  if f["filename"].startswith(cfg["corrections_dir"]) and f["filename"].endswith(".md")]
    if not corr_files:
        log.info("no correction files in this PR — nothing to close")
        return

    state = load_state(cfg["state"]["path"])
    merged_pt = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")) \
        .astimezone().strftime("%b %-d, %-I:%M %p PT")
    clean = pr.get("commits", 0) == 1   # merged untouched = a clean report for graduation

    for path in corr_files:
        full = REPO_ROOT / path
        if not full.exists():
            continue
        fm = parse_frontmatter(full.read_text())
        if not fm.get("channel") or not fm.get("thread_ts"):
            continue
        name = fm.get("reporter", "there")
        post_reply(fm["channel"], fm["thread_ts"],
                   f"{name} — closing the loop: your report on *{fm.get('agent_label', fm.get('agent'))}* "
                   f"was accepted into the correction log {merged_pt} "
                   f"({pr['title']}). It's now part of what the fleet trains against.", dry_run)
        for r in state["reports"]:
            if r.get("correction_path") == path:
                r["status"] = "resolved"
        if clean:
            state["graduation"]["clean_merges"] += 1

    if not dry_run:
        save_state(state, cfg["state"]["path"], cfg["state"]["max_processed_ids"])
    log.info("close-loop complete")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Feedback Agent v1")
    ap.add_argument("--mode", choices=["intake", "digest", "close-loop"], default="intake")
    ap.add_argument("--pr", type=int, help="PR number (close-loop mode)")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + print; no Slack/PR/ticket writes, no state persist")
    args = ap.parse_args()

    if os.getenv("CHECK_ONLY") == "true":
        missing = [n for n, v in [("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
                                  ("SLACK_BOT_TOKEN", SLACK_BOT_TOKEN),
                                  ("GH_TOKEN/GITHUB_TOKEN", GH_TOKEN)] if not v]
        if missing:
            log.error(f"CHECK_ONLY: missing secrets: {', '.join(missing)}")
            sys.exit(1)
        log.info("CHECK_ONLY: secrets wired, config loads, registry parses "
                 f"({len(load_registry_agents(load_config()))} agents). OK.")
        return

    cfg = load_config()
    if args.mode == "intake":
        raw = os.getenv("REPORT_PAYLOAD", "")
        if not raw:
            log.error("REPORT_PAYLOAD env var is empty — nothing to process")
            sys.exit(1)
        payload = json.loads(raw)
        for key in ("channel", "user", "text", "ts"):
            if not payload.get(key):
                log.error(f"payload missing '{key}' — ignoring event")
                return
        intake(cfg, payload, args.dry_run)
    elif args.mode == "digest":
        digest(cfg, args.dry_run)
    else:
        if not args.pr:
            log.error("--pr required for close-loop mode")
            sys.exit(1)
        close_loop(cfg, args.pr, args.dry_run)


if __name__ == "__main__":
    main()
