"""Capture plans for APPROVED opportunities, plus the action-recommendation engine."""
from __future__ import annotations

from datetime import date, timedelta

from .store import DATA, OUTPUT, load_json

UNVERIFIED = "_[to be validated by BD team]_"


def _due(item: dict, today: date) -> date | None:
    try:
        return date.fromisoformat(str(item.get("bid_due_date"))[:10])
    except (TypeError, ValueError):
        return None


def _target(today: date, due: date | None, days_before_due: int, fallback_days: int) -> str:
    if due and due > today:
        t = max(today + timedelta(days=1), due - timedelta(days=days_before_due))
    else:
        t = today + timedelta(days=fallback_days)
    return t.isoformat()


def actions(opp: dict, today: date) -> list[dict]:
    """Prioritised next actions, each with impact, effort, owner and target date."""
    due = _due(opp, today)
    rec = opp["decision"]["recommendation"]
    otype = opp.get("opportunity_type", "")
    country = opp.get("country", "")
    top_risks = opp["risk"]["top_risks"]
    acts = []

    def add(action, impact, effort, owner, before, fallback):
        acts.append({"action": action, "expected_impact": impact, "effort": effort,
                     "responsible": owner, "target_date": _target(today, due, before, fallback)})

    if rec == "NO GO":
        add("Log NO-GO rationale; set market-watch alert for follow-on packages from this client.",
            "Low - preserves BD capacity", "Low", "BD Analyst", 0, 3)
        return acts

    if due and 0 <= (due - today).days <= 10:
        add(f"Bid/no-bid decision within 24h - only {(due - today).days} days to submission; confirm portal registration and bid bond.",
            "Critical - avoids missed deadline", "Low", "BD Director", 10, 1)
    if "sub-consult" in otype.lower() or otype == "Pre-tender intelligence":
        add("Identify shortlisted bidders/likely winner and approach their bid manager with a tailored ECEC local-capability statement.",
            "High - secures a teaming seat before the scope is locked", "Medium", "BD Manager", 0, 7)
    else:
        add("Purchase / download tender documents and run a compliance shred (eligibility, classification, bond, local-content).",
            "High - de-risks disqualification", "Medium", "Proposal Manager", 14, 3)
    if opp["fit"]["criteria"]["client_relationship_potential"]["score"] < 7:
        add(f"Arrange introductory meeting with {opp.get('client')} project director / procurement lead.",
            "High - relationship is the largest win-probability lever", "Medium", "BD Director / CCO", 14, 10)
    else:
        add(f"Executive touch-point with {opp.get('client')} using existing relationship; confirm evaluation priorities.",
            "High", "Low", "CEO / CCO", 14, 7)
    if country != "Saudi Arabia":
        add(f"Engage a licensed local partner in {country} with prior {opp.get('client')} track record (JV or sub-consultancy).",
            "Critical - market-entry and registration prerequisite", "High", "BD Director", 21, 7)
    if "subconsultant" in top_risks or opp["fit"]["criteria"]["service_alignment"]["score"] < 7:
        add("Line up specialist sub-consultants for service gaps (see risk register) and obtain fee quotes.",
            "Medium - closes technical gaps", "Medium", "Technical Director", 10, 10)
    add(f"Prepare capability statement focused on {opp.get('sector')} references and named key staff CVs.",
        "Medium - raises technical score", "Medium", "Proposal Manager", 7, 10)
    if opp["fit"]["consulting_value_usd"] is None:
        add("Obtain budget / fee envelope (client contact, MEED Projects, prior similar awards) to validate economics.",
            "Medium - confirms return on effort", "Low", "BD Analyst", 14, 5)
    return acts


# ------------------------------------------------------------------ capture plan

