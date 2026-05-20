#!/usr/bin/env python3
"""Full v2.0 batch generator for the A+ May 19, 2026 weekly bundle.

Applies aplus-graphic-prompts v2.0 rules:
- 2 pull-quote graphics max (down from 3)
- Blog-body-width landscape for hero / social card / pull-quotes (not square)
- Heavy A+ brand colors throughout (not just accent)
- Playfair Display headings + DM Sans body in text overlays (prompted)
- No date watermark, no "A+ Tutoring blog" subtitle, no "Source: A+ Tutoring blog"
- Carousel swipe indicator on slide 1 only
- Logo overlap check applied post-generation in _composite_logo_v2.py

Per-bundle graphics produced by this script (11 AI-generated):
  1. hero (1536x1024) — Gemini 3.1, documentary homeschool scene
  2. social-card (1536x1024) — GPT Image 2, B2B navy + orange
  3. pull-quote-s1 (1536x1024) — GPT Image 2, orange bg, NO date, NO subtitle
  4. pull-quote-s2 (1536x1024) — GPT Image 2, orange bg, NO date, NO subtitle
  5. linkedin-carousel-slide-1 (1024x1536) — hook + swipe indicator
  6-8. linkedin-carousel-slide-2..4 (1024x1536) — insights
  9. linkedin-carousel-slide-5 (1024x1536) — CTA, NO swipe indicator
  10. instagram-post (1024x1024) — Gemini 3.1, B2C
  11. instagram-story (1024x1536, 9:16) — Gemini 3.1, B2C vertical
  12. facebook (1536x1024) — Gemini 3.1, B2C

Two additional graphics are generated separately (deterministic matplotlib):
  - preset-stat-graphic.png (copied from aplus-b2b-brand-kit canonical)
  - topic-graphic.png (built by _build_topic_graphic.py: 21-day timeline)

Text content (pull_quotes, carousel_slides) sourced from
blog-anchor-meta.md.
"""
import json, base64, urllib.request, urllib.error, os, sys, time, re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/romanslavinsky/Desktop/aplus-marketing-skills/.env")
GEMINI = os.environ.get("GEMINI_API_KEY")
OPENAI = os.environ.get("OPENAI_API_KEY")

BUNDLE_DIR = Path("/Users/romanslavinsky/Desktop/aplus-marketing-skills/aplus-content/2026-05-19-weekly")
OUT = BUNDLE_DIR / "graphics"
META = BUNDLE_DIR / "blog-anchor-meta.md"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "_results.json"


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
carousel_slides = extract_list(meta_text, "carousel_slides")

# v2.0: pull_quotes capped at 2
if len(pull_quotes) < 2:
    print("WARN: meta has fewer than 2 pull_quotes; padding")
    pull_quotes = (pull_quotes + ["Pull quote 1 placeholder.", "Pull quote 2 placeholder."])[:2]
if len(carousel_slides) < 4:
    print("WARN: meta has fewer than 4 carousel_slides; padding")
    carousel_slides = (carousel_slides + ["Insight 1.", "Insight 2.", "Insight 3.", "CTA."])[:4]


results = []


