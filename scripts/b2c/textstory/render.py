#!/usr/bin/env python3
"""
render.py — render {bundle}/textstory/scenes.json to {bundle}/textstory/textstory.mp4

Pure programmatic pipeline (no generation APIs):
  scenes.json -> timeline (python, single source of truth for frames AND audio)
              -> headless Chromium seek(t) frame capture (1080x1920 @ 30fps)
              -> ffmpeg h264 encode
              -> ffmpeg SFX mix (typing clicks / swoosh / pop / shutter) over a
                 music bed ducked via sidechain compression
              -> final MP4

Usage:
    python3 scripts/b2c/textstory/render.py --bundle aplus-content/{bundle}/
    python3 scripts/b2c/textstory/render.py --episode-json path.json --out out.mp4
      (fixture mode for testing without a bundle)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textstory_common as tc  # noqa: E402

HERE = Path(__file__).resolve().parent
FPS, W, H = tc.FPS, tc.W, tc.H

TARGET_CHAT_SECONDS = 27.5   # chat portion budget; endcard rides on top
ENDCARD_SECONDS = 4.2

# pacing constants (seconds)
DIVIDER_HOLD = 0.75          # divider fade + hold before first typing
SAME_SENDER_GAP = 0.42       # quick-fire follow-up from the same sender
PAUSE_TYPING = 1.5           # typing_pause: dots run this long...
PAUSE_STILLNESS = 0.85       # ...then stop. beat of stillness.
SCREENSHOT_DWELL = 1.5


def typing_dur(text: str) -> float:
    return min(max(0.6 + 0.007 * len(text), 0.65), 1.05)


def read_dwell(text: str) -> float:
    return min(max(0.32 + 0.011 * len(text), 0.55), 1.0)


VOICE_DWELL = 3.0       # on-screen dwell + waveform-sweep time for a voice note
REACTION_DWELL = 0.6    # quick tapback


def _first_letter(label: str) -> str:
    for ch in label:
        if ch.isalpha():
            return ch.upper()
    return (label.strip()[:1] or "•").upper()


def _resolve_header(episode: dict) -> dict:
    """Header = the person/group being texted. right side is always 'you'."""
    contacts = episode.get("contacts") or {}
    if episode.get("dynamic") == "family_group" or contacts.get("group"):
        name = contacts.get("group") or "The Group Chat"
        return {"mode": "group", "name": name, "letter": "👨‍👩‍👧‍👦"}
    # solo: prefer explicit contacts.left; fall back to legacy `contact` field
    if contacts.get("left"):
        name = contacts["left"]
    elif episode.get("contact"):
        name = episode["contact"].get("name", "Hubby 💍")
    else:
        name = "Hubby 💍"
    return {"mode": "solo", "name": name, "letter": _first_letter(name)}


def _resolve_sender(msg: dict, episode: dict, header: dict):
    """Return (side, sender_label, who_key) for a message.

    right = phone owner ("you"/Mom, blue). In group chats every non-owner
    sender renders left/grey with their display name labelled above the
    bubble. Legacy mom/dad keys map mom->right, dad->left.
    """
    frm = msg.get("from", "right")
    if frm in ("right", "me", "you"):
        return "right", None, "me"
    if frm == "left":
        return "left", None, "them"
    if frm == "mom":
        return "right", None, "me"
    if frm == "dad":
        return "left", None, "dad"
    # group member key -> look up display name from contacts.members
    members = (episode.get("contacts") or {}).get("members") or {}
    if header["mode"] == "group":
        label = members.get(frm, frm.replace("_", " ").title())
        return "left", label, frm
    # unknown solo key -> treat as the contact (left)
    return "left", None, frm


def build_timeline(episode: dict) -> dict:
    """Flatten scenes into DOM items + typing windows + sfx events, all with
    absolute times. One source of truth for both frames and audio.

    Supports msg types: text (default), typing_pause, screenshot,
    voice_message, reaction. Sides come from `from` (left/right or group
    member keys) resolved against the episode's `contacts`."""
    header = _resolve_header(episode)
    items, typing, sfx = [], [], []
    t = 0.7  # settle on the empty thread for a beat

    for scene in episode["scenes"]:
        items.append({"kind": "divider", "text": scene["ts"], "appear": t})
        t += DIVIDER_HOLD
        prev_sender = None
        msgs = scene["msgs"]
        for i, msg in enumerate(msgs):
            mtype = msg.get("type")
            side, label, who_key = _resolve_sender(msg, episode, header)

            if mtype == "typing_pause":
                typing.append({"side": side, "start": t, "end": t + PAUSE_TYPING})
                sfx.append({"t": t, "name": "keyboard_clicks", "dur": PAUSE_TYPING})
                t += PAUSE_TYPING + PAUSE_STILLNESS
                prev_sender = None  # they type again -> dots again
                continue

            if mtype == "reaction":
                # instant tap — no typing indicator, quick beat
                items.append({"kind": "reaction", "side": side, "appear": t,
                              "emoji": msg.get("emoji", "❤️"),
                              "who": label, "who_key": who_key})
                sfx.append({"t": t, "name": "pop"})
                t += REACTION_DWELL
                prev_sender = None
                continue

            is_shot = mtype == "screenshot"
            is_voice = mtype == "voice_message"
            text = msg.get("text", "")

            # typing indicator before a fresh sender's turn (recording, for voice)
            if msg.get("from") != prev_sender:
                if is_voice:
                    dur = 1.1
                elif is_shot:
                    dur = 0.9
                else:
                    dur = typing_dur(text)
                typing.append({"side": side, "start": t, "end": t + dur})
                sfx.append({"t": t, "name": "keyboard_clicks", "dur": dur})
                t += dur
            else:
                t += SAME_SENDER_GAP

            item = {"side": side, "appear": t, "sender_label": label, "who_key": who_key}
            if is_shot:
                item.update(kind="screenshot", shot=msg.get("shot") or {})
            elif is_voice:
                item.update(kind="voice_message", duration=msg.get("duration", "0:30"),
                            play=VOICE_DWELL)
            else:
                item.update(kind="msg", text=text, caps=bool(msg.get("caps")))
            items.append(item)

            if is_shot:
                sfx.append({"t": t, "name": "shutter"})
            elif is_voice:
                sfx.append({"t": t, "name": "swoosh"})
            else:
                sfx.append({"t": t, "name": "swoosh" if side == "right" else "pop"})

            nxt = msgs[i + 1] if i + 1 < len(msgs) else None
            if is_shot:
                t += SCREENSHOT_DWELL
            elif is_voice:
                t += VOICE_DWELL
            elif nxt and nxt.get("from") == msg.get("from") and not nxt.get("type"):
                t += 0.15  # same-sender gap applied on the next message
            else:
                t += read_dwell(text)
            prev_sender = msg.get("from")
        t += 0.3  # breath at scene end

    # scale chat timing to budget if it ran long
    if t > TARGET_CHAT_SECONDS:
        k = TARGET_CHAT_SECONDS / t
        for it in items:
            it["appear"] *= k
        for w in typing:
            w["start"] *= k
            w["end"] *= k
        for e in sfx:
            e["t"] *= k
            if "dur" in e:
                e["dur"] *= k
        t = TARGET_CHAT_SECONDS

    endcard_start = t + 0.5
    total = endcard_start + ENDCARD_SECONDS
    ec = episode.get("endcard", {})
    return {
        "items": items,
        "typing": typing,
        "sfx": sfx,
        "header": header,
        "endcard": {
            "start": endcard_start,
            "line": ec.get("line") or "Every parent deserves this text.",
            "cta": ec.get("cta") or "Book a free consultation",
            "url_display": (ec.get("cta_url")
                            or "https://meetings.hubspot.com/successful/consultation"
                            ).replace("https://", ""),
            # baked-in by design — never sourced from generated JSON
            "disclosure": "Based on real A+ family outcomes",
            "logo": "",  # set in main() once the tinted logo exists
        },
        "total": total,
    }


