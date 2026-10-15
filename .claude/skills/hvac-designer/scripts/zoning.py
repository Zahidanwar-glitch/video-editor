"""Step B2 - assign a system to each conditioned room and group rooms into zones.

Priority: project.json zones_override > systems.by_room > systems.by_space_type > systems.default.
Room-unit systems (wall_split, vrf) -> one zone per room. Ducted systems (ducted_split,
packaged_rooftop, chilled_water) -> rooms grouped per floor: 'own_zone_types' get their own
zone, 'dressing' joins an adjacent own-zone room, the rest are grouped by position until the
largest allowed unit (with safety factor) is reached.

CLI: python zoning.py -w WORK   -> zones.json
"""
import argparse

import common as C
import geom as G

ROOM_UNIT = {"wall_split": "wall_split", "vrf": "vrf_indoor_ducted"}
DUCTED = {"ducted_split": "ducted_split", "packaged_rooftop": "packaged_rooftop", "chilled_water": "fcu_ducted"}
VALID = set(ROOM_UNIT) | set(DUCTED)
ATTACH_TYPES = ("dressing",)


def max_kw(p, system):
    cat = C.ref("equipment_catalog.json")
    if system == "ducted_split":
        return p["design"]["zoning"]["max_ducted_unit_kw"]
    key = DUCTED.get(system) or ROOM_UNIT.get(system)
    return max(mm["cool_kw"] for mm in cat[key]["models"])


def compute(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    loads = {r["id"]: r for r in C.load(work, "loads.json")["rooms"]}
    log = C.Log(work, "zoning")
    sysc = p.get("systems", {})
    sf = p["design"]["loads"]["safety_factor_cooling"]
    zc = p["design"]["zoning"]
    zones, exhaust_only, uncond = [], [], []

    def system_of(r):
        s = sysc.get("by_room", {}).get(r["id"]) or sysc.get("by_space_type", {}).get(r["space_type"]) or sysc.get("default")
        if s not in VALID:
            raise SystemExit(f"System '{s}' for {r['id']} not recognised - use one of {sorted(VALID)} (ask the user).")
        return s

    if not sysc.get("default"):
        raise SystemExit("project.json systems.default is empty - ask the user which HVAC system to use.")
    override = p.get("zones_override") or []
    fixed = {rid for z in override for rid in z["rooms"]}
    for fl in G.floors(rooms):
        n = 0
        def new_zone(system, members, kind):
            nonlocal n
            n += 1
            zones.append({"id": f"Z-{fl['id']}-{n:02d}", "floor": fl["id"], "system": system, "kind": kind,
                          "rooms": [r["id"] for r in members],
                          "load_kw": round(sum(loads[r["id"]]["total_w"] for r in members) / 1000, 2)})
        for z in override:
            mem = [r for r in fl["rooms"] if r["id"] in z["rooms"]]
            if mem:
                new_zone(z["system"], mem, "room_unit" if z["system"] in ROOM_UNIT else "ducted")
        pool = {}
        for r in fl["rooms"]:
            if r["id"] in fixed:
                continue
            L = loads.get(r["id"])
            if not L or not L["conditioned"]:
                st = C.ref("space_types.json")["types"].get(r["space_type"], {})
                (exhaust_only if st.get("exhaust") else uncond).append(r["id"])
                continue
            s = system_of(r)
            if s in ROOM_UNIT:
                new_zone(s, [r], "room_unit")
            else:
                pool.setdefault(s, []).append(r)
        for s, members in pool.items():
            cap = max_kw(p, s)
            own = [r for r in members if r["space_type"] in zc["own_zone_types"]] if zc.get("group_ducted_rooms", True) else list(members)
            rest = [r for r in members if r not in own]
            groups = [[r] for r in own]
            for r in list(rest):
                if r["space_type"] in ATTACH_TYPES:
                    for g in groups:
                        if G.adjacent(r, g[0], fl):
                            g.append(r)
                            rest.remove(r)
                            break
            x0, y0, x1, y1 = (min(r["bbox_pt"][0] for r in members), min(r["bbox_pt"][1] for r in members),
                              max(r["bbox_pt"][2] for r in members), max(r["bbox_pt"][3] for r in members))
            axis = 0 if (x1 - x0) >= (y1 - y0) else 1
            rest.sort(key=lambda r: (r["centroid_pt"][axis], r["centroid_pt"][1 - axis]))
            cur, cur_kw = [], 0.0
            for r in rest:
                kw = loads[r["id"]]["total_w"] / 1000 * (1 + sf)
                if cur and cur_kw + kw > cap:
                    groups.append(cur)
                    cur, cur_kw = [], 0.0
                cur.append(r)
                cur_kw += kw
            if cur:
                groups.append(cur)
            for g in groups:
                if sum(loads[r["id"]]["total_w"] for r in g) / 1000 * (1 + sf) > cap:
                    log.ask("Gate2", f"zone_cap_{g[0]['id']}", f"Rooms {[r['id'] for r in g]} exceed the largest {s} unit ({cap} kW): split the room or allow a larger unit.")
                new_zone(s, g, "ducted")
    log.add("B-zoning", "zoning", f"Zoning: own zone for {zc['own_zone_types']}; other ducted rooms grouped by position per floor up to {zc['max_ducted_unit_kw']} kW per unit (incl. safety factor)",
            "references/design_defaults.json zoning", confirm=True)
    if exhaust_only:
        log.add("B-zoning", "exhaust_only", f"Rooms exhaust-only (not cooled; make-up by transfer air): {', '.join(exhaust_only)}", "references/space_types.json", confirm=True)
    out = {"zones": zones, "exhaust_only": exhaust_only, "unconditioned": uncond}
    C.save(work, "zones.json", out)
    log.save()
    print(f"zones.json: {len(zones)} zones; exhaust-only {len(exhaust_only)}; unconditioned {len(uncond)}")
    for z in zones:
        print(f"  {z['id']} {z['system']:<14} {z['load_kw']:>6} kW  {z['rooms']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
