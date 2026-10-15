"""Learning loop: compare past predictions with real outcomes and calibrate the win model.

Outcomes are recorded when an opportunity reaches WON or LOST (via ``set-status``).
Once enough outcomes exist, the gap between predicted and actual win rates becomes a
logit shift applied to every new win-probability estimate (bounded by config).
"""
from __future__ import annotations

import math

from .store import DATA, load_json, save_json


def outcomes() -> list[dict]:
    return load_json(DATA / "outcomes.json", [])


def record_outcome(opp: dict, result: str, note: str = "") -> None:
    rows = outcomes()
    rows = [r for r in rows if r["id"] != opp["id"]]
    rows.append({
        "id": opp["id"],
        "project": opp["project"],
        "country": opp.get("country"),
        "sector": opp.get("sector"),
        "opportunity_type": opp.get("opportunity_type"),
        "predicted_win": opp["win"]["probability"],
        "predicted_risk": opp["risk"]["score"],
        "fit": opp["fit"]["score"],
        "recommendation": opp["decision"]["recommendation"],
        "result": result,
        "note": note,
    })
    save_json(DATA / "outcomes.json", rows)


def calibration(cfg: dict) -> dict:
    rows = [r for r in outcomes() if r["result"] in ("WON", "LOST")]
    n = len(rows)
    out = {"n_outcomes": n, "shift": 0.0, "brier": None, "predicted_mean": None, "actual_rate": None}
    if not n:
        return out
    pred = sum(r["predicted_win"] for r in rows) / n
    act = sum(r["result"] == "WON" for r in rows) / n
    out.update(
        brier=round(sum((r["predicted_win"] - (r["result"] == "WON")) ** 2 for r in rows) / n, 4),
        predicted_mean=round(pred, 3),
        actual_rate=round(act, 3),
    )
    if n >= cfg["learning"]["min_outcomes_for_calibration"]:
        eps = 0.02
        a, p = min(max(act, eps), 1 - eps), min(max(pred, eps), 1 - eps)
        shift = math.log(a / (1 - a)) - math.log(p / (1 - p))
        cap = cfg["learning"]["max_calibration_shift"]
        # shrink toward zero with few data points
        shift *= n / (n + 10)
        out["shift"] = round(max(-cap, min(cap, shift)), 3)
    return out
