# ECEC BD Intelligence Agent

An autonomous business-development intelligence system for **East Consulting Engineering Company (ecec)**, Riyadh.
Every day it finds consulting opportunities in Saudi Arabia, the UAE and Qatar. It qualifies, risk-scores and ranks them,
then produces an executive report, an Excel register and capture plans.

| You want to… | Do this |
|---|---|
| Read today's report | `output/LATEST_REPORT.md` or `output/reports/<date>/daily_executive_report.pdf` |
| Work the register | `output/opportunities.xlsx` (the Status column has a dropdown) |
| Approve an opportunity | Set Status = `APPROVED` in Excel and commit, **or** run `python3 -m bd_agent set-status OPP-XXXXXXXX APPROVED --note "BD committee"`. This generates `output/capture_plans/OPP-XXXXXXXX.md` |
| Record a result (for learning) | `python3 -m bd_agent set-status OPP-XXXXXXXX WON` (or `LOST`, `NO BID`) |
| See the top of the pipeline | `python3 -m bd_agent list --top 20` |
| Inspect one opportunity | `python3 -m bd_agent show OPP-XXXXXXXX` |
| Change weights or thresholds | Edit `config/scoring_config.json` (each run logs the config hash) |

Statuses: NEW → QUALIFIED → UNDER REVIEW → APPROVED → IN PURSUIT → SUBMITTED → WON / LOST, plus NO BID, CANCELLED and CLOSED.
Items still NEW or QUALIFIED 14 days after their deadline are auto-closed.

## Architecture
```
data/inbox/<date>_<region>.json   ← discovery agents (web research) write raw findings here
        │
bd_agent/pipeline.py   sync Excel statuses → ingest + de-duplicate → filter (GCC, ≥50% technical alignment)
        │              → Fit → Risk → Win → Go/No-Go → rank by return on effort → actions → capture plans
        ▼
data/opportunities.json (database)   data/market_intelligence.json   data/outcomes.json
data/audit_log.jsonl (append-only: every score, override, status change and rejection, with model version and config hash)
output/opportunities.xlsx  (Register · Detailed Risk Register · Market Intelligence · Approved · Scoring Audit · Rejected)
output/reports/<date>/daily_executive_report.{md,pdf}     output/capture_plans/<ID>.md
```
Company knowledge lives in `data/knowledge_base.json`: services, sectors, documented and logo-wall clients, project
references, partners, prequalifications and known gaps. Every entry has a source URL. All scoring reuses it.

## Scoring models
**Fit (0-100)** is the weighted sum of 10 criteria, each scored 0-10 with a written justification. Technical fit (15%), service alignment (15%),
sector experience (10%), client relationship (10%), geographic fit (5%), strategic importance (10%), revenue potential (15%),
resource availability (5%), competitive position (10%) and long-term growth (5%). An item is rejected if technical alignment is below 50%.

**Risk (0-100)** comes from 15 categories, each scored 1-5 (commercial, financial, client credit, technical complexity, contractual,
competition, resource, schedule, supply chain, regulatory, political, market entry, sub-consultant, reputation, payment).
The overall score is (mean − 1) / 4 × 100. If any single category is Very High, the result is floored at Medium.
Bands: 0-30 Low, 31-60 Medium, 61-80 High, 81-100 Critical. Client-specific profiles, such as NEOM funding re-phasing or onerous Aramco/ADNOC terms, are kept in config.

**Win probability** starts from a base rate for the procurement route, shifted in logit space by 8 factors: relationship, prior experience,
framework, competitor presence, capability, market positioning, capacity and partnerships. The shift is capped. Once at least 8 WON/LOST outcomes exist,
it is calibrated against them (Brier score reported).

**Go / No-Go** combines fit, risk, win, profitability (expected value × margin ÷ bid cost = *return on effort*), strategic value and
resource demand. Every decision lists its reasons. The priority ranking orders items by return on effort, tempered by fit, win and risk.

Every criterion is labelled `rule`, `client_profile` or `analyst`. Analyst overrides need a written reason, and they appear in the Excel
*Scoring Audit* sheet and in the audit log.

## Honesty rules
- Nothing is invented. Unknown values stay empty and are listed under *Missing / Uncertain Info*.
- If the fee is unknown, the economics use a labelled placeholder fee by procurement type. The report shows how many items rely on one.
- A fee estimated from capex is scaled for sub-consultancy share and capped at ECEC's addressable capacity.

## Run it
```bash
cd ecec_bd_agent
python3 -m unittest discover tests
python3 -m bd_agent run --date 2026-10-15 --weekly
```
Requires Python 3.11+, `openpyxl` and `reportlab`. The automated daily procedure is in [AGENT.md](AGENT.md).
