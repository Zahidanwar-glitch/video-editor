# Assumptions log

Generated 2026-10-15. Items marked **confirm** need the engineer's confirmation.

| ID | Step | Assumption | Source | Status |
|---|---|---|---|---|
| A001 | A-read | Page 1 scale 1:100 (title+dimensions, confidence high) | scale_detect.py | default |
| A002 | A-read | Page 1 north = 19.6 deg clockwise from page-up (detected from north arrow) | pdf_reader.py | default |
| A003 | A-read | Page 2 scale 1:100 (title+dimensions, confidence high) | scale_detect.py | default |
| A004 | A-read | Page 2 north = 19.6 deg clockwise from page-up (detected from north arrow) | pdf_reader.py | default |
| A005 | A-read | Page 3 scale 1:100 (title+dimensions, confidence high) | scale_detect.py | default |
| A006 | A-read | Page 3 north = 19.6 deg clockwise from page-up (detected from north arrow) | pdf_reader.py | default |
| A007 | B-loads | Outdoor design 45.6 °C DB / 19.4 °C MCWB (0.4 %), daily range 14.6 K, heating 6.6 °C (99.6 %), elevation 612.0 m (ASHRAE 2021 Ch.14 (0.4% cool / 99.6% heat) - OERK, approximate - verify) | references/climate_data.csv | default |
| A008 | B-loads | Indoor design 24.0 °C / 50 % RH cooling, 21.0 °C heating | SBC 602 §302 / SBC 601 §302.1 (design conditions); ASHRAE Fundamentals 2021 Ch.14 (0.4 % cooling, 99.6 % heating) | default |
| A009 | B-loads | Envelope U-values = code maximum (SBC602: wall 0.4, roof 0.2, glazing U 2.67 / SHGC 0.25 W/m²K) - actual build-up not given | SBC 602 Ch.4 prescriptive envelope table / SBC 601 Ch.5 (max U-factor, SHGC) | **confirm** |
| A010 | B-loads | Cooling loads by CLTD/SCL/CLF; CLTD tables for wall group D, roof 'roof_insulated_concrete', latitude row nearest 24.71°, July; colour factor K=0.83 (medium walls), roof K=1.0; glass with interior shading=True | ASHRAE Fundamentals 1997 Ch.28 CLTD/SCL/CLF method, Tables 30-36 | **confirm** |
| A011 | B-loads | CLTD/LM/SHGF/CLF tables in references/cltd_tables.json are transcribed-approximate - verify against licensed ASHRAE 1997 Ch.28 tables | references/cltd_tables.json | **confirm** |
| A012 | B-loads | CLF for people/lights/equipment = 1.0 (24 h operation, no storage credit) | ASHRAE Fundamentals 1997 Ch.28 CLTD/SCL/CLF method, Tables 30-36 | default |
| A013 | B-loads | Partitions/floors between conditioned and exhaust-only rooms (baths, stores) not counted: those rooms are near room temperature | designer judgement | default |
| A014 | B-loads | Outdoor humidity ratio 4.4 g/kg < indoor 10.0 g/kg at design: outdoor-air latent load taken as 0 (conservative); check a dehumidification design day | ASHRAE Fundamentals 2021 Ch.14 (DP design) | **confirm** |
| A015 | B-loads | Supply air 13.0 °C (room-supply ΔT 11.0 K) for airflow | designer default | default |
| A016 | B-loads | Infiltration by air-change method: {'one_exterior_side': 0.5, 'two_plus_exterior_sides': 0.75, 'no_exterior': 0.0} ACH (residential) | ASHRAE Fundamentals 2021 Ch.16 §'Residential air change method' | default |
| A017 | B-loads | Occupancy, lighting and equipment densities from references/space_types.json | ASHRAE Fundamentals 2021 Ch.18 Table 1 (people), Tables 2-3 (lighting), Tables 5-9 (equipment) | default |
| A018 | B-zoning | Zoning: own zone for ['majlis', 'master_bedroom']; other ducted rooms grouped by position per floor up to 17.6 kW per unit (incl. safety factor) | references/design_defaults.json zoning | **confirm** |
| A019 | B-zoning | Rooms exhaust-only (not cooled; make-up by transfer air): GF-09, GF-11, GF-13, FF-01, FF-02, FF-12, FF-14 | references/space_types.json | **confirm** |
| A020 | B-vent | Z-GF-01 (KITCHEN) has no exterior wall: its 14 L/s OA is supplied via Z-GF-04 and transferred | SBC 501 §403.3.1.1 & Table 403.3.1.1; ASHRAE 62.1-2019 §6.2.2.1 Eq.6-1, Table 6-1 | **confirm** |
| A021 | B-vent | Zone air distribution effectiveness Ez = 0.8 (heat-pump heating with ceiling supply of warm air) | ASHRAE 62.1-2019 §6.2.2.2 Table 6-2 (Ez) | default |
| A022 | B-vent | Exhaust fans sized for the intermittent (rated) rate; continuous operation would allow the lower rate | SBC 501 Table 403.3.1.1 (toilet rooms, private dwellings: 25 L/s intermittent or 10 L/s continuous) | default |
| A023 | B-equip | Safety factor 10% on cooling and 10% on heating, applied to coil loads at selection (shown in tables) | Designer allowance - not a code requirement | **confirm** |
| A024 | B-equip | Nominal (T1) capacities derated x0.88 for 45.6 °C outdoor design (T3) - replace with brand T3 data | references/equipment_catalog.json t3_derate | **confirm** |
| A025 | B-equip | Equipment from GENERIC catalogue (references/equipment_catalog.json) - replace with the approved brand | references/equipment_catalog.json | **confirm** |
| A026 | B-equip | Minimum supply per served room 30 L/s (smallest diffuser) | references/air_terminals.json | default |
| A027 | B-equip | GF-06 KITCHEN has no exterior wall: wall split on interior wall, refrigerant/condensate run in ceiling | designer judgement | **confirm** |
| A028 | B-equip | IU-GF-02 (WS-09) is 141 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A029 | B-equip | Z-GF-03 indoor unit in the ceiling void of GF-02 ENTRANCE HALL (service space next to the zone) | references/design_defaults.json unit_host_preference | **confirm** |
| A030 | B-equip | Z-GF-04: sensible capacity governs (8.2 kW sensible at catalogue SHR) - DS-48 chosen instead of DS-36; brand data at actual (dry) entering conditions may allow the smaller unit | designer note | **confirm** |
| A031 | B-equip | Z-GF-04 indoor unit in the ceiling void of GF-04 CORRIDOR (service space next to the zone) | references/design_defaults.json unit_host_preference | **confirm** |
| A032 | B-equip | IU-FF-01 (DS-24) is 127 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A033 | B-equip | Z-FF-01 indoor unit in the ceiling void of FF-04 DRESSING (service space next to the zone) | references/design_defaults.json unit_host_preference | **confirm** |
| A034 | B-equip | Z-FF-02 indoor unit in the ceiling void of FF-07 LOBBY (service space next to the zone) | references/design_defaults.json unit_host_preference | **confirm** |
| A035 | B-equip | Outdoor units grouped on the roof near the riser/shaft with 0.6 m service clearance; check structure, parapet height and acoustic screening | designer judgement | **confirm** |
| A036 | B-ducts | Ducts sized by equal friction 0.8 Pa/m with velocity limits {'main': 5.0, 'branch': 3.5, 'runout': 2.5, 'return': 3.5, 'fresh_air': 4.0, 'exhaust': 4.0} m/s; max duct depth 300 mm from ceiling void | ASHRAE Fundamentals 2021 Ch.21 (equal friction method, Eq.18-19 Altshul-Tsal) | default |
| A037 | B-ducts | Fittings allowed as +50% equivalent length; unit plenum/filter 40.0 Pa | designer default | **confirm** |
| A038 | B-ducts | Duct routes are schematic trunk-and-branch lines over the plan; coordinate with structure (beams), lighting and other services | designer judgement | **confirm** |
| A039 | B-ducts | Return air from rooms via door undercut / door transfer grilles to the return grille near the unit | ASHRAE Fundamentals 2021 Ch.21 (equal friction method, Eq.18-19 Altshul-Tsal) | **confirm** |
| A040 | B-pipes | Refrigerant pipe sizes from GENERIC table (references/pipe_sizing.json) - replace with the selected brand's table | SBC 501 Ch.11 §1107 (refrigerant piping); ASHRAE 15; manufacturer piping tables | **confirm** |
| A041 | B-pipes | Refrigerant length = route x (1+10%) + vertical rise to roof (+1.5 m allowance) | designer default | default |
| A042 | B-pipes | Condensate to nearest wet-room floor drain / stack with trap; min 25 mm, slope 1.0 % | SBC 501 §307.2.1 (disposal), §307.2.2 Table 307.2.2 (drain size), slope >= 1 % | **confirm** |
