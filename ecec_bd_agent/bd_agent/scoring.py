"""ECEC opportunity models: Fit, Risk, Win Probability, Go/No-Go and Return-on-Effort ranking.

Every criterion returns a score *and* a written justification. A rule-based score is
computed from the knowledge base and the opportunity record; an analyst (human or the
research agent) may override any criterion by supplying
``item["analyst"]["fit"|"risk"|"win"][criterion] = {"score": x, "why": "..."}``.
Overrides are kept and labelled ``method: analyst`` so the audit trail shows who decided.
"""
from __future__ import annotations

import math
import re
from datetime import date

# ------------------------------------------------------------------ taxonomies

SERVICE_SYNONYMS = {
    "design": ["design", "detailed design", "concept", "engineering", "architect", "structural", "mep", "schematic", "drawings"],
    "supervision": ["supervision", "resident engineer", "construction management", "site", "inspection", "cms"],
    "pmc": ["pmc", "project management", "program management", "programme management", "pmo", "owner's engineer",
            "owners engineer", "owner engineer", "client representative", "delivery partner", "development management"],
    "studies": ["feasibility", "study", "studies", "master plan", "masterplan", "planning", "advisory", "due diligence", "assessment"],
    "cost": ["cost", "quantity surveying", "qs", "cost management", "estimating", "contract administration", "claims"],
    "transport": ["traffic", "transport", "highway", "road", "bridge", "rail", "metro", "airport", "its"],
    "smart_ict": ["smart", "ict", "telecom", "digital", "iot", "scada", "elv", "bim", "gis", "data cent", "cyber"],
    "utilities": ["water", "wastewater", "sewage", "sewer", "storm", "utilit", "power", "substation", "electric",
                  "desalination", "irrigation", "district cooling", "drainage"],
    "environmental": ["environment", "eia", "sustainab", "mostadam", "leed", "esg"],
    "survey": ["geotechnical", "survey", "topograph"],
    "commissioning": ["commissioning", "testing", "t&c", "handover"],
}

SECTOR_SYNONYMS = {
    "Transportation": ["transport", "road", "highway", "rail", "metro", "airport", "port", "bridge", "traffic", "mobility"],
    "Buildings": ["building", "architect", "residential", "commercial", "housing", "real estate", "hospitality",
                  "mixed-use", "mixed use", "office", "tower"],
    "Infrastructure": ["infrastructure", "civil", "earthwork", "utility network", "site development"],
    "Utilities-Water": ["water", "wastewater", "sewer", "desalination", "storm", "irrigation", "drainage"],
    "Utilities-Power": ["power", "electric", "energy", "substation", "renewable", "solar", "grid"],
    "Smart City": ["smart"],
    "ICT": ["ict", "telecom", "information technology", "digital", "data cent"],
    "Oil & Gas": ["oil", "gas", "petro", "refin"],
    "Urban Development": ["urban", "master plan", "masterplan", "city", "municipal", "giga"],
    "Healthcare": ["health", "hospital", "medical", "clinic"],
    "Education": ["education", "school", "university", "campus"],
    "Sports & Entertainment": ["sport", "stadium", "entertainment", "leisure", "tourism", "arena"],
}


def _has(text: str, syn: str) -> bool:
    # match at a word start so "port" does not fire on "sports"
    return re.search(r"(?<![a-z])" + re.escape(syn), text) is not None


def canon_services(items) -> set[str]:
    out = set()
    for raw in items or []:
        s = (raw if isinstance(raw, str) else (raw.get("name", "") + " " + raw.get("detail", ""))).lower()
        for key, syns in SERVICE_SYNONYMS.items():
            if any(_has(s, x) for x in syns):
                out.add(key)
    return out


def canon_sector(text: str) -> set[str]:
    t = (text or "").lower()
    return {k for k, syns in SECTOR_SYNONYMS.items() if k.lower() in t or any(_has(t, x) for x in syns)}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _crit(score, why, method="rule", evidence=None):
    return {"score": round(float(score), 1), "why": why, "method": method, "evidence": evidence or []}


# ------------------------------------------------------------------ KB helpers

