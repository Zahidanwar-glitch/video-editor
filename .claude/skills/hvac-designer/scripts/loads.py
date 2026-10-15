"""Step B1 - room cooling and heating loads (CLTD/SCL/CLF, ASHRAE Fundamentals 1997 Ch.28).

Per room, per design hour (solar 8..20): walls, roof, glass conduction, glass solar,
people, lighting, equipment, infiltration. Room peak sensible sets supply airflow;
coincident (block) sums are kept for zone/plant sizing. Heating: steady-state
conduction + infiltration + slab edge, no internal-gain credit.
Safety factors are NOT applied here (they are applied and shown at equipment selection).

CLI: python loads.py -w WORK        reads project.json + rooms.json -> loads.json
"""
import argparse
import math

import common as C


def nearest_lat_row(table, lat):
    keys = [k for k in table if not k.startswith("_")]
    return table[min(keys, key=lambda k: abs(float(k) - abs(lat)))]


def design_conditions(p, log):
    loc = p["project"]["location"]
    clim = C.climate_for(loc["city"], loc["country"])
    over = p.get("design_conditions", {})
    if clim is None and not over.get("cool_db_c"):
        raise SystemExit(f"No climate data for {loc['city']}, {loc['country']}: add a row to references/climate_data.csv "
                         "or give design_conditions in project.json (ask the user).")
    clim = clim or {}
    ind = C.deep_merge(p["codes"]["indoor"], over.get("indoor", {}))
    dc = {
        "city": loc["city"], "country": loc["country"],
        "lat": over.get("lat", clim.get("lat_deg")), "elev_m": over.get("elev_m", clim.get("elev_m", 0)),
        "to_c": over.get("cool_db_c", clim.get("cool_db_c")), "twb_c": over.get("cool_mcwb_c", clim.get("cool_mcwb_c")),
        "dr_k": over.get("daily_range_k", clim.get("daily_range_k")), "th_c": over.get("heat_db_c", clim.get("heat_db_c")),
        "ti_c": ind["cooling_db_c"], "rhi": ind["cooling_rh_pct"], "tih_c": ind["heating_db_c"],
        "source": clim.get("source", "project.json"), "status": clim.get("status", "user"),
    }
    pa = C.p_atm_kpa(dc["elev_m"])
    dc["p_kpa"] = round(pa, 2)
    dc["wo"] = C.w_from_wb(dc["to_c"], dc["twb_c"], pa)
    dc["wi"] = C.w_from_rh(dc["ti_c"], dc["rhi"], pa)
    dc["cs"], dc["cl"] = C.air_factors(dc["elev_m"])
    conf = not p["project"].get("confirmed", {}).get("design_conditions")
    log.add("B-loads", "climate", f"Outdoor design {dc['to_c']} °C DB / {dc['twb_c']} °C MCWB (0.4 %), daily range {dc['dr_k']} K, "
            f"heating {dc['th_c']} °C (99.6 %), elevation {dc['elev_m']} m ({dc['source']}, {dc['status']})", "references/climate_data.csv", confirm=conf)
    log.add("B-loads", "indoor", f"Indoor design {dc['ti_c']} °C / {dc['rhi']} % RH cooling, {dc['tih_c']} °C heating",
            C.clause(p, "design_conditions"), confirm=conf)
    return dc


def envelope(p, log):
    cls = C.building_class(p)
    set_name = p["codes"]["u_value_set"][cls]
    u = dict(C.ref("u_values.json")["sets"][set_name])
    over = p["project"].get("envelope_override") or {}
    u.update(over)
    if not over:
        log.add("B-loads", "u_values", f"Envelope U-values = code maximum ({set_name}: wall {u['wall_ext']}, roof {u['roof']}, "
                f"glazing U {u['glazing_u']} / SHGC {u['glazing_shgc']} W/m²K) - actual build-up not given",
                C.clause(p, "envelope_u"), confirm=True)
    return set_name, u


