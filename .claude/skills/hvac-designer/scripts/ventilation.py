"""Step B3 - outdoor air per zone (ASHRAE 62.1 ventilation rate procedure / local code)
and exhaust per room (toilets, kitchens, laundries).

Vbz = Rp*Pz + Ra*Az ; Voz = Vbz/Ez ; single-zone Vot = Voz ;
multi-zone Vot = (D*sum(Rp*Pz) + sum(Ra*Az)) / Ev  (simplified procedure).
Room-unit (wall split) rooms: through-wall fresh-air fan when the room has an exterior wall,
otherwise their OA is added to an adjacent ducted zone (transfer) - both logged.

CLI: python ventilation.py -w WORK   -> ventilation.json
"""
import argparse

import common as C
import geom as G


def compute(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    loads = {r["id"]: r for r in C.load(work, "loads.json")["rooms"]}
    zones = C.load(work, "zones.json")
    log = C.Log(work, "ventilation")
    V = C.ref("ventilation_rates.json")
    cs = p["project"]["code_set"]
    cats = C.deep_merge(V["oa_categories"]["default"], V["oa_categories"].get(cs, {}))
    exh_rules = C.deep_merge(V["exhaust"]["default"], V["exhaust"].get(cs, {}))
    st_tbl = C.ref("space_types.json")["types"]
    idx = G.room_index(rooms)
    heating = any(r["heating_w"] > 0 for r in loads.values())
    ez = V["zone_effectiveness_Ez"]["ceiling_supply_warm"] if heating else V["zone_effectiveness_Ez"]["ceiling_supply_cool"]
    D = V["system_effectiveness"]["D_residential"] if C.building_class(p) == "residential" else None
    out = {"zones": {}, "exhaust": {}, "transfers": [], "basis": {}}

    def vbz(rid):
        L = loads[rid]
        st = st_tbl.get(L["space_type"], st_tbl["unknown"])
        cat = cats.get(st.get("vent_category") or "", None)
        if not cat:
            return 0.0, 0.0, None
        return cat["Rp"] * L["people"], cat["Ra"] * L["area_m2"], st["vent_category"]

    ducted = [z for z in zones["zones"] if z["kind"] == "ducted"]
    for z in zones["zones"]:
        rows, sum_p, sum_a = [], 0.0, 0.0
        for rid in z["rooms"]:
            pp, aa, cat = vbz(rid)
            rows.append({"room": rid, "category": cat, "people": loads[rid]["people"], "area_m2": loads[rid]["area_m2"],
                         "Rp_Pz": round(pp, 1), "Ra_Az": round(aa, 1), "Vbz": round(pp + aa, 1), "Voz": round((pp + aa) / ez, 1)})
            sum_p += pp
            sum_a += aa
        if len(z["rooms"]) == 1:
            ev, vot, method = 1.0, (sum_p + sum_a) / ez, "single-zone: Vot = Voz"
        else:
            Dz = D if D is not None else 1.0
            ev = 0.88 * Dz + 0.22 if Dz < 0.60 else 0.75
            vot, method = (Dz * sum_p + sum_a) / ev, "multi-zone simplified: Vot = (D·ΣRpPz + ΣRaAz)/Ev"
        oa_method = "ducted to unit return plenum" if z["kind"] == "ducted" else None
        if z["kind"] == "room_unit":
            f, r = idx[z["rooms"][0]]
            if r.get("exterior_walls"):
                oa_method = "through-wall fresh air fan"
            else:
                host = next((d for d in ducted if d["floor"] == z["floor"] and any(G.adjacent(r, idx[x][1], f) for x in d["rooms"])), None)
                host = host or next((d for d in ducted if d["floor"] == z["floor"]), None)
                if host:
                    oa_method = f"transfer air from {host['id']} (OA added to that zone)"
                    out["transfers"].append({"from_zone": host["id"], "to_zone": z["id"], "ls": round(vot, 1)})
                    log.add("B-vent", f"transfer_{z['id']}", f"{z['id']} ({r['name']}) has no exterior wall: its {vot:.0f} L/s OA is supplied via {host['id']} and transferred", C.clause(p, "oa_rate"), confirm=True)
                else:
                    oa_method = "NONE - no exterior wall and no ducted zone"
                    log.ask("Gate2", f"oa_{z['id']}", f"{z['id']} ({r['name']}): no exterior wall and no ducted zone nearby - how should outdoor air be provided?")
        out["zones"][z["id"]] = {"rooms": rows, "Ez": ez, "Ev": round(ev, 2), "sum_RpPz": round(sum_p, 1), "sum_RaAz": round(sum_a, 1),
                                 "Vot_ls": round(vot, 1), "method": method, "oa_method": oa_method}
    for t in out["transfers"]:
        out["zones"][t["from_zone"]]["Vot_ls"] = round(out["zones"][t["from_zone"]]["Vot_ls"] + t["ls"], 1)
        out["zones"][t["from_zone"]].setdefault("transfer_out_ls", 0)
        out["zones"][t["from_zone"]]["transfer_out_ls"] += t["ls"]

    for f in G.floors(rooms):
        for r in f["rooms"]:
            st = st_tbl.get(r["space_type"], {})
            rule = st.get("exhaust")
            if not rule:
                continue
            ru = exh_rules[rule]
            if ru["mode"] == "intermittent":
                ls = ru["ls"]
            elif ru["mode"] == "area":
                ls = ru["ls_m2"] * r["area_m2"]
            else:
                nfix = r.get("fixtures")
                if not nfix:
                    log.ask("Gate2", f"fixtures_{r['id']}", f"{r['id']} {r['name']}: number of WCs/urinals needed for exhaust sizing.")
                    nfix = 1
                ls = ru["ls_per_fixture"] * nfix
            out["exhaust"][r["id"]] = {"room": r["name"], "floor": f["id"], "rule": rule, "ls": round(ls, 1), "mode": ru["mode"],
                                       "clause": C.clause(p, ru["clause"]), "note": ru.get("note", "")}
    tot_oa = sum(z["Vot_ls"] for z in out["zones"].values() if z["oa_method"] and "transfer air" not in z["oa_method"])
    tot_ex = sum(e["ls"] for e in out["exhaust"].values())
    bal = C.ref("ventilation_rates.json")["residential_whole_house_62_2"]
    cond_area = sum(r["area_m2"] for r in loads.values() if r["conditioned"])
    nbr = sum(1 for r in loads.values() if r["space_type"] in ("bedroom", "master_bedroom", "maid_room"))
    out["basis"] = {"Ez": ez, "Ez_reason": "heat-pump heating with ceiling supply of warm air" if heating else "cooling only",
                    "clause_oa": C.clause(p, "oa_rate"), "clause_ez": C.clause(p, "oa_zone_eff"), "clause_ev": C.clause(p, "oa_system_eff")}
    out["totals"] = {"oa_ls": round(tot_oa, 1), "exhaust_ls": round(tot_ex, 1),
                     "balance_ls": round(tot_oa - tot_ex, 1),
                     "res_62_2_check_ls": round(bal["a"] * cond_area + bal["b"] * (nbr + 1), 1) if C.building_class(p) == "residential" else None}
    log.add("B-vent", "ez", f"Zone air distribution effectiveness Ez = {ez} ({out['basis']['Ez_reason']})", C.clause(p, "oa_zone_eff"))
    log.add("B-vent", "exhaust_mode", "Exhaust fans sized for the intermittent (rated) rate; continuous operation would allow the lower rate", C.clause(p, "exhaust_toilet"))
    if tot_oa < tot_ex:
        log.add("B-vent", "balance", f"Building OA {tot_oa:.0f} L/s < exhaust {tot_ex:.0f} L/s (intermittent): building slightly negative when all fans run; acceptable for intermittent fans, else raise OA",
                "designer judgement", confirm=True)
    C.save(work, "ventilation.json", out)
    log.save()
    print(f"ventilation.json: OA {tot_oa:.0f} L/s, exhaust {tot_ex:.0f} L/s ({len(out['exhaust'])} rooms), 62.2 check {out['totals']['res_62_2_check_ls']} L/s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
