#!/usr/bin/env python3
"""Full 14-graphic batch generator for an A+ weekly bundle.

Per the May 18, 2026 expansion (Change 3), each weekly bundle produces:

  1. hero (1536x1024) — Gemini 3.1, documentary homeschool scene
  2. social-card (1200x630-ish via 1536x1024) — GPT Image 2, B2B navy + orange
  3. pull-quote-s1, s2, s3 (1024x1024) — GPT Image 2, orange bg, NO date line
  4. linkedin-carousel-slide-1..5 (1024x1536, 2:3 portrait) — GPT Image 2, B2B
     - Slide 1: hook
     - Slides 2-4: insights / data points (from bundle meta)
     - Slide 5: CTA
  5. instagram-post (1024x1024) — Gemini 3.1, B2C parent-facing warm
  6. instagram-story (1024x1536, 9:16 closest via 2:3) — Gemini 3.1, B2C vertical
  7. facebook (1536x1024) — Gemini 3.1, B2C
  8. creative-graphic (1024x1024) — GPT Image 2, data viz of iLEAD outcomes

All pull-quote / carousel / data-viz text comes from the bundle's
blog-anchor-meta.md (the v1.3 schema). Hero / social-card / facebook /
instagram-post / instagram-story / creative-graphic use static scene
prompts that don't change week to week.

Usage: edit BUNDLE_DIR below if running standalone, or import the
functions and pass your own paths.
"""
import json, base64, urllib.request, urllib.error, os, sys, time, re, shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/romanslavinsky/Desktop/aplus-marketing-skills/.env")
GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")

BUNDLE_DIR = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-18-weekly")
OUT = BUNDLE_DIR / "graphics"
META = BUNDLE_DIR / "blog-anchor-meta.md"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "_results.json"


# ---------- providers ----------

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
        return {"name": name, "ok": False, "error": str(e)[:300], "elapsed_s": round(time.time() - start, 1)}
    for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img = base64.b64decode(part["inlineData"]["data"])
            (OUT / out_file).write_bytes(img)
            return {"name": name, "ok": True, "provider": "gemini-3.1-flash-image", "file": out_file,
                    "bytes": len(img), "elapsed_s": round(time.time() - start, 1),
                    "usage": result.get("usageMetadata", {})}
    return {"name": name, "ok": False, "error": "no inlineData", "elapsed_s": round(time.time() - start, 1)}


def gpt_image_2(name, prompt, size, quality, out_file):
    url = "https://api.openai.com/v1/images/generations"
    body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": size, "quality": quality}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI}"})
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=240)
        result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:300]}", "elapsed_s": round(time.time() - start, 1)}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)[:300], "elapsed_s": round(time.time() - start, 1)}
    item = result.get("data", [{}])[0]
    if "b64_json" in item:
        img = base64.b64decode(item["b64_json"])
        (OUT / out_file).write_bytes(img)
        return {"name": name, "ok": True, "provider": "gpt-image-2", "size": size, "quality": quality,
                "file": out_file, "bytes": len(img), "elapsed_s": round(time.time() - start, 1),
                "usage": result.get("usage", {})}
    return {"name": name, "ok": False, "error": "no b64_json", "elapsed_s": round(time.time() - start, 1)}


# ---------- meta parsing ----------

def extract_list(text, field):
    m = re.search(rf"^{re.escape(field)}:\s*$", text, re.MULTILINE)
    if not m:
        return []
    items = []
    for line in text[m.end():].split("\n")[1:]:
        s = line.strip()
        if not s or not s.startswith("-"):
            break
        item = s[1:].strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1]
        items.append(item)
    return items


meta_text = META.read_text() if META.exists() else ""
pull_quotes = extract_list(meta_text, "pull_quotes")
carousel_slides = extract_list(meta_text, "carousel_slides")  # v1.3 field

# Fallbacks if meta doesn't have what we need yet
if len(pull_quotes) < 3:
    print("WARN: meta has fewer than 3 pull_quotes; using defaults")
    pull_quotes = (pull_quotes + [
        "Pull quote 1 placeholder.", "Pull quote 2 placeholder.", "Pull quote 3 placeholder."
    ])[:3]
if len(carousel_slides) < 4:
    # carousel_slides supplies the 4 NON-hook slides (2-5). slide 1 is generated from blog hook
    print("WARN: meta has fewer than 4 carousel_slides; using defaults")
    carousel_slides = (carousel_slides + [
        "Insight 1 placeholder.", "Insight 2 placeholder.", "Insight 3 placeholder.", "CTA placeholder."
    ])[:4]


results = []


# ---------- 1. HERO ----------