SLACK_POST_GAP = 1.1        # beat before each new post
SLACK_REACT_DELAY = 0.9     # reactions pop this long after their post
SLACK_REACT_DWELL = 0.7     # extra hold when a post has reactions


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", name) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def build_timeline_slack(episode: dict) -> dict:
    """Timeline for the Slack 'team_slack' skin: a #channel thread of posts
    (avatar + name + timestamp), each able to carry reaction count pills.
    Members map sender keys -> display names; @channel etc. are rendered as
    mention pills in the template."""
    members = episode.get("members") or {}
    items, sfx = [], []
    t = 0.7
    for scene in episode["scenes"]:
        for msg in scene.get("msgs", []):
            key = msg.get("from", "")
            name = members.get(key, key.replace("_", " ").title())
            text = msg.get("text", "")
            t += SLACK_POST_GAP
            reactions = msg.get("reactions") or []
            react_at = t + SLACK_REACT_DELAY
            items.append({
                "kind": "post", "appear": t, "sender_key": key, "sender": name,
                "initials": _initials(name), "ts": msg.get("ts", ""),
                "text": text, "reactions": reactions, "react_at": react_at,
            })
            # a broadcast ping gets the swoosh; ordinary posts pop
            sfx.append({"t": t, "name": "swoosh" if re.search(r"@(channel|here|everyone)", text) else "pop"})
            if reactions:
                sfx.append({"t": react_at, "name": "pop"})
            t += read_dwell(text) + (SLACK_REACT_DWELL if reactions else 0.0)
        t += 0.3

    if t > TARGET_CHAT_SECONDS:
        k = TARGET_CHAT_SECONDS / t
        for it in items:
            it["appear"] *= k
            it["react_at"] *= k
        for e in sfx:
            e["t"] *= k
        t = TARGET_CHAT_SECONDS

    endcard_start = t + 0.5
    total = endcard_start + ENDCARD_SECONDS
    ec = episode.get("endcard", {})
    return {
        "items": items,
        "typing": [],
        "sfx": sfx,
        "header": {"mode": "slack", "channel": episode.get("channel", "student-wins")},
        "endcard": {
            "start": endcard_start,
            "line": ec.get("line") or "Behind every win is a team that loses it over your kid.",
            "cta": ec.get("cta") or "Book a free consultation",
            "url_display": (ec.get("cta_url")
                            or "https://meetings.hubspot.com/successful/consultation"
                            ).replace("https://", ""),
            # disclosure is baked into template_slack.html ("real A+ team moments")
            "logo": "",
        },
        "total": total,
    }


