#!/usr/bin/env python3
"""Score a rendered video against objective editing standards (0-100).

Needs the render_report.json written next to the plan by render.py. Subjective checks
(hook strength, story, taste) are done by Claude with references/review-checklist.md;
this script covers everything a machine can measure reliably.

Usage: score.py WORK/render_report.json [--json OUT.json]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import adaptive_silences, contact_sheet, decode_audio  # noqa: E402
from captions import output_words  # noqa: E402
from common import PLATFORMS, Piece, ffmpeg, load_json, load_style, probe, save_json  # noqa: E402


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def overlap(a, b) -> float:
    """Intersection area / area of a. Boxes are [x, y, w, h]."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, a[2] * a[3])


def measure_output(path: str) -> dict:
    err = ffmpeg(["-i", path, "-af", "ebur128=peak=true", "-vf", "blackdetect=d=0.25:pix_th=0.08",
                  "-f", "null", "-"], check=False).stderr
    summ = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summ)
    tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ)
    _, _, _, _, runs = adaptive_silences(decode_audio(path), min_ms=250)
    sil = [r["dur"] for r in runs if 0.05 < r["start"] and r["end"] < probe(path)["duration"] - 0.4]  # ignore head/tail
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    return {"lufs": float(i.group(1)) if i else None, "true_peak": float(tp.group(1)) if tp else None,
            "longest_silence": max(sil) if sil else 0.0, "silences_over_1s": sum(s > 1.0 for s in sil), "black": blacks}


