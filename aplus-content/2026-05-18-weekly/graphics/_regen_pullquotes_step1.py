#!/usr/bin/env python3
"""Step 1 helper: regenerate the 3 May 18 pull-quotes WITHOUT date line.

Pulls the updated prompts from _batch.py (already edited) and re-runs ONLY
the 3 pull-quote calls. Does not touch hero / social-card / carousel /
facebook. Logo re-composite happens via _composite_logo.py after this.
"""
import json, base64, urllib.request, urllib.error, os, sys, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/romanslavinsky/Desktop/aplus-marketing-skills/.env")
OPENAI = os.environ.get("OPENAI_API_KEY")
OUT = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-18-weekly/graphics")


def gpt_image_2(name, prompt, out_file):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": "1024x1024", "quality": "medium"}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI}",
    })
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    item = result.get("data", [{}])[0]
    if "b64_json" in item:
        img = base64.b64decode(item["b64_json"])
        (OUT / out_file).write_bytes(img)
        elapsed = time.time() - start
        return {"name": name, "ok": True, "bytes": len(img), "elapsed_s": round(elapsed, 1), "usage": result.get("usage", {})}
    return {"name": name, "ok": False, "error": "no b64_json"}


main_pq = """A square social media pull quote graphic. Solid background
A+ Orange hex #EF5829. Subtle paper-grain texture at about 5 percent
opacity. Large white Inter Bold sans-serif text, centered vertically,
reading exactly: "A charter LEA with documented outcomes already has a
CSI plan. They just need to submit it." A small white A+ Tutoring
wordmark in the bottom-right corner. Generous whitespace. No additional
decorative elements. No date line, no blog name, no attribution text.
No em dashes. Aspect 1:1 square."""

s2_pq = """A square social media pull quote graphic. Solid background A+
Orange hex #EF5829. Subtle paper-grain texture at 5 percent opacity.
Large white Inter Bold sans-serif text, centered vertically, reading
exactly: "A charter executive director cannot look at the 2025 Dashboard
alone and conclude the school is safe." A small white A+ Tutoring
wordmark in the bottom-right corner. Generous whitespace. No date line,
no blog name, no attribution text. No em dashes. Aspect 1:1 square."""

s3_pq = """A square social media pull quote graphic. Solid background A+
Orange hex #EF5829. Subtle paper-grain texture at 5 percent opacity.
Large white Inter Bold sans-serif text, centered vertically, reading
exactly: "A charter director who waits for the designation letter to
begin the procurement process is already a month behind the calendar."
A small white A+ Tutoring wordmark in the bottom-right corner. Generous
whitespace. No date line, no blog name, no attribution text. No em
dashes. Aspect 1:1 square."""

for name, prompt, out_file in [
    ("pull_quote", main_pq, "pull-quote.png"),
    ("pull_quote_s2", s2_pq, "pull-quote-s2.png"),
    ("pull_quote_s3", s3_pq, "pull-quote-s3.png"),
]:
    r = gpt_image_2(name, prompt, out_file)
    print(f"{name}: ok={r.get('ok')} bytes={r.get('bytes')} {r.get('error', '')}")

# Refresh s6 copy from the regenerated main pull-quote
import shutil
shutil.copy(OUT / "pull-quote.png", OUT / "pull-quote-s6.png")
print("pull-quote-s6.png: copied from new pull-quote.png")
