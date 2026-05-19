#!/usr/bin/env python3
"""Single-shot batch generator for the May 18 graphics package.

5 main graphics:
- hero (Gemini, 16:9, charter administrator at home office)
- social-card (GPT Image 2, 16:9 wide, text "2026 Dashboard")
- carousel-slide-1 (GPT Image 2, 2:3 portrait, hook quote)
- pull-quote main (GPT Image 2, 1:1 orange with verbatim §6 quote)
- facebook (Gemini, 16:9, B2C warm scene)

3 inline pull-quote graphics for the blog body:
- pull-quote-s2 (§2 quote)
- pull-quote-s3 (§3 quote)
- pull-quote-s6 (§6 quote - same quote as the main pull-quote)
"""
import json, base64, urllib.request, urllib.error, os, sys, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/romanslavinsky/Desktop/aplus-marketing-skills/.env")
GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")
OUT = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-18-weekly/graphics")
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
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "aplus/1.0"})
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)[:300], "elapsed_s": round(time.time()-start, 1)}
    for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img = base64.b64decode(part["inlineData"]["data"])
            (OUT / out_file).write_bytes(img)
            return {"name": name, "ok": True, "provider": "gemini-3.1-flash-image", "file": out_file,
                    "bytes": len(img), "elapsed_s": round(time.time()-start, 1),
                    "usage": result.get("usageMetadata", {})}
    return {"name": name, "ok": False, "error": "no inlineData", "elapsed_s": round(time.time()-start, 1)}


def gpt_image_2(name, prompt, size, quality, out_file):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": size, "quality": quality}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI}"})
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:300]}", "elapsed_s": round(time.time()-start, 1)}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)[:300], "elapsed_s": round(time.time()-start, 1)}
    item = result.get("data", [{}])[0]
    if "b64_json" in item:
        img = base64.b64decode(item["b64_json"])
        (OUT / out_file).write_bytes(img)
        return {"name": name, "ok": True, "provider": "gpt-image-2", "size": size, "quality": quality,
                "file": out_file, "bytes": len(img), "elapsed_s": round(time.time()-start, 1),
                "usage": result.get("usage", {})}
    return {"name": name, "ok": False, "error": "no b64_json", "elapsed_s": round(time.time()-start, 1)}


# === 1. HERO — Gemini 3.1, 16:9 ===
hero_prompt = """A photorealistic documentary photograph of a California charter
school administrator at a real home-office desk reviewing a printed
California School Dashboard report. The administrator is mid-40s,
professional but not corporate, in three-quarter profile with focused
concentration. Natural morning light from a side window. The desk holds:
the printed Dashboard report with the visible heading "California School
Dashboard 2025" or similar, a laptop displaying a budget spreadsheet, a
coffee mug, a wall calendar in the soft-focus background showing
November 2026 with a single date circled. The setting is unmistakably a
home office (visible bookshelf with framed family photo, doorway to a
hallway, plant), NOT a traditional school administrator's office. Style:
candid documentary photography similar to The Atlantic education
features. Natural color grading, warm shadows, neutral highlights. Shot
at 35mm equivalent, shallow depth of field. 16:9 widescreen. No text
overlay outside the natural document and calendar. No watermarks. No
logos."""
results.append(gemini("hero", hero_prompt, "16:9", "hero.png"))
print("hero:", results[-1].get("ok"), results[-1].get("error", ""))


# === 2. SOCIAL CARD — GPT Image 2, 16:9 ===
social_card_prompt = """A flat institutional social media share card. Solid background
A+ Navy hex #1A3A52. Large white sans-serif headline in Inter Bold,
left-aligned upper third, reading exactly: "2026 CA Dashboard". Below,
a thin horizontal A+ Orange #EF5829 divider line. Below the divider, in
smaller white Inter Regular: "CSI designations land this fall. Charter
LEAs: lock your plan now." In the bottom-right corner, a small white
A+ Tutoring wordmark placeholder at about 10 percent of canvas width.
Generous whitespace. Clean, institutional. No photographs. No decorative
icons. No em dashes. Aspect 16:9."""
results.append(gpt_image_2("social_card", social_card_prompt, "1536x1024", "medium", "social-card.png"))
print("social_card:", results[-1].get("ok"), results[-1].get("error", ""))