class KBIndex:
    def __init__(self, kb: dict):
        self.kb = kb or {}
        self.services = canon_services(self.kb.get("service_offerings", []))
        self.sectors = set()
        for s in self.kb.get("market_sectors", []):
            self.sectors |= canon_sector(s if isinstance(s, str) else s.get("name", ""))
        self.clients = [
            ((c if isinstance(c, str) else c.get("client", "")).lower(),
             "documented_projects" if isinstance(c, str) else c.get("evidence", "documented_projects"))
            for c in self.kb.get("client_references", [])
        ]
        self.projects = self.kb.get("project_references", [])
        self.countries = {
            (g if isinstance(g, str) else g.get("country", "")).lower()
            for g in self.kb.get("geographic_presence", [])
        }
        self.partners = self.kb.get("strategic_partners", [])

    def projects_in_sector(self, sector: str) -> list[dict]:
        target = canon_sector(sector) or {sector}
        hits = []
        for p in self.projects:
            text = " ".join(str(p.get(k, "")) for k in ("sector", "project", "role"))
            if canon_sector(text) & target:
                hits.append(p)
        return hits

    def client_match(self, client: str) -> tuple[str, str] | None:
        """Return (reference, evidence_level); documented projects beat logo-wall mentions."""
        c = (client or "").lower()
        if not c:
            return None
        generic = {"company", "authority", "ministry", "the", "for", "and", "saudi", "general", "development",
                   "services", "city", "region", "royal", "commission", "arabia", "department"}
        ctoks = set(re.findall(r"[a-z]{3,}", c)) - generic
        hits = []
        for ref, ev in self.clients:
            if not ref:
                continue
            rtoks = set(re.findall(r"[a-z]{3,}", ref)) - generic
            if re.search(r"\b" + re.escape(ref) + r"\b", c) or (rtoks and rtoks <= ctoks) or (ctoks and ctoks <= rtoks and len(ctoks) >= 2):
                hits.append((ref, ev))
        if not hits:
            return None
        hits.sort(key=lambda h: h[1] != "documented_projects")
        return hits[0]


# ------------------------------------------------------------------ economics

def consulting_value(item: dict, cfg: dict) -> tuple[float | None, str | None]:
    """Return (consulting fee USD, note). Estimates from capex when the fee is unknown."""
    fee = item.get("expected_consulting_value_usd")
    if fee:
        return float(fee), None
    capex = item.get("estimated_project_value_usd")
    if not capex:
        return None, "Consulting value and project value unknown"
    svc = canon_services(item.get("services_needed", []))
    pct_tab = cfg["economics"]["default_consulting_pct_of_capex"]
    if "design" in svc and "supervision" in svc:
        pct = pct_tab["design+supervision"]
    elif "pmc" in svc:
        pct = pct_tab["PMC"]
    elif "design" in svc:
        pct = pct_tab["design"]
    elif "supervision" in svc:
        pct = pct_tab["supervision"]
    else:
        pct = pct_tab["default"]
    est, note = float(capex) * pct, f"Consulting value estimated at {pct:.1%} of capex (rule-based)"
    if "sub-consult" in (item.get("opportunity_type") or "").lower():
        share = cfg["economics"]["sub_consultancy_share"]
        est *= share
        note += f", x{share:.0%} sub-consultancy share"
    cap = cfg["capacity"]["stretch_fee_usd"]
    if est > cap:
        est, note = cap, note + f", capped at ECEC addressable fee USD {cap/1e6:.0f}M"
    return est, note


def economic_fee(item: dict, fee: float | None, cfg: dict) -> tuple[float, bool]:
    """Fee used for EV/ROE ranking. Falls back to a labelled placeholder by opportunity type."""
    if fee:
        return fee, False
    tab = cfg["economics"]["assumed_fee_when_unknown_usd"]
    return float(tab.get(item.get("opportunity_type", ""), tab["default"])), True


def bid_cost(fee: float | None, cfg: dict) -> float:
    e = cfg["economics"]
    if not fee:
        return e["bid_cost_min_usd"] * 2
    return _clamp(fee * e["bid_cost_pct_of_fee"], e["bid_cost_min_usd"], e["bid_cost_max_usd"])


