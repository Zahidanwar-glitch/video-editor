#!/usr/bin/env python3
"""Audio helpers: speech enhancement chains, synthesized SFX, loudness, and AI voiceover.

CLI (voiceover via ElevenLabs text-to-speech; needs ELEVENLABS_API_KEY):
  audio.py tts "Script text..." -o WORK/voiceover.mp3 --voice VOICE_ID [--model eleven_multilingual_v2]
  audio.py voices                      # list available voice ids
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SKILL_DIR, ffmpeg  # noqa: E402

# Order matters: clean low end -> denoise -> declick -> tame dynamics -> presence -> de-ess.
ENHANCE = {
    "light": "highpass=f=75,afftdn=nf=-50:nr=6:nt=w,acompressor=threshold=-20dB:ratio=2:attack=15:release=200:makeup=1.5,deesser=i=0.2",
    "medium": "highpass=f=80,afftdn=nf=-45:nr=10:nt=w,acompressor=threshold=-22dB:ratio=3:attack=10:release=180:makeup=2,"
              "equalizer=f=3200:t=q:w=1.2:g=2,deesser=i=0.35",
    "strong": "highpass=f=90,lowpass=f=15000,adeclick,afftdn=nf=-38:nr=18:nt=w:tn=1,"
              "acompressor=threshold=-24dB:ratio=3.5:attack=8:release=160:makeup=2.5,"
              "equalizer=f=250:t=q:w=1:g=-2,equalizer=f=3200:t=q:w=1.2:g=3,deesser=i=0.5",
}

SFX = {
    "pop": ["-f", "lavfi", "-i", "aevalsrc='0.9*sin(2*PI*(950-650*t/0.09)*t)*exp(-t*38)':s=48000:d=0.14"],
    "click": ["-f", "lavfi", "-i", "aevalsrc='0.8*sin(2*PI*2600*t)*exp(-t*220)':s=48000:d=0.04"],
    "ding": ["-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*1318*t)*exp(-t*5)+0.25*sin(2*PI*2637*t)*exp(-t*8)':s=48000:d=1.1"],
    "riser": ["-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(180*t+500*t*t))*min(1,t/0.9)':s=48000:d=1.0"],
    "whoosh": ["-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.7:r=48000"],
}
SFX_FILTER = {"whoosh": "bandpass=f=1400:w=1200,afade=t=in:d=0.28:curve=exp,afade=t=out:st=0.28:d=0.22"}


def enhance_filter(level) -> str | None:
    if level in (False, None):
        return None
    return ENHANCE["medium" if level is True else level]


def sfx_file(kind: str) -> Path:
    cache = SKILL_DIR / "assets" / "sfx"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{kind}.wav"
    if not f.exists():
        args = list(SFX[kind])
        if kind in SFX_FILTER:
            args += ["-af", SFX_FILTER[kind]]
        ffmpeg(args + ["-ac", "2", str(f)])
    return f


def measure_loudness(path: Path, target: float, tp: float = -1.5, lra: float = 11) -> dict:
    proc = ffmpeg(["-i", str(path), "-af", f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    return json.loads(m.group(0)) if m else {}


def loudnorm_filter(meas: dict, target: float, tp: float = -1.5, lra: float = 11) -> str:
    if not meas or meas.get("input_i") in (None, "-inf"):
        return f"loudnorm=I={target}:TP={tp}:LRA={lra}"
    return (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
            f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")


# ------------------------------------------------------------ ElevenLabs

def _el_request(url: str, body: dict | None = None) -> bytes:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set (or use the ElevenLabs connector in Claude to generate the voiceover).")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, method="POST" if body else "GET",
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def tts(text: str, out: Path, voice: str, model: str, stability: float, similarity: float, style: float) -> None:
    data = _el_request(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                       {"text": text, "model_id": model,
                        "voice_settings": {"stability": stability, "similarity_boost": similarity, "style": style}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"voiceover: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tts")
    t.add_argument("text")
    t.add_argument("-o", "--out", required=True)
    t.add_argument("--voice", required=True)
    t.add_argument("--model", default="eleven_multilingual_v2")
    t.add_argument("--stability", type=float, default=0.45)
    t.add_argument("--similarity", type=float, default=0.8)
    t.add_argument("--style", type=float, default=0.25)
    sub.add_parser("voices")
    s = sub.add_parser("sfx", help="pre-generate built-in sound effects")
    s.add_argument("kinds", nargs="*", default=list(SFX))
    a = ap.parse_args()
    if a.cmd == "tts":
        tts(Path(a.text).read_text() if Path(a.text).is_file() else a.text, Path(a.out), a.voice, a.model, a.stability, a.similarity, a.style)
    elif a.cmd == "voices":
        for v in json.loads(_el_request("https://api.elevenlabs.io/v1/voices")).get("voices", []):
            print(f"{v['voice_id']}  {v['name']}  {v.get('labels', {})}")
    else:
        for k in a.kinds:
            print(sfx_file(k))


if __name__ == "__main__":
    main()