# === 3. CAROUSEL SLIDE 1 — GPT Image 2, 2:3 portrait ===
carousel_prompt = """A portrait-orientation flat design slide for a LinkedIn carousel
post. Solid background A+ Navy hex #1A3A52. Single bold white Inter
Bold sans-serif headline, centered vertically, taking the middle half
of the canvas, reading exactly: "The 2026 California School Dashboard
arrives this fall. If you wait for the designation letter to start
planning, you are already behind." Below, a small white Inter Regular
line, centered: "Swipe to see what charter LEAs should do this spring."
A small white A+ Tutoring wordmark placeholder in the top-left corner.
Generous whitespace. No photographs. No decorative icons. No em dashes.
Aspect 2:3 portrait."""
results.append(gpt_image_2("carousel_slide_1", carousel_prompt, "1024x1536", "medium", "carousel-slide-1.png"))
print("carousel:", results[-1].get("ok"), results[-1].get("error", ""))


# === 4. MAIN PULL QUOTE (§6 quote, also used inline) — GPT Image 2, 1:1 ===
main_pq_prompt = """A square social media pull quote graphic. Solid background
A+ Orange hex #EF5829. Subtle paper-grain texture at about 5 percent
opacity. Large white Inter Bold sans-serif text, centered vertically,
reading exactly: "A charter LEA with documented outcomes already has a
CSI plan. They just need to submit it." A small white A+ Tutoring
wordmark in the bottom-right corner. Generous whitespace. No additional
decorative elements. No date line, no blog name, no attribution text.
No em dashes. Aspect 1:1 square."""
results.append(gpt_image_2("pull_quote", main_pq_prompt, "1024x1024", "medium", "pull-quote.png"))
print("pull_quote:", results[-1].get("ok"), results[-1].get("error", ""))


# === 5. FACEBOOK — Gemini 3.1, 16:9, B2C warm ===
fb_prompt = """A photorealistic documentary photograph for a parent-facing
Facebook post. A parent and a middle-school-age child are at a kitchen
table. The child is reading from a notebook; the parent sits next to
them, holding a tablet, in conversation. Late-afternoon golden sunlight
through a kitchen window. School supplies and an open notebook on the
table. Style: candid documentary photography, warm color grading, natural
skin tones. The scene is unmistakably a home (visible kitchen cabinets,
refrigerator partly in frame, plant, family photos on a shelf), NOT a
school setting. Composition follows rule of thirds with parent-and-child
pair on right two-thirds of frame. Shot at 50mm equivalent, shallow
depth of field. 16:9 widescreen. No text overlay. No watermarks. No
logos."""
results.append(gemini("facebook", fb_prompt, "16:9", "facebook.png"))
print("facebook:", results[-1].get("ok"), results[-1].get("error", ""))


# === 6, 7. INLINE PULL-QUOTES FOR §2 and §3 — GPT Image 2, 1:1 ===
s2_pq_prompt = """A square social media pull quote graphic. Solid background A+
Orange hex #EF5829. Subtle paper-grain texture at 5 percent opacity.
Large white Inter Bold sans-serif text, centered vertically, reading
exactly: "A charter executive director cannot look at the 2025 Dashboard
alone and conclude the school is safe." A small white A+ Tutoring
wordmark in the bottom-right corner. Generous whitespace. No date line,
no blog name, no attribution text. No em dashes. Aspect 1:1 square."""
results.append(gpt_image_2("pull_quote_s2", s2_pq_prompt, "1024x1024", "medium", "pull-quote-s2.png"))
print("pull_quote_s2:", results[-1].get("ok"), results[-1].get("error", ""))

s3_pq_prompt = """A square social media pull quote graphic. Solid background A+
Orange hex #EF5829. Subtle paper-grain texture at 5 percent opacity.
Large white Inter Bold sans-serif text, centered vertically, reading
exactly: "A charter director who waits for the designation letter to
begin the procurement process is already a month behind the calendar."
A small white A+ Tutoring wordmark in the bottom-right corner. Generous
whitespace. No date line, no blog name, no attribution text. No em
dashes. Aspect 1:1 square."""
results.append(gpt_image_2("pull_quote_s3", s3_pq_prompt, "1024x1024", "medium", "pull-quote-s3.png"))
print("pull_quote_s3:", results[-1].get("ok"), results[-1].get("error", ""))

# pull-quote-s6 is the same as the main pull-quote (§6 quote). Just copy.
import shutil
shutil.copy(OUT / "pull-quote.png", OUT / "pull-quote-s6.png")
print("pull_quote_s6: copied from main pull-quote.png")


LOG.write_text(json.dumps(results, indent=2))
print(f"\n--- {sum(1 for r in results if r.get('ok'))}/{len(results)} OK ---")
