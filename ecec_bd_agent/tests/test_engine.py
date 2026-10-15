"""Run with:  cd ecec_bd_agent && python3 -m unittest discover tests"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bd_agent import scoring  # noqa: E402
from bd_agent.store import find_duplicate, load_config, load_kb, similarity  # noqa: E402

CFG, KB = load_config(), scoring.KBIndex(load_kb())
TODAY = date(2026, 10, 15)


def opp(**kw):
    base = dict(project="Hospital design", client="Ministry of Health", country="Saudi Arabia", location="Riyadh",
                sector="Healthcare", opportunity_type="RFP", services_needed=["design", "construction supervision"],
                estimated_project_value_usd=200e6, expected_consulting_value_usd=None, bid_due_date="2026-11-30",
                description="", source="https://example.com/a")
    base.update(kw)
    return base


def full(o, go=0):
    f = scoring.fit_model(o, KB, CFG, go)
    r = scoring.risk_model(o, f, KB, CFG, TODAY)
    w = scoring.win_model(o, f, r, KB, CFG)
    return f, r, w, scoring.decision(o, f, r, w, CFG)


class FitModel(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(CFG["fit_weights"].values()), 1.0)

    def test_every_criterion_justified(self):
        f, r, w, d = full(opp())
        for c in list(f["criteria"].values()) + list(r["categories"].values()):
            self.assertTrue(c["why"])
        self.assertEqual(len(r["categories"]), 15)
        self.assertTrue(d["reasons"])

    def test_existing_client_beats_unknown(self):
        known = scoring.fit_model(opp(), KB, CFG, 0)
        unknown = scoring.fit_model(opp(client="Unknown Developer LLC"), KB, CFG, 0)
        self.assertGreater(known["score"], unknown["score"])

    def test_home_market_beats_qatar(self):
        ksa = full(opp(client="Some Authority"))
        qat = full(opp(client="Some Authority", country="Qatar"))
        self.assertGreater(ksa[2]["probability"], qat[2]["probability"])

    def test_sports_is_not_transport(self):
        self.assertNotIn("Transportation", scoring.canon_sector("sports and entertainment"))

    def test_analyst_override_labelled(self):
        o = opp(analyst={"fit": {"technical_fit": {"score": 2, "why": "test"}}})
        f = scoring.fit_model(o, KB, CFG, 0)
        self.assertEqual(f["criteria"]["technical_fit"]["method"], "analyst")


class RiskAndDecision(unittest.TestCase):
    def test_risk_bounds_and_class(self):
        _, r, _, _ = full(opp())
        self.assertTrue(0 <= r["score"] <= 100)
        self.assertIn(r["classification"], [b[1] for b in CFG["risk_bands"]])

    def test_imminent_deadline_raises_schedule_risk(self):
        _, near, _, _ = full(opp(bid_due_date="2026-10-18"))
        _, far, _, _ = full(opp(bid_due_date="2026-12-30"))
        self.assertGreater(near["categories"]["schedule"]["score"], far["categories"]["schedule"]["score"])

    def test_win_probability_bounded(self):
        lo, hi = CFG["win_probability_bounds"]
        for c in ("Saudi Arabia", "UAE", "Qatar"):
            p = full(opp(country=c))[2]["probability"]
            self.assertTrue(lo <= p <= hi)

    def test_low_fit_is_no_go(self):
        o = opp(client="X", country="Qatar", sector="Oil & Gas", services_needed=["process engineering"],
                analyst={"fit": {k: {"score": 2, "why": "t"} for k in CFG["fit_weights"]}})
        self.assertEqual(full(o)[3]["recommendation"], "NO GO")

    def test_capex_estimate_capped(self):
        fee, note = scoring.consulting_value(opp(estimated_project_value_usd=30e9), CFG)
        self.assertLessEqual(fee, CFG["capacity"]["stretch_fee_usd"])
        self.assertIn("capped", note)


class Dedupe(unittest.TestCase):
    def test_distinct_tender_numbers_not_merged(self):
        a = opp(project="Call-Off Design Roads (2) - PWA/GTC/19/2026", country="Qatar", source="https://x")
        b = opp(project="Call-Off Design Roads (Highways) 3 - PWA/STC/25/2026", country="Qatar", source="https://x")
        self.assertEqual(similarity(a, b), 0.0)

    def test_same_project_reworded_merged(self):
        a = opp(project="Riyadh Metro Line 7 design support")
        b = opp(project="Riyadh Metro Line 7 - design support package", source="https://other")
        self.assertIsNotNone(find_duplicate(b, {"OPP-1": a}))


if __name__ == "__main__":
    unittest.main()