def days_to_due(item: dict, today: date) -> int | None:
    d = item.get("bid_due_date")
    if not d:
        return None
    try:
        return (date.fromisoformat(str(d)[:10]) - today).days
    except ValueError:
        return None


# ------------------------------------------------------------------ FIT MODEL

def fit_model(item: dict, kb: KBIndex, cfg: dict, active_pursuits: int) -> dict:
    W = cfg["fit_weights"]
    country = item.get("country", "")
    cprof = cfg["country_profile"].get(country, {"geo": 2})
    needed = canon_services(item.get("services_needed", []) + [item.get("description", "")[:0]])
    sector_set = canon_sector(item.get("sector", "")) or canon_sector(item.get("description", ""))
    fee, fee_note = consulting_value(item, cfg)
    text = " ".join(str(item.get(k, "")) for k in ("project", "client", "description", "location")).lower()
    c: dict[str, dict] = {}

    # Technical fit: does the scope sit in sectors ECEC delivers?
    sector_hit = bool(sector_set & kb.sectors)
    tech_svc_hit = needed & {"transport", "smart_ict", "utilities", "environmental", "survey", "commissioning", "design"}
    score = 3 + (5 if sector_hit else 1) + (2 if tech_svc_hit & kb.services else 0)
    c["technical_fit"] = _crit(
        score,
        f"Sector {sorted(sector_set) or 'unclassified'} {'is' if sector_hit else 'is NOT'} in ECEC's declared sectors; "
        f"technical disciplines matched: {sorted(tech_svc_hit & kb.services) or 'none'}.",
        evidence=sorted(sector_set & kb.sectors),
    )

    # Service alignment: share of required services ECEC offers
    if needed:
        cov = len(needed & kb.services) / len(needed)
        score = 2 + 8 * cov
        why = f"{len(needed & kb.services)}/{len(needed)} required service lines offered ({sorted(needed & kb.services)}); gaps: {sorted(needed - kb.services) or 'none'}."
    else:
        score, why = 5, "Required services not stated in source - neutral score; FLAG: confirm scope."
    c["service_alignment"] = _crit(score, why)

    # Sector experience: count of KB project references in sector
    refs = kb.projects_in_sector(item.get("sector", ""))
    n = len(refs)
    score = 2 if n == 0 else 5 if n == 1 else 7 if n <= 3 else 9 if n <= 6 else 10
    c["sector_experience"] = _crit(
        score, f"{n} documented ECEC reference project(s) in this sector.",
        evidence=[r.get("project") for r in refs[:5]],
    )

    # Client relationship potential
    hit = kb.client_match(item.get("client", ""))
    client_l = (item.get("client") or "").lower()
    is_gov = any(k in client_l for k in ("ministry", "authority", "royal commission", "municipality", "amanah",
                                          "ashghal", "public works", "government", "council", "commission"))
    if hit and hit[1] == "documented_projects":
        score, why = 9, f"Existing client with documented ECEC projects ('{hit[0]}')."
    elif hit:
        score, why = 7, f"Client '{hit[0]}' appears on ECEC client logo wall (relationship depth unverified)."
    elif country == "Saudi Arabia" and is_gov:
        score, why = 6, "KSA government client - ECEC is a registered local consultant; no direct reference found."
    elif country == "Saudi Arabia":
        score, why = 5, "KSA client with no documented prior relationship."
    else:
        score, why = 3, "Out-of-home-market client with no documented relationship."
    c["client_relationship_potential"] = _crit(score, why)

    # Geographic fit
    geo = cprof.get("geo", 2)
    if country.lower() in kb.countries and country != "Saudi Arabia":
        geo = min(10, geo + 2)
    loc = (item.get("location") or "").lower()
    if country == "Saudi Arabia" and loc and "riyadh" not in loc:
        geo -= 1
    c["geographic_fit"] = _crit(geo, f"{country} / {item.get('location') or 'location n/a'}; HQ Riyadh"
                                + ("; ECEC presence recorded in country." if country.lower() in kb.countries else "."))

    # Strategic importance
    s_imp, s_kw = 4, None
    for lvl in ("10", "8", "6"):
        for kw in cfg["strategic_keywords"][lvl]:
            if kw in f" {text} ":
                s_imp, s_kw = int(lvl), kw
                break
        if s_kw:
            break
    c["strategic_importance"] = _crit(
        s_imp, f"Strategic marker '{s_kw}' found." if s_kw else "No flagship / giga-project / key-account marker found."
    )

    # Revenue potential
    if fee is None:
        score, why = 5, "Fee unknown - neutral score; FLAG: obtain budget."
    else:
        bands = [(50e6, 10), (20e6, 9), (10e6, 8), (5e6, 7), (2e6, 6), (1e6, 5), (0.5e6, 4)]
        score = next((s for lim, s in bands if fee >= lim), 3)
        why = f"Consulting fee ~USD {fee/1e6:,.1f}M" + (f" ({fee_note})." if fee_note else " (stated).")
    c["revenue_potential"] = _crit(score, why)

    # Resource availability
    cap = cfg["capacity"]
    if fee is None:
        score, why = 6, "Fee unknown - assumed within normal capacity."
    elif fee <= cap["comfortable_fee_usd"]:
        score, why = 8, "Fee within comfortable delivery capacity."
    elif fee <= cap["stretch_fee_usd"]:
        score, why = 6, "Fee at stretch capacity - may need staff augmentation."
    else:
        score, why = 3, "Fee exceeds stretch capacity - JV/partner needed."
    if active_pursuits >= cap["max_concurrent_major_bids"]:
        score -= 2
        why += f" {active_pursuits} concurrent GO pursuits already (limit {cap['max_concurrent_major_bids']})."
    c["resource_availability"] = _crit(_clamp(score, 1, 10), why)

    # Competitive position
    score, notes = 5, []
    if cprof.get("local_preference") and country == "Saudi Arabia":
        score += 2; notes.append("Saudi local-content / local-consultant preference")
    if hit:
        score += 2 if hit[1] == "documented_projects" else 1
        notes.append("prior work for client" if hit[1] == "documented_projects" else "client listed on ECEC logo wall")
    if s_imp == 10 and (item.get("estimated_project_value_usd") or 0) >= 1e9:
        score -= 2; notes.append("mega-project typically dominated by global tier-1 PMCs")
    otype = item.get("opportunity_type", "")
    if "sub-consult" in otype.lower():
        score += 1; notes.append("sub-consultancy route lowers competitive bar")
    if otype in ("Tender", "RFP") and not hit:
        score -= 1; notes.append("open competitive tender")
    c["competitive_position"] = _crit(_clamp(score, 1, 10), "; ".join(notes) or "Neutral competitive position.")

    # Long-term growth
    score = 5
    notes = []
    if set(cfg["growth_sectors"]) & (sector_set or {item.get("sector", "")}):
        score += 2; notes.append("growth sector")
    if s_imp >= 8:
        score += 1; notes.append("anchor client / programme")
    if any(k in text for k in ("framework", "programme", "program", "phase 1", "phase one", "multiple", "network")):
        score += 1; notes.append("follow-on / multi-phase potential")
    c["long_term_growth_potential"] = _crit(_clamp(score, 1, 10), "; ".join(notes) or "Limited follow-on visibility.")

    # analyst overrides
    for k, ov in ((item.get("analyst") or {}).get("fit", {}) or {}).items():
        if k in c:
            c[k] = _crit(ov["score"], ov.get("why", "analyst override"), method="analyst")

    total = sum(c[k]["score"] * 10 * W[k] for k in W)
    align = (c["technical_fit"]["score"] + c["service_alignment"]["score"]) / 2 * 10
    return {
        "score": round(total, 1),
        "technical_alignment_pct": round(align, 1),
        "criteria": c,
        "consulting_value_usd": fee,
        "consulting_value_note": fee_note,
        "strategic_importance": s_imp,
    }


