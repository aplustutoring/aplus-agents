#!/usr/bin/env python3
"""
A+ Switchboard — build the calls-and-texts dashboard page from JustCall.

    python ops/switchboard/refresh.py --days 14 --out switchboard.html [--prior previous.html]

Steps (deterministic except step 2's Claude call):
  1. fetch    every call and text on every JustCall line for the last N days,
              one day per request (the API times out on wide windows; paging is
              zero-indexed, see memory justcall-paging-zero-indexed).
  2. classify each INBOUND text as needs_reply true/false. Rules catch tapback
              reactions, opt-outs, verification codes, empty and emoji-only
              texts; Claude (claude-opus-5, low effort) judges the rest in
              batches of 40 with the last thing we said to that number as
              context. Verdicts already present in --prior (the previously
              published page) are reused, so a daily run only classifies new
              texts.
  3. build    embed the data in template.html and write the page.

The output page contains family names, numbers and message bodies. It is
NEVER committed to the repo — publish it as the private A+ Switchboard
artifact and discard the file (FERPA pass, 2026-09-24).

Env: JUSTCALL_API_KEY, JUSTCALL_API_SECRET, ANTHROPIC_API_KEY (.env is loaded
when python-dotenv is installed; Actions and cloud routines set them directly).
"""
import argparse, datetime, html, json, os, re, sys, time
from collections import defaultdict

import requests

try:
    from dotenv import load_dotenv
    _d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(7):  # repo root, or the main checkout above a .claude/worktrees/ copy
        if os.path.exists(os.path.join(_d, ".env")):
            load_dotenv(os.path.join(_d, ".env"))
            break
        _d = os.path.dirname(_d)
except ImportError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
JC = "https://api.justcall.io"
LINES = {  # keep in sync with ops/call_agent/config.yml justcall.line_names
    "18188506284": "Main line", "18188691627": "Support line", "18185736644": "Sales line",
    "18185736293": "Roman's line", "18185736258": "Recruitment", "13235150123": "Sales line 2",
    "18888697637": "Sales line 3 (888)",
}
UTC_OFFSET_H = 7  # JustCall call_time/sms_time are UTC; the page shows Pacific. PDT until Nov 1, then 8.


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ── 1. fetch ─────────────────────────────────────────────────────────────────
def _jc_headers():
    k, s = os.environ.get("JUSTCALL_API_KEY"), os.environ.get("JUSTCALL_API_SECRET")
    if not (k and s):
        sys.exit("JUSTCALL_API_KEY / JUSTCALL_API_SECRET not set")
    return {"Authorization": f"{k}:{s}", "Accept": "application/json"}


def _pull(path, start, end):
    h = _jc_headers()
    out = []
    day = start
    while day <= end:
        page = 0
        while True:
            d = None
            for _ in range(6):
                try:
                    r = requests.get(f"{JC}{path}", headers=h, timeout=45, params={
                        "from_datetime": f"{day} 00:00:00", "to_datetime": f"{day} 23:59:59",
                        "per_page": 100, "page": page, "order": "asc"})
                    if r.status_code == 429:
                        time.sleep(6)
                        continue
                    r.raise_for_status()
                    d = r.json()
                    break
                except requests.exceptions.RequestException as e:
                    log("retry", path, day, page, type(e).__name__)
                    time.sleep(3)
            if d is None:
                sys.exit(f"gave up on {path} {day} page {page}")
            data = d.get("data", [])
            if not data:
                break
            out += data
            page += 1
            if not d.get("next_page_link"):
                break
        day += datetime.timedelta(days=1)
    log(path, "rows:", len(out))
    return out


def _pt(date, t):
    dt = datetime.datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=UTC_OFFSET_H)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _clean(x):
    x = html.unescape(x or "")
    x = x.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
    return re.sub(r"\\(?=[|/])", "", x)


def fetch(days):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    calls = []
    for c in _pull("/v2.1/calls", start, end):
        ci, cd, ivr = c.get("call_info") or {}, c.get("call_duration") or {}, c.get("ivr_info") or {}
        calls.append({
            "id": c["id"], "t": _pt(c["call_date"], c["call_time"]), "num": c["contact_number"],
            "name": _clean(c.get("contact_name")), "line": LINES.get(c["justcall_number"], c["justcall_number"]),
            "agent": c.get("agent_name") or "Unassigned",
            "dir": "in" if (ci.get("direction") or "").lower() == "incoming" else "out",
            "type": (ci.get("type") or "").lower(), "reason": ci.get("missed_call_reason") or "",
            "ring": cd.get("ring_time") or 0, "dur": cd.get("total_duration") or 0,
            "key": ivr.get("digit_pressed") or "", "rec": bool(ci.get("recording")),
        })
    texts = []
    for x in _pull("/v2.1/texts", start, end):
        si = x.get("sms_info") or {}
        texts.append({
            "id": x["id"], "t": _pt(x["sms_date"], x["sms_time"]), "num": x["contact_number"],
            "name": _clean(x.get("contact_name")), "line": LINES.get(x["justcall_number"], x["justcall_number"]),
            "agent": x.get("agent_name") or "Unassigned",
            "dir": "in" if (x.get("direction") or "").lower() == "incoming" else "out",
            "body": _clean(si.get("body")), "mms": si.get("is_mms") == "yes",
            "status": x.get("delivery_status") or "", "medium": x.get("medium") or "",
        })
    return {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT"),
            "from": str(start), "to": str(end), "calls": calls, "texts": texts}