# ---------- 1. HERO ----------
# Matches blog-anchor-meta.md hero_image_alt_text exactly.
hero_prompt = """A photorealistic documentary photograph of a California
charter school administrator at a home-office desk reviewing a spring
MAP data report on a laptop in late May. Mid-40s, professional but not
corporate, three-quarter profile, focused. Handwritten cohort notes on
a notepad beside the laptop. Natural late-afternoon side light from a
window. The desk holds the laptop, a coffee mug, a desk plant, the
notepad, and a small stack of printed reports. The setting is
unmistakably a home office (bookshelf with framed family photo,
doorway to hallway, plant), NOT a school administrator's office.
Style: candid documentary photography, similar to The Atlantic
education features. Natural color grading. Shot at 35mm equivalent,
shallow depth of field. 3:2 widescreen, landscape orientation. No
text overlay. No watermarks. No logos."""
results.append(gemini("hero", hero_prompt, "16:9", "hero.png"))
print("hero:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 2. SOCIAL CARD ----------
social_card_prompt = """A flat institutional social media share card for an
A+ Tutoring blog post about charter school summer intervention. Solid
background A+ Navy hex #1A3A52. Large white serif headline (Playfair
Display style, similar to elegant editorial serif) in the upper third,
left-aligned, reading exactly: "Summer as a Tier 3 Runway". Below the
headline, a thin horizontal A+ Orange #EF5829 divider, then a smaller
white sans-serif (DM Sans style) subhead reading exactly: "Not Summer
School. The 21-day decision window for charter LEAs." In the
bottom-right corner, leave a clean ~120x120 pixel area free of text or
graphic elements (the A+ logo will be composited here). Generous
whitespace. Clean, institutional. No photographs. No decorative icons.
No date. No "A+ Tutoring blog" text. Aspect 16:9 landscape."""
results.append(gpt_image_2("social_card", social_card_prompt, "1536x1024", "medium", "social-card.png"))
print("social_card:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 3-4. PULL QUOTES (s1, s2 ONLY) ----------
def pull_quote_prompt(quote_text):
    return (
        "A landscape blog-body-width pull-quote graphic. Solid background "
        "A+ Orange hex #EF5829. Subtle paper-grain texture at 5 percent "
        "opacity. Large white serif text (Playfair Display style, elegant "
        "editorial serif weight 700), centered vertically with generous "
        "left and right margins, reading exactly: \"" + quote_text + "\" "
        "In the bottom-right corner, leave a clean ~120x120 pixel area "
        "free of text or graphic elements (the A+ logo will be composited "
        "here later). Generous whitespace overall. NO date line. NO "
        "'A+ Tutoring blog' text. NO attribution subtitle. NO 'Source:' "
        "footer. Just the verbatim quote and an empty corner for the logo. "
        "Aspect 3:2 landscape, blog-body-width orientation."
    )

for slot, quote in zip(["s1", "s2"], pull_quotes[:2]):
    results.append(gpt_image_2(f"pull_quote_{slot}", pull_quote_prompt(quote),
                                "1536x1024", "medium", f"pull-quote-{slot}.png"))
    print(f"pull_quote_{slot}:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 5. LINKEDIN CAROUSEL SLIDE 1 (hook + swipe indicator) ----------
slide1_prompt = (
    "A portrait-orientation flat design slide for a LinkedIn carousel "
    "post by A+ Tutoring. Solid background A+ Navy hex #1A3A52. Single "
    "bold white serif headline (Playfair Display style, weight 700), "
    "centered vertically in the upper two-thirds of the canvas, reading "
    "exactly: \"" + pull_quotes[0] + "\" Below the headline near the "
    "bottom, a small white sans-serif (DM Sans style) line, centered, "
    "reading exactly: \"Swipe →\" with a chevron arrow indicator (this "
    "is the FIRST slide of a 5-slide carousel so the swipe indicator "
    "belongs here). In the bottom-right corner, leave a clean ~120x120 "
    "pixel area free of text or graphic elements for the A+ logo "
    "composite. Generous whitespace. No photographs. No decorative "
    "icons. No em dashes. No date. Aspect 2:3 portrait."
)
results.append(gpt_image_2("carousel_slide_1", slide1_prompt, "1024x1536", "medium", "linkedin-carousel-slide-1.png"))
print("carousel_1:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 6-8. LINKEDIN CAROUSEL SLIDES 2-4 (insights) ----------
for i, slot in enumerate([2, 3, 4]):
    body_text = carousel_slides[i]
    # Alternate background palette between slides for visual interest while
    # maintaining heavy brand color use per v2.0
    if slot == 3:
        bg_color = "A+ Orange hex #EF5829"
        text_color = "white"
        accent_note = "no accent stripe"
    else:
        bg_color = "white hex #FFFFFF"
        text_color = "A+ Navy hex #1A3A52"
        accent_note = "with a vertical A+ Orange #EF5829 accent stripe down the left edge, about 40 pixels wide"
    p = (
        f"A portrait-orientation flat design slide for a LinkedIn carousel "
        f"by A+ Tutoring. Background: {bg_color}, {accent_note}. "
        f"Large sans-serif (DM Sans style, weight 500) text in {text_color}, "
        f"centered vertically with generous left and right margins, reading "
        f"exactly: \"{body_text}\" "
        f"In the bottom-right corner, leave a clean ~120x120 pixel area free "
        f"of text or graphic elements for the A+ logo composite. NO 'Source: "
        f"A+ Tutoring blog' footer. NO date. NO swipe indicator (this is an "
        f"interior slide of the carousel). No decorative icons. No em "
        f"dashes. Aspect 2:3 portrait."
    )
    results.append(gpt_image_2(f"carousel_slide_{slot}", p, "1024x1536", "medium", f"linkedin-carousel-slide-{slot}.png"))
    print(f"carousel_{slot}:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 9. LINKEDIN CAROUSEL SLIDE 5 (CTA, NO swipe indicator) ----------
slide5_prompt = (
    "A portrait-orientation flat design slide for a LinkedIn carousel "
    "by A+ Tutoring. This is the FINAL slide so NO swipe indicator. "
    "Solid background A+ Navy hex #1A3A52. White serif headline "
    "(Playfair Display style, weight 600), centered in the upper-middle, "
    "reading exactly: \"" + carousel_slides[3] + "\" "
    "Below the headline, an A+ Orange #EF5829 rectangular CTA button "
    "(1/3 width of the slide, centered horizontally, rounded corners, "
    "generous padding) with white sans-serif (DM Sans style, weight 700) "
    "text reading exactly: \"Read the full post\". Below the button, a "
    "small white sans-serif URL line, centered, reading: "
    "\"blog.wetutorathome.com\". In the bottom-right corner, leave a "
    "clean ~120x120 pixel area free of text or graphic elements for the "
    "A+ logo composite. Generous whitespace. NO swipe indicator. NO date. "
    "No em dashes. Aspect 2:3 portrait."
)
results.append(gpt_image_2("carousel_slide_5", slide5_prompt, "1024x1536", "medium", "linkedin-carousel-slide-5.png"))
print("carousel_5:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 10. INSTAGRAM POST (B2C parent-facing) ----------
ig_post_prompt = """A photorealistic documentary photograph for an Instagram
post by A+ Tutoring, parent-facing audience. A middle-school-age student
sitting at a kitchen table working on a notebook, with a parent nearby
in supportive conversation (not hovering). California charter homeschool
demographic, diverse family aesthetic, NOT stock-photo styling. Late
afternoon warm golden sunlight through a kitchen window. Plants, family
photos, a fruit bowl visible in the background. Style: candid
documentary, warm natural color grading, real-looking faces (no
uncanny-valley artifacts), warm-and-hopeful tone consistent with A+'s
B2C brand. Composition follows rule of thirds. Shot at 50mm equivalent,
shallow depth of field. Square aspect 1:1. No text overlay. No
watermarks. No logos."""
results.append(gemini("instagram_post", ig_post_prompt, "1:1", "instagram-post.png"))
print("instagram_post:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 11. INSTAGRAM STORY (B2C vertical) ----------
ig_story_prompt = """A vertical photorealistic documentary photograph for
an Instagram Story by A+ Tutoring. A parent and middle-school-age student
at a kitchen table, in conversation about schoolwork. Vertical
composition with the parent-child interaction in the lower two-thirds
and natural ceiling + window light in the upper third. Warm golden
afternoon sunlight. California charter homeschool demographic, real-
looking faces (no uncanny-valley artifacts), diverse family aesthetic.
Style: candid documentary, warm color grading, B2C parent-facing tone.
The scene is unmistakably a home (kitchen cabinets, plants, family
photos), NOT a school setting. Shot at 35mm equivalent. 9:16 vertical
aspect ratio. No text overlay (Story captions are added in IG later).
No watermarks. No logos."""
results.append(gemini("instagram_story", ig_story_prompt, "9:16", "instagram-story.png"))
print("instagram_story:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- 12. FACEBOOK (B2C horizontal) ----------
fb_prompt = """A photorealistic documentary photograph for a parent-facing
Facebook post by A+ Tutoring. A parent and middle-school-age child at a
kitchen table. The child is reading from a notebook; the parent sits
next to them holding a tablet, in conversation. Late-afternoon golden
sunlight through a kitchen window. School supplies and an open notebook
on the table. California charter homeschool demographic, real-looking
faces (no uncanny-valley artifacts), diverse family aesthetic, NOT
stock-photo styling. Style: candid documentary photography, warm
natural color grading. The scene is unmistakably a home (kitchen
cabinets, refrigerator partly in frame, plant, family photos on a
shelf), NOT a school setting. Composition follows rule of thirds with
parent-and-child pair on the right two-thirds of the frame. Shot at
50mm equivalent, shallow depth of field. 16:9 widescreen. No text
overlay. No watermarks. No logos."""
results.append(gemini("facebook", fb_prompt, "16:9", "facebook.png"))
print("facebook:", results[-1].get("ok"), results[-1].get("error", ""))


# ---------- write log ----------
LOG.write_text(json.dumps(results, indent=2))
ok = sum(1 for r in results if r.get("ok"))
print(f"\n--- {ok}/{len(results)} OK ---")
print(f"Results: {LOG}")
