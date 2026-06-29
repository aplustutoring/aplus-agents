#!/usr/bin/env python3
"""
make_vo.py — voiceover for the reel via the DIRECT Gemini TTS API
(GEMINI_API_KEY from .env). Reads voice + per-beat lines/delivery from
{bundle}/reel/script.json. Output WAVs -> {bundle}/reel/work/vo_<key>.wav

Usage:  python3 scripts/b2c/reel/make_vo.py --bundle aplus-content/{bundle}/ [--force]
"""
import argparse
import sys
import wave
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel_common as rc

MODEL = "gemini-2.5-flash-preview-tts"
RATE = 24000
BASE_TONE = ("Warm, parent-to-parent, sincere and human — never salesy or "
             "announcer-like. Natural pacing with real emotion. Clear diction.")


def save_wav(pcm, path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(pcm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not rc.GEMINI_KEY:
        sys.exit("GEMINI_API_KEY not set")

    script = rc.load_script(args.bundle)
    voice = script.get("voice", "Achird")
    work = rc.work_dir(args.bundle)
    work.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=rc.GEMINI_KEY)

    items = [(b["key"], b["vo"], b.get("delivery", "")) for b in script["beats"]]
    items.append(("endcard", script["endcard"]["vo"], script["endcard"].get("delivery", "")))

    for key, line, delivery in items:
        out = work / f"vo_{key}.wav"
        if out.exists() and not args.force:
            print(f"  {key}: reuse {out.name}")
            continue
        prompt = f"{BASE_TONE} {delivery}\n\nSay this:\n{line}"
        resp = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
        pcm = resp.candidates[0].content.parts[0].inline_data.data
        save_wav(pcm, out)
        print(f"  {key:12s} [{voice}] -> {out.name} ({out.stat().st_size} bytes)")
    print("vo done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
