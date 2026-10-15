# ECEC_BD_INTELLIGENCE_AGENT: Daily Run Playbook

The scheduled task follows this playbook every day at about 03:00 AST. A person can also run it by hand.
Act as ECEC's **Business Development Director**, not as a researcher. Quality beats quantity: only log
opportunities ECEC can realistically win or reach by teaming.

## 0. Setup
```bash
git fetch origin claude/inspiring-hopper-t95859 && git checkout claude/inspiring-hopper-t95859 && git pull
cd ecec_bd_agent && python3 -m unittest discover tests
```
Read `config/scoring_config.json`, `data/knowledge_base.json`, and the project names and statuses in
`data/opportunities.json`. You need these so you don't re-log known items and so you notice changes to them.

## 1. Knowledge base refresh (Sundays, or if `_meta.last_updated` is more than 30 days old)
Check ecec.com.sa, the ECEC LinkedIn page and the news for new awards, partners, certifications, offices and leadership changes.
Update `data/knowledge_base.json` and include a source URL for every addition. Never credit projects belonging to
**ECEC (ecec.co, Dubai/Amman)** or **East China Engineering**. See `entity_disambiguation`.

## 2. Discovery (run research sub-agents in parallel: KSA, UAE, Qatar)
Sources: Etimad, NEOM/ENOWA, Diriyah, ROSHN, Qiddiya, Red Sea Global, RCRC/RCU/RCJY/RCMC, Aramco, SEC/SE-PDC/NG,
SWCC/SWPC, NWC, ministries, NHC, Expo 2030, NCP (PPP); ADNOC, DEWA, Dubai Municipality, RTA, ADGPG/ADPIC/DMT,
Etihad Rail, developers; Ashghal, QatarEnergy, Kahramaa, Monaqasat, Qatari Diar; MEED, Zawya, Construction Week,
Infrastructure Middle East, Argaam, Arab News, Gulf Times, The Peninsula.

Write each region's findings to `data/inbox/<YYYY-MM-DD>_<region>.json`:
```json
{"run_date": "YYYY-MM-DD", "researcher": "discovery-agent:<region>",
 "opportunities": [{"project": "", "client": "", "country": "Saudi Arabia|UAE|Qatar", "location": "", "sector": "",
   "opportunity_type": "Tender|RFP|RFQ|EOI|PQ|Pre-tender intelligence|Award (sub-consultancy angle)|Framework",
   "services_needed": [], "estimated_project_value_usd": null, "expected_consulting_value_usd": null,
   "current_stage": "", "bid_due_date": "YYYY-MM-DD|null", "project_duration_months": null, "procurement_route": "",
   "main_contractor": null, "consultant": null, "decision_makers": [], "source": "URL", "source_date": "YYYY-MM-DD",
   "description": "", "missing": [],
   "analyst": {"fit": {"<criterion>": {"score": 0, "why": "evidence"}}, "risk": {}, "win": {}}}],
 "market_intelligence": [{"date": "", "headline": "", "category": "", "country": "", "implication": "", "source": ""}]}
```
Rules:
- **Never invent anything.** Put unknown fields as `null` and list them in `missing`. Every item needs a source URL and a date.
- Include tender reference numbers in `project` (for example `PWA/STC/25/2026`). The de-duplicator relies on them.
- If a known item changes (deadline extended, award, cancellation), re-log it with the same project and client. The engine merges it and records the change.
- If the main bid has closed, log it as `Award (sub-consultancy angle)` and set `bid_due_date: null`.
- Use `analyst` overrides only with a concrete reason (for example: no ECEC rail references, or a reported bidder is an ECEC client). Each one is labelled as an override in the audit trail.
- Market intelligence categories: Project announcement, Funding approval, Consultant appointment, Contractor appointment, PIF investment, Infrastructure program, Smart city, Mega-project.

## 3-7. Qualify, score, rank, report
```bash
python3 -m bd_agent run            # picks up data/inbox/<today>_*.json
```
This syncs status edits made in the Excel file, ingests and de-duplicates the inbox, drops anything outside the target GCC countries or below 50% technical alignment,
scores Fit, Risk and Win, issues GO / GO WITH CAUTION / NO GO, ranks by return on effort, writes capture plans for APPROVED items,
and produces `output/opportunities.xlsx` plus `output/reports/<date>/daily_executive_report.{md,pdf}`. On Sundays it also writes the weekly trend analysis.

**BD-Director sanity check:** read the top 10 and the NO GO list. If a score is wrong because the input data is wrong, fix the inbox file and re-run.
Do not patch the database by hand.

## 6b. Approved opportunities: deepen capture intelligence
For each `APPROVED` item, research the organisation structure, named decision makers, incumbents and partners. Save the findings to
`data/capture_intel/<OPP-ID>.json`, using these keys: `org_structure`, `current_consultants`, `current_contractors`,
`procurement_pattern`, `competitors`, `incumbents`, `teaming_partners`, and `stakeholders`, where stakeholders maps a role to `{name, stance, owner}`.
Then re-run `python3 -m bd_agent run` so the capture plan picks them up. Use public sources only, and cite them.

## 8. Commit & push
```bash
git add -A ecec_bd_agent && git commit -m "BD intel run <date>: N new, top: <project>" && git push -u origin claude/inspiring-hopper-t95859
```

## 9. Notify
End with a short executive message: new count, top 5 by priority (with recommendation and win %), submissions due within 10 days,
any new APPROVED capture plans, and the 2-3 market developments that matter most to ECEC. Run notifications deliver this message.
