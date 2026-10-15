"""Step B6 - refrigerant / chilled-water piping and condensate drains.

Refrigerant (split, VRF): route indoor unit -> riser (nearest shaft, else nearest facade)
-> roof -> outdoor unit; size from the manufacturer-style table in references/pipe_sizing.json
and check max length / height. VRF: branch to riser sized per indoor unit, riser and roof
main sized on cumulative capacity, one branch kit per indoor unit.
Chilled water: FCU branches -> riser -> chiller, sized for velocity and friction limits
(Darcy-Weisbach, Swamee-Jain f).
Condensate: indoor unit -> nearest wet room drain or shaft, sized per Table 307.2.2.

CLI: python pipe_sizing.py -w WORK   -> design.json (pipes)
"""
import argparse
import math

import common as C
import geom as G

def refrig_size(kw, table):
    for row in table:
        if kw <= row["max_kw"]:
            return row
    return table[-1]


def chw_size(flow_ls, chw):
    rho, nu, eps = chw["water_density"], chw["water_viscosity_m2_s"], chw["roughness_mm"] / 1000
    for s in chw["steel_sch40"]:
        D = s["id_mm"] / 1000
        v = flow_ls / 1000 / (math.pi * D * D / 4)
        re = max(v * D / nu, 1)
        f = 0.25 / math.log10(eps / (3.7 * D) + 5.74 / re ** 0.9) ** 2
        dp = f / D * rho * v * v / 2
        vmax = next(vm for lim, vm in chw["max_velocity_m_s"] if s["dn"] <= lim)
        if v <= vmax and dp <= chw["max_friction_pa_m"]:
            return s, v, dp
    return s, v, dp


def riser_for(fl, pos, design, log, key):
    shafts = design["risers"].get(fl["id"], [])
    if shafts:
        s = min(shafts, key=lambda s: G.manhattan(pos, s["pos_pt"]))
        return tuple(s["pos_pt"]), f"shaft {s['room']}"
    q, e, r = G.nearest_exterior(fl, pos)
    log.add("B-pipes", f"facade_riser_{key}", f"No shaft on {fl['id']}: refrigerant/CHW riser on the facade at {r['name'] if r else '?'} (cladding/covers by architect)", "designer judgement", confirm=True)
    return (q if q else pos), "facade"


