#!/usr/bin/env python3
"""Run the booth's REAL research prompt against a company name and print the
brief exactly as the email would contain it.

    ANTHROPIC_API_KEY=... python3 booth/eo/try-brief.py "Acme Roofing"

Reads the prompt and model out of worker.js so this can never drift from what
ships, and mirrors worker.js's extractText()/cleanBody() so what you read here
is what an attendee gets. Read the output aloud — that is the real go/no-go.
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

WORKER = Path(__file__).with_name("worker.js")


def extract_const(const):
    m = re.search(rf"const {const} = `(.*?)`;", WORKER.read_text(), re.S)
    if not m:
        sys.exit(f"could not find {const} in worker.js")
    return m.group(1)


def model():
    return re.search(r'const CLAUDE_MODEL = "([^"]+)"', WORKER.read_text()).group(1)


def extract_text(blocks):
    """Mirror of extractText() in worker.js — text after the LAST tool block."""
    last_tool = -1
    for i, b in enumerate(blocks):
        if b.get("type") != "text":
            last_tool = i
    tail = "".join(b["text"] for b in blocks[last_tool + 1:] if b.get("type") == "text").strip()
    if tail:
        return tail
    return "".join(b["text"] for b in blocks if b.get("type") == "text").strip()


def clean_body(text):
    """Mirror of cleanBody() in worker.js — keep the two in step."""
    t = (text or "").strip()
    cut = 0
    for m in re.finditer(r"\bhere(?:'s| is)\b[^\n]{0,100}?:[ \t]*\n", t, re.I):
        cut = m.end()
    if cut and len(t[cut:].strip()) > 80:
        t = t[cut:]
    paras = re.split(r"\n\s*\n", t)
    if (len(paras) > 1
            and re.search(r"\b(?:I(?:'ve|'ll| have| will| am)|let me)\b", paras[0], re.I)
            and re.search(r"\bsearch(?:es|ed|ing)?\b", paras[0], re.I)
            and re.search(r"\b(?:write|writing|brief|per the rules)\b", paras[0], re.I)
            and len("\n\n".join(paras[1:]).strip()) > 80):
        t = "\n\n".join(paras[1:])
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*\n+", "", t)
    t = re.sub(r"\n+\s*(?:-{3,}|\*{3,}|_{3,})\s*$", "", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
    return t.strip()


POLISH_SYSTEM = """You are given the raw output of an AI assistant that was asked to research a company, write a short brief for an email, and then list five AI agents that company could build.

Return ONLY the deliverable itself, word for word as written. The deliverable is the brief AND the "Five agents you could build tonight:" section with its five numbered items — both are part of it. Keep the numbered list intact and keep that heading line exactly as written.

Remove anything that is not the brief: opening commentary about the research process ("I've now done five searches", "I now have enough information"), announcements of what is coming ("Here is the brief:", "Here's what I know:"), summaries of findings written as notes to self, horizontal rules, headers, and any closing remark addressed to whoever asked.

If a sentence or paragraph appears twice — a draft opening followed by the real one — keep only the version inside the final brief.

Do not rewrite, reword, shorten, expand, correct, or reorder anything you keep. You are deleting, not editing. If the entire input is already clean, return it unchanged."""


def call(body, key):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def polish(raw, key):
    """Mirror of polish() in worker.js — second pass, no tools."""
    data = call({
        "model": model(),
        "max_tokens": 2000,
        "system": POLISH_SYSTEM,
        "messages": [{"role": "user", "content": raw}],
    }, key)
    out = clean_body(extract_text(data.get("content", [])))
    if not out or len(out) < 120 or len(out) > len(raw) + 40:
        return raw
    return out


def brief(company, key):
    body = {
        "model": model(),
        "max_tokens": 2000,
        "system": extract_const("RESEARCH_SYSTEM"),
        "tools": [{"type": "web_search_20260209", "name": "web_search"}],
        "messages": [{
            "role": "user",
            "content": f"Company: {company}\n\nResearch them and write the brief.",
        }],
    }
    data = call(body, key)
    blocks = data.get("content", [])
    searches = sum(1 for b in blocks if b.get("type") == "server_tool_use")
    raw = clean_body(extract_text(blocks))
    return (polish(raw, key), searches,
            data.get("stop_reason"), data.get("usage", {}))


if __name__ == "__main__":
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("set ANTHROPIC_API_KEY")
    if len(sys.argv) < 2:
        sys.exit('usage: try-brief.py "Company Name" ["Another Co" ...]')

    for company in sys.argv[1:]:
        text, searches, stop, usage = brief(company, key)
        print("=" * 72)
        print(f"COMPANY: {company}")
        print(f"model={model()}  searches={searches}  stop={stop}  "
              f"in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
        print("=" * 72)
        print(text)
        print(f"\n[{len(text.split())} words]\n")
