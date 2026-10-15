# Worked test 2 - DDA MIG housing block, Scheme 182A (real traced drawing, 4 floors)

Input: `input/182A_housing_scheme.pdf` - a digitised 1980 DDA standard design, 4 pages: GF+FF plans on one
sheet, SF+TF on the next, terrace plan, elevations. Traced CAD (16k vector paths, glyph outlines as paths,
two plans per sheet, title block says 1:50 but the sheet was reduced). 4 identical mirrored flats per floor.

User decisions (recorded in `project.json` and `output/assumptions.md`):
- Test under **KSA codes / Riyadh climate** (SBC 602 envelope, ASHRAE 62.1); 3.0 m floor-to-floor, 2.75 m ceilings.
- Scale **1:139** from the grid A-J (14.45 m = 104 mm on paper); north = page-up; W1 = 600x600.
- **Mixed system**: ducted split (DS-18) for the open-plan drawing room + dining/lounge, wall split (WS-09) per
  bedroom with the outdoor unit on the facade; kitchens exhaust-only; baths/WCs exhausted to the shafts.
- Rooms that did not read on the GF/SF sheets were copied from the identical floor above (`fill_from_floor.py`).

Run
```bash
S=scripts; W=examples/housing_182A/output
python $S/pdf_reader.py examples/housing_182A/input/182A_housing_scheme.pdf -w $W --scale 139 --north 0 --pages 1,2,3
python $S/fill_from_floor.py -w $W --target GF --source FF
python $S/fill_from_floor.py -w $W --target SF --source TF
python $S/pipeline.py design -w $W && python $S/pipeline.py outputs -w $W && python $S/pipeline.py report -w $W
```
Result: 136 rooms (+16 copied), block peak 48.9 kW over 16 flats, 49 indoor units, 52 exhaust fans,
6 sheets, 5 DXF, 303-line BOQ, all checks PASS. ~2.5 min for the reader on this drawing.

Lessons built into the reader from this drawing: several plans per sheet (split by title), glyph outlines
on ink (label voting), schedule in cells, decimal-metre dimension strings, courtyards/shafts as exterior,
noise cells (title block, grid bubbles) dropped, tolerance on traced areas (12 %).

PRELIMINARY DESIGN - to be checked and stamped by a qualified HVAC engineer. Test data only.
