#!/usr/bin/env python3
"""Generate a synthetic 'talking head' test video with a matching word-level transcript.

The audio is speech-like tone bursts (one per word) over room noise, with deliberate
problems an editor must fix: a slow open, filler words, long pauses and quiet levels.
The picture burns in the source timecode so cuts can be checked by eye.

Usage: make_fixture.py OUT_DIR [--noise-db -45] [--size 1280x720]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import ffmpeg, find_font  # noqa: E402

SCRIPT = [
    ("pause", 4.0),
    "So today I want to talk about money.", ("pause", 1.2), "Um",
    "Last year our revenue grew 300% in just six months.", "Uh", ("pause", 0.9),
    "There are three lessons I learned.",
    "First, start small.", ("pause", 0.4), "Second, ship fast.", ("pause", 0.4), "Third, listen to customers.",
    ("pause", 2.0),
    "I lost everything in six months, and that was the best thing that ever happened to me!",
    ("pause", 0.8), "Thanks for watching.", ("pause", 1.0),
]


def build(out: Path, noise_db: float, size: str, sr: int = 48000) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    words, t = [], 0.0
    for item in SCRIPT:
        if isinstance(item, tuple):
            t += item[1]
            continue
        loud = item.isupper() or item.endswith("!")
        for w in item.split():
            d = 0.12 + 0.055 * len(w.strip(".,!%"))
            words.append({"w": w, "start": round(t, 3), "end": round(t + d, 3), "emph": loud})
            t += d + 0.09
    total = t + 0.5

    n = int(total * sr)
    noise = rng.normal(0, 10 ** (noise_db / 20), n)
    audio = noise.copy()
    for k, w in enumerate(words):
        a, b = int(w["start"] * sr), int(w["end"] * sr)
        tt = np.arange(b - a) / sr
        f0 = 120 + 25 * np.sin(2 * np.pi * 3 * tt + k)
        filler = w["w"].lower().strip(".,") in {"um", "uh"}
        tone = sum(np.sin(2 * np.pi * f0 * h * tt) / h for h in (1, 2, 3, 5))
        env = np.sin(np.pi * np.clip(tt / (b - a) * sr, 0, 1)) ** 0.6
        amp = 0.05 if filler else (0.22 if w["emph"] else 0.11)
        audio[a:b] += amp * tone * env
    audio = np.clip(audio, -1, 1)
    pcm = (audio * 32767).astype(np.int16)
    wav = out / "fixture_audio.raw"
    wav.write_bytes(pcm.tobytes())

    font = find_font("bold")
    fontopt = f":fontfile='{font}'" if font else ""
    w, h = size.split("x")
    vf = (f"drawbox=x=iw*0.40:y=ih*0.22:w=iw*0.20:h=ih*0.42:color=0xE0B090@1:t=fill,"
          f"drawtext=text='SRC %{{pts\\:hms}}'{fontopt}:fontsize=h/14:fontcolor=white:x=(w-tw)/2:y=h*0.80:box=1:boxcolor=black@0.5")
    video = out / "fixture.mp4"
    ffmpeg(["-f", "lavfi", "-i", f"color=c=0x2B3A55:s={w}x{h}:r=30:d={total:.3f}",
            "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(wav),
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(video)])
    wav.unlink()
    tr = {"language": "en", "words": [{"w": x["w"], "start": x["start"], "end": x["end"]} for x in words]}
    (out / "fixture_transcript.json").write_text(json.dumps(tr, indent=1))
    print(f"{video}\n{out / 'fixture_transcript.json'}\n{total:.1f}s, {len(words)} words")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--noise-db", type=float, default=-45)
    ap.add_argument("--size", default="1280x720")
    a = ap.parse_args()
    build(Path(a.out), a.noise_db, a.size)