# ------------------------------------------------------------------ RISK MODEL

def risk_model(item: dict, fit: dict, kb: KBIndex, cfg: dict, today: date) -> dict:
    country = item.get("country", "")
    cp = cfg["country_profile"].get(country, {})
    fee = fit["consulting_value_usd"]
    capex = item.get("estimated_project_value_usd") or 0
    client_l = (item.get("client") or "").lower() + " " + (item.get("project") or "").lower()
    otype = item.get("opportunity_type", "")
    needed = canon_services(item.get("services_needed", []))
    r: dict[str, dict] = {}

    route = (item.get("procurement_route") or "").lower()
    r["commercial"] = _crit(4 if any(k in route for k in ("lowest", "l1", "price only")) else 3 if (fee or 0) < 5e5 else 2,
                            f"Procurement route: {item.get('procurement_route') or 'unknown'}; fee {'unknown' if fee is None else f'~USD {fee/1e6:.1f}M'}.")
    cap = cfg["capacity"]
    r["financial"] = _crit(4 if (fee or 0) > cap["stretch_fee_usd"] else 3 if (fee or 0) > cap["comfortable_fee_usd"] else 2,
                           "Working-capital exposure scaled to fee vs. firm capacity.")
    r["client_credit"] = _crit(2, "Government/GRE client - default low-moderate credit risk.")
    r["technical_complexity"] = _crit(
        (4 if capex >= 1e9 else 3 if capex >= 2e8 else 2) + (1 if "Oil & Gas" in item.get("sector", "") else 0),
        f"Project scale USD {capex/1e6:,.0f}M" if capex else "Project scale unknown - moderate assumed.")
    r["contractual"] = _crit(3, "Standard GCC consultancy terms (unlimited liability / PI cover clauses typical) - review on receipt of RFP.")
    comp = {"Tender": 4, "RFP": 4, "RFQ": 3, "EOI": 3, "PQ": 3, "Pre-tender intelligence": 3}.get(otype, 3)
    if "sub-consult" in otype.lower():
        comp = 2
    if fit["strategic_importance"] == 10:
        comp = min(5, comp + 1)
    r["competition"] = _crit(comp, f"{otype or 'Unknown route'}; flagship projects attract global tier-1 competition." if fit["strategic_importance"] == 10 else f"{otype or 'Unknown route'} competition level.")
    ra = fit["criteria"]["resource_availability"]["score"]
    r["resource_availability"] = _crit(_clamp(round(6 - ra / 2), 1, 5), "Derived from Fit resource-availability score.")
    dd = days_to_due(item, today)
    if dd is None:
        r["schedule"] = _crit(3, "Bid due date unknown - FLAG.")
    else:
        r["schedule"] = _crit(5 if dd < 7 else 4 if dd < 14 else 3 if dd < 30 else 2,
                              f"{dd} days to submission." if dd >= 0 else f"Due date passed {abs(dd)} days ago - verify extension.")
    r["supply_chain"] = _crit(2 if "supervision" in needed else 1, "Consulting services - limited supply-chain exposure.")
    r["regulatory"] = _crit(cp.get("regulatory_risk", 3), f"{country} regulatory/registration environment.")
    r["political"] = _crit(cp.get("political_risk", 3), f"{country} political/program-prioritisation risk.")
    me = cp.get("market_entry_risk", 4)
    if country.lower() in kb.countries and country != "Saudi Arabia":
        me = max(1, me - 2)
    r["market_entry"] = _crit(me, "Home market." if country == "Saudi Arabia" else
                              f"Requires local registration / licensed partner in {country}.")
    gaps = needed - kb.services
    r["subconsultant"] = _crit(_clamp(1 + len(gaps), 1, 5), f"Service gaps needing sub-consultants: {sorted(gaps) or 'none'}.")
    r["reputation"] = _crit(3 if fit["strategic_importance"] == 10 else 2, "High-visibility programme." if fit["strategic_importance"] == 10 else "Normal visibility.")
    r["payment"] = _crit(cp.get("payment_risk", 3), f"Typical {country} public-sector payment cycle.")

    for key, ov in cfg.get("client_risk_overrides", {}).items():
        if key.startswith("_") or key not in client_l:
            continue
        for cat, val in ov.items():
            if cat in r:
                r[cat] = _crit(val, ov.get("note", f"Client-specific profile '{key}'."), method="client_profile")

    for k, ov in ((item.get("analyst") or {}).get("risk", {}) or {}).items():
        if k in r:
            r[k] = _crit(ov["score"], ov.get("why", "analyst override"), method="analyst")

    cats = cfg["risk_categories"]
    avg = sum(r[c]["score"] for c in cats) / len(cats)
    total = round((avg - 1) / 4 * 100, 1)
    # A single Very-High category floors the overall rating at Medium
    if any(r[c]["score"] >= 5 for c in cats):
        total = max(total, 45.0)
    cls = next(lbl for lim, lbl in cfg["risk_bands"] if total <= lim)
    top = sorted(cats, key=lambda c: -r[c]["score"])[:3]
    return {"score": total, "classification": cls, "categories": r, "top_risks": top}


