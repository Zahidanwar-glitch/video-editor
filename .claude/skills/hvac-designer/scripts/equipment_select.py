"""Step B4 - select equipment per zone and place it on the plans.

Per zone: coil load = coincident room loads + outdoor-air load (hour by hour), peak x (1+SF).
Select the smallest catalogue model whose derated total and sensible capacity and airflow
cover the requirement. Unit airflow is shared to rooms in proportion to their need.
VRF: one outdoor unit per system on the block load (combination ratio check).
Chilled water: FCUs per zone + air-cooled chiller on the block load.
Placement: ducted units in a service room of/next to the zone, wall splits on the
exterior wall, thermostats on an interior wall of the main room, outdoor units on the roof.

CLI: python equipment_select.py -w WORK   -> design.json (equipment part)
"""
import argparse
import math

import common as C
import geom as G
from zoning import ROOM_UNIT, DUCTED


def catalogue_key(system):
    return ROOM_UNIT.get(system) or DUCTED.get(system)


def pick(models, req_total, req_sens, req_air, derate, tol):
    for mdl in sorted(models, key=lambda x: x["cool_kw"]):
        cap = mdl["cool_kw"] * derate
        if cap >= req_total and cap * mdl.get("shr", 1) >= req_sens and mdl.get("airflow_ls", 1e9) >= req_air * (1 - tol):
            return mdl, True
    return max(models, key=lambda x: x["cool_kw"]), False


def odu_size(kw):
    for lim, wd in C.ref("equipment_catalog.json")["odu_footprint_m"]["by_kw"]:
        if kw <= lim:
            return wd
    return [1.7, 0.8]


