#!/usr/bin/env python3
"""Run the eval set: analyze -> plan -> render -> score for every case, and compare with the last run.

Cases live in evals/cases/*.json:
  {"name": "...", "video": "path or @fixture[:WxH]", "transcript": "optional path",
   "plan": "optional fixed plan (its source/analysis are rewritten)",
   "draft": {"style": "bold_shorts", "platform": "shorts", "keep": "S0-S5", "hook": "S6",
             "hook_mode": "move", "auto_graphics": true},
   "target_seconds": 25, "proxy": true}

A fixed `plan` tests the scripts (regressions in rendering); a `draft` case tests the rules.
To test Claude's judgment, have Claude write plans for real footage and save them as fixed plans,
then grade with references/review-checklist.md (judge prompt).

Usage: run_evals.py [--cases evals/cases] [--only NAME] [--full-res] [--fail-on-drop 2]
Exit code 1 if any case's score dropped more than --fail-on-drop points vs the previous run.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import load_json, save_json  # noqa: E402


def sh(args: list[str]) -> str:
    proc = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(str(args[0])).name} failed:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
    return proc.stdout


def fixture(spec: str) -> tuple[str, str]:
    size = spec.split(":", 1)[1] if ":" in spec else "1280x720"
    d = HERE / ".fixtures" / size
    if not (d / "fixture.mp4").exists():
        sh([HERE / "make_fixture.py", d, "--size", size])
    return str(d / "fixture.mp4"), str(d / "fixture_transcript.json")


def run_case(case: dict, full_res: bool) -> dict:
    t0 = time.time()
    work = HERE / ".runs" / case["name"]
    work.mkdir(parents=True, exist_ok=True)
    video, transcript = case["video"], case.get("transcript")
    if video.startswith("@fixture"):
        video, transcript = fixture(video)
    a = [SCRIPTS / "analyze.py", video, "-o", work]
    if transcript:
        a += ["--transcript", transcript]
    sh(a)
    plan_path = work / "edit_plan.json"
    if case.get("plan"):
        plan = load_json(HERE / case["plan"] if not Path(case["plan"]).is_absolute() else case["plan"])
        plan["source"] = str(Path(video).resolve())
        plan["analysis"] = str((work / "analysis.json").resolve())
        save_json(plan, plan_path)
    else:
        d = case.get("draft", {})
        a = [SCRIPTS / "draft_plan.py", work / "analysis.json", "-o", plan_path, "--style", d.get("style", "clean")]
        for k in ("platform", "keep", "hook", "hook_mode"):
            if d.get(k):
                a += [f"--{k.replace('_', '-')}", d[k]]
        if d.get("auto_graphics"):
            a.append("--auto-graphics")
        sh(a)
        if case.get("target_seconds"):
            plan = load_json(plan_path)
            plan["brief"]["target_seconds"] = case["target_seconds"]
            plan["brief"]["message"] = plan["brief"]["message"] or f"eval case {case['name']}"
            save_json(plan, plan_path)
    proxy = case.get("proxy", True) and not full_res
    out = work / "out.mp4"
    sh([SCRIPTS / "render.py", plan_path, "-o", out] + (["--proxy"] if proxy else []))
    report = work / ("render_report.proxy.json" if proxy else "render_report.json")
    sh([SCRIPTS / "score.py", report, "--json", work / "score.json"])
    s = load_json(work / "score.json")
    return {"name": case["name"], "score": s["score"], "checks": {c["check"]: c["score"] for c in s["checks"]},
            "seconds": round(time.time() - t0, 1), "output": str(out), "review_sheet": s.get("review_sheet")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=str(HERE / "cases"))
    ap.add_argument("--only")
    ap.add_argument("--full-res", action="store_true")
    ap.add_argument("--fail-on-drop", type=float, default=2.0)
    args = ap.parse_args()

    cases = [load_json(p) for p in sorted(Path(args.cases).glob("*.json"))]
    if args.only:
        cases = [c for c in cases if c["name"] == args.only]
    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)
    prev_files = sorted(results_dir.glob("*.json"))
    prev = {r["name"]: r for r in load_json(prev_files[-1])["cases"]} if prev_files else {}

    results = []
    for c in cases:
        try:
            r = run_case(c, args.full_res)
        except Exception as e:  # one broken case must not hide the others
            r = {"name": c["name"], "score": 0.0, "checks": {}, "error": str(e)[-800:]}
        results.append(r)

    print(f"\n{'case':<34} {'score':>6} {'prev':>6} {'delta':>6}  time")
    regressions = []
    for r in results:
        p = prev.get(r["name"])
        delta = r["score"] - p["score"] if p else 0.0
        print(f"{r['name']:<34} {r['score']:>6.1f} {p['score'] if p else '-':>6} {delta:>+6.1f}  {r.get('seconds', '-')}s"
              + (f"  ERROR: {r['error'].splitlines()[0]}" if r.get("error") else ""))
        if p:
            worse = [k for k, v in r["checks"].items() if v < p["checks"].get(k, v) - 0.05]
            if worse:
                print(f"{'':<34} checks down: {', '.join(worse)}")
        if (p and delta < -args.fail_on_drop) or r.get("error"):
            regressions.append(r["name"])
    mean = sum(r["score"] for r in results) / max(1, len(results))
    print(f"\nmean score {mean:.1f}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    save_json({"timestamp": stamp, "mean": round(mean, 2), "cases": results}, results_dir / f"{stamp}.json")
    if regressions:
        print(f"REGRESSIONS: {', '.join(regressions)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
