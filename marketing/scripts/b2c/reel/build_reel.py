#!/usr/bin/env python3
"""
build_reel.py — assemble the narrated spotlight reel for a bundle:
  Veo clips + top-left A+ watermark + word-by-word karaoke captions (brand
  DM Sans, white -> A+ orange on the active word) + Gemini voiceover, then a
  branded end card. 9:16 vertical, h264 + AAC.

Inputs (already produced):
  {bundle}/reel/script.json
  {bundle}/reel/stills/<key>.png        (make_stills.py)
  {bundle}/reel/work/<key>.veo.mp4      (make_clips.py)
  {bundle}/reel/work/vo_<key>.wav       (make_vo.py)
Word timing via OpenAI Whisper (cached to work/words_<key>.json).
Output: {bundle}/reel/spotlight-reel.mp4

Usage:  python3 scripts/b2c/reel/build_reel.py --bundle aplus-content/{bundle}/
"""
import argparse
import json
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel_common as rc

# timeline: each beat = LEAD silence + narration + TAIL silence. If the
# narration runs longer than the (~8s) Veo clip, the clip's last frame is held
# so the line is never truncated. MAX_BEAT just bounds runaway lines.
LEAD, TAIL = 0.2, 0.45
MIN_BEAT, MAX_BEAT = 2.6, 12.0
ENDCARD_EXTRA_HOLD = 0.5
WM_MARGIN = 34


def words_for(work, key):
    cache = work / f"words_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    client = OpenAI(api_key=rc.OPENAI_KEY)
    with open(work / f"vo_{key}.wav", "rb") as f:
        r = client.audio.transcriptions.create(
            model="whisper-1", file=f, response_format="verbose_json",
            timestamp_granularities=["word"])
    words = [{"word": w.word, "start": w.start, "end": w.end} for w in r.words]
    cache.write_text(json.dumps(words))
    return words


def caption_words(whisper, line):
    """Pair the SCRIPTED words (correct punctuation/caps) with Whisper timings,
    so captions read as written instead of as a raw transcript. Clean TTS
    yields matching counts → exact per-word sync; otherwise distribute the
    scripted tokens evenly across the spoken span."""
    toks = line.split()
    if not whisper:
        return [{"word": t, "start": i * 0.4, "end": i * 0.4 + 0.4} for i, t in enumerate(toks)]
    if len(toks) == len(whisper):
        return [{"word": t, "start": whisper[i]["start"], "end": whisper[i]["end"]}
                for i, t in enumerate(toks)]
    t0, t1 = whisper[0]["start"], whisper[-1]["end"]
    span = max(0.3, t1 - t0); n = len(toks)
    return [{"word": t, "start": t0 + span * i / n, "end": t0 + span * (i + 1) / n}
            for i, t in enumerate(toks)]


def video_beat(work, idx, key, beat_dur, states):
    wm, clip = work / "watermark.png", work / f"{key}.veo.mp4"
    inputs = ["-i", str(clip), "-i", str(wm)]
    for p, _, _ in states:
        inputs += ["-i", p]
    # If narration outlasts the clip, hold the last frame for the remainder so
    # the line is never cut off; otherwise trim the clip to the beat length.
    hold = max(0.0, beat_dur - rc.dur(clip))
    base = (f"[0:v]scale={rc.W}:{rc.H}:force_original_aspect_ratio=increase,"
            f"crop={rc.W}:{rc.H},setsar=1,fps={rc.FPS}")
    if hold > 0.04:
        base += f",tpad=stop_mode=clone:stop_duration={hold:.3f}"
    else:
        base += f",trim=0:{beat_dur},setpts=PTS-STARTPTS"
    fc = f"{base}[v0];[v0][1:v]overlay={WM_MARGIN}:{WM_MARGIN}[v1]"
    label = "v1"
    for k, (_, a, b) in enumerate(states):
        nxt = f"v{2+k}"
        fc += f";[{label}][{2+k}:v]overlay=0:0:enable='between(t,{a},{b})'[{nxt}]"
        label = nxt
    fc += f";[{label}]format=yuv420p[out]"
    out = work / f"seg_{idx}_{key}.mp4"
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
            "-map", "[out]", "-an", "-t", f"{beat_dur}", "-c:v", "libx264",
            "-preset", rc.PRESET, "-crf", str(rc.CRF), "-pix_fmt", "yuv420p", str(out)])
    return out