# ── 2. classify ──────────────────────────────────────────────────────────────
TAPBACK = re.compile(r"^\s*(\u200b)*(liked|loved|laughed at|emphasized|disliked|questioned|\U0001F44D)\s*(\u200b)*\s*(to\s*)?[\u201c\"]", re.I)
SYSTEM = (
    "You triage inbound text messages for A+ Tutoring, a K-12 tutoring company. For each message decide "
    "whether the staff NEED to send a reply. Reply needed = the sender asks a question, requests something "
    "(schedule, reschedule, cancel, call me, send info, sign up, a new student), reports a problem or "
    "complaint, gives information that requires our action or confirmation back, or is a new lead. "
    "No reply needed = thanks, acknowledgements, courtesy sign-offs (\"you too\", \"have a nice weekend\"), "
    "plain yes/no or confirmations that close the loop we opened, tapback reactions, opt-outs, marketing or "
    "spam from businesses, wrong numbers with nothing to answer, texts our own staff sent from personal "
    "numbers, and automated codes. If a message closes a loop but adds a request, it needs a reply. "
    "Return ONLY a JSON array, one object per message, in the same order: "
    "{\"id\": \"...\", \"needs_reply\": true|false, \"why\": \"<= 8 words, no names\"}."
)


def _rule(t):
    b = (t["body"] or "").strip()
    if not b:
        return (False, "empty (image or attachment only)")
    if TAPBACK.search(b):
        return (False, "tapback reaction")
    if re.fullmatch(r"(stop|unsubscribe|cancel|end|quit)\W*", b, re.I):
        return (False, "opt-out")
    if re.search(r"verification code|security code|your code is|one-time code", b, re.I):
        return (False, "verification code")
    if re.fullmatch(r"[\W\U0001F300-\U0001FAFF\u2600-\u27BF\s]+", b):
        return (False, "emoji only")
    return None


def prior_verdicts(prior_html):
    """Reuse needs_reply verdicts embedded in the previously published page."""
    if not prior_html or not os.path.exists(prior_html):
        return {}
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', open(prior_html, encoding="utf-8").read(), re.S)
    if not m:
        return {}
    try:
        prev = json.loads(m.group(1).replace("<\\/", "</"))
    except json.JSONDecodeError:
        return {}
    out = {str(t["id"]): {"nr": t["nr"], "why": t.get("why", "")} for t in prev.get("texts", []) if "nr" in t}
    log("prior verdicts reused:", len(out))
    return out


def classify(d, cache):
    by_num = defaultdict(list)
    for t in d["texts"]:
        by_num[t["num"]].append(t)
    todo = []
    for arr in by_num.values():
        arr.sort(key=lambda x: x["t"])
        for i, t in enumerate(arr):
            if t["dir"] != "in":
                continue
            key = str(t["id"])
            if key in cache:
                continue
            r = _rule(t)
            if r:
                cache[key] = {"nr": r[0], "why": r[1]}
                continue
            prev = next((x for x in reversed(arr[:i]) if x["dir"] == "out"), None)
            todo.append({"id": key, "from": t["name"] or "unknown", "line": t["line"],
                         "prev_from_us": (prev["body"][:160] if prev else ""), "text": t["body"][:400]})
    log("classify: rules/prior covered", len(cache), "| Claude to judge", len(todo))
    if todo:
        import anthropic
        client = anthropic.Anthropic()
        B = 40
        for s in range(0, len(todo), B):
            batch = todo[s:s + B]
            resp = client.messages.create(
                model="claude-opus-5", max_tokens=8000, system=SYSTEM, output_config={"effort": "low"},
                messages=[{"role": "user", "content": json.dumps(batch, ensure_ascii=False)}])
            txt = "".join(b.text for b in resp.content if b.type == "text").strip()
            txt = re.sub(r"^```(json)?|```$", "", txt, flags=re.M).strip()
            try:
                arr = json.loads(txt)
            except json.JSONDecodeError:
                m = re.search(r"\[.*\]", txt, re.S)
                arr = json.loads(m.group(0)) if m else []
            got = {str(a["id"]): a for a in arr if isinstance(a, dict) and "id" in a}
            for item in batch:
                a = got.get(item["id"])
                if a is not None:
                    cache[item["id"]] = {"nr": bool(a.get("needs_reply")), "why": str(a.get("why", ""))[:60]}
            log(f"  batch {s // B + 1}: {len(got)}/{len(batch)}")
    n_in = n_nr = n_miss = 0
    for t in d["texts"]:
        if t["dir"] != "in":
            continue
        n_in += 1
        f = cache.get(str(t["id"]))
        if f is None:
            n_miss += 1  # unclassified: the page falls back to its word-list closer()
            continue
        t["nr"], t["why"] = f["nr"], f["why"]
        n_nr += f["nr"]
    log(f"inbound {n_in}: needs reply {n_nr}, no reply {n_in - n_nr - n_miss}, unclassified {n_miss}")


# ── 3. build ─────────────────────────────────────────────────────────────────
def build(d, out):
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    tpl = "".join(ch if ord(ch) < 128 else f"&#{ord(ch)};" for ch in tpl)
    data = json.dumps(d).replace("</", "<\\/")
    open(out, "w", encoding="utf-8").write(tpl.replace("__DATA__", data))
    log("wrote", out, f"({os.path.getsize(out) // 1024} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default="switchboard.html")
    ap.add_argument("--prior", help="previously published page; its needs_reply verdicts are reused")
    ap.add_argument("--no-classify", action="store_true", help="skip Claude (rules + prior only)")
    a = ap.parse_args()
    d = fetch(a.days)
    cache = prior_verdicts(a.prior)
    if a.no_classify:
        for t in d["texts"]:
            f = cache.get(str(t["id"]))
            if f:
                t["nr"], t["why"] = f["nr"], f["why"]
    else:
        classify(d, cache)
    build(d, a.out)


if __name__ == "__main__":
    main()
