# Gate 2 - loads, equipment and sizing (please review)

Block cooling peak **20.8 kW** at 17:00 over 288.5 m² (72 W/m²); heating 5.6 kW. Safety factor 10% applied at selection; T3 derate x0.88.

## Room loads

| Room | Name | Sens W | Lat W | Total W | W/m² | Peak | Supply |
|---|---|---|---|---|---|---|---|
| GF-01 | MAJLIS | 2426 | 495 | 2921 | 106.3 | 18:00 | 193 L/s |
| GF-02 | ENTRANCE HALL | 453 | 45 | 498 | 30.1 | 15:00 | 36 L/s |
| GF-03 | LIVING | 2457 | 360 | 2817 | 94.2 | 15:00 | 195 L/s |
| GF-04 | CORRIDOR | 43 | 0 | 43 | 6.0 | 8:00 | 3 L/s |
| GF-05 | DINING | 1757 | 405 | 2162 | 102.4 | 18:00 | 140 L/s |
| GF-06 | KITCHEN | 2494 | 460 | 2954 | 134.8 | 8:00 | 198 L/s |
| GF-07 | MAID ROOM | 573 | 25 | 598 | 46.5 | 15:00 | 46 L/s |
| GF-08 | STAIR | 270 | 0 | 270 | 21.6 | 16:00 | 22 L/s |
| FF-03 | MASTER BEDROOM | 1891 | 50 | 1941 | 70.6 | 18:00 | 150 L/s |
| FF-04 | DRESSING | 81 | 0 | 81 | 14.2 | 17:00 | 6 L/s |
| FF-05 | BEDROOM 2 | 1035 | 50 | 1085 | 51.2 | 15:00 | 82 L/s |
| FF-07 | LOBBY | 88 | 0 | 88 | 12.2 | 17:00 | 7 L/s |
| FF-08 | BEDROOM 3 | 499 | 50 | 549 | 27.8 | 17:00 | 40 L/s |
| FF-09 | BEDROOM 4 | 1023 | 50 | 1073 | 83.3 | 9:00 | 81 L/s |
| FF-10 | FAMILY LIVING | 3259 | 405 | 3664 | 113.6 | 18:00 | 259 L/s |
| FF-11 | STAIR | 345 | 0 | 345 | 27.7 | 16:00 | 27 L/s |

## Zones and equipment

| Zone | Rooms | System | Required | Selected | Derated | Airflow | OA | Host |
|---|---|---|---|---|---|---|---|---|
| Z-GF-01 | GF-06 | wall_split | 3.6 kW | IU-GF-01 WS-18 | 4.7 kW | 250 L/s | 14 L/s (6%) | GF-06 |
| Z-GF-02 | GF-07 | wall_split | 0.9 kW | IU-GF-02 WS-09 | 2.3 kW | 140 L/s | 8 L/s (6%) | GF-07 |
| Z-GF-03 | GF-01 | ducted_split | 4.3 kW | IU-GF-03 DS-24 | 6.2 kW | 380 L/s | 45 L/s (12%) | GF-02 |
| Z-GF-04 | GF-05, GF-08, GF-04, GF-02, GF-03 | ducted_split | 9.1 kW | IU-GF-04 DS-48 | 12.3 kW | 750 L/s | 106 L/s (14%) | GF-04 |
| Z-FF-01 | FF-03, FF-04 | ducted_split | 2.7 kW | IU-FF-01 DS-18 | 4.7 kW | 300 L/s | 20 L/s (7%) | FF-04 |
| Z-FF-02 | FF-10, FF-11, FF-07, FF-08, FF-05, FF-09 | ducted_split | 9.7 kW | IU-FF-02 DS-48 | 12.3 kW | 750 L/s | 92 L/s (12%) | FF-07 |

| Outdoor | Model | Serves | Capacity |
|---|---|---|---|
| ODU-01 | WS-O-18 | IU-GF-01 | 5.3 kW |
| ODU-02 | WS-O-09 | IU-GF-02 | 2.6 kW |
| ODU-03 | DS-O-24 | IU-GF-03 | 7.0 kW |
| ODU-04 | DS-O-48 | IU-GF-04 | 14.0 kW |
| ODU-05 | DS-O-18 | IU-FF-01 | 5.3 kW |
| ODU-06 | DS-O-48 | IU-FF-02 | 14.0 kW |

Ventilation: OA 271 L/s, exhaust 225 L/s.

## Duct sizing (mains and branches)

