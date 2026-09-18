#!/usr/bin/env python3
"""Daily 9:00 AM PT fleet recap to the Leadership team channel (Roman
2026-09-16, STEP 7): the previous day's fleet builds (PRs merged), config
changes (email/config.yaml, registry.yml, ops/hubspot-schema/properties.yml
commits), and failures (GitHub Actions runs that failed). Nothing outside the
fleet. Reads GitHub through `gh`; posts through the Slack bot. DRY_RUN prints.
Deterministic: no prompt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "email"))

from src import slack_client  # noqa: E402
from src.business_hours import now_la  # noqa: E402
from src.config import DRY_RUN, cfg  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "aplustutoring/aplus-agents")
CONFIG_PATHS = ("email/config.yaml", "registry.yml", "ops/hubspot-schema/properties.yml", ".github/workflows/")


def gh(args: list[str]) -> list | dict:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return json.loads(r.stdout or "[]")


def yesterday_window() -> tuple[datetime, datetime]:
    today = now_la().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=1), today


def merged_prs(start: datetime, end: datetime) -> list[dict]:
    prs = gh(["pr", "list", "--repo", REPO, "--state", "merged", "--limit", "60",
              "--json", "number,title,mergedAt,author,files"])
    out = []
    for p in prs:
        m = p.get("mergedAt")
        if not m:
            continue
        when = datetime.fromisoformat(m.replace("Z", "+00:00")).astimezone(start.tzinfo)
        if start <= when < end:
            files = [f.get("path", "") for f in (p.get("files") or [])]
            p["config_change"] = any(f.startswith(CONFIG_PATHS) for f in files)
            out.append(p)
    return out


def failed_runs(start: datetime, end: datetime) -> list[dict]:
    runs = gh(["run", "list", "--repo", REPO, "--status", "failure", "--limit", "100",
               "--json", "name,conclusion,createdAt,url,workflowName"])
    out = []
    for r in runs:
        when = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")).astimezone(start.tzinfo)
        if start <= when < end:
            out.append(r)
    return out


def build() -> str:
    start, end = yesterday_window()
    lines = [f"*Fleet recap for {start.strftime('%a %b %-d')}*"]
    try:
        prs = merged_prs(start, end)
        if prs:
            lines.append(f"*Merged ({len(prs)})*")
            for p in prs:
                flag = " (config)" if p.get("config_change") else ""
                lines.append(f"• #{p['number']} {p['title'][:90]}{flag}")
        else:
            lines.append("*Merged*: nothing")
    except Exception as e:  # noqa: BLE001
        lines.append(f"*Merged*: could not read ({str(e)[:80]})")
    try:
        fails = failed_runs(start, end)
        if fails:
            by = {}
            for r in fails:
                by.setdefault(r.get("workflowName") or r.get("name"), []).append(r)
            lines.append(f"*Failed runs ({len(fails)})*")
            for wf, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
                lines.append(f"• {wf}: {len(rs)} <{rs[0]['url']}|latest>")
        else:
            lines.append("*Failed runs*: none")
    except Exception as e:  # noqa: BLE001
        lines.append(f"*Failed runs*: could not read ({str(e)[:80]})")
    return "\n".join(lines)


def main() -> None:
    text = build()
    channel = ((cfg().get("case_engine") or {}).get("digest") or {}).get("channel") or ""
    print(text)
    if DRY_RUN or not channel:
        print("[DRY_RUN] not posted")
        return
    slack_client.post_message(channel, text)


if __name__ == "__main__":
    main()