# ------------------------------------------------------------------ WIN PROBABILITY

def _logit(p):
    return math.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + math.exp(-x))


def win_model(item: dict, fit: dict, risk: dict, kb: KBIndex, cfg: dict, calibration_shift: float = 0.0) -> dict:
    base = cfg["win_base_rates"].get(item.get("opportunity_type", ""), cfg["win_base_rates"]["default"])
    fc = fit["criteria"]
    a = (item.get("analyst") or {}).get("win", {}) or {}
    country = item.get("country", "")
    has_partner = bool(a.get("strategic_partnerships", {}).get("score", 0) > 0)

    def norm(s):  # 0-10 -> -2..+2
        return (s - 5) / 2.5

    f = {
        "client_relationship_strength": (norm(fc["client_relationship_potential"]["score"]), fc["client_relationship_potential"]["why"]),
        "previous_ecec_experience": (norm(fc["sector_experience"]["score"]), fc["sector_experience"]["why"]),
        "existing_framework_agreements": (0.0, "No framework agreement recorded - FLAG if one exists."),
        "competitor_presence": (3 - risk["categories"]["competition"]["score"], risk["categories"]["competition"]["why"]),
        "technical_capability": (norm((fc["technical_fit"]["score"] + fc["service_alignment"]["score"]) / 2), "Average of technical fit and service alignment."),
        "market_positioning": ((1.0 if country == "Saudi Arabia" else -1.0), "Home-market positioning." if country == "Saudi Arabia" else "Limited brand recognition outside KSA."),
        "delivery_capacity": (norm(fc["resource_availability"]["score"]), fc["resource_availability"]["why"]),
        "strategic_partnerships": ((0.0 if country == "Saudi Arabia" else -1.0), "No teaming partner identified." + ("" if country == "Saudi Arabia" else " Local partner usually decisive outside KSA.")),
    }
    for k, ov in a.items():
        if k in f:
            f[k] = (float(ov["score"]), ov.get("why", "analyst override"))
    _ = has_partner

    coef, cap = cfg.get("win_factor_coef", 0.2), cfg.get("win_factor_cap_logit", 1.4)
    adj = _clamp(coef * sum(v for v, _ in f.values()), -cap, cap)
    x = _logit(base) + adj + calibration_shift
    lo, hi = cfg["win_probability_bounds"]
    p = _clamp(_sig(x), lo, hi)
    return {
        "probability": round(p, 3),
        "base_rate": base,
        "calibration_shift": round(calibration_shift, 3),
        "factors": {k: {"value": round(v, 2), "why": w} for k, (v, w) in f.items()},
        "logit_adjustment": round(adj, 3),
        "rationale": (f"Base rate {base:.0%} for {item.get('opportunity_type') or 'unknown route'}; "
                      f"strongest positives: {', '.join(k for k, (v, _) in sorted(f.items(), key=lambda kv: -kv[1][0])[:2] if v > 0) or 'none'}; "
                      f"main drags: {', '.join(k for k, (v, _) in sorted(f.items(), key=lambda kv: kv[1][0])[:2] if v < 0) or 'none'}."),
    }


