#!/usr/bin/env python3
"""
make_sfx.py — synthesize the royalty-free SFX bed into assets/sfx/.

Every sound is generated from scratch here (sine/noise synthesis + light
filtering, saturation and reverb), so the files are ours outright: no
attribution, no license tracking, no third-party provenance, and they
regenerate identically in CI. This satisfies the format guardrail ("SFX
from our own assets folder, never Apple's"). If you ever want a specific
hand-picked Pixabay SFX instead, drop it in under the same filename — the
renderer only cares about the filenames, not how they were made.

Files produced (48 kHz mono 16-bit WAV):
    assets/sfx/keyboard_clicks.wav   ~2.0s soft tick loop (typing dots)
    assets/sfx/swoosh.wav            send sound (right-side bubble)
    assets/sfx/pop.wav               receive sound (left-side bubble)
    assets/sfx/shutter.wav           screenshot bubble
    assets/sfx/music_bed.wav         ~40s gentle pad bed (ducked under SFX)
"""
import random
import wave
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parents[3] / "assets" / "sfx"


def write_wav(path: Path, samples: np.ndarray) -> None:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"  wrote {path.relative_to(OUT.parents[1])} ({len(samples)/SR:.2f}s)")


def env_exp(n: int, attack: float, decay: float) -> np.ndarray:
    """Fast attack, exponential decay envelope."""
    t = np.arange(n) / SR
    a = np.minimum(t / max(attack, 1e-4), 1.0)
    d = np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4))
    return a * d


def bandpass_sweep(noise: np.ndarray, f_start: float, f_end: float, q: float = 4.0) -> np.ndarray:
    """State-variable bandpass with a swept center frequency (sample loop;
    inputs are short so plain Python speed is fine)."""
    n = len(noise)
    out = np.zeros(n)
    low = band = 0.0
    for i in range(n):
        f_c = f_start + (f_end - f_start) * (i / n)
        f1 = 2 * np.sin(np.pi * f_c / SR)
        low += f1 * band
        high = noise[i] - low - band / q
        band += f1 * high
        out[i] = band
    peak = np.max(np.abs(out)) or 1.0
    return out / peak


def make_pop() -> np.ndarray:
    """Short downward 'bloop' — message received."""
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    freq = 760 * np.exp(-t * 9.0) + 360
    phase = 2 * np.pi * np.cumsum(freq) / SR
    tone = np.sin(phase)
    return 0.85 * tone * env_exp(n, 0.004, 0.045)


def make_swoosh() -> np.ndarray:
    """Rising filtered-noise whoosh — message sent."""
    rng = np.random.default_rng(7)
    n = int(0.28 * SR)
    noise = rng.standard_normal(n)
    sw = bandpass_sweep(noise, 500, 2600, q=3.0)
    t = np.arange(n) / SR
    shape = np.sin(np.pi * np.minimum(t / 0.28, 1.0)) ** 1.5  # rise then fall
    return 0.7 * sw * shape


def make_keyboard(duration: float = 2.0) -> np.ndarray:
    """Soft irregular ticks ~10/s. Loopable (no tick at the very end)."""
    rng = np.random.default_rng(42)
    rnd = random.Random(42)
    n = int(duration * SR)
    out = np.zeros(n)
    t = 0.03
    while t < duration - 0.12:
        tick_n = int(0.007 * SR)
        burst = rng.standard_normal(tick_n)
        burst = np.diff(burst, prepend=0.0)  # cheap highpass: thin clicky tick
        burst *= env_exp(tick_n, 0.0005, 0.002)
        amp = rnd.uniform(0.18, 0.42)
        i0 = int(t * SR)
        out[i0:i0 + tick_n] += amp * burst / (np.max(np.abs(burst)) or 1.0)
        t += rnd.uniform(0.06, 0.13)
    return out


def make_shutter() -> np.ndarray:
    """Two crisp ticks — generic camera/screenshot, not Apple's."""
    def tick(freq_hint: float) -> np.ndarray:
        rng = np.random.default_rng(int(freq_hint))
        tn = int(0.012 * SR)
        b = np.diff(rng.standard_normal(tn), prepend=0.0)
        b *= env_exp(tn, 0.0004, 0.003)
        return b / (np.max(np.abs(b)) or 1.0)

    n = int(0.18 * SR)
    out = np.zeros(n)
    t1, t2 = tick(11), tick(23)
    out[: len(t1)] += 0.8 * t1
    i2 = int(0.07 * SR)
    out[i2 : i2 + len(t2)] += 0.65 * t2
    return out