def compute(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    design = C.load(work, "design.json")
    log = C.Log(work, "pipe_sizing")
    PS = C.ref("pipe_sizing.json")
    dz = p["design"]
    fls = {f["id"]: f for f in rooms["floors"]}
    floors = G.floors(rooms)
    order = [f["id"] for f in floors]
    cfg = {f["id"]: f for f in p["project"].get("floors", [])}
    roof = next((f for f in rooms["floors"] if f.get("kind") == "roof"), None)
    extra = dz["pipes"]["refrigerant_extra_length_factor"]
    va = dz["equipment"]["vertical_allowance_m"]
    odus = {t: o for o in design["outdoor_units"] for t in o["serves"]}
    pipes = {"refrigerant": [], "condensate": [], "chw": [], "branch_kits": []}

    def rise_to_roof(fid):
        i = order.index(fid)
        return sum(cfg.get(f, {}).get("floor_to_floor_m", 3.5) for f in order[i:]) + va

    for z in design["zones"]:
        fl = fls[z["floor"]]
        u = z["unit"]
        pos = tuple(u["pos_pt"])
        rpos, rdesc = riser_for(fl, pos, design, log, z["id"])
        floor_route = G.l_route(pos, rpos)
        h_floor = G.m(fl, G.polyline_len(floor_route))
        o = odus.get(u["tag"])
        if u["type"] != "fcu_ducted":
            vert = rise_to_roof(fl["id"]) if (o and o.get("floor") == "RF") else va
            roof_route, h_roof = [], 0.0
            if o and o.get("pos_pt") and roof:
                roof_route = G.l_route(rpos, tuple(o["pos_pt"]))
                h_roof = G.m(roof, G.polyline_len(roof_route))
            total = (h_floor + vert + h_roof) * (1 + extra)
            kind = "vrf_indoor_ducted" if z["system"] == "vrf" else u["type"]
            sz = refrig_size(u["nominal_kw"], PS["refrigerant"]["by_capacity_kw"])
            maxL = PS["refrigerant"]["max_length_m"].get(kind, 50)
            maxH = PS["refrigerant"]["max_height_m"].get(kind, 30)
            ok = total <= maxL and vert <= maxH
            if not ok:
                log.ask("Gate2", f"refl_{u['tag']}", f"{u['tag']}: refrigerant run {total:.1f} m / rise {vert:.1f} m exceeds {kind} limits ({maxL} m / {maxH} m) - move outdoor unit closer?")
            pipes["refrigerant"].append({
                "tag": f"RP-{u['tag']}", "unit": u["tag"], "odu": o["tag"] if o else None, "floor": fl["id"], "riser": rdesc,
                "pts_floor": [[round(x, 2), round(y, 2)] for x, y in floor_route], "pts_roof": [[round(x, 2), round(y, 2)] for x, y in roof_route],
                "riser_pt": [round(rpos[0], 2), round(rpos[1], 2)], "horiz_floor_m": round(h_floor, 2), "vertical_m": round(vert, 2), "horiz_roof_m": round(h_roof, 2),
                "total_m": round(total, 1), "liquid_mm": sz["liquid_mm"], "gas_mm": sz["gas_mm"], "liquid_in": sz["liquid_in"], "gas_in": sz["gas_in"],
                "max_length_m": maxL, "max_height_m": maxH, "ok": ok, "bends": max(0, len(floor_route) - 2) + max(0, len(roof_route) - 2) + 2,
                "capacity_kw": u["nominal_kw"], "system": z["system"]})
            if z["system"] == "vrf":
                pipes["branch_kits"].append({"unit": u["tag"], "floor": fl["id"], "pos_pt": [round(rpos[0], 2), round(rpos[1], 2)]})
        else:
            flow = u["nominal_kw"] / (4.186 * dz["pipes"]["chw_delta_t_k"])
            s, v, dp = chw_size(flow, PS["chilled_water"])
            pipes["chw"].append({"tag": f"CHW-{u['tag']}", "unit": u["tag"], "floor": fl["id"], "kind": "branch", "flow_ls": round(flow, 3), "dn": s["dn"], "in": s["in"],
                                 "velocity_m_s": round(v, 2), "friction_pa_m": round(dp), "length_m": round(h_floor * 2, 1),
                                 "pts_floor": [[round(x, 2), round(y, 2)] for x, y in floor_route], "riser_pt": [round(rpos[0], 2), round(rpos[1], 2)]})
        # condensate
        wets = [r for r in fl["rooms"] if r["space_type"] in dz["pipes"]["wet_room_types"]]
        if wets:
            tgt = min(wets, key=lambda r: G.manhattan(pos, r["centroid_pt"]))
            croute = G.l_route(pos, tuple(tgt["centroid_pt"]), horizontal_first=False)
            dn = next(r for r in PS["condensate"]["by_capacity_kw"] if u["nominal_kw"] <= r["max_kw"])
            dmin = dz["pipes"]["condensate_min_mm"]
            pipes["condensate"].append({"tag": f"CD-{u['tag']}", "unit": u["tag"], "floor": fl["id"], "to": f"{tgt['id']} {tgt['name']} (floor drain / waste stack with trap)",
                                        "pts": [[round(x, 2), round(y, 2)] for x, y in croute], "length_m": round(G.m(fl, G.polyline_len(croute)) * 1.1, 2),
                                        "code_min_mm": dn["dn_mm"], "dn_mm": max(dn["dn_mm"], dmin), "slope_pct": dz["pipes"]["condensate_slope_pct"]})
        else:
            log.ask("Gate2", f"cond_{u['tag']}", f"{u['tag']}: no wet room or shaft on {fl['id']} for the condensate drain - where should it discharge?")

    # VRF / CHW risers and mains (cumulative)
    vrf = [r for r in pipes["refrigerant"] if r["system"] == "vrf"]
    if vrf:
        tot = sum(r["capacity_kw"] for r in vrf)
        sz = refrig_size(tot, PS["refrigerant"]["by_capacity_kw"])
        pipes["refrigerant"].append({"tag": "RP-VRF-MAIN", "unit": "VRF main", "odu": vrf[0]["odu"], "floor": "riser", "riser": "shaft", "pts_floor": [], "pts_roof": [],
                                     "horiz_floor_m": 0, "vertical_m": 0, "horiz_roof_m": 0, "total_m": round(max(r["vertical_m"] + r["horiz_roof_m"] for r in vrf), 1),
                                     "liquid_mm": sz["liquid_mm"], "gas_mm": sz["gas_mm"], "liquid_in": sz["liquid_in"], "gas_in": sz["gas_in"], "ok": True, "bends": 4,
                                     "capacity_kw": tot, "system": "vrf_main"})
        log.add("B-pipes", "vrf_main", "VRF main/riser sized on total connected indoor capacity from the generic table - final sizes from the brand's selection software", C.clause(p, "refrigerant_piping"), confirm=True)
    if pipes["chw"] and design.get("plant"):
        flow = design["plant"]["chw_flow_ls"]
        s, v, dp = chw_size(flow, PS["chilled_water"])
        pipes["chw"].append({"tag": "CHW-MAIN", "unit": "riser + roof main", "floor": "riser", "kind": "main", "flow_ls": round(flow, 2), "dn": s["dn"], "in": s["in"],
                             "velocity_m_s": round(v, 2), "friction_pa_m": round(dp), "length_m": round(2 * (rise_to_roof(order[0]) + 10), 1), "pts_floor": [], "riser_pt": None})
    log.add("B-pipes", "refrig_table", "Refrigerant pipe sizes from GENERIC table (references/pipe_sizing.json) - replace with the selected brand's table", C.clause(p, "refrigerant_piping"), confirm=True)
    log.add("B-pipes", "refrig_len", f"Refrigerant length = route x (1+{extra:.0%}) + vertical rise to roof (+{va} m allowance)", "designer default")
    log.add("B-pipes", "condensate", f"Condensate to nearest wet-room floor drain / stack with trap; min {dz['pipes']['condensate_min_mm']} mm, slope {dz['pipes']['condensate_slope_pct']} %", C.clause(p, "condensate"), confirm=True)
    design["pipes"] = pipes
    C.save(work, "design.json", design)
    log.save()
    print(f"pipe_sizing: {len(pipes['refrigerant'])} refrigerant runs, {len(pipes['condensate'])} condensate, {len(pipes['chw'])} CHW")
    for r in pipes["refrigerant"]:
        print(f"  {r['tag']}: {r['liquid_mm']}/{r['gas_mm']} mm, {r['total_m']} m (limit {r.get('max_length_m')}) {'OK' if r['ok'] else 'CHECK'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
