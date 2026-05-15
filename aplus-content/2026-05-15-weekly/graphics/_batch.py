#!/usr/bin/env python3
"""Single-shot batch generator for the May 15 graphics package.
Runs all 5 images sequentially with a 240s timeout each and a per-asset log."""
import json, base64, urllib.request, urllib.error, os, sys, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/romanslavinsky/Desktop/aplus-marketing-skills/.env")

GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")
OUT = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-15-weekly/graphics")
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "_results.json"

results = []


def gemini(name, prompt, aspect, out_file):
    model = "gemini-3.1-flash-image-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
            "temperature": 0.7,
        },
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "aplus-marketing-engine/1.0",
    })
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:400]}", "elapsed_s": time.time() - start}
    except Exception as e:
        return {"name": name, "ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": time.time() - start}

    for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img = base64.b64decode(part["inlineData"]["data"])
            (OUT / out_file).write_bytes(img)
            usage = result.get("usageMetadata", {})
            return {
                "name": name, "ok": True, "provider": "gemini-3.1-flash-image",
                "file": out_file, "bytes": len(img),
                "elapsed_s": round(time.time() - start, 1),
                "usage": usage,
            }
    return {"name": name, "ok": False, "error": "no inlineData in response", "elapsed_s": time.time() - start}


def gpt_image_2(name, prompt, size, quality, out_file):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI}",
    })
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:400]}", "elapsed_s": time.time() - start}
    except Exception as e:
        return {"name": name, "ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": time.time() - start}

    item = result.get("data", [{}])[0]
    if "b64_json" in item:
        img = base64.b64decode(item["b64_json"])
        (OUT / out_file).write_bytes(img)
        return {
            "name": name, "ok": True, "provider": "gpt-image-2",
            "size": size, "quality": quality,
            "file": out_file, "bytes": len(img),
            "elapsed_s": round(time.time() - start, 1),
            "usage": result.get("usage", {}),
        }
    return {"name": name, "ok": False, "error": "no b64_json", "elapsed_s": time.time() - start}


# 1. HERO IMAGE — Gemini 3.1, 16:9
hero_prompt = """A photorealistic documentary photograph of a California charter school
administrator at a home-office desk reviewing printed federal grant award
letters and a state funding spreadsheet. The administrator is mid-40s,
professional but not corporate, in three-quarter profile with focused
concentration. Natural morning light from a side window. The desk holds: a
small stack of paper letters in plausible federal-grant format, a laptop
displaying a budget spreadsheet with column headers visible, a coffee mug,
a desk plant. A wall calendar in the soft-focus background shows September
2026. The setting is unmistakably a home office (visible bookshelf with
framed family photo and personal books, doorway to a hallway), NOT a
traditional school administrator's office. Style: candid documentary
photography similar to The Atlantic education features. Natural color
grading, warm shadows, neutral highlights. Shot at 35mm equivalent,
shallow depth of field. Subject's face is the focal point on the right
third. 16:9 widescreen aspect ratio. No text overlay. No watermarks.
No logos."""
results.append(gemini("hero", hero_prompt, "16:9", "hero.png"))
print("hero:", results[-1].get("ok"), results[-1].get("error", ""))

# 2. SOCIAL CARD — GPT Image 2 for text rendering, 16:9
social_card_prompt = """A flat institutional social media share card. Solid background color
A+ Navy hex #1A3A52. Large white sans-serif headline in Inter Bold,
left-aligned in the upper third, reading exactly: "Federal K-12 Grants
Withheld". A thin horizontal divider in A+ Orange #EF5829 below the
headline. Below the divider, in smaller white Inter Regular: "$2B in
approved funds held back. 30+ programs affected." In the bottom-right
corner, a small white A+ Tutoring wordmark placeholder at about 10
percent of the canvas width. Generous whitespace. Clean, institutional,
not corporate-stocky. No photographs. No decorative icons. No stock
imagery. No em dashes. Aspect 16:9."""
results.append(gpt_image_2("social_card", social_card_prompt, "1536x1024", "medium", "social-card.png"))
print("social_card:", results[-1].get("ok"), results[-1].get("error", ""))

# 3. CAROUSEL SLIDE 1 — GPT Image 2, portrait 2:3
carousel_prompt = """A portrait-orientation flat design slide for a LinkedIn carousel post.
Solid background color A+ Navy hex #1A3A52. Single bold white Inter Bold
sans-serif headline, centered vertically, taking up roughly the middle
half of the canvas, reading exactly: "California charter LEAs: $2 billion
in federal K-12 grants are being withheld in 2026." Below the headline,
a small white Inter Regular line, centered: "Swipe to see what's safe and
what's not." A small white A+ Tutoring wordmark placeholder in the
top-left corner. Generous whitespace. No photographs. No decorative
icons. No em dashes. Aspect 2:3 portrait."""
results.append(gpt_image_2("carousel_slide_1", carousel_prompt, "1024x1536", "medium", "carousel-slide-1.png"))
print("carousel:", results[-1].get("ok"), results[-1].get("error", ""))

# 4. PULL QUOTE — GPT Image 2, square 1:1
pullquote_prompt = """A square social media pull quote graphic. Solid background color A+
Orange hex #EF5829. Subtle paper-grain texture at about 5 percent opacity.
Large white Inter Bold sans-serif text, centered vertically, reading
exactly: "Outcomes track operational design, not which federal grant code
paid the bill." Below the quote, in smaller white Inter Regular text at
about 70 percent opacity, centered: "A+ Tutoring blog · May 20, 2026". A
small white A+ Tutoring wordmark in the bottom-right corner. Generous
whitespace. No additional decorative elements. No em dashes. Aspect 1:1
square."""
results.append(gpt_image_2("pull_quote", pullquote_prompt, "1024x1024", "medium", "pull-quote.png"))
print("pullquote:", results[-1].get("ok"), results[-1].get("error", ""))

# 5. FACEBOOK IMAGE — Gemini 3.1, 16:9, B2C warm aesthetic
fb_prompt = """A photorealistic documentary photograph for a parent-facing Facebook
post. A parent and a middle-school-age child are at a kitchen table.
The child is working on schoolwork on a laptop; the parent sits next to
them, supportive but not hovering, perhaps reading something themselves.
Late-afternoon golden sunlight streams through a kitchen window. School
supplies and an open notebook on the table. Style: candid documentary
photography, warm color grading, natural skin tones. The scene is
unmistakably a home (visible kitchen cabinets, refrigerator partly in
frame, plant, family photos on a shelf), NOT a school setting.
Composition follows rule of thirds with the parent-and-child pair on the
right two-thirds of the frame. Shot at 50mm equivalent, shallow depth of
field. 16:9 widescreen aspect ratio. No text overlay. No watermarks.
No logos."""
results.append(gemini("facebook", fb_prompt, "16:9", "facebook.png"))
print("facebook:", results[-1].get("ok"), results[-1].get("error", ""))


LOG.write_text(json.dumps(results, indent=2))
print(f"\n--- Wrote {LOG} ---")
print(f"OK: {sum(1 for r in results if r.get('ok'))} / {len(results)}")