def _onepole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Cheap one-pole low-pass to round off the synthetic edge."""
    dt = 1.0 / SR
    rc = 1.0 / (2 * np.pi * cutoff_hz)
    a = dt / (rc + dt)
    out = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        out[i] = acc
    return out


def _reverb(x: np.ndarray, decay: float = 1.6, mix: float = 0.28) -> np.ndarray:
    """Light convolution reverb with an exponentially-decaying noise tail —
    smears the pad into a warmer, roomier wash."""
    rng = np.random.default_rng(99)
    ir_n = int(decay * SR)
    t = np.arange(ir_n) / SR
    ir = rng.standard_normal(ir_n) * np.exp(-t / (decay / 4.0))
    ir[0] = 1.0
    ir = _onepole_lowpass(ir, 3500)
    ir /= np.max(np.abs(ir)) or 1.0
    wet = np.convolve(x, ir)[: len(x)]
    wet /= np.max(np.abs(wet)) or 1.0
    return (1 - mix) * x + mix * wet


def make_music_bed(duration: float = 40.0) -> np.ndarray:
    """Warm, hopeful pad — I–V–vi–IV in C, the classic uplifting progression.
    Detuned voices (chorus), soft attacks, harmonic rolloff, gentle saturation
    and a light reverb wash so it reads as a real instrument, not raw sines.
    Quiet by design: it sits well under the SFX and ducks further when they hit.
    A soft bell pluck marks each chord change for subtle forward motion."""
    chords = [
        [130.81, 261.63, 329.63, 392.00],   # C
        [98.00, 246.94, 293.66, 392.00],    # G
        [110.00, 220.00, 261.63, 329.63],   # Am
        [87.31, 261.63, 349.23, 440.00],    # F
    ]
    # detune cents per stacked voice -> chorus thickness
    detune = (-7.0, 0.0, 6.0)
    chord_len = 4.0
    n = int(duration * SR)
    out = np.zeros(n)
    t_all = np.arange(n) / SR
    idx = 0
    t0 = 0.0
    while t0 < duration:
        chord = chords[idx % len(chords)]
        cn = int(min(chord_len + 1.6, duration - t0) * SR)  # 1.6s overlap tail
        seg_t = np.arange(cn) / SR
        seg = np.zeros(cn)
        # slow vibrato shared across the chord for a hand-played feel
        vib = 1.0 + 0.0025 * np.sin(2 * np.pi * 4.7 * seg_t)
        for j, f in enumerate(chord):
            voice = np.zeros(cn)
            for cents in detune:
                fv = f * (2 ** (cents / 1200.0)) * vib
                phase = 2 * np.pi * np.cumsum(fv) / SR
                for h, ha in ((1, 1.0), (2, 0.22), (3, 0.07), (4, 0.03)):
                    voice += ha * np.sin(h * phase)
            seg += voice / (j + 1.6)        # upper voices softer than the root
        # soft pluck of the chord's top note on the change
        bell_f = chord[-1] * 2
        bell = np.sin(2 * np.pi * bell_f * seg_t) * np.exp(-seg_t / 0.45)
        seg += 0.18 * bell
        attack = np.minimum(seg_t / 1.3, 1.0) ** 1.4   # slow swell-in
        release = np.minimum((cn / SR - seg_t) / 1.5, 1.0)
        seg *= attack * np.clip(release, 0, 1)
        i0 = int(t0 * SR)
        seg = seg[: n - i0]
        out[i0 : i0 + len(seg)] += seg
        t0 += chord_len
        idx += 1

    out /= np.max(np.abs(out)) or 1.0
    out = _onepole_lowpass(out, 2600)              # tame the brightness
    out = np.tanh(1.6 * out)                        # gentle tube-ish warmth
    out = _reverb(out, decay=1.6, mix=0.26)         # roomy wash
    out *= 1.0 + 0.05 * np.sin(2 * np.pi * 0.12 * t_all)  # slow gentle swell
    return 0.17 * out / (np.max(np.abs(out)) or 1.0)


def main() -> None:
    print("Synthesizing SFX -> assets/sfx/")
    write_wav(OUT / "pop.wav", make_pop())
    write_wav(OUT / "swoosh.wav", make_swoosh())
    write_wav(OUT / "keyboard_clicks.wav", make_keyboard())
    write_wav(OUT / "shutter.wav", make_shutter())
    write_wav(OUT / "music_bed.wav", make_music_bed())


if __name__ == "__main__":
    main()