def review_sheet(rep: dict, out_dir: Path, n: int = 12) -> str | None:
    """Frames from the OUTPUT: hook, every graphic mid-animation, and even coverage of the rest."""
    from concurrent.futures import ThreadPoolExecutor
    dur = rep["duration"]
    times = {0.4, max(0.0, dur - 0.5)}
    times |= {min(dur - 0.1, g["start"] + 0.7) for g in rep.get("graphics", [])}
    k = 1
    while len(times) < n and k < n:
        times.add(round(dur * k / n, 2))
        k += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("out_*.jpg"):
        old.unlink()

    def grab(t):
        f = out_dir / f"out_{t:08.2f}.jpg"
        ffmpeg(["-ss", f"{t:.3f}", "-i", rep["output"], "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "4", str(f)], check=False)
        return {"t": t, "file": str(f)} if f.exists() else None

    with ThreadPoolExecutor(max_workers=6) as ex:
        frames = [f for f in ex.map(grab, sorted(times)) if f]
    return contact_sheet(frames, out_dir / "review_sheet.jpg", cols=4 if rep["height"] <= rep["width"] else 6)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--json")
    ap.add_argument("--no-sheet", action="store_true", help="skip the review contact sheet")
    args = ap.parse_args()

    rep = load_json(args.report)
    plan = load_json(rep["plan"])
    analysis = load_json(plan["analysis"]) if plan.get("analysis") and Path(plan["analysis"]).exists() else {}
    style = load_style(plan.get("style")) if plan.get("style") else load_style("clean")
    W, H = rep["width"], rep["height"]
    safe = PLATFORMS.get(plan.get("platform", "youtube"), PLATFORMS["youtube"])["safe"]
    pieces = [Piece(src=p["src"], a=p["in"], b=p["out"], out_start=p["out_start"]) for p in rep["pieces"]]
    words = analysis.get("transcript", {}).get("words", [])
    ow = output_words(words, pieces, plan["source"], drop_fillers=False)
    m = measure_output(rep["output"])
    info = probe(rep["output"])
    checks = []

    def add(name, score, weight, detail):
        checks.append({"check": name, "score": round(clamp01(score), 3), "weight": weight, "detail": detail})

    target = plan["output"].get("lufs", -14)
    if m["lufs"] is not None:
        add("loudness", 1 - max(0, abs(m["lufs"] - target) - 1) / 3, 3, f"{m['lufs']} LUFS (target {target})")
    if m["true_peak"] is not None:
        add("true_peak", 1.0 if m["true_peak"] <= -1.0 else (0.5 if m["true_peak"] <= 0 else 0), 2, f"{m['true_peak']} dBTP (max -1)")
    allowed = style["pacing"]["pause_after_sentence"] + 0.35
    if ow:  # speech gaps from the transcript: music/room tone can't hide dead air
        gaps = [b["start"] - a["end"] for a, b in zip(ow, ow[1:])]
        longest, over = max(gaps, default=0.0), sum(g > 1.0 for g in gaps)
        src = "speech gap"
    else:
        longest, over, src = m["longest_silence"], m["silences_over_1s"], "silence"
    add("dead_air", 1 - max(0, longest - allowed) / 1.5, 3, f"longest {src} {longest:.2f}s (allowed {allowed:.2f}s), {over} over 1s")

    if ow:
        first = ow[0]["start"]
        n3 = sum(w["start"] < 3 for w in ow)
        add("hook_speed", (1 - max(0, first - 0.3) / 2) * 0.5 + min(1, n3 / 6) * 0.5, 3,
            f"first word at {first:.2f}s, {n3} words in first 3s")
        cut_pts = [p.a for p in pieces] + [p.b for p in pieces]
        split = [(t, w["w"]) for t in cut_pts for w in words if w["start"] + 0.03 < t < w["end"] - 0.03]
        add("clean_cuts", 1 - 0.25 * len(split), 3, f"{len(split)} cuts inside words" + (f": {split[:3]}" if split else ""))
        hard = sum(re.sub(r"[^\w]", "", w["w"].lower()) in {"um", "uh", "erm", "uhm", "umm", "uhh"} for w in ow)
        add("fillers_removed", 1 - hard / max(1, len(ow)) * 20, 2, f"{hard} hard fillers left in {len(ow)} words")

    cap = plan.get("captions", {})
    if cap.get("enabled") and ow:
        lines = rep.get("captions", [])
        covered = sum(any(l["start"] - 0.05 <= w["start"] <= l["end"] for l in lines) for w in ow)
        add("caption_coverage", covered / len(ow), 2, f"{covered}/{len(ow)} spoken words captioned")
        box = rep.get("caption_box") or {}
        bottom_edge = (box.get("y", 0) + box.get("height", 0) / 2) / H
        add("caption_safe_zone", 1.0 if bottom_edge <= 1 - safe["bottom"] + 0.01 else 0.3, 2,
            f"caption bottom at {bottom_edge:.2f} of height (limit {1 - safe['bottom']:.2f})")

    gfx = rep.get("graphics", [])
    if gfx:
        fa = analysis.get("faces", {})
        if fa.get("median_center_x") is not None:
            fh = fa["median_face_height"]
            fw = fh * H / W * 0.8
            fbox = [(fa["median_center_x"] - fw / 2) * W, (fa["median_center_y"] - fh / 2) * H, fw * W, fh * H]
            worst = max(overlap(fbox, g["box"]) for g in gfx)
            add("graphics_clear_of_face", 1 - worst * 2, 2, f"max face coverage {worst:.0%}")
        box = rep.get("caption_box")
        if box:
            band = [0, box["y"] - box["height"] / 2, W, box["height"]]
            worst = max(overlap(band, g["box"]) for g in gfx)
            add("graphics_clear_of_captions", 1 - worst * 3, 2, f"max caption-band overlap {worst:.0%}")
        starts = sorted(g["start"] for g in gfx)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        min_gap = style["graphics"]["min_gap_s"]
        add("graphic_spacing", 1.0 if not gaps else clamp01(min(gaps) / min_gap), 1,
            f"min gap {min(gaps):.1f}s (style {min_gap}s)" if gaps else "single graphic")

    events = len(pieces) - 1 + len(plan.get("zooms", [])) + len(gfx) + len([b for b in plan.get("broll", []) if b.get("file")])
    every = rep["duration"] / max(1, events)
    tgt = style["pacing"]["target_cut_every_s"]
    ratio = every / tgt
    add("pacing", 1 - abs(1 - ratio) / 2 if ratio > 1 else 1 - (1 - ratio) / 3, 2,
        f"visual change every {every:.1f}s (style target {tgt}s)")

    black = sum(b - a for a, b in m["black"])
    add("no_black_frames", 1 - black / 1.0, 2, f"{black:.2f}s black")
    tgt_len = plan.get("brief", {}).get("target_seconds")
    if tgt_len:
        add("length", 1 - max(0, abs(rep["duration"] - tgt_len) / tgt_len - 0.1) * 3, 1, f"{rep['duration']:.1f}s vs target {tgt_len}s")
    add("av_duration", 1.0 if abs(info["duration"] - rep["duration"]) < 0.15 else 0.4, 1, f"file {info['duration']:.2f}s vs timeline {rep['duration']:.2f}s")

    total = sum(c["score"] * c["weight"] for c in checks) / sum(c["weight"] for c in checks) * 100
    result = {"score": round(total, 1), "output": rep["output"], "checks": checks, "measured": m}
    width = max(len(c["check"]) for c in checks)
    for c in checks:
        flag = "OK " if c["score"] >= 0.9 else ("~  " if c["score"] >= 0.6 else "FIX")
        print(f"{flag} {c['check']:<{width}}  {c['score']:.2f}  {c['detail']}")
    print(f"\nSCORE {total:.1f}/100")
    out = args.json or str(Path(args.report).with_name("score.json"))
    if not args.no_sheet:
        result["review_sheet"] = review_sheet(rep, Path(out).with_name("review"))
        print(f"review sheet: {result['review_sheet']}  (look at it: framing, graphics, captions, faces)")
    save_json(result, out)


if __name__ == "__main__":
    main()