hero_prompt = """A photorealistic documentary photograph of a California
charter school administrator at a home-office desk reviewing planning
documents. Mid-40s, professional but not corporate, three-quarter
profile, focused concentration. Natural morning light from a side
window. The desk holds documents, a laptop, a coffee mug, a desk plant.
The setting is unmistakably a home office (bookshelf with framed family
photo, doorway to hallway, plant), NOT a school administrator's office.
Style: candid documentary photography, similar to The Atlantic education
features. Natural color grading, warm shadows, neutral highlights. Shot
at 35mm equivalent, shallow depth of field. 16:9 widescreen. No text
overlay. No watermarks. No logos."""
results.append(gemini("hero", hero_prompt, "16:9", "hero.png"))
print("hero:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 2. SOCIAL CARD ----------

social_card_prompt = """A flat institutional social media share card. Solid
background A+ Navy hex #1A3A52. Large white sans-serif headline in
Inter Bold, left-aligned upper third. Below, a thin horizontal A+ Orange
#EF5829 divider line, then smaller white Inter Regular subhead. In the
bottom-right corner, a small white A+ Tutoring wordmark at about 10
percent of canvas width. Generous whitespace. Clean, institutional. No
photographs. No decorative icons. No em dashes. The headline and subhead
text content for this specific card: headline 'Weekly Update', subhead
'New analysis on blog.wetutorathome.com'. Aspect 16:9."""
results.append(gpt_image_2("social_card", social_card_prompt, "1536x1024", "medium", "social-card.png"))
print("social_card:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 3. PULL QUOTES (s1, s2, s3) ----------

def pull_quote_prompt(quote_text):
    return (
        "A square social media pull quote graphic. Solid background A+ "
        "Orange hex #EF5829. Subtle paper-grain texture at 5 percent "
        "opacity. Large white Inter Bold sans-serif text, centered "
        "vertically, reading exactly: \"" + quote_text + "\" A small "
        "white A+ Tutoring wordmark in the bottom-right corner. Generous "
        "whitespace. No date line, no blog name, no attribution text. No "
        "em dashes. Aspect 1:1 square."
    )

for idx, slot in enumerate(["s1", "s2", "s3"]):
    quote = pull_quotes[idx]
    results.append(gpt_image_2(f"pull_quote_{slot}", pull_quote_prompt(quote),
                                "1024x1024", "medium", f"pull-quote-{slot}.png"))
    print(f"pull_quote_{slot}:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 4. LINKEDIN CAROUSEL (5 slides) ----------

# Slide 1: hook (uses pull_quotes[0] or a hook line from meta — using s1 quote as hook for now)
slide1_prompt = (
    "A portrait-orientation flat design slide for a LinkedIn carousel "
    "post. Solid background A+ Navy hex #1A3A52. Single bold white Inter "
    "Bold sans-serif headline, centered vertically, reading exactly: "
    "\"" + pull_quotes[0] + "\" Below the headline, a small white Inter "
    "Regular line, centered: \"Swipe ->\" A small white A+ Tutoring "
    "wordmark placeholder in the top-left corner. Generous whitespace. "
    "No photographs. No decorative icons. No em dashes. Aspect 2:3 portrait."
)
results.append(gpt_image_2("carousel_slide_1", slide1_prompt, "1024x1536", "medium", "linkedin-carousel-slide-1.png"))
print("carousel_1:", results[-1].get("ok"), results[-1].get("error", ""))

# Slides 2-4: insights from meta carousel_slides[0..2]
for i, slot in enumerate([2, 3, 4]):
    body = carousel_slides[i]
    p = (
        "A portrait-orientation flat design slide for a LinkedIn carousel. "
        "Background: white hex #FFFFFF, with a thin vertical A+ Orange #EF5829 "
        "accent stripe down the left edge. White interior. Inter Regular "
        "charcoal text reading exactly: \"" + body + "\" centered "
        "vertically with generous margins. A small footer line in Inter "
        "Regular at 60 percent opacity reading exactly: \"Source: A+ "
        "Tutoring blog\". A small A+ Tutoring wordmark in two-color version "
        "(orange wordmark, navy book icon) bottom-right. No decorative "
        "icons. No em dashes. Aspect 2:3 portrait."
    )
    results.append(gpt_image_2(f"carousel_slide_{slot}", p, "1024x1536", "medium", f"linkedin-carousel-slide-{slot}.png"))
    print(f"carousel_{slot}:", results[-1].get("ok"), results[-1].get("error", ""))

# Slide 5: CTA
slide5_prompt = (
    "A portrait-orientation flat design slide for a LinkedIn carousel. "
    "Solid background A+ Navy hex #1A3A52. White Inter Bold headline, "
    "centered upper-middle, reading exactly: \"" + carousel_slides[3] + "\" "
    "Below the headline, an A+ Orange #EF5829 rectangular CTA button "
    "(1/3 width, centered horizontally) with white Inter Bold text "
    "reading exactly: \"Read the full post\". Below the button, a small "
    "white Inter Regular URL line, centered: \"blog.wetutorathome.com\". "
    "A small white A+ Tutoring wordmark placeholder in the bottom-left. "
    "Generous whitespace. No em dashes. Aspect 2:3 portrait."
)
results.append(gpt_image_2("carousel_slide_5", slide5_prompt, "1024x1536", "medium", "linkedin-carousel-slide-5.png"))
print("carousel_5:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 5. INSTAGRAM POST ----------

ig_post_prompt = """A photorealistic documentary photograph for an Instagram
post for parents of California charter homeschool families. A
middle-school-age student is doing schoolwork at a kitchen table, with
a parent nearby (in conversation, not hovering). Late-afternoon warm
golden sunlight through a kitchen window. Plants, family photos visible
in the background. Style: candid documentary photography, warm color
grading, natural skin tones, slightly more saturated than B2B work for
Instagram aesthetic. The scene is unmistakably a home (visible kitchen
cabinets, refrigerator partly in frame, family items), NOT a school
setting. Composition follows rule of thirds. Shot at 50mm equivalent,
shallow depth of field. Square aspect 1:1. No text overlay. No
watermarks. No logos."""
results.append(gemini("instagram_post", ig_post_prompt, "1:1", "instagram-post.png"))
print("instagram_post:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 6. INSTAGRAM STORY ----------

ig_story_prompt = """A vertical photorealistic documentary photograph for
an Instagram Story. A parent and middle-school-age student at a kitchen
table, in conversation about schoolwork. Vertical composition with the
parent-child interaction in the lower two-thirds, and natural ceiling
+ window light visible in the upper third. Warm golden afternoon
sunlight. The scene is unmistakably a home (kitchen cabinets, plants,
family photos on a shelf), NOT a school setting. Style: candid
documentary, warm color grading, B2C parent-facing tone. Shot at 35mm
equivalent. 9:16 vertical aspect ratio. No text overlay (Story
captions are added later in Instagram). No watermarks. No logos."""
results.append(gemini("instagram_story", ig_story_prompt, "9:16", "instagram-story.png"))
print("instagram_story:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 7. FACEBOOK ----------

fb_prompt = """A photorealistic documentary photograph for a parent-facing
Facebook post. A parent and middle-school-age child at a kitchen table.
The child is reading from a notebook; the parent sits next to them,
holding a tablet, in conversation. Late-afternoon golden sunlight
through a kitchen window. School supplies and an open notebook on the
table. Style: candid documentary photography, warm color grading,
natural skin tones. The scene is unmistakably a home (visible kitchen
cabinets, refrigerator partly in frame, plant, family photos on a
shelf), NOT a school setting. Composition follows rule of thirds with
parent-and-child pair on right two-thirds of frame. Shot at 50mm
equivalent, shallow depth of field. 16:9 widescreen. No text overlay.
No watermarks. No logos."""
results.append(gemini("facebook", fb_prompt, "16:9", "facebook.png"))
print("facebook:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 8. CREATIVE GRAPHIC (data viz of iLEAD outcomes) ----------

creative_prompt = """A square 1024x1024 clean infographic data-visualization
graphic showing iLEAD 2024-25 Tier 3 tutoring outcomes. Solid background
A+ Navy hex #1A3A52. White Inter Bold headline centered at the top
reading exactly: "iLEAD 2024-25 Tier 3 Outcomes". Below the headline,
three large white circular percentage indicators arranged in a single
row, each with an orange #EF5829 partial ring around the outside
indicating the percentage filled (so the orange ring fills more for
higher percentages):
- LEFT circle: very large white Inter Bold percentage label "75%",
  smaller white Inter Regular label below: "Math Tier 3", and below
  that in lighter Inter Regular: "12 students".
- CENTER circle: very large white Inter Bold percentage label "87.5%",
  smaller label below: "ELA Tier 3", below: "8 students".
- RIGHT circle: very large white Inter Bold percentage label "80%",
  smaller label below: "Combined", below: "20 students".
Each percentage label MUST exactly match the number on its circle.
Small white Inter Regular footer line at the bottom reading exactly:
"Source: A+ Tutoring published case studies". A small white A+ Tutoring
wordmark in the bottom-right corner. Generous whitespace. Clean,
institutional data-visualization aesthetic. No em dashes. No extra
text or decoration. Aspect 1:1 square."""
results.append(gpt_image_2("creative_graphic", creative_prompt, "1024x1024", "medium", "creative-graphic.png"))
print("creative_graphic:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- write log ----------

LOG.write_text(json.dumps(results, indent=2))
ok_count = sum(1 for r in results if r.get("ok"))
print(f"\n--- {ok_count}/{len(results)} OK ---")
print(f"Results: {LOG}")