def endcard_beat(work, idx, beat_dur):
    png = work / "zz_endcard.png"
    out = work / f"seg_{idx}_endcard.mp4"
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-t", f"{beat_dur}",
            "-i", str(png), "-an",
            "-vf", f"scale={rc.W}:{rc.H},setsar=1,fps={rc.FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", rc.PRESET, "-crf", str(rc.CRF),
            "-pix_fmt", "yuv420p", str(out)])
    return out


def audio_beat(work, idx, key, beat_dur):
    out = work / f"aud_{idx}.m4a"
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", "-i", str(work / f"vo_{key}.wav"),
            "-af", f"adelay={int(LEAD*1000)}:all=1,apad", "-t", f"{beat_dur}",
            "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "160k", str(out)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    args = ap.parse_args()
    if not rc.OPENAI_KEY:
        sys.exit("OPENAI_API_KEY not set (needed for caption word-timing)")

    script = rc.load_script(args.bundle)
    work = rc.work_dir(args.bundle)
    work.mkdir(parents=True, exist_ok=True)

    # preflight
    for b in script["beats"]:
        for f in (work / f"{b['key']}.veo.mp4", work / f"vo_{b['key']}.wav"):
            if not f.exists():
                sys.exit(f"missing {f}")
    if not (work / "vo_endcard.wav").exists():
        sys.exit("missing vo_endcard.wav")

    rc.build_watermark(work / "watermark.png")
    ec = script["endcard"]
    rc.build_endcard(work / "zz_endcard.png", ec["headline1"], ec["headline2"],
                     ec["cta"], ec.get("note"), ec.get("url"))

    vsegs, asegs = [], []
    for idx, b in enumerate(script["beats"]):
        key = b["key"]
        vo_d = rc.dur(work / f"vo_{key}.wav")
        beat_dur = round(min(MAX_BEAT, max(MIN_BEAT, LEAD + vo_d + TAIL)), 3)
        disp = caption_words(words_for(work, key), b["vo"])
        states = rc.render_caption_states(disp, work / f"cap_{key}", LEAD)
        print(f"  {key}: vo={vo_d:.2f}s beat={beat_dur:.2f}s words={len(states)}", flush=True)
        vsegs.append(video_beat(work, idx, key, beat_dur, states))
        asegs.append(audio_beat(work, idx, key, beat_dur))

    eidx = len(script["beats"])
    vo_e = rc.dur(work / "vo_endcard.wav")
    end_dur = round(LEAD + vo_e + TAIL + ENDCARD_EXTRA_HOLD, 3)
    print(f"  endcard: vo={vo_e:.2f}s beat={end_dur:.2f}s", flush=True)
    vsegs.append(endcard_beat(work, eidx, end_dur))
    asegs.append(audio_beat(work, eidx, "endcard", end_dur))

    # absolute paths — concat resolves entries relative to the list file's dir
    (work / "vconcat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in vsegs))
    (work / "aconcat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in asegs))
    video_only, vo_track = work / "video_only.mp4", work / "vo_track.m4a"
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(work / "vconcat.txt"), "-c:v", "libx264", "-preset", rc.PRESET,
            "-crf", str(rc.CRF), "-pix_fmt", "yuv420p", str(video_only)])
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(work / "aconcat.txt"), "-c", "copy", str(vo_track)])

    out = rc.output_path(args.bundle)
    rc.run([rc.FFMPEG, "-y", "-loglevel", "error", "-i", str(video_only), "-i", str(vo_track),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            "-shortest", str(out)])
    print(f"\nDONE -> {out}")
    print(f"duration: {rc.dur(out):.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
