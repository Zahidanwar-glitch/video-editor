#!/usr/bin/env python3
"""Render an edit plan to a finished video.

Pipeline (each stage cached, so re-renders only redo what changed):
  1. pieces   kept source ranges -> cuts snapped to quiet audio + frame grid -> reframed,
              zoomed clips rendered in parallel
  2. concat   join pieces (lossless)
  3. audio    speech enhancement, voiceover, music ducking, SFX, two-pass loudness
  4. picture  colour, B-roll, animated graphics, captions, fades -> final encode
  5. report   render_report.json (timeline map, overlay boxes) for score.py

Usage:
  render.py WORK/edit_plan.json -o OUT.mp4 [--proxy] [--jobs N] [--hw]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio as A  # noqa: E402
from captions import build_ass  # noqa: E402
from common import (PLATFORMS, Piece, build_pieces, ffmpeg, load_json, map_time, probe, require_ffmpeg,  # noqa: E402
                    run, save_json, total_duration)
from graphics import render_graphic  # noqa: E402
from validate_plan import validate  # noqa: E402

SR = 48000


def h(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:14]


def esc_path(p: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


# ------------------------------------------------------------ cut refinement

def snap_pieces(pieces: list[Piece], analysis: dict | None, fps: float, window: float = 0.05) -> list[Piece]:
    """Move each cut point to the quietest 10 ms within +-window (never into a word), then onto the frame grid."""
    db = None
    words = []
    if analysis:
        ef = analysis.get("energy_file")
        if ef and Path(ef).exists():
            db = np.load(ef).astype(np.float32)
        words = analysis.get("transcript", {}).get("words", [])
    src0 = analysis["info"]["path"] if analysis else None

    def inside_word(t):
        return any(w["start"] + 0.02 < t < w["end"] - 0.02 for w in words)

    def snap(t, src):
        if db is not None and src == src0:
            i0, i1 = max(0, int((t - window) * 100)), min(len(db) - 1, int((t + window) * 100))
            if i1 > i0:
                cands = sorted(range(i0, i1 + 1), key=lambda i: (float(db[i]), abs(i / 100 - t)))
                for i in cands[:6]:
                    if not inside_word(i / 100):
                        t = i / 100
                        break
        return round(round(t * fps) / fps, 4)

    out, cursor = [], 0.0
    for p in pieces:
        a, b = snap(p.a, p.src), snap(p.b, p.src)
        if b - a < 1.5 / fps:
            continue
        out.append(Piece(src=p.src, a=a, b=b, out_start=cursor, segment_index=p.segment_index, reframe_x=p.reframe_x))
        cursor += b - a
    return out


# ------------------------------------------------------------ per-piece video

def face_center(analysis: dict | None, a: float, b: float) -> tuple[float | None, float | None]:
    if not analysis or not analysis.get("faces", {}).get("available"):
        return None, None
    f = analysis["faces"]
    xs = [s["boxes"][0][0] + s["boxes"][0][2] / 2 for s in f.get("samples", []) if s["boxes"] and a - 0.5 <= s["t"] <= b + 0.5]
    ys = [s["boxes"][0][1] + s["boxes"][0][3] / 2 for s in f.get("samples", []) if s["boxes"] and a - 0.5 <= s["t"] <= b + 0.5]
    if xs:
        return float(np.median(xs)), float(np.median(ys))
    return f.get("median_center_x"), f.get("median_center_y")


def zoom_expr(p: Piece, zooms: list[dict]) -> str | None:
    terms = []
    for z in zooms:
        s, e = max(z["at"], p.a) - p.a, min(z["at"] + z["dur"], p.b) - p.a
        if e <= s:
            continue
        k = z["scale"] - 1
        if z.get("ease", "punch") == "punch":
            terms.append(f"{k:.4f}*between(it,{s:.3f},{e:.3f})")
        else:
            r = min(0.45, (e - s) / 2)
            # smoothstep ramp in and out
            up = f"clip((it-{s:.3f})/{r:.3f},0,1)"
            dn = f"clip(({e:.3f}-it)/{r:.3f},0,1)"
            terms.append(f"{k:.4f}*({up}*{up}*(3-2*{up}))*({dn}*{dn}*(3-2*{dn}))")
    return "1+" + "+".join(terms) if terms else None


def piece_filters(p: Piece, info: dict, W: int, H: int, fps: float, zooms: list[dict], analysis: dict | None) -> str:
    sw, sh = info["width"], info["height"]
    target = W / H
    fx, fy = face_center(analysis, p.a, p.b) if p.src == (analysis or {}).get("info", {}).get("path") else (None, None)
    cx = p.reframe_x if p.reframe_x is not None else (fx if fx is not None else 0.5)
    chain = [f"fps={fps}", "setpts=PTS-STARTPTS"]
    src_aspect = sw / sh
    if abs(src_aspect - target) < 0.01:
        cw, ch = sw, sh
    elif src_aspect > target:  # crop sides (e.g. 16:9 -> 9:16), follow the face
        cw, ch = int(sh * target) // 2 * 2, sh
        x = min(max(0, int(cx * sw - cw / 2)), sw - cw)
        chain.append(f"crop={cw}:{ch}:{x}:0")
    else:  # taller source into wider frame: blurred background fill
        z = zoom_expr(p, zooms)
        fg = f"scale=-2:{H}"
        return (f"fps={fps},setpts=PTS-STARTPTS,split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=20:2,eq=brightness=-0.08[bgb];[fg]{fg}[fgs];[bgb][fgs]overlay=(W-w)/2:0"
                + (f",zoompan=z='{z}':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={W}x{H}:fps={fps}" if z else "")
                + ",setsar=1,format=yuv420p")
    z = zoom_expr(p, zooms)
    if z:
        zx = f"{cx if src_aspect <= target + 0.01 else 0.5:.4f}"
        zy = f"{(fy - 0.06) if fy is not None else 0.45:.4f}"  # keep eyes high in frame
        chain.append(f"zoompan=z='{z}':d=1:x='min(max(0,iw*{zx}-iw/zoom/2),iw-iw/zoom)':"
                     f"y='min(max(0,ih*{zy}-ih/zoom/2),ih-ih/zoom)':s={W}x{H}:fps={fps}")
    else:
        chain.append(f"scale={W}:{H}:flags=lanczos")
    chain += ["setsar=1", "format=yuv420p"]
    return ",".join(chain)


def render_piece(args) -> Path:
    p, info, W, H, fps, zooms, analysis, cache, enc = args
    vf = piece_filters(p, info, W, H, fps, zooms, analysis)
    key = h([p.src, os.path.getmtime(p.src), p.a, p.b, vf, enc])
    out = cache / f"piece_{key}.mkv"
    if out.exists():
        return out
    tmp = out.with_suffix(".tmp.mkv")
    inputs = ["-ss", f"{p.a:.4f}", "-t", f"{p.dur:.4f}", "-i", p.src]
    if not info.get("has_audio"):
        inputs += ["-f", "lavfi", "-t", f"{p.dur:.4f}", "-i", f"anullsrc=r={SR}:cl=stereo"]
    fade = min(0.008, p.dur / 4)
    af = f"aresample={SR},aformat=channel_layouts=stereo,afade=t=in:d={fade},afade=t=out:st={max(0, p.dur - fade):.4f}:d={fade},apad,atrim=0:{p.dur:.4f}"
    ffmpeg([*inputs, "-filter_complex", f"[0:v]{vf}[v];[{1 if not info.get('has_audio') else 0}:a]{af}[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{p.dur:.4f}", *enc, "-c:a", "pcm_s16le", str(tmp)])
    tmp.rename(out)
    return out


# ------------------------------------------------------------ audio pass

def render_audio(plan, pieces, base: Path, total: float, work: Path, report: dict) -> Path:
    au = plan.get("audio", {})
    src0 = plan["source"]
    inputs = ["-i", str(base)]
    graph = []
    idx = 1
    speech = "[0:a]"
    ench = A.enhance_filter(au.get("enhance_speech", "light"))
    if ench:
        graph.append(f"{speech}{ench}[sp0]")
        speech = "[sp0]"
    vo = au.get("voiceover")
    if vo:
        inputs += ["-i", vo["file"]]
        vol = vo.get("volume_db", 0)
        if vo.get("mode", "replace") == "replace":
            graph.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,volume={vol}dB,apad,atrim=0:{total:.3f}[sp1]")
        else:
            graph.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,volume={vol}dB,apad,atrim=0:{total:.3f}[vo];"
                         f"{speech}[vo]amix=inputs=2:normalize=0[sp1]")
        speech = "[sp1]"
        idx += 1
    mix = [speech]
    music = au.get("music")
    if music:
        inputs += ["-stream_loop", "-1", "-ss", f"{music.get('start_in', 0)}", "-i", music["file"]]
        fi, fo = music.get("fade_in", 0.5), music.get("fade_out", 1.5)
        graph.append(f"{speech}asplit=2[spm][sc]")
        mix = ["[spm]"]
        graph.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                     f"volume={music.get('volume_db', -20)}dB,afade=t=in:d={fi},afade=t=out:st={max(0, total - fo):.3f}:d={fo}[mus]")
        duck = abs(music.get("duck_db", -14))
        ratio = min(20, max(2, 10 ** (duck / 20)))
        graph.append(f"[mus][sc]sidechaincompress=threshold=0.02:ratio={ratio:.1f}:attack=25:release=350:makeup=1[musd]")
        mix.append("[musd]")
        idx += 1
    sfx_used = []
    for k, s in enumerate(au.get("sfx", [])):
        t = map_time(pieces, s.get("src", src0), s["at"])
        if t is None:
            continue
        f = s.get("file") or str(A.sfx_file(s.get("type", "pop")))
        inputs += ["-i", f]
        lead = 0.12 if s.get("type") in ("whoosh", "riser") else 0.0  # whoosh peaks slightly after start
        d = max(0, int((t - lead) * 1000))
        graph.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,volume={s.get('volume_db', -8)}dB,adelay={d}|{d}[sfx{k}]")
        mix.append(f"[sfx{k}]")
        sfx_used.append({"at_out": round(t, 3), "file": f})
        idx += 1
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first[pre]")
    else:
        graph.append(f"{mix[0]}anull[pre]")
    graph.append(f"[pre]atrim=0:{total:.3f},alimiter=limit=0.95:level=false[out]")
    pre = work / "audio_pre.wav"
    ffmpeg([*inputs, "-filter_complex", ";".join(graph), "-map", "[out]", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", str(pre)])
    target = plan["output"].get("lufs", -14)
    meas = A.measure_loudness(pre, target)
    final = work / "audio_final.wav"
    ffmpeg(["-i", str(pre), "-af", A.loudnorm_filter(meas, target) + f",aresample={SR}", "-ar", str(SR), "-c:a", "pcm_s24le", str(final)])
    report["audio"] = {"input_lufs": meas.get("input_i"), "target_lufs": target, "enhance": au.get("enhance_speech", "light"),
                       "music": bool(music), "voiceover": bool(vo), "sfx": sfx_used}
    return final


# ------------------------------------------------------------ picture pass

def color_filters(c: dict) -> list[str]:
    f = []
    if c.get("lut"):
        f.append(f"lut3d=file='{esc_path(c['lut'])}'")
    eq = {k: c[k] for k in ("contrast", "saturation", "brightness", "gamma") if k in c}
    if eq:
        f.append("eq=" + ":".join(f"{k}={v}" for k, v in eq.items()))
    w = c.get("warmth", 0)
    if w:
        # chroma shift in YUV: warmer = less blue (U), more red (V). ~6x faster than colorbalance (RGB).
        f.append(f"lutyuv=u='clip(val-{18 * w:.2f},0,255)':v='clip(val+{14 * w:.2f},0,255)'")
    if c.get("vignette"):
        f.append("vignette=PI/5")
    return f


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--proxy", action="store_true", help="fast half-resolution preview")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--hw", action="store_true", help="use NVENC/VideoToolbox if available")
    args = ap.parse_args()
    require_ffmpeg()
    t0 = time.time()
    timings = {}

    plan = load_json(args.plan)
    errors, warnings = validate(plan)
    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        raise SystemExit("plan invalid: fix the errors above (validate_plan.py) and re-run")

    out = Path(args.out).resolve()
    work = Path(args.plan).resolve().parent
    cache = work / ".render_cache"
    cache.mkdir(parents=True, exist_ok=True)
    analysis = load_json(plan["analysis"]) if plan.get("analysis") and Path(plan["analysis"]).exists() else None

    W, H = plan["output"]["width"], plan["output"]["height"]
    fps = float(plan["output"].get("fps", 30))
    if args.proxy:
        W, H = W // 4 * 2, H // 4 * 2
        fps = min(fps, 30)
        plan = json.loads(json.dumps(plan))
        plan["output"].update({"width": W, "height": H})

    hw = []
    if args.hw:
        encs = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
        hw = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19"] if "h264_nvenc" in encs else (
            ["-c:v", "h264_videotoolbox", "-q:v", "65"] if "h264_videotoolbox" in encs else [])
    piece_enc = hw or ["-c:v", "libx264", "-preset", "ultrafast" if args.proxy else "fast", "-crf", "28" if args.proxy else "14", "-g", str(int(fps))]

    # 1. pieces
    ts = time.time()
    infos = {}
    pieces = snap_pieces(build_pieces(plan), analysis, fps)
    for p in pieces:
        if p.src not in infos:
            infos[p.src] = probe(p.src)
    zooms = plan.get("zooms", [])
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        files = list(ex.map(render_piece, [(p, infos[p.src], W, H, fps, [z for z in zooms if z.get("src", plan["source"]) == p.src],
                                            analysis, cache, piece_enc) for p in pieces]))
    timings["pieces"] = round(time.time() - ts, 2)

    # 2. concat
    ts = time.time()
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{f.resolve()}'\n" for f in files))
    base = work / "base.mkv"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
    total = total_duration(pieces)
    timings["concat"] = round(time.time() - ts, 2)

    report = {"plan": str(Path(args.plan).resolve()), "output": str(out), "proxy": args.proxy, "width": W, "height": H, "fps": fps,
              "duration": round(total, 3), "warnings": warnings,
              "pieces": [{"src": p.src, "in": p.a, "out": p.b, "out_start": round(p.out_start, 3)} for p in pieces]}

    # 3. audio
    ts = time.time()
    final_audio = render_audio(plan, pieces, base, total, work, report)
    timings["audio"] = round(time.time() - ts, 2)

    # 4. picture
    ts = time.time()
    src0 = plan["source"]
    safe = PLATFORMS.get(plan.get("platform", "youtube"), PLATFORMS["youtube"])["safe"]
    fa = (analysis or {}).get("faces", {})
    face = {"cx": fa.get("median_center_x"), "cy": fa.get("median_center_y"), "h": fa.get("median_face_height")} if fa.get("median_center_x") is not None else None
    inputs = ["-i", str(base), "-i", str(final_audio)]
    vchain = [f"[0:v]{','.join(color_filters(plan.get('color', {})) or ['null'])}[v0]"]
    cur, idx = "[v0]", 2

    for k, b in enumerate(plan.get("broll", [])):
        if not b.get("file"):
            continue
        t = map_time(pieces, src0, b["at"])
        if t is None:
            continue
        d = min(b["dur"], total - t)
        is_img = Path(b["file"]).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        inputs += (["-loop", "1", "-t", f"{d:.3f}", "-i", b["file"]] if is_img else ["-ss", f"{b.get('file_in', 0)}", "-t", f"{d:.3f}", "-i", b["file"]])
        kb = f",zoompan=z='1+0.06*on/{int(d * fps)}':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={W}x{H}:fps={fps}" if is_img else ""
        vchain.append(f"[{idx}:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}{kb},setsar=1,"
                      f"format=yuva420p,fade=t=in:d=0.12:alpha=1,fade=t=out:st={max(0, d - 0.12):.3f}:d=0.12:alpha=1,"
                      f"setpts=PTS-STARTPTS+{t:.3f}/TB[b{k}]")
        vchain.append(f"{cur}[b{k}]overlay=eof_action=pass:enable='between(t,{t:.3f},{t + d:.3f})'[v{idx}]")
        cur = f"[v{idx}]"
        idx += 1

    cap_y = plan.get("captions", {}).get("position_y") if plan.get("captions", {}).get("enabled") else None
    gfx_report = []
    accent_default = "#FFD400"
    for k, g in enumerate(plan.get("graphics", [])):
        t = map_time(pieces, src0, g["at"])
        if t is None:
            continue
        te = map_time(pieces, src0, g["at"] + g["dur"], snap_forward=False)
        d = (te - t) if te and te > t + 0.3 else g["dur"]
        d = min(d, total - t)
        offs = []
        for it in g.get("item_times", []):
            m = map_time(pieces, src0, it)
            offs.append(max(0.0, (m - t)) if m is not None else 0.0)
        gdir = cache / f"gfx_{h([g, W, H, fps, round(d, 3), offs, face, cap_y])}"
        accent = g.get("accent", accent_default)
        if (gdir / "meta.json").exists():
            meta = load_json(gdir / "meta.json")
        else:
            meta = render_graphic(g, W, H, fps, d, offs, gdir, accent, safe, face, cap_y)
            save_json(meta, gdir / "meta.json")
        inputs += ["-framerate", str(fps), "-i", meta["pattern"]]
        vchain.append(f"[{idx}:v]format=rgba,setpts=PTS-STARTPTS+{t:.3f}/TB[g{k}]")
        vchain.append(f"{cur}[g{k}]overlay=x={meta['x']}:y={meta['y']}:eof_action=pass:format=auto[v{idx}]")
        cur = f"[v{idx}]"
        gfx_report.append({"type": g["type"], "start": round(t, 3), "end": round(t + d, 3),
                           "box": [meta["x"], meta["y"], meta["w"], meta["h"]]})
        idx += 1

    words = (analysis or {}).get("transcript", {}).get("words", [])
    ass, cap_meta = build_ass(plan, pieces, words, work / "captions.ass")
    if ass:
        fontsdir = Path(cap_meta["font_file"]).parent if cap_meta.get("font_file") else None
        opt = f":fontsdir='{esc_path(fontsdir)}'" if fontsdir else ""
        vchain.append(f"{cur}ass='{esc_path(ass)}'{opt}[vc]")
        cur = "[vc]"
    fin = plan["output"].get("fade_in", 0)
    fout = plan["output"].get("fade_out", 0)
    tail = []
    if fin:
        tail.append(f"fade=t=in:d={fin}")
    if fout:
        tail.append(f"fade=t=out:st={max(0, total - fout):.3f}:d={fout}")
    vchain.append(f"{cur}{','.join(tail + ['format=yuv420p'])}[vout]")
    afade = f"afade=t=out:st={max(0, total - fout):.3f}:d={fout}" if fout else "anull"

    final_enc = hw or ["-c:v", "libx264", "-preset", "ultrafast" if args.proxy else plan["output"].get("preset", "medium"),
                       "-crf", "30" if args.proxy else str(plan["output"].get("crf", 18))]
    out.parent.mkdir(parents=True, exist_ok=True)
    script = work / "filtergraph.txt"
    script.write_text(";".join(vchain) + f";[1:a]{afade}[aout]")
    ffmpeg([*inputs, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]", *final_enc,
            "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{total:.3f}", str(out)])
    timings["picture"] = round(time.time() - ts, 2)
    timings["total"] = round(time.time() - t0, 2)

    report.update({"graphics": gfx_report, "captions": cap_meta.get("lines", []), "caption_box": cap_meta.get("box"),
                   "timings_s": timings})
    save_json(report, work / ("render_report.proxy.json" if args.proxy else "render_report.json"))
    for tmp in (base, lst):
        tmp.unlink(missing_ok=True)
    print(f"rendered {out} ({total:.1f}s, {W}x{H}) in {timings['total']}s  [{', '.join(f'{k} {v}s' for k, v in timings.items() if k != 'total')}]")


if __name__ == "__main__":
    main()
