# hvac-designer - detailed workflow

## Files in the work directory
| File | Written by | Edit at gate? |
|---|---|---|
| `project.json` | you (Claude) from the start questions | yes - systems, heights, preferences, `design` overrides, `answers` |
| `rooms.json` | `pdf_reader.py` | **Gate 1** - names, types, areas, heights, windows, exterior walls, `is_conditioned`, `occupants_override`, `fixtures` |
| `loads.json`, `zones.json`, `ventilation.json` | B scripts | no - change inputs and re-run |
| `design.json` | `equipment_select` → `duct_sizing` → `pipe_sizing` | no - use `zones_override` / `systems.by_room` / `design` overrides |
| `assumptions.md/json`, `open_questions.json` | all scripts | answer via `project.json.answers` |
| `gate1_rooms.md`, `gate2_summary.md`, `gate3_summary.md`, `checks.md` | gates | show to user |
| `out/` | C scripts | deliverables |

Re-running a script clears its own earlier questions/assumptions, so the logs always match the current design.

## Start questions - what to do with each answer
1. **Location** → `code_lookup.py`. Not found → code set `DEFAULT` (ASHRAE) - tell the user and confirm.
   City missing from `climate_data.csv` → ask for 0.4 % DB/MCWB, daily range, 99.6 % heating DB, elevation, latitude
   and put them in `project.json.design_conditions` (`cool_db_c`, `cool_mcwb_c`, `daily_range_k`, `heat_db_c`, `elev_m`, `lat`).
   Indoor overrides: `design_conditions.indoor`. Set `project.confirmed.codes/design_conditions = true` once confirmed.
2. **Building** → `building_type` (residential types use residential rules), `floors[]` with ids matching plan titles
   (GF, FF, SF, TF, L4…, B1, RF). Heights per floor.
3. **System** → `systems.default`; mixed: `systems.by_space_type` (e.g. `{"maid_room": "wall_split"}`) or `systems.by_room`.
   Custom zones: `zones_override: [{"rooms": ["GF-01","GF-02"], "system": "ducted_split"}]`.
4. **Preferences** → `preferences`. A brand → ask for its catalogue/piping table and replace the generic entries in
   `equipment_catalog.json`, `air_terminals.json`, `pipe_sizing.json` (keep keys).

## Step A - read the plan (Gate 1)
- Vector PDF: rooms = enclosed spaces between wall linework (door arcs seal doorways); names from text inside;
  areas measured (and cross-checked with area text); windows from W-tags + window schedule; exterior walls by probing
  outward to the building exterior; orientation from the north arrow; roof exposure from the floor above's footprint.
- Scale: title block "SCALE 1:n" cross-checked with dimension strings. Low confidence → ask; re-run with `--scale n`.
  North not found → ask; re-run with `--north deg` (clockwise from page-up).
- **Scanned PDF** (`needs_vision`): open `WORK/pages/page_N.png`, read it visually, ask for a known dimension to fix the
  scale, then write the floor into `rooms.json` by hand with the same fields (`id, name, space_type, area_m2,
  bbox_pt, centroid_pt, polygon_pt, edges[], exterior_walls[], windows[], roof_exposed_frac, height_m, is_conditioned`),
  `mm_per_pt`, `scale`, `north_deg`, `page_size_pt`. Polygons in page points of the PNG's PDF page.
- Show `gate1_rooms.md` as a table and the `gate1_<floor>.png` images. Ask each open question. Apply edits to
  `rooms.json` (e.g. fix a space type, mark a room unconditioned, add a missing window). Wait for approval.

## Step B - calculations (Gate 2)
- `loads.py`: CLTD/SCL/CLF per room, hours 8-20; room peak → airflow (supply ΔT from `design_defaults`), block peak
  for zones. Heating steady state. US homes → raises the Manual J question (CLTD is preliminary only).
- `zoning.py`: system per room, ducted rooms grouped per floor ≤ max unit size; own-zone types; exhaust-only rooms.
- `ventilation.py`: 62.1 VRP per zone (or ADF for UK), exhaust per room; transfer air for rooms without exterior wall.
- `equipment_select.py`: coil load = rooms + OA, × safety factor, T3 derate; smallest unit meeting total, sensible,
  airflow; outdoor units on the roof near the shaft; thermostats.
- `duct_sizing.py`: diffusers by flow/NC/coverage, trunk-and-branch layout avoiding shafts/stairs/columns, equal
  friction sizing, ESP check, return + fresh-air louver, exhaust fans/ducts/louvers.
- `pipe_sizing.py`: refrigerant/CHW runs and sizes, length/height limits, condensate drains.
- Present `gate2_summary.md`: load summary (W/m² sanity), equipment list with SF shown, duct/diffuser/pipe tables,
  open questions (OA fraction, oversize, ESP, conflicts). Changes → edit `project.json` and re-run `design`.

## Step C - drawings, BOQ, checks (Gate 3)
- `drawing_overlay.py`: sheet per floor (+ roof, + controls/schedule M-901), architectural background faded,
  HVAC on PDF layers named as the DXF layers; legend, schedule, north arrow, scale, title block, preliminary note.
- `dxf_export.py`: real-world mm, layers M-DUCT-SUPP/RETN/FRSH/EXHS, M-PIPE-REFG/CHWS/COND, M-EQPM, M-CTRL, M-ANNO, A-ARCH-REF.
- `boq.py`: quantities only, sections A-L, waste % column editable (formula column).
- `checks.py`: every room served, no unresolved crossings, airflow balance, tags unique, every drawn tag in BOQ,
  ESP, refrigerant limits, NC, OA fraction, open questions. Any FAIL → fix before Gate 3.
- Show 1-2 `out/preview_M-10x.png` sheets, the BOQ section summary and the checks. Wait for approval.

## Final
`pipeline.py report` → Word report (design basis, codes, conditions, envelope, internal loads, assumptions, room
schedule, loads with worked example, ventilation/exhaust, equipment, ducts, terminals, pipes, checks, clause register)
converted to PDF with LibreOffice. Tell the user what still needs their confirmation (items marked **confirm** in
`assumptions.md`).

## Limits to state to the user
- Reference data marked "approximate - verify" (CLTD tables, climate rows, code U-values, generic catalogues) must be
  checked against licensed code editions and the chosen brand.
- Duct/pipe routes are schematic: structure (beams), lighting and other services are not on the architectural plan.
- Fire dampers / compartmentation, electrical power and BMS integration are outside this preliminary package.
