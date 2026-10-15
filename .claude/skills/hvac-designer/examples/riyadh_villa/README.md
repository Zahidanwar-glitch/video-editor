# Worked test - sample villa, Riyadh (ducted split + wall split)

Inputs
- `sample_villa.pdf` - 3-page vector plan (ground, first, roof), A3 at 1:100, north 20° from page-up,
  16 x 12 m villa. Regenerate with `python make_sample_villa.py sample_villa.pdf`.
- `project.json` - answers to the start questions: Riyadh, KSA (SBC + ASHRAE, SI); villa, 2 floors,
  3.6 m floor-to-floor, 3.0 m ceilings; ducted split by default, wall split for kitchen and maid room;
  450 mm ceiling void; outdoor units on the roof.

Run (from the skill folder)
```bash
mkdir -p W && cp examples/riyadh_villa/project.json W/
python scripts/pipeline.py read    -w W --pdf examples/riyadh_villa/sample_villa.pdf   # Gate 1
python scripts/pipeline.py design  -w W                                              # Gate 2
python scripts/pipeline.py outputs -w W                                              # Gate 3
python scripts/pipeline.py report  -w W                                              # final
```
`output/` holds the result of the same run without stops (`pipeline.py all`).

Results (`output/`)
- Gate 1 `gate1_rooms.md`, `gate1_GF.png`, `gate1_FF.png`: 27 rooms + roof read; areas within 3 % of the plan text;
  orientations and windows correct; scale 1:100 found by title block and dimensions.
- Gate 2 `gate2_summary.md`: block peak 20.5 kW (70 W/m² - low because SBC 602 maximum U-values and SHGC 0.25 were
  used as the envelope); 4 ducted splits + 2 wall splits; 8 exhaust fans.
- Gate 3 `gate3_summary.md`: sheets M-101/102/103 + controls M-901, DXF per floor, 105-line BOQ, all checks PASS.
- Final `out/`: `HVAC_plans.pdf`, `HVAC_GF/FF/RF.dxf`, `HVAC_BOQ.xlsx`, `HVAC_Design_Report.docx/.pdf`, `assumptions.md`.

This is test data. Like every output of the skill it is a PRELIMINARY DESIGN to be checked and stamped by a
qualified HVAC engineer.