def make_white_logo(work: Path) -> Path:
    """Build the Ivory end-card logo. Prefer the transparent logo (clean
    anti-aliased edges); if it's missing, fall back to chroma-keying the
    ivory background out of the tracked logo.png so a missing asset can never
    silently fail every render again."""
    from PIL import Image
    ivory = (248, 244, 237)
    transparent = tc.REPO / "assets" / "logo-transparent.png"
    if transparent.exists():
        src = Image.open(transparent).convert("RGBA")
        px = src.load()
        for y in range(src.height):
            for x in range(src.width):
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = (*ivory, a)
    else:
        # fallback: derive the mark from the ivory-background logo.png
        src = Image.open(tc.REPO / "assets" / "logo.png").convert("RGBA")
        px = src.load()
        for y in range(src.height):
            for x in range(src.width):
                r, g, b, a = px[x, y]
                if r > 225 and g > 215 and b > 205:   # near-ivory/white -> transparent
                    px[x, y] = (255, 255, 255, 0)
                else:
                    px[x, y] = (*ivory, 255)
    out = work / "logo_white.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    src.save(out)
    return out


def render_html(data: dict, work: Path, template: str = "template.html") -> Path:
    tpl = (HERE / template).read_text()
    tpl = tpl.replace("__FRAUNCES_URL__", (HERE / "fonts" / "Fraunces-SemiBold.ttf").as_uri())
    tpl = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = work / "episode.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl)
    return out


def _skin(episode: dict) -> str:
    """messenger (1:1 / group bubbles) vs slack (team #channel thread)."""
    if episode.get("skin"):
        return episode["skin"]
    return "slack" if episode.get("dynamic") == "team_slack" else "messenger"


def build_audio(data: dict, out_path: Path) -> None:
    """Mix SFX events + ducked music bed into one track via ffmpeg."""
    total = data["total"]
    inputs, filters, labels = [], [], []
    idx = 0

    def add_input(path: Path, extra: list[str] | None = None) -> int:
        nonlocal idx
        inputs.extend((extra or []) + ["-i", str(path)])
        i = idx
        idx += 1
        return i

    music_i = add_input(tc.SFX_DIR / "music_bed.wav")

    vol = {"pop": 0.9, "swoosh": 0.65, "shutter": 0.9, "keyboard_clicks": 0.5}
    for n, e in enumerate(data["sfx"]):
        delay_ms = int(e["t"] * 1000)
        if e["name"] == "keyboard_clicks":
            i = add_input(tc.SFX_DIR / "keyboard_clicks.wav", ["-stream_loop", "-1"])
            filters.append(
                f"[{i}:a]atrim=duration={e['dur']:.3f},volume={vol['keyboard_clicks']},"
                f"adelay={delay_ms}:all=1[s{n}]")
        else:
            i = add_input(tc.SFX_DIR / f"{e['name']}.wav")
            filters.append(f"[{i}:a]volume={vol[e['name']]},adelay={delay_ms}:all=1[s{n}]")
        labels.append(f"[s{n}]")

    nsfx = len(labels)
    # pad to full length or sidechaincompress stops at the last SFX event
    filters.append(f"{''.join(labels)}amix=inputs={nsfx}:normalize=0,"
                   f"apad=whole_dur={total:.3f}[sfx]")
    filters.append("[sfx]asplit=2[sfxout][sfxkey]")
    fade_st = total - 1.4
    filters.append(
        f"[{music_i}:a]atrim=duration={total:.3f},volume=0.55,"
        f"afade=t=out:st={fade_st:.3f}:d=1.4[mus]")
    filters.append(
        "[mus][sfxkey]sidechaincompress=threshold=0.02:ratio=6:attack=25:release=420[musd]")
    filters.append(
        f"[musd][sfxout]amix=inputs=2:normalize=0,"
        f"atrim=duration={total:.3f},alimiter=limit=0.92[aout]")

    cmd = [tc.FFMPEG, "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[aout]", "-ar", "48000", "-c:a", "pcm_s16le", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)


