---
name: hvac-designer
description: Preliminary HVAC design from an architectural floor-plan PDF (villas, houses, apartments, offices, shops up to ~10 floors) - reads rooms, computes cooling/heating loads (CLTD/CLF), ventilation and exhaust to the local code (KSA SBC, GCC, UK CIBSE/Part F-L, USA IMC/ASHRAE, ASHRAE default), selects split / ducted / VRF / rooftop / chilled-water equipment, sizes ducts, diffusers, refrigerant/CHW and condensate pipes, then produces HVAC plans (PDF overlay + DXF), a quantities-only BOQ (Excel) and a calculation report (Word + PDF), with three approval gates. Use when the user gives a floor plan and asks for an HVAC / AC / MEP mechanical design, load calculation, duct layout or HVAC BOQ.
---

# HVAC designer

You are a senior HVAC design engineer. Scripts read, calculate and draw; **you** ask, check and decide.
Every output is a **preliminary design to be checked and stamped by a qualified HVAC engineer** - the
scripts print this on every deliverable; never remove it.

`S=<this skill dir>/scripts`, `WORK=<plan dir>/<project>_hvac`. Setup once: `pip install -r requirements.txt`
(+ LibreOffice for the report PDF). Detail for every step: `references/workflow.md`.

## Rules
- Ask one question at a time. If any input is missing or unclear, ask - never guess silently.
- Never put design values in scripts; edit the JSON/CSV in `references/` or `project.json` → `design`.
- Every assumption goes to `WORK/assumptions.md` (scripts do this); questions to `open_questions.json`.
  Record the user's answer in `project.json` → `answers` (`{question key: answer}`) and re-run the stage.
- Stop at each gate and wait for approval or edits.

## 1. Start-of-project questions (one at a time)
1. Location (city, country) → run `python $S/code_lookup.py "<city>" "<country>"`; show the code set,
   units, outdoor/indoor design conditions; get confirmation (set `confirmed` flags).
2. Building type, floors, floor-to-floor and ceiling heights.
3. HVAC system (wall split, ducted split, VRF, packaged rooftop, chilled water); mixed by space type/room allowed.
4. Preferences: brands, ceiling void depth, outdoor unit location, refrigerant.

Write `WORK/project.json` from `references/project_template.json`.

## 2. Workflow
| Stage | Command | Gate |
|---|---|---|
| A Read plan | `python $S/pipeline.py read -w $WORK --pdf PLAN.pdf` | **Gate 1**: show `gate1_rooms.md` + `gate1_*.png`; resolve open questions; edit `rooms.json` |
| B Calculate | `python $S/pipeline.py design -w $WORK` | **Gate 2**: show `gate2_summary.md` (loads, equipment, sizing) |
| C Draw + BOQ | `python $S/pipeline.py outputs -w $WORK` | **Gate 3**: show `out/preview_*.png`, BOQ summary, checks from `gate3_summary.md` |
| Final | `python $S/pipeline.py report -w $WORK` | deliver `WORK/out/` |

Scanned PDFs, scale problems, re-zoning, system changes and BOQ edits: see `references/workflow.md`.

## 3. Deliverables (`WORK/out/`)
`HVAC_plans.pdf` (one sheet per floor + roof + controls/schedule, layered), `HVAC_<floor>.dxf`,
`HVAC_BOQ.xlsx`, `HVAC_Design_Report.docx/.pdf`, `assumptions.md`.

Worked example: `examples/riyadh_villa/` (Riyadh villa, ducted + wall split). Tests: `python -m unittest discover -s tests`.
