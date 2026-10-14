#!/usr/bin/env python3
"""Analyze a video so Claude can make editing decisions.

Produces in the work directory:
  analysis.json      full machine-readable analysis (words, pauses, scenes, faces, audio)
  summary.md         compact digest for Claude to read first
  frames/*.jpg       one still per scene
  contact_sheet.jpg  all stills on one image with timestamps (look at this, not every frame)

Every expensive step is cached by file fingerprint, and independent steps run in parallel.

Usage:
  analyze.py VIDEO -o WORK [--transcript FILE] [--asr auto|whisper|elevenlabs|none]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ffmpeg, file_fingerprint, load_json, probe, require_ffmpeg, save_json  # noqa: E402

HARD_FILLERS = {"um", "uh", "erm", "er", "ah", "uhm", "umm", "uhh", "hmm", "mm", "mhm", "eh"}
SOFT_FILLERS = {"like", "basically", "actually", "literally", "so", "right", "okay", "you know", "i mean", "kind of", "sort of"}
FRAME_MS = 10


# ---------------------------------------------------------------- audio

def decode_audio(path: str, sr: int = 16000) -> np.ndarray:
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode()[-1000:])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def adaptive_silences(x: np.ndarray, sr: int = 16000, min_ms: int = 300):
    """10 ms RMS in dB, noise floor, speech level, adaptive threshold and silence runs.
    The threshold adapts to the recording, so it works before and after loudness changes."""
    hop = sr * FRAME_MS // 1000
    n = len(x) // hop
    if n == 0:
        return np.array([]), -90.0, -90.0, -90.0, []
    frames = x[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12) + 1e-9)
    audible = db[db > -85]
    noise = float(np.percentile(audible, 10)) if len(audible) else -90.0
    speech = float(np.percentile(audible, 95)) if len(audible) else -90.0
    thr = noise + 0.35 * (speech - noise)
    silences = []
    below = db < thr
    i = 0
    while i < n:
        if below[i]:
            j = i
            while j < n and below[j]:
                j += 1
            if (j - i) * FRAME_MS >= min_ms:
                silences.append({"start": round(i * FRAME_MS / 1000, 3), "end": round(j * FRAME_MS / 1000, 3),
                                 "dur": round((j - i) * FRAME_MS / 1000, 3)})
            i = j
        else:
            i += 1
    return db, noise, speech, thr, silences


def audio_analysis(path: str, info: dict, energy_path: Path) -> dict:
    if not info.get("has_audio"):
        return {"present": False}
    sr = 16000
    x = decode_audio(path, sr)
    db, noise, speech, thr, silences = adaptive_silences(x, sr)
    n = len(db)
    if n == 0:
        return {"present": False}

    # energy curve, 0.5 s resolution, for "how it's said" scoring
    step = 50
    m = n // step
    energy = [round(float(np.mean(db[k * step:(k + 1) * step])), 1) for k in range(m)]
    clip_ratio = float(np.mean(np.abs(x) > 0.985))
    np.save(energy_path, db.astype(np.float16))
    return {
        "present": True,
        "noise_floor_db": round(noise, 1),
        "speech_level_db": round(speech, 1),
        "snr_db": round(speech - noise, 1),
        "silence_threshold_db": round(thr, 1),
        "clipping_ratio": round(clip_ratio, 6),
        "silences": silences,
        "energy_curve_0p5s": energy,
    }


def loudness(path: str, info: dict) -> dict:
    if not info.get("has_audio"):
        return {}
    proc = ffmpeg(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], check=False)
    err = proc.stderr
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else err
    def grab(pat):
        m = re.search(pat, summary)
        return float(m.group(1)) if m else None
    return {"integrated_lufs": grab(r"I:\s+(-?[\d.]+) LUFS"), "lra_lu": grab(r"LRA:\s+(-?[\d.]+) LU"),
            "true_peak_dbfs": grab(r"Peak:\s+(-?[\d.]+) dBFS")}


# ---------------------------------------------------------------- video

def scenes(path: str, info: dict, threshold: float = 0.32) -> list[dict]:
    if not info.get("has_video"):
        return []
    try:
        from scenedetect import ContentDetector, detect  # type: ignore
        res = detect(path, ContentDetector())
        cuts = [s[0].get_seconds() for s in res][1:]
    except Exception:
        proc = ffmpeg(["-i", path, "-an", "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"], check=False)
        cuts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)]
    bounds = [0.0] + [c for c in cuts if 0.2 < c < info["duration"] - 0.2] + [info["duration"]]
    return [{"index": i, "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3)} for i, (a, b) in enumerate(zip(bounds, bounds[1:]))]


def faces(path: str, info: dict) -> dict:
    if not info.get("has_video"):
        return {"available": False}
    try:
        import cv2  # type: ignore
        cv2.CascadeClassifier  # removed in OpenCV 5
    except Exception:
        return {"available": False, "note": "pip install 'opencv-python-headless<5' for face-aware reframing and graphic placement"}
    dur = info["duration"]
    rate = 1.0 if dur <= 900 else max(0.1, 900 / dur)
    W = 480
    H = int(round(info["height"] * W / info["width"] / 2) * 2)
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-an", "-vf", f"fps={rate},scale={W}:{H},format=gray",
                           "-f", "rawvideo", "-"], capture_output=True)
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    count = len(buf) // (W * H)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    samples = []
    for k in range(count):
        img = buf[k * W * H:(k + 1) * W * H].reshape(H, W)
        dets = cascade.detectMultiScale(img, scaleFactor=1.15, minNeighbors=5, minSize=(int(W * 0.06), int(W * 0.06)))
        boxes = sorted(([float(x) / W, float(y) / H, float(w) / W, float(h) / H] for x, y, w, h in dets), key=lambda b: -b[2] * b[3])
        samples.append({"t": round(k / rate, 2), "boxes": [[round(v, 3) for v in b] for b in boxes[:3]]})
    with_face = [s for s in samples if s["boxes"]]
    summary = {"available": True, "sample_rate_hz": rate, "frames_sampled": len(samples),
               "face_presence": round(len(with_face) / max(1, len(samples)), 2)}
    if with_face:
        cx = [s["boxes"][0][0] + s["boxes"][0][2] / 2 for s in with_face]
        cy = [s["boxes"][0][1] + s["boxes"][0][3] / 2 for s in with_face]
        size = [s["boxes"][0][3] for s in with_face]
        summary.update({"median_center_x": round(float(np.median(cx)), 3), "median_center_y": round(float(np.median(cy)), 3),
                        "median_face_height": round(float(np.median(size)), 3),
                        "multi_face_ratio": round(sum(len(s["boxes"]) > 1 for s in with_face) / len(with_face), 2)})
    summary["samples"] = samples
    return summary


def extract_frames(path: str, info: dict, scene_list: list[dict], out_dir: Path, max_frames: int = 24) -> list[dict]:
    if not info.get("has_video"):
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    times = [round((s["start"] + s["end"]) / 2, 2) for s in scene_list]
    dur = info["duration"]
    if len(times) < 8:
        times = sorted(set(times + [round(dur * (k + 0.5) / 8, 2) for k in range(8)]))
    if len(times) > max_frames:
        idx = np.linspace(0, len(times) - 1, max_frames).round().astype(int)
        times = [times[i] for i in sorted(set(idx))]

    def grab(t):
        f = out_dir / f"frame_{t:08.2f}.jpg"
        if not f.exists():
            ffmpeg(["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "4", str(f)], check=False)
        return {"t": t, "file": str(f)} if f.exists() else None

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        res = [r for r in ex.map(grab, times) if r]
    return res


def contact_sheet(frames: list[dict], out: Path, cols: int = 4) -> str | None:
    if not frames:
        return None
    from PIL import Image, ImageDraw, ImageFont
    thumbs = [Image.open(f["file"]).convert("RGB") for f in frames]
    tw = 384
    th = int(thumbs[0].height * tw / thumbs[0].width)
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 26)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:
        font = ImageFont.load_default()
    for k, (im, f) in enumerate(zip(thumbs, frames)):
        x, y = (k % cols) * tw, (k // cols) * (th + 26)
        sheet.paste(im.resize((tw, th)), (x, y + 26))
        t = f["t"]
        draw.text((x + 6, y + 3), f"{int(t // 60):02d}:{t % 60:05.2f}", fill=(255, 220, 0), font=font)
    sheet.save(out, quality=85)
    return str(out)


# ---------------------------------------------------------------- transcript

def _norm_word(w: str) -> str:
    return re.sub(r"[^\w']+", "", w.lower())


def load_transcript_file(path: str) -> dict:
    p = Path(path)
    if p.suffix.lower() == ".srt":
        words = []
        blocks = re.split(r"\n\s*\n", p.read_text(encoding="utf-8").strip())
        for b in blocks:
            m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", b)
            if not m:
                continue
            g = list(map(int, m.groups()))
            a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            text = " ".join(b.split("\n")[2:]).split()
            for k, w in enumerate(text):  # spread evenly: approximate, segment-level source
                words.append({"w": w, "start": a + (e - a) * k / len(text), "end": a + (e - a) * (k + 1) / len(text)})
        return {"source": "srt", "approximate": True, "words": words}
    data = load_json(p)
    words = []
    if "segments" in data and data["segments"] and "words" in data["segments"][0]:
        for s in data["segments"]:
            for w in s.get("words", []):
                words.append({"w": (w.get("word") or w.get("text") or "").strip(), "start": w["start"], "end": w["end"], "speaker": s.get("speaker")})
    else:
        for w in data.get("words", []):
            if w.get("type") in ("spacing", "audio_event"):
                continue
            words.append({"w": (w.get("w") or w.get("word") or w.get("text") or "").strip(), "start": w["start"], "end": w["end"],
                          "speaker": w.get("speaker") or w.get("speaker_id")})
    return {"source": f"file:{p.name}", "language": data.get("language") or data.get("language_code"), "words": [w for w in words if w["w"]]}


def transcribe_whisper(path: str, language: str | None) -> dict:
    from faster_whisper import WhisperModel  # type: ignore
    model = WhisperModel(os.environ.get("VD_WHISPER_MODEL", "small"), device="auto", compute_type="auto")
    segs, meta = model.transcribe(path, word_timestamps=True, vad_filter=True, language=language)
    words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)}
             for s in segs for w in (s.words or [])]
    return {"source": "faster-whisper", "language": meta.language, "words": words}


def transcribe_elevenlabs(path: str, language: str | None, tmp: Path) -> dict:
    key = os.environ["ELEVENLABS_API_KEY"]
    audio = tmp / "asr.m4a"
    ffmpeg(["-i", path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "64k", str(audio)])
    boundary = uuid.uuid4().hex
    fields = {"model_id": "scribe_v1", "timestamps_granularity": "word", "diarize": "true", "tag_audio_events": "true"}
    if language:
        fields["language_code"] = language
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"asr.m4a\"\r\n"
             f"Content-Type: audio/mp4\r\n\r\n").encode() + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    words = [{"w": w["text"].strip(), "start": w["start"], "end": w["end"], "speaker": w.get("speaker_id")}
             for w in data.get("words", []) if w.get("type") == "word" and w["text"].strip()]
    events = [{"event": w["text"], "start": w["start"], "end": w["end"]} for w in data.get("words", []) if w.get("type") == "audio_event"]
    return {"source": "elevenlabs-scribe", "language": data.get("language_code"), "words": words, "audio_events": events}


def transcript(path: str, info: dict, args, tmp: Path) -> dict:
    if args.transcript:
        return load_transcript_file(args.transcript)
    if not info.get("has_audio") or args.asr == "none":
        return {"source": "none", "words": []}
    order = {"auto": ["whisper", "elevenlabs"], "whisper": ["whisper"], "elevenlabs": ["elevenlabs"]}[args.asr]
    errors = []
    for eng in order:
        try:
            if eng == "whisper":
                return transcribe_whisper(path, args.language)
            if eng == "elevenlabs" and os.environ.get("ELEVENLABS_API_KEY"):
                return transcribe_elevenlabs(path, args.language, tmp)
            errors.append("elevenlabs: ELEVENLABS_API_KEY not set")
        except ImportError:
            errors.append("whisper: pip install faster-whisper")
        except Exception as e:  # network/model errors must not kill the whole analysis
            errors.append(f"{eng}: {e}")
    return {"source": "none", "words": [], "errors": errors}


# ---------------------------------------------------------------- derived structure

def derive(tr: dict, audio: dict) -> dict:
    words = tr.get("words", [])
    for k, w in enumerate(words):
        n = _norm_word(w["w"])
        w["id"] = k
        w["filler"] = "hard" if n in HARD_FILLERS else ("soft" if n in SOFT_FILLERS else None)
        w["start"], w["end"] = round(float(w["start"]), 3), round(float(w["end"]), 3)
    pauses = []
    for a, b in zip(words, words[1:]):
        gap = b["start"] - a["end"]
        if gap >= 0.35:
            pauses.append({"start": a["end"], "end": b["start"], "dur": round(gap, 3), "after_word": a["id"],
                           "after_sentence_end": bool(re.search(r"[.!?]['\"]?$", a["w"]))})
    energy = audio.get("energy_curve_0p5s") or []
    med = float(np.median(energy)) if energy else 0.0

    sentences, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        if nxt is None or re.search(r"[.!?]['\"]?$", w["w"]) or nxt["start"] - w["end"] > 1.2:
            a, b = cur[0]["start"], cur[-1]["end"]
            seg = energy[int(a * 2):max(int(a * 2) + 1, int(b * 2))] if energy else []
            real = [x for x in cur if x["filler"] != "hard"]
            sentences.append({"id": len(sentences), "start": a, "end": b, "first_word": cur[0]["id"], "last_word": cur[-1]["id"],
                              "text": " ".join(x["w"] for x in cur),
                              "wpm": round(len(real) / max(0.1, b - a) * 60),
                              "energy_vs_median_db": round(float(np.mean(seg)) - med, 1) if seg else None,
                              "fillers": sum(x["filler"] == "hard" for x in cur)})
            cur = []
    hard = [w for w in words if w["filler"] == "hard"]
    spoken = sum(w["end"] - w["start"] for w in words)
    return {"pauses": pauses, "sentences": sentences, "filler_ids": [w["id"] for w in hard],
            "stats": {"words": len(words), "hard_fillers": len(hard), "pauses_over_0p7s": sum(p["dur"] > 0.7 for p in pauses),
                      "speech_seconds": round(spoken, 1),
                      "wpm": round(len(words) / max(1e-6, (words[-1]["end"] - words[0]["start"])) * 60) if words else 0}}


def detect_issues(info, audio, loud, scene_list, face, tr, d) -> list[dict]:
    issues = []
    def add(code, sev, msg, fix):
        issues.append({"code": code, "severity": sev, "message": msg, "suggested_fix": fix})
    if audio.get("present"):
        if audio["noise_floor_db"] > -50:
            add("noisy_audio", "high" if audio["noise_floor_db"] > -40 else "medium", f"Noise floor {audio['noise_floor_db']} dBFS", "audio.enhance_speech = true")
        if audio["clipping_ratio"] > 0.0005:
            add("clipping", "high", f"{audio['clipping_ratio'] * 100:.2f}% samples clipped", "audio.enhance_speech (declip); consider re-recording key lines")
    if loud.get("integrated_lufs") is not None and abs(loud["integrated_lufs"] - (-14)) > 2:
        add("loudness", "medium", f"Integrated loudness {loud['integrated_lufs']} LUFS", "output.lufs normalisation (render does this)")
    st = d["stats"]
    if st["hard_fillers"]:
        add("fillers", "medium", f"{st['hard_fillers']} filler words (um/uh)", "cuts_removed (draft_plan.py adds them)")
    if st["pauses_over_0p7s"]:
        add("long_pauses", "medium", f"{st['pauses_over_0p7s']} pauses longer than 0.7s", "tighten to style.max_pause")
    if d["sentences"] and d["sentences"][0]["start"] > 3:
        add("slow_open", "high", f"First speech at {d['sentences'][0]['start']}s", "open on the strongest line (hook)")
    long_static = [s for s in scene_list if s["dur"] > 20]
    if long_static:
        add("static_shots", "low", f"{len(long_static)} shots longer than 20s", "punch-in zooms, B-roll or graphics every 6-10s")
    if info.get("variable_frame_rate"):
        add("vfr", "low", "Variable frame rate source (phone footage)", "render normalises to constant fps")
    if not tr.get("words") and info.get("has_audio"):
        add("no_transcript", "high", "No transcript: " + "; ".join(tr.get("errors", [])), "pass --transcript, install faster-whisper, or set ELEVENLABS_API_KEY")
    if face.get("available") and face.get("face_presence", 0) < 0.3:
        add("few_faces", "low", "Faces visible in under 30% of samples", "reframing falls back to centre; check contact sheet")
    return issues


def write_summary(a: dict, out: Path) -> None:
    i, au, ld = a["info"], a["audio"], a["loudness"]
    L = [f"# Analysis summary: {Path(i['path']).name}", "",
         f"- Duration {i['duration']:.1f}s, {i.get('width')}x{i.get('height')} @ {i.get('fps')} fps",
         f"- Shots: {len(a['scenes'])} (avg {i['duration'] / max(1, len(a['scenes'])):.1f}s)"]
    if au.get("present"):
        L.append(f"- Audio: noise {au['noise_floor_db']} dBFS, speech {au['speech_level_db']} dBFS, SNR {au['snr_db']} dB, "
                 f"loudness {ld.get('integrated_lufs')} LUFS, true peak {ld.get('true_peak_dbfs')} dBFS")
    f = a["faces"]
    if f.get("available") and f.get("median_center_x") is not None:
        L.append(f"- Faces: present {int(f['face_presence'] * 100)}% of samples, centre x={f['median_center_x']}, "
                 f"height {f['median_face_height']} of frame, multi-face {int(f['multi_face_ratio'] * 100)}%")
    s = a["derived"]["stats"]
    L.append(f"- Speech: {s['words']} words, {s['wpm']} wpm, {s['hard_fillers']} hard fillers, {s['pauses_over_0p7s']} pauses > 0.7s "
             f"(transcript: {a['transcript']['source']})")
    L += ["", "## Issues"] + ([f"- [{x['severity']}] {x['code']}: {x['message']} -> {x['suggested_fix']}" for x in a["issues"]] or ["- none"])
    L += ["", "## Sentences  (id [start-end] energy-vs-median wpm | text)",
          "_High positive energy + high quotability = hook candidates._", ""]
    for se in a["derived"]["sentences"]:
        e = se["energy_vs_median_db"]
        L.append(f"S{se['id']} [{se['start']:.2f}-{se['end']:.2f}] {'' if e is None else f'{e:+.1f}dB'} {se['wpm']}wpm | {se['text']}")
    L += ["", f"Contact sheet: {a.get('contact_sheet')}"]
    out.write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True, help="work directory")
    ap.add_argument("--transcript", help="existing transcript (our JSON, Whisper JSON, ElevenLabs JSON or SRT)")
    ap.add_argument("--asr", default="auto", choices=["auto", "whisper", "elevenlabs", "none"])
    ap.add_argument("--language")
    ap.add_argument("--max-frames", type=int, default=24)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    require_ffmpeg()

    t0 = time.time()
    video = str(Path(args.video).resolve())
    work = Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    fp = file_fingerprint(video)
    cache = work / ".cache" / fp
    cache.mkdir(parents=True, exist_ok=True)
    energy_path = cache / "energy_10ms.npy"
    info = probe(video)
    info["fingerprint"] = fp

    def cached(name, fn, *fa):
        f = cache / f"{name}.json"
        stale = (name == "transcript" and args.transcript) or (name == "audio" and not energy_path.exists())
        if f.exists() and not args.no_cache and not stale:
            return load_json(f)
        res = fn(*fa)
        save_json(res, f)
        return res

    with tempfile.TemporaryDirectory() as td, ThreadPoolExecutor(max_workers=5) as ex:
        tmp = Path(td)
        futs = {
            "audio": ex.submit(cached, "audio", audio_analysis, video, info, energy_path),
            "loudness": ex.submit(cached, "loudness", loudness, video, info),
            "scenes": ex.submit(cached, "scenes", scenes, video, info),
            "faces": ex.submit(cached, "faces", faces, video, info),
            "transcript": ex.submit(cached, "transcript", transcript, video, info, args, tmp),
        }
        res = {k: f.result() for k, f in futs.items()}

    frames = extract_frames(video, info, res["scenes"], work / "frames", args.max_frames)
    sheet = contact_sheet(frames, work / "contact_sheet.jpg")
    d = derive(res["transcript"], res["audio"])
    analysis = {"version": 1, "info": info, **res, "derived": d, "frames": frames, "contact_sheet": sheet,
                "energy_file": str(energy_path) if energy_path.exists() else None}
    analysis["issues"] = detect_issues(info, res["audio"], res["loudness"], res["scenes"], res["faces"], res["transcript"], d)
    analysis["elapsed_s"] = round(time.time() - t0, 1)
    save_json(analysis, work / "analysis.json")
    write_summary(analysis, work / "summary.md")
    print(f"analysis: {work / 'analysis.json'}\nsummary:  {work / 'summary.md'}\nsheet:    {sheet}\n"
          f"issues:   {', '.join(x['code'] for x in analysis['issues']) or 'none'}\n({analysis['elapsed_s']}s)")


if __name__ == "__main__":
    main()
