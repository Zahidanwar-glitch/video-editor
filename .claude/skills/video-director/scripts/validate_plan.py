#!/usr/bin/env python3
"""Validate an edit plan: schema, files, timing, and editorial rules. Exit 1 on errors.

Usage: validate_plan.py WORK/edit_plan.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SKILL_DIR, build_pieces, load_json, map_time, probe, total_duration  # noqa: E402


def validate(plan: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        import jsonschema  # type: ignore
        schema = load_json(SKILL_DIR / "schemas" / "edit_plan.schema.json")
        for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(plan), key=lambda e: list(e.path)):
            errors.append(f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")
    except ImportError:
        warnings.append("jsonschema not installed: schema check skipped (pip install jsonschema)")
    if errors:
        return errors, warnings

    def need_file(path, what):
        if path and not Path(path).exists():
            errors.append(f"{what}: file not found: {path}")

    need_file(plan["source"], "source")
    durations = {}
    for seg in plan["segments"]:
        src = seg.get("src", plan["source"])
        need_file(src, "segment")
        if Path(src).exists() and src not in durations:
            durations[src] = probe(src)["duration"]
    for i, seg in enumerate(plan["segments"]):
        src = seg.get("src", plan["source"])
        if seg["out"] <= seg["in"]:
            errors.append(f"segments[{i}]: out ({seg['out']}) must be after in ({seg['in']})")
        if src in durations and seg["out"] > durations[src] + 0.05:
            errors.append(f"segments[{i}]: out {seg['out']} beyond source duration {durations[src]:.2f}")
    for b in plan.get("broll", []):
        if b.get("file"):
            need_file(b["file"], "broll")
        else:
            warnings.append(f"broll at {b['at']}: no file (query '{b.get('query', '')}') -> skipped. Add a licensed clip path.")
    au = plan.get("audio", {})
    if au.get("music"):
        need_file(au["music"].get("file"), "music")
    if au.get("voiceover"):
        need_file(au["voiceover"].get("file"), "voiceover")
    for s in au.get("sfx", []):
        need_file(s.get("file"), "sfx")
        if not s.get("file") and not s.get("type"):
            errors.append(f"sfx at {s['at']}: needs 'type' or 'file'")
    need_file(plan.get("color", {}).get("lut"), "lut")
    if errors:
        return errors, warnings

    pieces = build_pieces(plan)
    if not pieces:
        return ["all segments were removed by cuts"], warnings
    total = total_duration(pieces)
    src0 = plan["source"]

    for i, g in enumerate(plan.get("graphics", [])):
        if map_time(pieces, src0, g["at"]) is None:
            errors.append(f"graphics[{i}] ({g['type']}) at {g['at']}: that moment is not in the edit")
        if g["type"] == "list" and not g.get("items"):
            errors.append(f"graphics[{i}]: list needs items")
        if g["type"] == "bar" and not g.get("bars"):
            errors.append(f"graphics[{i}]: bar needs bars")
        if g["type"] == "counter" and "value" not in g:
            errors.append(f"graphics[{i}]: counter needs value")
        if g["type"] == "quote" and not g.get("text"):
            errors.append(f"graphics[{i}]: quote needs text")
    for i, z in enumerate(plan.get("zooms", [])):
        if map_time(pieces, z.get("src", src0), z["at"]) is None:
            warnings.append(f"zooms[{i}] at {z['at']}: not in the edit (ignored)")

    # editorial checks
    gt = sorted(t for t in (map_time(pieces, src0, g["at"]) for g in plan.get("graphics", [])) if t is not None)
    for a, b in zip(gt, gt[1:]):
        if b - a < 4:
            warnings.append(f"graphics {a:.1f}s and {b:.1f}s (output time) are {b - a:.1f}s apart: cluttered (aim for >= 6-15s by style)")
    an_path = plan.get("analysis")
    if an_path and Path(an_path).exists():
        an = load_json(an_path)
        words = an["transcript"].get("words", [])
        cut_points = [(c["start"], "cut start") for c in plan.get("cuts_removed", []) if c.get("src", src0) == src0]
        cut_points += [(c["end"], "cut end") for c in plan.get("cuts_removed", []) if c.get("src", src0) == src0]
        cut_points += [(s["in"], "segment in") for s in plan["segments"] if s.get("src", src0) == src0]
        cut_points += [(s["out"], "segment out") for s in plan["segments"] if s.get("src", src0) == src0]
        for t, kind in cut_points:
            for w in words:
                if w["start"] + 0.03 < t < w["end"] - 0.03:
                    warnings.append(f"{kind} at {t:.2f}s splits the word '{w['w']}' ({w['start']:.2f}-{w['end']:.2f})")
                    break
        first3 = [w for w in words if (mt := map_time(pieces, src0, w["start"], snap_forward=False)) is not None and mt < 3]
        if words and len(first3) < 3:
            warnings.append("hook check: fewer than 3 words in the first 3 output seconds (slow open)")
    target = plan.get("brief", {}).get("target_seconds")
    if target and abs(total - target) > 0.15 * target:
        warnings.append(f"length {total:.1f}s vs brief target {target}s")
    if not plan.get("brief", {}).get("message"):
        warnings.append("brief.message is empty: write the one-sentence message before cutting")
    return errors, warnings


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    plan = load_json(sys.argv[1])
    errors, warnings = validate(plan)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if not errors:
        pieces = build_pieces(plan)
        print(f"OK: {len(pieces)} pieces, output {total_duration(pieces):.2f}s")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
