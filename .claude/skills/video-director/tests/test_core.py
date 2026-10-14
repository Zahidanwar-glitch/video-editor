"""Fast unit tests for timeline, captions, planning and validation. Run: python -m pytest tests -q"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from captions import group_lines, output_words  # noqa: E402
from common import Piece, build_pieces, map_time, subtract_ranges, total_duration  # noqa: E402
from draft_plan import filler_and_pause_cuts, merge_cuts, parse_ids  # noqa: E402


def test_subtract_ranges():
    assert subtract_ranges(0, 10, [(2, 3), (5, 6)]) == [(0, 2), (3, 5), (6, 10)]
    assert subtract_ranges(0, 10, [(-1, 11)]) == []
    assert subtract_ranges(0, 10, [(9, 12)]) == [(0, 9)]


def test_build_pieces_and_map_time_with_reorder():
    plan = {"source": "a.mp4", "segments": [{"in": 20, "out": 25}, {"in": 0, "out": 10}],
            "cuts_removed": [{"start": 4, "end": 5}]}
    ps = build_pieces(plan)
    assert [(p.a, p.b, p.out_start) for p in ps] == [(20, 25, 0), (0, 4, 5), (5, 10, 9)]
    assert total_duration(ps) == 14
    assert map_time(ps, "a.mp4", 21) == 1           # hook first
    assert map_time(ps, "a.mp4", 6) == 10           # after the cut
    assert map_time(ps, "a.mp4", 4.5) == 9          # inside a cut -> snaps to next kept frame
    assert map_time(ps, "a.mp4", 4.5, snap_forward=False) is None
    assert map_time(ps, "a.mp4", 15) is None        # dropped material


def test_output_words_tease_captions_both_plays():
    words = [{"w": "hook", "start": 20.1, "end": 20.5}, {"w": "um", "start": 1.0, "end": 1.2}, {"w": "body", "start": 2.0, "end": 2.4}]
    ps = [Piece("a.mp4", 20, 21, 0), Piece("a.mp4", 0, 21, 1)]
    ow = output_words(words, ps, "a.mp4", drop_fillers=True)
    assert [w["w"] for w in ow] == ["hook", "body", "hook"]
    assert ow[0]["start"] == pytest.approx(0.1) and ow[2]["start"] == pytest.approx(21.1)


def test_group_lines_breaks_on_punctuation_and_limits():
    ws = [{"w": w, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, w in enumerate("one two three four. five six".split())]
    lines = group_lines(ws, max_words=3, max_chars=40)
    assert [len(l) for l in lines] == [3, 1, 2]


def test_filler_and_pause_cuts_never_touch_neighbouring_words():
    words = [{"id": 0, "w": "Hello", "start": 0.0, "end": 0.4, "filler": None},
             {"id": 1, "w": "um", "start": 0.7, "end": 0.9, "filler": "hard"},
             {"id": 2, "w": "world.", "start": 1.3, "end": 1.7, "filler": None},
             {"id": 3, "w": "Next", "start": 3.0, "end": 3.3, "filler": None}]
    pauses = [{"start": 1.7, "end": 3.0, "dur": 1.3, "after_sentence_end": True}]
    cuts = filler_and_pause_cuts(words, pauses, {"max_pause": 0.25, "pause_after_sentence": 0.35, "cut_hard_fillers": True})
    for c in cuts:
        for w in words:
            if w["filler"] is None:
                assert c["end"] <= w["start"] or c["start"] >= w["end"], (c, w)
    assert any(c["start"] < 0.7 and c["end"] > 0.9 for c in cuts)  # filler removed


def test_merge_cuts_and_parse_ids():
    assert len(merge_cuts([{"start": 0, "end": 1, "reason": "a"}, {"start": 1.005, "end": 2, "reason": "b"}])) == 1
    assert parse_ids("S1-S3,S7", 10) == [1, 2, 3, 7]
    with pytest.raises(SystemExit):
        parse_ids("1..3", 10)


@pytest.fixture(scope="module")
def fixture_work(tmp_path_factory):
    d = tmp_path_factory.mktemp("vd")
    subprocess.run([sys.executable, ROOT / "evals" / "make_fixture.py", d / "fx", "--size", "640x360"], check=True, capture_output=True)
    subprocess.run([sys.executable, ROOT / "scripts" / "analyze.py", d / "fx" / "fixture.mp4", "-o", d / "w",
                    "--transcript", d / "fx" / "fixture_transcript.json"], check=True, capture_output=True)
    return d


def test_analysis_finds_planted_problems(fixture_work):
    an = json.loads((fixture_work / "w" / "analysis.json").read_text())
    codes = {i["code"] for i in an["issues"]}
    assert {"fillers", "long_pauses", "slow_open"} <= codes
    hook = max(an["derived"]["sentences"], key=lambda s: s["energy_vs_median_db"] or -99)
    assert hook["text"].startswith("I lost everything")  # loudest line = planted hook


def test_validator_rejects_graphic_inside_cut(fixture_work):
    from validate_plan import validate
    w = fixture_work / "w"
    subprocess.run([sys.executable, ROOT / "scripts" / "draft_plan.py", w / "analysis.json", "-o", w / "p.json", "--style", "bold_shorts"],
                   check=True, capture_output=True)
    plan = json.loads((w / "p.json").read_text())
    errors, _ = validate(plan)
    assert errors == []
    # 0.5s is inside the trimmed 4s slow open, so it never appears in the edit
    plan["graphics"] = [{"type": "callout", "at": 0.5, "dur": 1, "text": "x"}]
    errors, _ = validate(plan)
    assert any("not in the edit" in e for e in errors)


def test_end_to_end_proxy_render_scores_well(fixture_work):
    w = fixture_work / "w"
    subprocess.run([sys.executable, ROOT / "scripts" / "draft_plan.py", w / "analysis.json", "-o", w / "e2e.json",
                    "--style", "bold_shorts", "--keep", "S0-S5", "--hook", "S6", "--auto-graphics"], check=True, capture_output=True)
    subprocess.run([sys.executable, ROOT / "scripts" / "render.py", w / "e2e.json", "-o", w / "out.mp4", "--proxy"], check=True, capture_output=True)
    subprocess.run([sys.executable, ROOT / "scripts" / "score.py", w / "render_report.proxy.json", "--json", w / "s.json", "--no-sheet"],
                   check=True, capture_output=True)
    s = json.loads((w / "s.json").read_text())
    assert s["score"] >= 90, s["checks"]
    checks = {c["check"]: c["score"] for c in s["checks"]}
    assert checks["clean_cuts"] == 1 and checks["hook_speed"] >= 0.9 and checks["loudness"] >= 0.9
