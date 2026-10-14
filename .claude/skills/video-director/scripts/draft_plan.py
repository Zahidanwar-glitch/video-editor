#!/usr/bin/env python3
"""Build a first-draft edit plan from analysis.json using the style's mechanical rules.

It handles the rule-based work (filler/pause cuts, captions, zoom rhythm, output format,
audio fixes) so Claude can spend its judgment on story: which sentences to keep, the
hook, graphics, B-roll and music. Claude then edits the resulting plan.

Usage:
  draft_plan.py WORK/analysis.json -o WORK/edit_plan.json --style bold_shorts [--platform shorts]
                [--keep S2-S5,S7] [--hook S6] [--hook-mode move|tease] [--auto-graphics]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PLATFORMS, load_json, load_style, save_json  # noqa: E402

NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]


def parse_ids(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    ids: list[int] = []
    for part in spec.replace(" ", "").split(","):
        m = re.fullmatch(r"S?(\d+)(?:-S?(\d+))?", part, re.I)
        if not m:
            raise SystemExit(f"bad sentence spec '{part}' (use e.g. S2-S5,S7)")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        ids += [i for i in range(a, b + 1) if i < n and i not in ids]
    return ids


def group_runs(ids: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for i in ids:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def segment_for(run: list[int], sents: list[dict], words: list[dict], pacing: dict, dur: float) -> dict:
    first, last = sents[run[0]], sents[run[-1]]
    w0 = first["first_word"]
    # skip leading hard fillers ("Um, last year...") so the segment starts on a real word
    while w0 < last["last_word"] and words[w0]["filler"] == "hard":
        w0 += 1
    start = words[w0]["start"]
    end = last["end"]
    prev_end = words[w0 - 1]["end"] if w0 > 0 else 0.0
    nxt = words[last["last_word"] + 1]["start"] if last["last_word"] + 1 < len(words) else dur
    a = max(prev_end + 0.02, start - pacing.get("lead_pad", 0.08), 0.0)
    b = min(nxt - 0.02, end + pacing.get("tail_pad", 0.2), dur)
    return {"in": round(a, 3), "out": round(b, 3), "role": "body", "note": f"S{run[0]}-S{run[-1]}" if len(run) > 1 else f"S{run[0]}"}


def filler_and_pause_cuts(words: list[dict], pauses: list[dict], pacing: dict) -> list[dict]:
    cuts = []
    if pacing.get("cut_hard_fillers", True):
        for k, w in enumerate(words):
            if w["filler"] != "hard":
                continue
            p = words[k - 1] if k > 0 else None
            n = words[k + 1] if k + 1 < len(words) else None
            a = (p["end"] + 0.06) if p else w["start"] - 0.05
            b = (n["start"] - 0.06) if n else w["end"] + 0.05
            a, b = min(a, w["start"] - 0.01), max(b, w["end"] + 0.01)
            cuts.append({"start": round(a, 3), "end": round(b, 3), "reason": f"filler '{w['w']}'"})
    for p in pauses:
        keep = pacing["pause_after_sentence"] if p["after_sentence_end"] else pacing["max_pause"]
        if p["dur"] > keep + 0.08:
            a = p["start"] + keep * 0.55  # keep a little more tail than lead: sounds natural
            b = p["end"] - keep * 0.45
            cuts.append({"start": round(a, 3), "end": round(b, 3), "reason": f"pause {p['dur']:.2f}s -> {keep:.2f}s"})
    return merge_cuts(cuts)


def merge_cuts(cuts: list[dict]) -> list[dict]:
    out: list[dict] = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1]["end"] + 0.01:
            out[-1]["end"] = max(out[-1]["end"], c["end"])
            out[-1]["reason"] += " + " + c["reason"]
        else:
            out.append(dict(c))
    return out


def kept_duration(segments: list[dict], cuts: list[dict]) -> float:
    tot = 0.0
    for s in segments:
        tot += s["out"] - s["in"]
        for c in cuts:
            tot -= max(0.0, min(s["out"], c["end"]) - max(s["in"], c["start"]))
    return tot


def zoom_rhythm(segments: list[dict], sents: list[dict], z: dict) -> list[dict]:
    """Punch-ins at sentence starts, roughly every z['every_s'] seconds of kept speech."""
    zooms, since, on = [], 1e9, False
    for seg in segments:
        inside = [s for s in sents if s["start"] >= seg["in"] - 0.01 and s["end"] <= seg["out"] + 0.01]
        for s in inside:
            if since >= z["every_s"]:
                on = (not on) if z.get("alternate") else True
                if on:
                    dur = s["end"] - s["start"] + 0.1 if z["ease"] == "punch" else min(4.0, s["end"] - s["start"])
                    zooms.append({"at": round(s["start"], 3), "dur": round(dur, 3), "scale": z["scale"], "ease": z["ease"],
                                  "reason": f"rhythm S{s['id']}"})
                since = 0.0
            since += s["end"] - s["start"]
    return zooms


def short_label(words: list[dict], s: dict, limit: int = 32) -> str:
    """Sentence text without fillers, cut at a word boundary. Claude should rewrite it."""
    out = ""
    for w in words[s["first_word"]:s["last_word"] + 1]:
        if w["filler"] == "hard":
            continue
        nxt = (out + " " + w["w"]).strip()
        if len(nxt) > limit:
            break
        out = nxt
    return out.rstrip(".,!?")


def graphic_suggestions(words: list[dict], sents: list[dict], accent: str) -> list[dict]:
    sugg = []
    for s in sents:
        for w in words[s["first_word"]:s["last_word"] + 1]:
            m = re.fullmatch(r"\$?(\d[\d,]*\.?\d*)(%|x|k|m|b)?[.,!?]?", w["w"], re.I)
            if m and (m.group(2) or w["w"].startswith("$") or float(m.group(1).replace(",", "")) >= 10):
                val = float(m.group(1).replace(",", ""))
                suffix = m.group(2) or ""
                sugg.append({"type": "counter", "at": w["start"], "dur": 2.5, "value": val, "prefix": "$" if w["w"].startswith("$") else "",
                             "suffix": suffix.upper() if suffix.lower() in "kmb" else suffix, "label": short_label(words, s),
                             "accent": accent, "reason": f"number spoken in S{s['id']}"})
        m = re.search(r"\b(two|three|four|five|six|seven|\d)\s+(lessons|reasons|ways|tips|steps|things|mistakes|rules)\b", s["text"], re.I)
        if m:
            n = NUM_WORDS.get(m.group(1).lower()) or int(m.group(1))
            items, times, end = [], [], s["end"]
            for later in sents[s["id"] + 1:s["id"] + 1 + n * 2]:
                first = later["text"].split()[0].strip(",.").lower()
                if first in ORDINALS[:n]:
                    items.append(re.sub(r"^\w+,?\s*", "", later["text"]).rstrip(".!"))
                    times.append(later["start"])
                    end = later["end"]
            if items:
                sugg.append({"type": "list", "at": s["start"], "dur": round(end - s["start"] + 1.0, 2),
                             "title": f"{m.group(1).title()} {m.group(2).lower()}", "items": items, "item_times": times,
                             "accent": accent, "reason": f"list announced in S{s['id']}"})
    return sugg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("analysis")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--style", default="clean")
    ap.add_argument("--platform")
    ap.add_argument("--keep", help="sentences to keep, e.g. S0-S5,S7 (default: all)")
    ap.add_argument("--hook", help="sentence to open with, e.g. S6")
    ap.add_argument("--hook-mode", choices=["move", "tease"], default="move")
    ap.add_argument("--auto-graphics", action="store_true", help="insert graphic suggestions directly (spaced by style)")
    args = ap.parse_args()

    an = load_json(args.analysis)
    style = load_style(args.style)
    platform = args.platform or style.get("platform", "youtube")
    pf = PLATFORMS[platform]
    words = an["transcript"].get("words", [])
    for k, w in enumerate(words):  # analysis.derive() already annotated; keep robust for hand-made files
        w.setdefault("id", k)
        w.setdefault("filler", None)
    sents = an["derived"]["sentences"]
    dur = an["info"]["duration"]
    pacing = style["pacing"]

    notes = []
    if not sents:
        segments = [{"in": 0.0, "out": round(dur, 3), "role": "body", "note": "no transcript: whole clip"}]
        cuts: list[dict] = []
        notes.append("No transcript: only format/audio/colour applied. Get a transcript for real editing.")
    else:
        keep = parse_ids(args.keep, len(sents))
        hook = parse_ids(args.hook, len(sents))[0] if args.hook else None
        body = [i for i in keep if not (hook is not None and i == hook and args.hook_mode == "move")]
        segments = []
        if hook is not None:
            seg = segment_for([hook], sents, words, pacing, dur)
            seg["role"] = "hook"
            segments.append(seg)
        for run in group_runs(body):
            segments.append(segment_for(run, sents, words, pacing, dur))
        if hook is not None and args.hook_mode == "tease":
            notes.append(f"Hook S{hook} teased at the start and kept in place.")
        cuts = filler_and_pause_cuts(words, an["derived"]["pauses"], pacing)
        cuts = [c for c in cuts if any(s["in"] < c["end"] and c["start"] < s["out"] for s in segments)]

    z = style["zoom"]
    plan = {
        "version": 1,
        "source": an["info"]["path"],
        "analysis": str(Path(args.analysis).resolve()),
        "platform": platform,
        "style": style["name"],
        "brief": {"message": "", "audience": "", "arc": "", "hook": "", "cta": ""},
        "output": {"width": pf["width"], "height": pf["height"], "fps": min(60, round(an["info"].get("fps") or 30)),
                   "lufs": style["audio"].get("lufs", pf["lufs"]), "fade_in": 0.0, "fade_out": 0.3},
        "segments": segments,
        "cuts_removed": cuts,
        "zooms": zoom_rhythm(segments, sents, z) if sents else [],
        "broll": [],
        "graphics": [],
        "captions": dict(style["captions"]) if words else {"enabled": False},
        "audio": {
            "enhance_speech": next((("strong" if i["severity"] == "high" else True) for i in an["issues"] if i["code"] in ("noisy_audio", "clipping")), "light"),
            "voiceover": None,
            "music": None,
            "sfx": [],
        },
        "color": dict(style.get("color", {})),
        "notes": notes,
        "suggestions": graphic_suggestions(words, sents, style["graphics"]["accent"]) if sents else [],
    }
    if args.auto_graphics:
        last = -1e9
        for g in plan["suggestions"]:
            if g["at"] - last >= style["graphics"]["min_gap_s"] and any(s["in"] <= g["at"] <= s["out"] for s in segments):
                plan["graphics"].append(g)
                if style["graphics"].get("sfx"):
                    plan["audio"]["sfx"].append({"at": g["at"], "type": style["graphics"]["sfx"], "volume_db": -10})
                last = g["at"]
        plan["suggestions"] = [g for g in plan["suggestions"] if g not in plan["graphics"]]

    est = kept_duration(segments, cuts)
    plan["notes"].append(f"Estimated output length {est:.1f}s from {dur:.1f}s source ({len(cuts)} internal cuts).")
    save_json(plan, args.out)
    print(f"plan: {args.out}\nsegments {len(segments)}, cuts {len(cuts)}, zooms {len(plan['zooms'])}, graphics {len(plan['graphics'])}, "
          f"suggestions {len(plan['suggestions'])}\nestimated length {est:.1f}s")


if __name__ == "__main__":
    main()