def compute(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    L = C.load(work, "loads.json")
    loads = {r["id"]: r for r in L["rooms"]}
    zones = C.load(work, "zones.json")
    vent = C.load(work, "ventilation.json")
    log = C.Log(work, "equipment_select")
    cat = C.ref("equipment_catalog.json")
    dz = p["design"]
    sf, sfh = dz["loads"]["safety_factor_cooling"], dz["loads"]["safety_factor_heating"]
    dc = L["design_conditions"]
    hours = L["hours"]
    to_h = L["to_hourly_c"]
    derate = cat["t3_derate"].get(p["project"]["code_set"], cat["t3_derate"]["default"]) if dc["to_c"] > 43 else 1.0
    tol = dz["equipment"]["airflow_tolerance"]
    min_room_ls = min(d["min_ls"] for d in C.ref("air_terminals.json")["supply_diffusers"])
    idx = G.room_index(rooms)
    fls = {f["id"]: f for f in rooms["floors"]}
    dw = max(0.0, dc["wo"] - dc["wi"])
    log.add("B-equip", "sf", f"Safety factor {sf:.0%} on cooling and {sfh:.0%} on heating, applied to coil loads at selection (shown in tables)", C.clause(p, "safety_factor"), confirm=True)
    if derate < 1:
        log.add("B-equip", "derate", f"Nominal (T1) capacities derated x{derate} for {dc['to_c']} °C outdoor design (T3) - replace with brand T3 data", "references/equipment_catalog.json t3_derate", confirm=True)
    log.add("B-equip", "catalogue", "Equipment from GENERIC catalogue (references/equipment_catalog.json) - replace with the approved brand", "references/equipment_catalog.json", confirm=True)
    log.add("B-equip", "min_room_air", f"Minimum supply per served room {min_room_ls} L/s (smallest diffuser)", "references/air_terminals.json")

    design = {"zones": [], "outdoor_units": [], "plant": {}, "derate": derate, "sf_cooling": sf, "sf_heating": sfh}
    n_iu = {}
    hosts_used = {}
    for z in zones["zones"]:
        fl = fls[z["floor"]]
        zr = [loads[r] for r in z["rooms"]]
        vot = vent["zones"][z["id"]]["Vot_ls"]
        oa_s = [dc["cs"] * vot * (t - dc["ti_c"]) for t in to_h]
        oa_l = dc["cl"] * vot * dw
        tot = [sum(r["hourly_sensible_w"][j] + r["hourly_latent_w"][j] for r in zr) + oa_s[j] + oa_l for j in range(len(hours))]
        pk = max(range(len(hours)), key=lambda j: tot[j])
        sens_pk = sum(r["hourly_sensible_w"][pk] for r in zr) + oa_s[pk]
        room_air = {r["id"]: max(r["supply_ls"], min_room_ls) for r in zr}
        req_air = sum(room_air.values())
        req_total = tot[pk] * (1 + sf) / 1000
        req_sens = sens_pk * (1 + sf) / 1000
        key = catalogue_key(z["system"])
        mdl, ok = pick(cat[key]["models"], req_total, req_sens, req_air, derate, tol)
        tot_only, _ = pick(cat[key]["models"], req_total, 0, req_air, derate, tol)
        if ok and tot_only["cool_kw"] < mdl["cool_kw"]:
            log.add("B-equip", f"sens_gov_{z['id']}", f"{z['id']}: sensible capacity governs ({req_sens:.1f} kW sensible at catalogue SHR) - {mdl['model']} chosen instead of {tot_only['model']}; "
                    "brand data at actual (dry) entering conditions may allow the smaller unit", "designer note", confirm=True)
        if not ok:
            log.ask("Gate2", f"nounit_{z['id']}", f"{z['id']}: no {key} model covers {req_total:.1f} kW / {req_air:.0f} L/s - split the zone or change system.")
        air = mdl.get("airflow_ls", req_air)
        share = {rid: round(air * a / req_air, 1) for rid, a in room_air.items()}
        heat_req = sum(r["heating_w"] for r in zr) / 1000 * (1 + sfh) + dc["cs"] * vot * (dc["tih_c"] - dc["th_c"]) / 1000 * (1 + sfh)
        n_iu[z["floor"]] = n_iu.get(z["floor"], 0) + 1
        tag = f"IU-{z['floor']}-{n_iu[z['floor']]:02d}"
        unit = {"tag": tag, "type": key, "model": mdl["model"], "nominal_kw": mdl["cool_kw"], "derated_kw": round(mdl["cool_kw"] * derate, 2),
                "sensible_kw": round(mdl["cool_kw"] * derate * mdl.get("shr", 1), 2), "airflow_ls": air, "esp_pa": mdl.get("esp_pa", 0),
                "heat_kw": mdl.get("heat_kw", 0), "eer": mdl.get("eer"), "power_kw": round(mdl["cool_kw"] / mdl["eer"], 2) if mdl.get("eer") else None,
                "btu": mdl.get("btu"), "req_total_kw": round(req_total, 2), "req_sensible_kw": round(req_sens, 2), "req_airflow_ls": round(req_air, 1),
                "block_kw": round(tot[pk] / 1000, 2), "room_kw": round(sum(r["hourly_sensible_w"][pk] + r["hourly_latent_w"][pk] for r in zr) / 1000, 2),
                "oa_kw": round((oa_s[pk] + oa_l) / 1000, 2), "peak_hour": hours[pk], "heat_req_kw": round(heat_req, 2),
                "oversize_pct": round((mdl["cool_kw"] * derate / req_total - 1) * 100, 0), "selected_ok": ok}
        oa_frac = vot / air if air else 0
        unit["oa_ls"], unit["oa_frac"] = vot, round(oa_frac, 3)
        if oa_frac > dz["ventilation"]["max_oa_fraction_without_pretreat"] and z["kind"] == "ducted":
            log.ask("Gate2", f"oafrac_{z['id']}", f"{z['id']}: outdoor air is {oa_frac:.0%} of unit airflow (> {dz['ventilation']['max_oa_fraction_without_pretreat']:.0%}). "
                    "Pre-treat fresh air (FAHU / energy-recovery ventilator) or accept the coil load already included?")
        if unit["heat_kw"] and unit["heat_kw"] < heat_req:
            log.ask("Gate2", f"heat_{z['id']}", f"{z['id']}: unit heating {unit['heat_kw']} kW < required {heat_req:.1f} kW - add supplementary heat?")
        if unit["oversize_pct"] > 60:
            log.add("B-equip", f"oversize_{z['id']}", f"{tag} ({mdl['model']}) is {unit['oversize_pct']:.0f} % above requirement - smallest catalogue size; consider combining zones or a smaller (VRF/wall) unit",
                    "designer note", confirm=True)
        # ---- placement
        zrooms = [idx[r][1] for r in z["rooms"]]
        main = max(zrooms, key=lambda r: loads[r["id"]]["total_w"])
        if z["kind"] == "ducted":
            pos, host = place_ducted(p, fl, zrooms, loads, hosts_used, log, z)
        else:
            pos, host = place_wall_unit(fl, main, log)
        unit["pos_pt"] = [round(pos[0], 2), round(pos[1], 2)]
        unit["host_room"] = host["id"]
        unit["footprint_m"] = cat["indoor_footprint_m"].get(key, [1.0, 0.5])
        tpos = G.interior_wall_point(fl, main, 0.3)
        tstat = {"tag": f"T-{z['floor']}-{n_iu[z['floor']]:02d}", "room": main["id"], "pos_pt": [round(tpos[0], 2), round(tpos[1], 2)],
                 "type": "wired programmable thermostat" if z["kind"] == "ducted" else "wired controller"}
        zone = {"id": z["id"], "floor": z["floor"], "system": z["system"], "kind": z["kind"], "rooms": z["rooms"], "unit": unit,
                "room_airflow_ls": share, "thermostat": tstat, "oa_method": vent["zones"][z["id"]]["oa_method"]}
        if zone["oa_method"] == "through-wall fresh air fan":
            fm, _ = next(((m, True) for m in cat["fresh_air_fan"]["models"] if m["airflow_ls"] >= vot), (cat["fresh_air_fan"]["models"][-1], False))
            q, e, rr = G.nearest_exterior(fl, tuple(main["centroid_pt"]), rooms=[main], min_frac=0.25)
            zone["fa_fan"] = {"tag": f"FAF-{z['floor']}-{n_iu[z['floor']]:02d}", "model": fm["model"], "airflow_ls": round(vot, 1),
                              "power_w": fm["power_w"], "pos_pt": [round(x, 2) for x in G.inset(q, e, fl, 0.1)] if q else unit["pos_pt"]}
        design["zones"].append(zone)

    # ---- outdoor units / plant
    roof = next((f for f in rooms["floors"] if f.get("kind") == "roof"), None)
    loc = p.get("preferences", {}).get("odu_location") or dz["equipment"]["odu_location"]
    if loc == "roof" and not roof:
        log.ask("Gate2", "odu_loc", "Outdoor units on the roof, but no roof plan page was read - where should outdoor units go?")
    split_like = [z for z in design["zones"] if z["unit"]["type"] in ("wall_split", "ducted_split")]
    for i, z in enumerate(split_like, 1):
        design["outdoor_units"].append({"tag": f"ODU-{i:02d}", "serves": [z["unit"]["tag"]], "model": z["unit"]["model"].replace("WS", "WS-O").replace("DS", "DS-O"),
                                        "cool_kw": z["unit"]["nominal_kw"], "power_kw": z["unit"]["power_kw"], "system": z["system"]})
    vrf = [z for z in design["zones"] if z["system"] == "vrf"]
    if vrf:
        block = block_load(vrf, loads, vent, dc, to_h, hours) * (1 + sf) / 1000
        sum_iu = sum(z["unit"]["nominal_kw"] for z in vrf)
        lo, hi = cat["vrf_outdoor"]["combination_ratio"]
        mdl = next((m for m in cat["vrf_outdoor"]["models"] if m["cool_kw"] * derate >= block and lo <= sum_iu / m["cool_kw"] <= hi), None)
        if not mdl:
            mdl = cat["vrf_outdoor"]["models"][-1]
            log.ask("Gate2", "vrf_odu", f"VRF block load {block:.1f} kW / IU sum {sum_iu:.1f} kW: no single outdoor unit fits - split into two VRF systems?")
        design["outdoor_units"].append({"tag": f"ODU-{len(design['outdoor_units']) + 1:02d}", "serves": [z["unit"]["tag"] for z in vrf], "model": mdl["model"],
                                        "cool_kw": mdl["cool_kw"], "power_kw": round(mdl["cool_kw"] / mdl["eer"], 2), "system": "vrf",
                                        "block_kw": round(block, 2), "combination_ratio": round(sum_iu / mdl["cool_kw"], 2)})
    chw = [z for z in design["zones"] if z["system"] == "chilled_water"]
    if chw:
        block = block_load(chw, loads, vent, dc, to_h, hours) * (1 + sf) / 1000
        mdl = next((m for m in cat["chiller_air_cooled"]["models"] if m["cool_kw"] * derate >= block), cat["chiller_air_cooled"]["models"][-1])
        dt = dz["pipes"]["chw_delta_t_k"]
        flow = mdl["cool_kw"] / (4.186 * dt)
        design["outdoor_units"].append({"tag": "CH-01", "serves": [z["unit"]["tag"] for z in chw], "model": mdl["model"], "cool_kw": mdl["cool_kw"],
                                        "power_kw": round(mdl["cool_kw"] / mdl["eer"], 1), "system": "chilled_water", "block_kw": round(block, 2)})
        design["plant"] = {"chiller": "CH-01", "chw_flow_ls": round(flow, 2), "delta_t_k": dt, "pumps": [
            {"tag": "CHWP-01", "duty": "duty", "flow_ls": round(flow, 2)}, {"tag": "CHWP-02", "duty": "standby", "flow_ls": round(flow, 2)}]}
        log.add("B-equip", "chw", f"Chilled water {dz['pipes']['chw_supply_c']} °C supply, ΔT {dt} K, constant-flow duty/standby pumps (head by detailed design)", C.clause(p, "chw_piping"), confirm=True)
    if roof and design["outdoor_units"]:
        place_odus(roof, design, rooms, log)
    design["risers"] = risers(rooms)
    C.save(work, "design.json", design)
    log.save()
    print(f"design.json: {len(design['zones'])} indoor units, {len(design['outdoor_units'])} outdoor units/plant")
    for z in design["zones"]:
        u = z["unit"]
        print(f"  {z['id']} {u['tag']} {u['model']:<8} req {u['req_total_kw']:>5} kW / {u['req_airflow_ls']:>5} L/s -> {u['derated_kw']} kW, {u['airflow_ls']} L/s, OA {u['oa_frac']:.0%}  host {u['host_room']}")


def block_load(zs, loads, vent, dc, to_h, hours):
    best = 0
    dw = max(0.0, dc["wo"] - dc["wi"])
    for j in range(len(hours)):
        s = 0
        for z in zs:
            s += sum(loads[r]["hourly_sensible_w"][j] + loads[r]["hourly_latent_w"][j] for r in z["rooms"])
            vot = vent["zones"][z["id"]]["Vot_ls"]
            s += dc["cs"] * vot * (to_h[j] - dc["ti_c"]) + dc["cl"] * vot * dw
        best = max(best, s)
    return best


def place_ducted(p, fl, zrooms, loads, used, log, z):
    pref = p["design"]["zoning"]["unit_host_preference"]
    w = sum(loads[r["id"]]["total_w"] for r in zrooms) or 1
    cx = sum(r["centroid_pt"][0] * loads[r["id"]]["total_w"] for r in zrooms) / w
    cy = sum(r["centroid_pt"][1] * loads[r["id"]]["total_w"] for r in zrooms) / w
    cands = []
    for r in fl["rooms"]:
        if r["space_type"] not in pref:
            continue
        inside = r in zrooms
        if inside or any(G.adjacent(r, zr, fl) for zr in zrooms):
            score = pref.index(r["space_type"]) * G.pt(fl, 2.0) + G.manhattan((cx, cy), r["centroid_pt"]) + (0 if inside else G.pt(fl, 3.0))
            score += used.get(r["id"], 0) * G.pt(fl, 3.0)
            cands.append((score, r))
    if cands:
        host = min(cands, key=lambda c: c[0])[1]
        k = used.get(host["id"], 0)
        used[host["id"]] = k + 1
        x0, y0, x1, y1 = host["bbox_pt"]
        step = G.pt(fl, 1.5) * ((k + 1) // 2) * (1 if k % 2 else -1)
        cx_, cy_ = host["centroid_pt"]
        pos = (cx_ + step, cy_) if (x1 - x0) >= (y1 - y0) else (cx_, cy_ + step)
        log.add("B-equip", f"host_{z['id']}", f"{z['id']} indoor unit in the ceiling void of {host['id']} {host['name']} (service space next to the zone)", "references/design_defaults.json unit_host_preference", confirm=True)
        return pos, host
    main = max(zrooms, key=lambda r: loads[r["id"]]["total_w"])
    log.ask("Gate2", f"host_{z['id']}", f"{z['id']}: no corridor/service room next to the zone for the ducted unit - unit placed in {main['name']} ceiling. Confirm location / access panel.")
    return tuple(G.interior_wall_point(fl, main, 0.8)), main


def place_wall_unit(fl, room, log):
    ext = [e for e in room.get("edges", []) if e["exterior_frac"] >= 0.5]
    edges = ext or room.get("edges", [])
    e = max(edges, key=lambda e: e["length_m"])
    f = 0.3 if ext else 0.5
    p = (e["p1"][0] + (e["p2"][0] - e["p1"][0]) * f, e["p1"][1] + (e["p2"][1] - e["p1"][1]) * f)
    if not ext:
        log.add("B-equip", f"wall_unit_{room['id']}", f"{room['id']} {room['name']} has no exterior wall: wall split on interior wall, refrigerant/condensate run in ceiling", "designer judgement", confirm=True)
    return G.inset(p, e, fl, 0.15), room


def risers(rooms):
    out = {}
    for f in G.floors(rooms):
        out[f["id"]] = [{"room": r["id"], "pos_pt": r["centroid_pt"]} for r in f["rooms"] if r["space_type"] == "shaft"]
    return out


def place_odus(roof, design, rooms, log):
    roof_area = max((r for r in roof["rooms"] if r["space_type"] == "roof"), key=lambda r: r["area_m2"], default=None)
    if not roof_area:
        log.ask("Gate2", "roof_area", "Roof plan has no open roof area - where do outdoor units go?")
        return
    others = [r["bbox_pt"] for r in roof["rooms"] if r is not roof_area]
    shafts = [s for v in risers(rooms).values() for s in v]
    anchor = shafts[0]["pos_pt"] if shafts else roof_area["centroid_pt"]
    clr = C.ref("equipment_catalog.json")["odu_footprint_m"]["clearance_m"]
    x0, y0, x1, y1 = roof_area["bbox_pt"]
    edge = G.pt(roof, 0.8)
    pitch_x = G.pt(roof, max(odu_size(o["cool_kw"])[0] for o in design["outdoor_units"]) + clr)
    pitch_y = G.pt(roof, max(odu_size(o["cool_kw"])[1] for o in design["outdoor_units"]) + 2 * clr)
    cands = []
    y = y0 + edge
    while y < y1 - edge:
        x = x0 + edge
        while x < x1 - edge:
            ok = G.point_in_poly((x, y), roof_area["polygon_pt"]) and not any(
                b[0] - edge < x < b[2] + edge and b[1] - edge < y < b[3] + edge for b in others)
            if ok:
                cands.append((G.manhattan((x, y), anchor), (x, y)))
            x += pitch_x
        y += pitch_y
    cands.sort()
    for o, (_, pos) in zip(design["outdoor_units"], cands):
        o["pos_pt"] = [round(pos[0], 2), round(pos[1], 2)]
        o["floor"] = roof["id"]
        o["footprint_m"] = odu_size(o["cool_kw"])
    if len(cands) < len(design["outdoor_units"]):
        log.ask("Gate2", "roof_space", "Not enough clear roof area for all outdoor units - confirm locations.")
    log.add("B-equip", "odu_roof", f"Outdoor units grouped on the roof near the riser/shaft with {clr} m service clearance; check structure, parapet height and acoustic screening",
            "designer judgement", confirm=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