def capture_plan_md(opp: dict, cfg: dict, kb: dict, today: date) -> str:
    country = opp.get("country", "")
    land = cfg["competitor_landscape"].get(country, {})
    intel = load_json(DATA / "capture_intel" / f"{opp['id']}.json", {})
    fc = opp["fit"]["criteria"]
    fee = opp["fit"]["consulting_value_usd"]
    refs = [p for p in kb.get("project_references", []) if opp.get("sector", "").split("-")[0].lower() in str(p.get("sector", "")).lower()][:5]

    def g(key, default):
        return intel.get(key) or default

    L = [f"# Capture Plan - {opp['project']}",
         f"**ID:** {opp['id']} | **Client:** {opp.get('client')} | **Country:** {country} | **Generated:** {today.isoformat()}",
         f"**Fit:** {opp['fit']['score']} | **Risk:** {opp['risk']['score']} ({opp['risk']['classification']}) | "
         f"**Win:** {opp['win']['probability']:.0%} | **Decision:** {opp['decision']['recommendation']} | "
         f"**Fee:** {'USD %.1fM' % (fee / 1e6) if fee else 'unknown'} | **Due:** {opp.get('bid_due_date') or 'TBC'}",
         "", "> Items marked _to be validated_ are hypotheses generated from public sources. Confirm them before acting.", "",
         "## 1. Client Analysis",
         f"- **Organisation structure:** {g('org_structure', UNVERIFIED)}",
         f"- **Key decision makers:** {', '.join(opp.get('decision_makers') or []) or UNVERIFIED}",
         f"- **Current consultants:** {opp.get('consultant') or g('current_consultants', UNVERIFIED)}",
         f"- **Current contractors:** {opp.get('main_contractor') or g('current_contractors', UNVERIFIED)}",
         f"- **Historical procurement pattern:** {g('procurement_pattern', opp.get('procurement_route') or UNVERIFIED)}",
         f"- **ECEC relationship today:** {fc['client_relationship_potential']['why']}",
         "", "## 2. Stakeholder Map",
         "| Role | Name / Position | Stance | Owner at ECEC |", "|---|---|---|---|"]
    stk = intel.get("stakeholders", {})
    for role in ["Decision Maker", "Influencer", "Technical Evaluator", "Commercial Evaluator", "Approver", "Champion"]:
        s = stk.get(role, {})
        L.append(f"| {role} | {s.get('name', UNVERIFIED)} | {s.get('stance', 'Unknown')} | {s.get('owner', 'TBD')} |")
    L += ["", "## 3. Competitor Intelligence",
          f"- **Likely competitors (global tier-1):** {', '.join(g('competitors', land.get('global_tier1', []))[:8])}",
          f"- **Likely competitors (regional/local):** {', '.join(land.get('local_leaders', [])[:6])}",
          f"- **Incumbents:** {opp.get('consultant') or g('incumbents', UNVERIFIED)}",
          f"- **Potential teaming partners:** {', '.join(g('teaming_partners', [])) or ('A licensed local firm in ' + country if country != 'Saudi Arabia' else 'A specialist international firm without a Saudi entity (fills technical gaps, ECEC provides local delivery)')}",
          "", "## 4. Win Strategy",
          f"- **Pursuit strategy:** {'Prime bid' if 'sub-consult' not in opp.get('opportunity_type', '').lower() else 'Teaming / sub-consultancy with the likely winner'}; "
          f"{'lead with existing client relationship' if fc['client_relationship_potential']['score'] >= 7 else 'build the relationship before the RFP drops'}.",
          "- **Engagement plan:** intro meeting, then a technical workshop with the client's engineering team, then a pre-bid clarifications strategy, then submission.",
          f"- **Key differentiators:** 45+ years in KSA (since 1979); integrated PMCCS (PMC + supervision under one mandate) with the 'Blue Book' governance system; "
          f"in-house six-discipline BIM design across Riyadh and Cairo; {'directly relevant references: ' + '; '.join(r['project'] for r in refs) if refs else 'adjacent references to be curated'}.",
          "- **Value proposition:** a Saudi-owned delivery partner with local-content credentials and Saudi-national staff ratios, offering lower mobilisation risk and faster authority approvals than international entrants.",
          "- **Executive engagement:** CEO-to-client-executive meeting before RFP issue; CCO to own the relationship plan.",
          f"- **Technical positioning:** emphasise {opp.get('sector')} methodology, named key staff, and how ECEC mitigates the top risks ({', '.join(opp['risk']['top_risks'])}).",
          f"- **Commercial positioning:** target win price set from the competitor field; fee envelope {'USD %.1fM' % (fee / 1e6) if fee else 'unknown - obtain'}; Cairo design hub as a cost lever.",
          f"- **Partnership strategy:** {opp['win']['factors']['strategic_partnerships']['why']}",
          "", "## 5. Risk Mitigation (top risks)"]
    for k in opp["risk"]["top_risks"]:
        c = opp["risk"]["categories"][k]
        L.append(f"- **{k.replace('_', ' ').title()} ({c['score']}/5):** {c['why']}")
    L += ["", "## 6. Prioritised Actions", "| # | Action | Impact | Effort | Owner | Target |", "|---|---|---|---|---|---|"]
    for i, a in enumerate(opp.get("actions", []), 1):
        L.append(f"| {i} | {a['action']} | {a['expected_impact']} | {a['effort']} | {a['responsible']} | {a['target_date']} |")
    L += ["", f"_Sources: {opp.get('source')}_", ""]
    return "\n".join(L)


def write_capture_plan(opp: dict, cfg: dict, kb: dict, today: date) -> str:
    path = OUTPUT / "capture_plans" / f"{opp['id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(capture_plan_md(opp, cfg, kb, today), encoding="utf-8")
    return str(path.relative_to(OUTPUT.parent))
