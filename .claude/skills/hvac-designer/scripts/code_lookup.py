"""Start-of-project helper: show the code set, units and design conditions for a location.

CLI: python code_lookup.py "Riyadh" "Saudi Arabia"
"""
import sys

import common as C


def main(city, country):
    cs = C.code_set_for(country)
    codes = C.ref("codes_by_country.json")["code_sets"][cs]
    clim = C.climate_for(city, country)
    print(f"Code set: {cs} - {codes['label']}   Units: {codes['units']}")
    for c in codes["codes"]:
        print(f"  {c['id']:<9} {c['title']}")
    if codes.get("local_codes"):
        print("  Local:", "; ".join(codes["local_codes"].get(country.lower(), ["(none listed - ask)"])))
    i = codes["indoor"]
    print(f"Indoor: cooling {i['cooling_db_c']} °C / {i['cooling_rh_pct']} % RH, heating {i['heating_db_c']} °C   ({codes['clauses']['design_conditions']})")
    if clim:
        print(f"Outdoor: {clim['cool_db_c']} °C DB / {clim['cool_mcwb_c']} °C MCWB (0.4 %), daily range {clim['daily_range_k']} K, "
              f"heating {clim['heat_db_c']} °C (99.6 %), elev {clim['elev_m']:.0f} m, lat {clim['lat_deg']}  [{clim['source']}; {clim['status']}]")
    else:
        print("Outdoor: city NOT in references/climate_data.csv - ask the user for design data (or add a row).")
    if codes.get("needs_confirmation"):
        print("NOTE: country not in lookup - ASHRAE default; confirm with the user.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