def capture_frames(html: Path, data: dict, video_out: Path) -> None:
    from playwright.sync_api import sync_playwright

    nframes = int(data["total"] * FPS)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(html.as_uri())
        page.wait_for_function("window.__ready === true", timeout=15000)
        enc = subprocess.Popen(
            [tc.FFMPEG, "-y", "-f", "image2pipe", "-framerate", str(FPS),
             "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", str(video_out)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for f in range(nframes):
                page.evaluate(f"seek({f / FPS:.4f})")
                enc.stdin.write(page.screenshot(type="jpeg", quality=92))
                if f % 150 == 0:
                    print(f"  frame {f}/{nframes} ({f / FPS:.1f}s)")
            enc.stdin.close()
            if enc.wait() != 0:
                raise RuntimeError("ffmpeg video encode failed")
        finally:
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", help="bundle dir containing textstory/scenes-<dynamic>.json")
    ap.add_argument("--dynamic", choices=tc.DYNAMICS,
                    help="which dynamic's scenes to render (default: legacy scenes.json)")
    ap.add_argument("--episode-json", help="fixture mode: render this scene JSON directly")
    ap.add_argument("--out", help="output mp4 (fixture mode; default alongside the json)")
    ap.add_argument("--keep-work", action="store_true",
                    help="keep the work/ intermediates (html, mix.wav, silent video) "
                         "for debugging; default removes them so the bundle holds only "
                         "the scene JSON + the mp4")
    args = ap.parse_args()
    if not args.bundle and not args.episode_json:
        ap.error("need --bundle or --episode-json")

    for f in tc.SFX_FILES:
        if not (tc.SFX_DIR / f).exists():
            sys.exit(f"Missing {tc.SFX_DIR / f} — run scripts/b2c/textstory/make_sfx.py first.")

    if args.bundle:
        episode = tc.load_scenes(args.bundle, args.dynamic)
        work = tc.work_dir(args.bundle)
        final = tc.output_path(args.bundle, args.dynamic)
    else:
        src = Path(args.episode_json)
        episode = json.loads(src.read_text())
        work = src.parent / "work"
        final = Path(args.out) if args.out else src.with_suffix(".mp4")

    # resolve to absolute: the renderer builds file:// URIs for the template,
    # font, and logo, which fail on a relative bundle path (e.g. when invoked
    # with --bundle aplus-content/<name> from the repo root).
    work = work.resolve()
    final = final.resolve()

    if _skin(episode) == "slack":
        data = build_timeline_slack(episode)
        template = "template_slack.html"
    else:
        data = build_timeline(episode)
        template = "template.html"
    data["endcard"]["logo"] = make_white_logo(work).as_uri()
    print(f"Timeline ({_skin(episode)}): {len(data['items'])} items, "
          f"total {data['total']:.1f}s (endcard at {data['endcard']['start']:.1f}s)")

    html = render_html(data, work, template)

    video_only = work / "video_only.mp4"
    print("Capturing frames -> h264 ...")
    capture_frames(html, data, video_only)

    print("Mixing audio ...")
    audio = work / "mix.wav"
    build_audio(data, audio)

    subprocess.run(
        [tc.FFMPEG, "-y", "-i", str(video_only), "-i", str(audio),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)],
        check=True, capture_output=True)

    if not args.keep_work and work.exists():
        shutil.rmtree(work, ignore_errors=True)
        print("Cleaned work/ (use --keep-work to retain intermediates)")

    print(f"Done: {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