# ------------------------------------------------------------------ GO / NO-GO

def decision(item: dict, fit: dict, risk: dict, win: dict, cfg: dict) -> dict:
    R = cfg["decision_rules"]
    e = cfg["economics"]
    fee = fit["consulting_value_usd"]
    efee, assumed = economic_fee(item, fee, cfg)
    p = win["probability"]
    cost = bid_cost(efee, cfg)
    ev = efee * p
    roe = (ev * e["assumed_margin_pct"]) / cost if cost else 0
    strategic = fit["strategic_importance"]
    demand = "High" if (fee or 0) > cfg["capacity"]["comfortable_fee_usd"] else "Medium" if (fee or 0) > 3e6 else "Low"

    no_go, caution, positives = [], [], []
    if fit["score"] < R["no_go"]["max_fit"]:
        no_go.append(f"Fit {fit['score']} below {R['no_go']['max_fit']}")
    if risk["score"] >= R["no_go"]["min_risk"]:
        no_go.append(f"Risk {risk['score']} is Critical")
    if p <= R["no_go"]["max_win"]:
        if strategic >= R["strategic_override_min_importance"]:
            caution.append(f"Win {p:.0%} very low but strategic importance {strategic}/10 - pursue only for positioning")
        else:
            no_go.append(f"Win probability {p:.0%} too low")
    if ev < R["min_expected_value_usd"]:
        (no_go if fit["score"] < 60 else caution).append(f"Expected value USD {ev:,.0f} below threshold")

    if fit["score"] >= R["go"]["min_fit"]: positives.append(f"strong fit ({fit['score']})")
    else: caution.append(f"Fit {fit['score']} < {R['go']['min_fit']}")
    if risk["score"] <= R["go"]["max_risk"]: positives.append(f"manageable risk ({risk['classification']})")
    else: caution.append(f"Risk {risk['score']} ({risk['classification']})")
    if p >= R["go"]["min_win"]: positives.append(f"win {p:.0%}")
    else: caution.append(f"Win {p:.0%} < {R['go']['min_win']:.0%}")
    if roe >= 3: positives.append(f"ROE {roe:.1f}x")
    else: caution.append(f"Return on bid effort only {roe:.1f}x")
    if demand == "High": caution.append("High resource demand")
    if assumed: caution.append(f"Fee unknown - economics use a placeholder of USD {efee/1e6:.1f}M")

    if no_go:
        rec, reasons = "NO GO", no_go
    elif not caution:
        rec, reasons = "GO", positives
    else:
        rec, reasons = "GO WITH CAUTION", positives + caution
    return {
        "recommendation": rec,
        "reasons": reasons,
        "expected_value_usd": round(ev),
        "fee_used_usd": round(efee),
        "fee_assumed": assumed,
        "bid_cost_usd": round(cost),
        "return_on_effort": round(roe, 2),
        "profitability_margin_assumed": e["assumed_margin_pct"],
        "strategic_value": strategic,
        "resource_demand": demand,
    }


def priority_score(fit: dict, risk: dict, win: dict, dec: dict) -> float:
    """0-100 index that orders by expected return on effort, tempered by fit and risk."""
    roe_part = 40 * min(1.0, math.log10(1 + dec["return_on_effort"]) / 2)  # ROE 99x -> full marks
    s = roe_part + 0.3 * fit["score"] + 30 * win["probability"] - 0.15 * risk["score"]
    s += {"GO": 10, "GO WITH CAUTION": 0, "NO GO": -30}[dec["recommendation"]]
    return round(_clamp(s, 0, 100), 1)


def missing_info(item: dict, fit: dict) -> list[str]:
    fields = ["client", "location", "estimated_project_value_usd", "expected_consulting_value_usd", "bid_due_date",
              "project_duration_months", "procurement_route", "decision_makers", "services_needed", "source"]
    miss = [f for f in fields if not item.get(f)]
    if fit.get("consulting_value_note"):
        miss.append(fit["consulting_value_note"])
    return sorted(set(miss + list(item.get("missing", []) or [])))
