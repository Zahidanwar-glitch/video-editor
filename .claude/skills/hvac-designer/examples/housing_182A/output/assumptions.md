# Assumptions log

Generated 2026-10-15. Items marked **confirm** need the engineer's confirmation.

| ID | Step | Assumption | Source | Status |
|---|---|---|---|---|
| A001 | A-read | Window W1 size 600x600 mm given by user (not in schedule) | user | default |
| A002 | A-read | Page 1 scale 1:139.0 (user, confidence high) | scale_detect.py | default |
| A003 | Gate1 | Page 1 TERRACE: measured 6.06 m² vs plan text 7.36 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A004 | Gate1 | Page 1 DINNING /LOUNGE: measured 22.82 m² vs plan text 11.14 m² (>12% difference). Which is right? -> USER ANSWER: drawing room + dining/lounge are open plan - one living zone ~18 m2 (measured) | user | default |
| A005 | Gate1 | Page 1 KITCHEN: measured 4.24 m² vs plan text 4.85 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A006 | Gate1 | Page 1 BATH: measured 1.59 m² vs plan text 1.85 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A007 | Gate1 | Page 1 SHAFT: measured 2.69 m² vs plan text 3.11 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A008 | Gate1 | Page 1 ROOM: measured 7.57 m² vs plan text 9.06 m² (>12% difference). Which is right? -> USER ANSWER: use measured (traced drawing) | user | default |
| A009 | A-read | Page 1: 36 labelled cells ignored as non-rooms (schedule/title/grid text): ['3.TERRACE', 'CB', 'D D A', 'DILSHAD GARDEN', 'DINNING /LOUNGE', 'Digitized By', 'EAST ZONE, VIKAS MINAR, D.D.A.', 'FG1', 'GROUND AND FIRST', 'JAHANGIRPURI', 'PASHCHIM PURI', 'PITAMPURA (D&P)', 'SHALIMAR BHAGH (P)', 'STANDARD DESIGN FOR MIG', 'Sch.no. 182A'] | pdf_reader.py | default |
| A010 | Gate1 | Page 1: 15 enclosed space(s) without a name (areas m²: [1.61, 1.71, 1.71, 3.26, 2.23, 1.71, 1.7, 1.7, 1.7, 2.26, 3.29, 1.71, 1.71, 2.66, 1.61]). Name them or confirm they are voids. -> USER ANSWER: small unnamed spaces are flat entrance lobbies/passages - not cooled, transfer air | user | default |
| A011 | A-read | Page 1: 'GROUND FLOOR PLAN' plan separated from the other plan(s) on the sheet by nearest title | pdf_reader.py | default |
| A012 | A-read | Page 1: 'FIRST  FLOOR PLAN' plan separated from the other plan(s) on the sheet by nearest title | pdf_reader.py | default |
| A013 | A-read | Page 2 scale 1:139.0 (user, confidence high) | scale_detect.py | default |
| A014 | Gate1 | Page 2 ROOM: measured 10.18 m² vs plan text 9.06 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A015 | Gate1 | Page 2 DINNING /LOUNGE: measured 22.92 m² vs plan text 11.14 m² (>12% difference). Which is right? -> USER ANSWER: same - one living zone | user | default |
| A016 | Gate1 | Page 2 KITCHEN: measured 5.74 m² vs plan text 4.85 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A017 | Gate1 | Page 2: one enclosed space carries several names ['SHAFT', 'SHAFT'] - an opening may be unsealed. Split or confirm. -> USER ANSWER: two shaft labels in one light well - one shaft | user | default |
| A018 | Gate1 | Page 2 TERRACE: measured 9.24 m² vs plan text 7.36 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A019 | Gate1 | Page 2 SHAFT: measured 3.65 m² vs plan text 3.11 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A020 | Gate1 | Page 2 BATH: measured 2.08 m² vs plan text 1.85 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A021 | A-read | Page 2: 33 labelled cells ignored as non-rooms (schedule/title/grid text): ['CB', 'D D A', 'DILSHAD GARDEN', 'Digitized By', 'EAST ZONE, VIKAS MINAR, D.D.A.', 'FG1', 'JAHANGIRPURI', 'PASHCHIM PURI', 'PITAMPURA (D&P)', 'SECOND AND THIRD', 'SHALIMAR BHAGH (P)', 'STANDARD DESIGN FOR MIG', 'Sch.no. 182A', 'TERRACE', 'WING'] | pdf_reader.py | default |
| A022 | Gate1 | Page 2: 9 enclosed space(s) without a name (areas m²: [2.41, 2.42, 3.46, 3.53, 3.7, 3.44, 3.52, 2.42, 2.42]). Name them or confirm they are voids. -> USER ANSWER: same - passages | user | default |
| A023 | A-read | Page 2: 'SECOND FLOOR PLAN' plan separated from the other plan(s) on the sheet by nearest title | pdf_reader.py | default |
| A024 | A-read | Page 2: 'THIRD FLOOR PLAN' plan separated from the other plan(s) on the sheet by nearest title | pdf_reader.py | default |
| A025 | A-read | Page 3 scale 1:139.0 (user, confidence high) | scale_detect.py | default |
| A026 | Gate1 | Page 3 SHAFT: measured 3.65 m² vs plan text 3.11 m² (>12% difference). Which is right? -> USER ANSWER: use measured | user | default |
| A027 | A-read | Page 3: 22 labelled cells ignored as non-rooms (schedule/title/grid text): ['D D A', 'Digitized By', 'SLOPE', 'STANDARD DESIGN FOR MIG', 'Sch.no. 182A', 'WING', 'WITH SA VIDE LETTER NO.ACE/D/III/S.D/9/E', 'add. ch. arch.', 'arch. asstt.', 'asstt. arch.', 'asstt. dir.', 'chief arch.', 'deputy director'] | pdf_reader.py | default |
| A028 | Gate1 | Page 3: 8 enclosed space(s) without a name (areas m²: [2.4, 2.32, 3.5, 2.91, 2.29, 2.13, 3.53, 2.42]). Name them or confirm they are voids. -> USER ANSWER: same - passages / mumty | user | default |
| A029 | Gate1 | Second Floor: 4 rooms copied from Third Floor where the plan did not read (typical flats): SF-34 BALCONY (TF-02), SF-35 BALCONY (TF-03), SF-36 BALCONY (TF-32), SF-37 BALCONY (TF-33) | user instruction | **confirm** |
| A030 | B-loads | Outdoor design 45.6 °C DB / 19.4 °C MCWB (0.4 %), daily range 14.6 K, heating 6.6 °C (99.6 %), elevation 612.0 m (ASHRAE 2021 Ch.14 (0.4% cool / 99.6% heat) - OERK, approximate - verify) | references/climate_data.csv | default |
| A031 | B-loads | Indoor design 24.0 °C / 50 % RH cooling, 21.0 °C heating | SBC 602 §302 / SBC 601 §302.1 (design conditions); ASHRAE Fundamentals 2021 Ch.14 (0.4 % cooling, 99.6 % heating) | default |
| A032 | B-loads | Envelope U-values = code maximum (SBC602: wall 0.4, roof 0.2, glazing U 2.67 / SHGC 0.25 W/m²K) - actual build-up not given | SBC 602 Ch.4 prescriptive envelope table / SBC 601 Ch.5 (max U-factor, SHGC) | **confirm** |
| A033 | B-loads | Cooling loads by CLTD/SCL/CLF; CLTD tables for wall group D, roof 'roof_insulated_concrete', latitude row nearest 24.71°, July; colour factor K=0.83 (medium walls), roof K=1.0; glass with interior shading=True | ASHRAE Fundamentals 1997 Ch.28 CLTD/SCL/CLF method, Tables 30-36 | **confirm** |
| A034 | B-loads | CLTD/LM/SHGF/CLF tables in references/cltd_tables.json are transcribed-approximate - verify against licensed ASHRAE 1997 Ch.28 tables | references/cltd_tables.json | **confirm** |
| A035 | B-loads | CLF for people/lights/equipment = 1.0 (24 h operation, no storage credit) | ASHRAE Fundamentals 1997 Ch.28 CLTD/SCL/CLF method, Tables 30-36 | default |
| A036 | B-loads | Partitions/floors between conditioned and exhaust-only rooms (baths, stores) not counted: those rooms are near room temperature | designer judgement | default |
| A037 | B-loads | Outdoor humidity ratio 4.4 g/kg < indoor 10.0 g/kg at design: outdoor-air latent load taken as 0 (conservative); check a dehumidification design day | ASHRAE Fundamentals 2021 Ch.14 (DP design) | **confirm** |
| A038 | B-loads | Conditioned/unconditioned overrides from the user: by type {'kitchen': False}, by room {} | user instruction | default |
| A039 | B-loads | Supply air 13.0 °C (room-supply ΔT 11.0 K) for airflow | designer default | default |
| A040 | B-loads | Infiltration by air-change method: {'one_exterior_side': 0.5, 'two_plus_exterior_sides': 0.75, 'no_exterior': 0.0} ACH (residential) | ASHRAE Fundamentals 2021 Ch.16 §'Residential air change method' | default |
| A041 | B-loads | Occupancy, lighting and equipment densities from references/space_types.json | ASHRAE Fundamentals 2021 Ch.18 Table 1 (people), Tables 2-3 (lighting), Tables 5-9 (equipment) | default |
| A042 | B-zoning | Zoning: own zone for ['majlis', 'master_bedroom']; other ducted rooms grouped by position per floor up to 17.6 kW per unit (incl. safety factor) | references/design_defaults.json zoning | **confirm** |
| A043 | B-zoning | Rooms exhaust-only (not cooled; make-up by transfer air): GF-04, GF-05, GF-06, GF-08, GF-09, GF-17, GF-18, GF-19, GF-21, GF-22, GF-23, GF-33, GF-34, GF-36, GF-37, FF-07, FF-08, FF-09, FF-11, FF-12, FF-13, FF-18, FF-19, FF-20, FF-22, FF-23, FF-24, SF-05, SF-07, SF-09, SF-11, SF-12, SF-13, SF-14, SF-20, SF-21, SF-23, SF-25, SF-27, SF-29, TF-07, TF-09, TF-11, TF-13, TF-14, TF-15, TF-19, TF-20, TF-22, TF-24, TF-26, TF-28 | references/space_types.json | **confirm** |
| A044 | B-vent | Zone air distribution effectiveness Ez = 0.8 (heat-pump heating with ceiling supply of warm air) | ASHRAE 62.1-2019 §6.2.2.2 Table 6-2 (Ez) | default |
| A045 | B-vent | Exhaust fans sized for the intermittent (rated) rate; continuous operation would allow the lower rate | SBC 501 Table 403.3.1.1 (toilet rooms, private dwellings: 25 L/s intermittent or 10 L/s continuous) | default |
| A046 | B-vent | Building OA 891 L/s < exhaust 1725 L/s (intermittent): building slightly negative when all fans run; acceptable for intermittent fans, else raise OA | designer judgement | **confirm** |
| A047 | B-equip | Safety factor 10% on cooling and 10% on heating, applied to coil loads at selection (shown in tables) | Designer allowance - not a code requirement | **confirm** |
| A048 | B-equip | Nominal (T1) capacities derated x0.88 for 45.6 °C outdoor design (T3) - replace with brand T3 data | references/equipment_catalog.json t3_derate | **confirm** |
| A049 | B-equip | Equipment from GENERIC catalogue (references/equipment_catalog.json) - replace with the approved brand | references/equipment_catalog.json | **confirm** |
| A050 | B-equip | Minimum supply per served room 30 L/s (smallest diffuser) | references/air_terminals.json | default |
| A051 | B-equip | IU-GF-01 (WS-09) is 194 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A052 | B-equip | IU-GF-02 (WS-09) is 215 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A053 | B-equip | IU-GF-03 (WS-09) is 193 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A054 | B-equip | IU-GF-04 (WS-09) is 184 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A055 | B-equip | IU-GF-05 (WS-09) is 192 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A056 | B-equip | IU-GF-06 (WS-09) is 226 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A057 | B-equip | IU-GF-07 (WS-09) is 204 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A058 | B-equip | IU-GF-08 (WS-09) is 178 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A059 | B-equip | IU-GF-09 (DS-18) is 76 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A060 | B-equip | Z-GF-09: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (GF-25) ceiling void, access panel required | designer judgement | **confirm** |
| A061 | B-equip | IU-GF-10 (DS-18) is 72 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A062 | B-equip | Z-GF-10: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (GF-26) ceiling void, access panel required | designer judgement | **confirm** |
| A063 | B-equip | IU-GF-11 (DS-18) is 81 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A064 | B-equip | Z-GF-11: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (GF-31) ceiling void, access panel required | designer judgement | **confirm** |
| A065 | B-equip | IU-GF-12 (DS-18) is 78 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A066 | B-equip | Z-GF-12: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (GF-32) ceiling void, access panel required | designer judgement | **confirm** |
| A067 | B-equip | IU-FF-01 (WS-09) is 95 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A068 | B-equip | IU-FF-02 (WS-09) is 129 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A069 | B-equip | IU-FF-03 (WS-09) is 178 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A070 | B-equip | IU-FF-04 (WS-09) is 192 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A071 | B-equip | IU-FF-05 (WS-09) is 177 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A072 | B-equip | IU-FF-06 (WS-09) is 191 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A073 | B-equip | IU-FF-07 (WS-09) is 97 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A074 | B-equip | IU-FF-08 (WS-09) is 131 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A075 | B-equip | IU-FF-09 (DS-18) is 81 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A076 | B-equip | Z-FF-09: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (FF-04) ceiling void, access panel required | designer judgement | **confirm** |
| A077 | B-equip | IU-FF-10 (DS-18) is 78 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A078 | B-equip | Z-FF-10: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (FF-05) ceiling void, access panel required | designer judgement | **confirm** |
| A079 | B-equip | IU-FF-11 (DS-18) is 76 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A080 | B-equip | Z-FF-11: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (FF-26) ceiling void, access panel required | designer judgement | **confirm** |
| A081 | B-equip | IU-FF-12 (DS-18) is 76 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A082 | B-equip | Z-FF-12: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (FF-27) ceiling void, access panel required | designer judgement | **confirm** |
| A083 | B-equip | IU-SF-01 (WS-09) is 150 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A084 | B-equip | IU-SF-02 (WS-09) is 157 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A085 | B-equip | IU-SF-03 (WS-09) is 217 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A086 | B-equip | IU-SF-04 (WS-09) is 130 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A087 | B-equip | IU-SF-05 (WS-09) is 153 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A088 | B-equip | IU-SF-06 (WS-09) is 130 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A089 | B-equip | IU-SF-07 (WS-09) is 152 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A090 | B-equip | IU-SF-08 (WS-09) is 132 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A091 | B-equip | IU-SF-09 (WS-09) is 138 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A092 | B-equip | Z-SF-10: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (SF-06) ceiling void, access panel required | designer judgement | **confirm** |
| A093 | B-equip | Z-SF-11: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (SF-10) ceiling void, access panel required | designer judgement | **confirm** |
| A094 | B-equip | Z-SF-12: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (SF-24) ceiling void, access panel required | designer judgement | **confirm** |
| A095 | B-equip | Z-SF-13: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (SF-28) ceiling void, access panel required | designer judgement | **confirm** |
| A096 | B-equip | IU-TF-01 (WS-09) is 98 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A097 | B-equip | IU-TF-02 (WS-09) is 118 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A098 | B-equip | IU-TF-03 (WS-09) is 116 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A099 | B-equip | IU-TF-04 (WS-09) is 137 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A100 | B-equip | IU-TF-05 (WS-09) is 115 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A101 | B-equip | IU-TF-06 (WS-09) is 135 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A102 | B-equip | IU-TF-07 (WS-09) is 99 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A103 | B-equip | IU-TF-08 (WS-09) is 103 % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit | designer note | **confirm** |
| A104 | B-equip | Z-TF-09: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (TF-08) ceiling void, access panel required | designer judgement | **confirm** |
| A105 | B-equip | Z-TF-10: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (TF-12) ceiling void, access panel required | designer judgement | **confirm** |
| A106 | B-equip | Z-TF-11: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (TF-23) ceiling void, access panel required | designer judgement | **confirm** |
| A107 | B-equip | Z-TF-12: no corridor/service room next to the zone - ducted unit in the DINNING /LOUNGE (TF-27) ceiling void, access panel required | designer judgement | **confirm** |
| A108 | B-equip | Wall-split outdoor units on brackets on the facade/courtyard wall just outside the served room (architect to approve appearance); ducted-unit ODUs on the roof | user preference | **confirm** |
| A109 | B-equip | Outdoor units grouped on the roof near the riser/shaft with 0.6 m service clearance; check structure, parapet height and acoustic screening | designer judgement | **confirm** |
| A110 | B-ducts | Ducts sized by equal friction 0.8 Pa/m with velocity limits {'main': 5.0, 'branch': 3.5, 'runout': 2.5, 'return': 3.5, 'fresh_air': 4.0, 'exhaust': 4.0} m/s; max duct depth 250 mm from ceiling void | ASHRAE Fundamentals 2021 Ch.21 (equal friction method, Eq.18-19 Altshul-Tsal) | default |
| A111 | B-ducts | Fittings allowed as +50% equivalent length; unit plenum/filter 40.0 Pa | designer default | **confirm** |
| A112 | B-ducts | Duct routes are schematic trunk-and-branch lines over the plan; coordinate with structure (beams), lighting and other services | designer judgement | **confirm** |
| A113 | B-ducts | Return air from rooms via door undercut / door transfer grilles to the return grille near the unit | ASHRAE Fundamentals 2021 Ch.21 (equal friction method, Eq.18-19 Altshul-Tsal) | **confirm** |
| A114 | B-pipes | Refrigerant pipe sizes from GENERIC table (references/pipe_sizing.json) - replace with the selected brand's table | SBC 501 Ch.11 §1107 (refrigerant piping); ASHRAE 15; manufacturer piping tables | **confirm** |
| A115 | B-pipes | Refrigerant length = route x (1+10%) + vertical rise to roof (+1.5 m allowance) | designer default | default |
| A116 | B-pipes | Condensate to nearest wet-room floor drain / stack with trap; min 25 mm, slope 1.0 % | SBC 501 §307.2.1 (disposal), §307.2.2 Table 307.2.2 (drain size), slope >= 1 % | **confirm** |