def compute(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    log = C.Log(work, "loads")
    d = p["design"]["loads"]
    T = C.ref("cltd_tables.json")
    st_tbl = C.ref("space_types.json")
    dc = design_conditions(p, log)
    u_set, U = envelope(p, log)
    if p["codes"].get("manual_j_required_for_homes") and C.building_class(p) == "residential":
        log.ask("Gate2", "manual_j", "US home: ACCA Manual J is required for the final load calculation (IRC M1401.3). This skill's CLTD result is preliminary - "
                "confirm you will run Manual J software for permit, or accept CLTD for concept design.")
    if p["codes"].get("needs_confirmation") and not p["project"].get("confirmed", {}).get("codes"):
        log.ask("Gate2", "default_codes", "Location not in the code lookup table: ASHRAE defaults were used - confirm the code set.")
    hours = d["design_hours"]
    idx = [T["hours"].index(h) for h in hours]
    lm = nearest_lat_row(T["latitude_month_correction_LM"], dc["lat"])
    shgf = nearest_lat_row(T["max_shgf_w_m2"], dc["lat"])
    K = T["color_factor_k"][d["wall_color"]]
    wall_tbl = T["walls"][U["wall_group"]]
    roof_tbl = T["roofs"][U["roof_type"]]["HOR"]
    f = 1 / 1.8 if T["unit"] == "F" else 1.0
    corr = (T["base"]["indoor_c"] - dc["ti_c"]) + ((dc["to_c"] - dc["dr_k"] / 2) - T["base"]["mean_outdoor_c"])
    to_h = [dc["to_c"] - dc["dr_k"] * T["daily_range_pct"]["pct"][str(h)] / 100 for h in hours]
    sc = U["glazing_shgc"] / 0.87
    clf_glass = T["clf_glass_interior_shading"]
    clfi = T["clf_internal"]
    acts = st_tbl["activity_gains_w"]
    dw = max(0.0, dc["wo"] - dc["wi"]) if d["ignore_negative_oa_latent"] else dc["wo"] - dc["wi"]
    log.add("B-loads", "method", "Cooling loads by CLTD/SCL/CLF; CLTD tables for wall group "
            f"{U['wall_group']}, roof '{U['roof_type']}', latitude row nearest {dc['lat']}°, July; colour factor K={K} "
            f"({d['wall_color']} walls), roof K=1.0; glass with interior shading={d['interior_shading']}", C.clause(p, "load_method"), confirm=True)
    log.add("B-loads", "cltd_status", "CLTD/LM/SHGF/CLF tables in references/cltd_tables.json are transcribed-approximate - verify against licensed ASHRAE 1997 Ch.28 tables",
            "references/cltd_tables.json", confirm=True)
    log.add("B-loads", "clf_internal", "CLF for people/lights/equipment = 1.0 (24 h operation, no storage credit)", C.clause(p, "load_method"))
    log.add("B-loads", "partitions", "Partitions/floors between conditioned and exhaust-only rooms (baths, stores) not counted: those rooms are near room temperature", "designer judgement")
    if dc["wo"] < dc["wi"]:
        log.add("B-loads", "dry_climate", f"Outdoor humidity ratio {dc['wo']*1000:.1f} g/kg < indoor {dc['wi']*1000:.1f} g/kg at design: outdoor-air latent load taken as 0 (conservative); check a dehumidification design day",
                "ASHRAE Fundamentals 2021 Ch.14 (DP design)", confirm=True)
    sf = p["design"]["loads"]
    out = {"design_conditions": dc, "u_set": u_set, "u_values": U, "hours": hours, "to_hourly_c": [round(t, 1) for t in to_h], "rooms": []}
    ach_cfg = d["infiltration_ach"] if C.building_class(p) == "residential" else None
    ts = d["supply_air_temp_c"]
    for fl in rooms["floors"]:
        if fl.get("kind") == "roof" or fl.get("needs_vision"):
            continue
        for r in fl["rooms"]:
            st = st_tbl["types"].get(r["space_type"], st_tbl["types"]["unknown"])
            cond = r.get("is_conditioned", st.get("conditioned", True))
            h_ceil = r.get("height_m")
            h_wall = r.get("floor_to_floor_m") or (h_ceil + 0.6 if h_ceil else None)
            if not h_ceil:
                raise SystemExit(f"{r['id']} {r['name']}: ceiling height missing - answer the Gate 1 height question first.")
            A = r["area_m2"]
            comp = {k: [0.0] * len(hours) for k in ("wall", "roof", "glass_cond", "glass_solar", "people_s", "lights", "equip_s", "infil_s")}
            lat = {"people_l": 0.0, "equip_l": 0.0, "infil_l": [0.0] * len(hours)}
            detail = {"walls": [], "windows": []}
            win_by_or = {}
            for w in r.get("windows", []):
                if w.get("width_m") is None:
                    raise SystemExit(f"{r['id']}: window {w['tag']} size missing - answer the Gate 1 window question first.")
                win_by_or[w["orientation"]] = win_by_or.get(w["orientation"], 0) + w["width_m"] * w["height_m"]
            for ew in r.get("exterior_walls", []):
                o = ew["orientation"]
                aw = max(0.0, ew["length_m"] * h_wall - win_by_or.get(o, 0))
                detail["walls"].append({"orientation": o, "gross_m2": round(ew["length_m"] * h_wall, 2), "net_m2": round(aw, 2), "u": U["wall_ext"]})
                for j, i in enumerate(idx):
                    cltd = (wall_tbl[o][i] + lm[o]) * K * f + corr
                    comp["wall"][j] += U["wall_ext"] * aw * cltd
            for w in r.get("windows", []):
                aw = w["width_m"] * w["height_m"]
                o = w["orientation"]
                detail["windows"].append({"tag": w["tag"], "orientation": o, "area_m2": round(aw, 2), "u": U["glazing_u"], "sc": round(sc, 3), "shgf": shgf[o]})
                for j, i in enumerate(idx):
                    comp["glass_cond"][j] += U["glazing_u"] * aw * (T["glass_conduction"][i] * f + corr)
                    comp["glass_solar"][j] += aw * sc * shgf[o] * clf_glass[o][i]
            roof_a = A * r.get("roof_exposed_frac", 0)
            if roof_a > 0:
                for j, i in enumerate(idx):
                    comp["roof"][j] += U["roof"] * roof_a * ((roof_tbl[i] + lm["HOR"]) * f + corr)
            occ = st["occupants"]
            n_people = occ.get("fixed") if "fixed" in occ else math.ceil(A / occ["m2_per_person"])
            r_occ = r.get("occupants_override")
            if r_occ is not None:
                n_people = r_occ
            g = acts[st["activity"]]
            vol = A * h_ceil
            n_ext = len({e["orientation"] for e in r.get("exterior_walls", [])})
            if ach_cfg:
                ach = ach_cfg["no_exterior"] if n_ext == 0 else ach_cfg["one_exterior_side"] if n_ext == 1 else ach_cfg["two_plus_exterior_sides"]
            else:
                ach = d["infiltration_non_residential_ach"]
            inf_ls = ach * vol / 3.6
            for j in range(len(hours)):
                comp["people_s"][j] = n_people * g["sensible"] * clfi["people"]
                comp["lights"][j] = st["lighting_w_m2"] * A * clfi["lights"]
                comp["equip_s"][j] = (st["equip_w_m2"] * A + st["equip_fixed_w"]) * clfi["equipment"]
                comp["infil_s"][j] = dc["cs"] * inf_ls * (to_h[j] - dc["ti_c"])
                lat["infil_l"][j] = dc["cl"] * inf_ls * dw
            lat["people_l"] = n_people * g["latent"]
            lat["equip_l"] = st["equip_latent_w"]
            sens = [sum(comp[k][j] for k in comp) for j in range(len(hours))]
            latent = [lat["people_l"] + lat["equip_l"] + lat["infil_l"][j] for j in range(len(hours))]
            pk = max(range(len(hours)), key=lambda j: sens[j] + latent[j])
            pks = max(range(len(hours)), key=lambda j: sens[j])
            qs, ql = sens[pk], latent[pk]
            supply_ls = sens[pks] / (dc["cs"] * (dc["ti_c"] - ts)) if cond else 0.0
            # heating
            dth = dc["tih_c"] - dc["th_c"]
            hq = {"walls": sum(U["wall_ext"] * w["net_m2"] for w in detail["walls"]) * dth,
                  "glass": sum(U["glazing_u"] * w["area_m2"] for w in detail["windows"]) * dth,
                  "roof": U["roof"] * roof_a * dth,
                  "infiltration": dc["cs"] * inf_ls * dth,
                  "slab_edge": U["slab_edge_f_w_mk"] * sum(e["length_m"] for e in r.get("exterior_walls", [])) * dth if r.get("ground_contact") else 0.0}
            out["rooms"].append({
                "id": r["id"], "name": r["name"], "floor": fl["id"], "space_type": r["space_type"], "conditioned": cond,
                "area_m2": A, "height_m": h_ceil, "volume_m3": round(vol, 1), "people": n_people, "infil_ach": ach, "infil_ls": round(inf_ls, 1),
                "envelope": detail, "roof_area_m2": round(roof_a, 2),
                "peak_hour": hours[pk], "peak_sensible_hour": hours[pks],
                "components_w": {k: round(v[pk], 0) for k, v in comp.items()} | {"people_l": round(lat["people_l"]), "equip_l": round(lat["equip_l"]), "infil_l": round(lat["infil_l"][pk])},
                "sensible_w": round(qs), "latent_w": round(ql), "total_w": round(qs + ql),
                "peak_sensible_w": round(sens[pks]),
                "hourly_sensible_w": [round(x) for x in sens], "hourly_latent_w": [round(x) for x in latent],
                "w_per_m2": round((qs + ql) / A, 1) if A else 0,
                "supply_ls": round(supply_ls, 1),
                "heating_w": round(sum(hq.values())), "heating_components_w": {k: round(v) for k, v in hq.items()},
            })
            lo, hi = d["sanity_w_m2"]
            if cond and n_people > 0 and not (lo <= (qs + ql) / max(A, 0.1) <= hi):
                log.ask("Gate2", f"wm2_{r['id']}", f"{r['id']} {r['name']}: cooling load {(qs + ql) / A:.0f} W/m² is outside {lo}-{hi} W/m² for an occupied room - check inputs.")
    log.add("B-loads", "supply_dt", f"Supply air {ts} °C (room-supply ΔT {dc['ti_c'] - ts:.1f} K) for airflow", "designer default")
    log.add("B-loads", "infiltration", f"Infiltration by air-change method: {d['infiltration_ach']} ACH (residential)", C.clause(p, "infiltration"))
    log.add("B-loads", "occupancy", "Occupancy, lighting and equipment densities from references/space_types.json", C.clause(p, "internal_gains"))
    cond_rooms = [x for x in out["rooms"] if x["conditioned"]]
    out["block_hourly_w"] = [sum(x["hourly_sensible_w"][j] + x["hourly_latent_w"][j] for x in cond_rooms) for j in range(len(hours))]
    out["summary"] = {"conditioned_area_m2": round(sum(x["area_m2"] for x in cond_rooms), 1),
                      "sum_room_peaks_kw": round(sum(x["total_w"] for x in cond_rooms) / 1000, 2),
                      "block_peak_kw": round(max(out["block_hourly_w"]) / 1000, 2),
                      "block_peak_hour": hours[out["block_hourly_w"].index(max(out["block_hourly_w"]))],
                      "heating_kw": round(sum(x["heating_w"] for x in cond_rooms) / 1000, 2)}
    C.save(work, "loads.json", out)
    log.save()
    s = out["summary"]
    print(f"loads.json: {len(cond_rooms)} conditioned rooms, block peak {s['block_peak_kw']} kW at {s['block_peak_hour']}:00, "
          f"sum of room peaks {s['sum_room_peaks_kw']} kW, heating {s['heating_kw']} kW")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