| Zone | Segment | Type | Flow | Size | Velocity | Friction |
|---|---|---|---|---|---|---|
| Z-GF-03 | D-GF-001 | riser | 380 L/s | 300x300 | 4.22 m/s | 0.72 Pa/m |
| Z-GF-03 | ESP |  |  | req 71 / avail 75 Pa |  |  |
| Z-GF-04 | D-GF-006 | main | 402 L/s | 300x300 | 4.47 m/s | 0.80 Pa/m |
| Z-GF-04 | D-GF-007 | main | 295 L/s | 300x250 | 3.94 m/s | 0.71 Pa/m |
| Z-GF-04 | D-GF-008 | main | 52 L/s | 150x150 | 2.32 m/s | 0.58 Pa/m |
| Z-GF-04 | D-GF-009 | branch | 243 L/s | 300x300 | 2.70 m/s | 0.32 Pa/m |
| Z-GF-04 | D-GF-012 | branch | 63 L/s | 200x150 | 2.09 m/s | 0.41 Pa/m |
| Z-GF-04 | D-GF-015 | branch | 340 L/s | 400x300 | 2.83 m/s | 0.29 Pa/m |
| Z-GF-04 | ESP |  |  | req 73 / avail 100 Pa |  |  |
| Z-FF-01 | D-FF-001 | main | 250 L/s | 300x250 | 3.33 m/s | 0.53 Pa/m |
| Z-FF-01 | D-FF-002 | branch | 250 L/s | 300x300 | 2.78 m/s | 0.34 Pa/m |
| Z-FF-01 | ESP |  |  | req 70 / avail 75 Pa |  |  |
| Z-FF-02 | D-FF-007 | riser | 750 L/s | 600x300 | 4.17 m/s | 0.49 Pa/m |
| Z-FF-02 | D-FF-008 | main | 372 L/s | 300x300 | 4.13 m/s | 0.69 Pa/m |
| Z-FF-02 | D-FF-009 | main | 292 L/s | 300x250 | 3.89 m/s | 0.70 Pa/m |
| Z-FF-02 | D-FF-010 | main | 235 L/s | 250x250 | 3.76 m/s | 0.73 Pa/m |
| Z-FF-02 | D-FF-011 | main | 117 L/s | 200x200 | 2.92 m/s | 0.61 Pa/m |
| Z-FF-02 | D-FF-012 | branch | 372 L/s | 400x300 | 3.10 m/s | 0.35 Pa/m |
| Z-FF-02 | D-FF-016 | branch | 43 L/s | 150x150 | 1.92 m/s | 0.41 Pa/m |
| Z-FF-02 | D-FF-017 | branch | 43 L/s | 150x150 | 1.92 m/s | 0.41 Pa/m |
| Z-FF-02 | D-FF-018 | branch | 57 L/s | 150x150 | 2.53 m/s | 0.68 Pa/m |
| Z-FF-02 | D-FF-019 | branch | 118 L/s | 200x200 | 2.95 m/s | 0.62 Pa/m |
| Z-FF-02 | ESP |  |  | req 74 / avail 100 Pa |  |  |

## Diffusers

| Tag | Room | Model | Flow | NC |
|---|---|---|---|---|
| SD-GF-01 | GF-01 | SD-250 | 190 L/s | 28 |
| SD-GF-02 | GF-01 | SD-250 | 190 L/s | 28 |
| SD-GF-03 | GF-05 | SD-200 | 122 L/s | 26 |
| SD-GF-04 | GF-05 | SD-200 | 122 L/s | 26 |
| SD-GF-05 | GF-08 | SD-150 | 52 L/s | 18 |
| SD-GF-06 | GF-04 | SD-150 | 52 L/s | 18 |
| SD-GF-07 | GF-02 | SD-150 | 31 L/s | 11 |
| SD-GF-08 | GF-02 | SD-150 | 31 L/s | 11 |
| SD-GF-09 | GF-03 | SD-250 | 170 L/s | 25 |
| SD-GF-10 | GF-03 | SD-250 | 170 L/s | 25 |
| SD-FF-01 | FF-03 | SD-250 | 125 L/s | 19 |
| SD-FF-02 | FF-03 | SD-250 | 125 L/s | 19 |
| SD-FF-03 | FF-04 | SD-150 | 50 L/s | 18 |
| SD-FF-04 | FF-10 | SD-200 | 124 L/s | 27 |
| SD-FF-05 | FF-10 | SD-200 | 124 L/s | 27 |
| SD-FF-06 | FF-10 | SD-200 | 124 L/s | 27 |
| SD-FF-07 | FF-11 | SD-150 | 43 L/s | 15 |
| SD-FF-08 | FF-07 | SD-150 | 43 L/s | 15 |
| SD-FF-09 | FF-08 | SD-150 | 57 L/s | 20 |
| SD-FF-10 | FF-05 | SD-150 | 59 L/s | 21 |
| SD-FF-11 | FF-05 | SD-150 | 59 L/s | 21 |
| SD-FF-12 | FF-09 | SD-250 | 117 L/s | 18 |

## Piping

| Run | Liquid/Gas mm | Length m | Status |
|---|---|---|---|
| RP-IU-GF-01 | 6.35/12.7 | 21.7 | OK |
| RP-IU-GF-02 | 6.35/9.52 | 16.5 | OK |
| RP-IU-GF-03 | 9.52/15.88 | 29.1 | OK |
| RP-IU-GF-04 | 9.52/15.88 | 27.8 | OK |
| RP-IU-FF-01 | 6.35/12.7 | 25.3 | OK |
| RP-IU-FF-02 | 9.52/15.88 | 24.1 | OK |

| Drain | To | Ø mm | Length m |
|---|---|---|---|
| CD-IU-GF-01 | GF-06 KITCHEN (floor drain / waste stack with trap) | 25 | 2.54 |
| CD-IU-GF-02 | GF-10 SHAFT (floor drain / waste stack with trap) | 25 | 4.87 |
| CD-IU-GF-03 | GF-06 KITCHEN (floor drain / waste stack with trap) | 25 | 8.14 |
| CD-IU-GF-04 | GF-06 KITCHEN (floor drain / waste stack with trap) | 25 | 5.48 |
| CD-IU-FF-01 | FF-01 MASTER BATH (floor drain / waste stack with trap) | 25 | 2.68 |
| CD-IU-FF-02 | FF-01 MASTER BATH (floor drain / waste stack with trap) | 25 | 6.23 |
