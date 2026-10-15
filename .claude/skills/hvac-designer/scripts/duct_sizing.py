"""Step B5 - air terminals, duct layout and duct sizing (equal friction).

Per ducted zone: diffusers per room (flow, NC, coverage), trunk-and-branch layout from the
unit (trunk line chosen to avoid shafts/stairs/columns), flexible run-outs, return grille +
plenum duct, fresh-air louver + duct. Per exhaust room: grille, fan, duct to the nearest
exterior wall (or shaft), louver. Every segment is sized for the friction target and
velocity limit, then pressure drop and the critical-path ESP are checked.

Friction: Darcy-Weisbach with Altshul-Tsal f (ASHRAE Fundamentals 2021 Ch.21).
Rectangular equivalent diameter: Huebscher De = 1.30 (ab)^0.625 / (a+b)^0.25.

CLI: python duct_sizing.py -w WORK   -> design.json (air_systems, exhaust_systems)
"""
import argparse
import math

import common as C
import geom as G

DS = None


def fric(q_ls, d_mm, ds=None):
    ds = ds or DS
    a = ds["air"]
    D = d_mm / 1000
    v = q_ls / 1000 / (math.pi * D * D / 4)
    re = v * D / a["viscosity_m2_s"]
    fp = 0.11 * (a["roughness_mm"] / 1000 / D + 68 / max(re, 1)) ** 0.25
    f = fp if fp >= 0.018 else 0.85 * fp + 0.0028
    return f / D * a["density_kg_m3"] * v * v / 2, v


def de_rect(w, h):
    return 1.30 * (w * h) ** 0.625 / (w + h) ** 0.25


def size_round(q, fmax, vmax, sizes):
    for d in sizes:
        fr, v = fric(q, d)
        if fr <= fmax * 1.05 and v <= vmax:
            return d, fr, v
    d = sizes[-1]
    fr, v = fric(q, d)
    return d, fr, v


def size_rect(q, fmax, vmax, max_depth, inc, hmin, aspect):
    lo, hi = 50.0, 3000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        fr, v = fric(q, mid)
        if fr <= fmax and v <= vmax * 0.97:
            hi = mid
        else:
            lo = mid
    dreq = hi
    best = None
    h = hmin
    while h <= max_depth + 1e-6:
        w = max(hmin, h)
        while w <= 4000:
            if de_rect(w, h) >= dreq and q / 1000 / (w * h / 1e6) <= vmax:
                break
            w += inc
        ok = w / h <= aspect
        cand = (not ok, 2 * (w + h), w, h)
        if best is None or cand < best:
            best = cand
        h += inc
    _, _, w, h = best
    de = de_rect(w, h)
    fr, _ = fric(q, de)
    return w, h, de, fr, q / 1000 / (w * h / 1e6), w / h <= aspect


def gauge(std, shape, longest):
    for lim, g in DS["gauge_tables"][std]["round" if shape == "round" else "rect"]:
        if longest <= lim:
            return g
    return "-"


class Builder:
    def __init__(self, p, fl, log, cls, units):
        self.p, self.fl, self.log = p, fl, log
        self.lim = DS["velocity_limits_m_s"][cls]
        self.fr = DS["friction_target_pa_m"][cls]
        dd = p["design"]["ducts"]
        void = p.get("preferences", {}).get("ceiling_void_mm") or dd["ceiling_void_mm"]
        self.max_depth = void - dd["clearance_mm"] - 2 * dd["insulation_mm"]
        self.ip = units == "IP"
        self.inc = DS["rect_increment_in"] * 25.4 if self.ip else DS["rect_increment_mm"]
        self.hmin = 6 * 25.4 if self.ip else DS["rect_min_mm"]
        self.round_sizes = [s * 25.4 for s in DS["round_sizes_in"]] if self.ip else DS["round_sizes_mm"]
        self.fit = dd["fittings_equivalent_length_factor"]
        self.std = DS["gauge_standard_by_code_set"].get(p["project"]["code_set"], "SMACNA")
        self.n = 0

    def seg(self, zone, system, kind, pts, q, shape="rect", fmax=None, vkey=None):
        self.n += 1
        L = G.m(self.fl, G.polyline_len(pts))
        vmax = self.lim[vkey or {"main": "main", "riser": "main", "branch": "branch", "runout": "runout"}.get(kind, "main")]
        fmax = fmax or self.fr
        s = {"id": f"D-{self.fl['id']}-{self.n:03d}", "zone": zone, "system": system, "kind": kind,
             "pts": [[round(x, 2), round(y, 2)] for x, y in pts], "flow_ls": round(q, 1), "length_m": round(L, 2)}
        if shape == "rect":
            w, h, de, fr, v, ok = size_rect(q, fmax, vmax, self.max_depth, self.inc, self.hmin, self.p["design"]["ducts"]["trunk_max_aspect"])
            s.update(shape="rect", w_mm=round(w), h_mm=round(h), de_mm=round(de), area_m2=round(2 * (w + h) / 1000 * L, 2),
                     gauge=gauge(self.std, "rect", max(w, h)))
            if not ok:
                self.log.ask("Gate2", f"aspect_{s['id']}", f"{s['id']}: duct {w:.0f}x{h:.0f} exceeds aspect ratio - ceiling void {self.max_depth + 150:.0f} mm too shallow? Confirm void depth.")
        else:
            sizes = DS["flex_sizes_mm"] if shape == "flex" else self.round_sizes
            d, fr, v = size_round(q, fmax, vmax, sizes)
            s.update(shape=shape, d_mm=round(d), de_mm=round(d), area_m2=round(math.pi * d / 1000 * L, 2) if shape == "round" else 0,
                     gauge=gauge(self.std, "round", d) if shape == "round" else "flex")
        s.update(velocity_m_s=round(v, 2), friction_pa_m=round(fr, 3), dp_pa=round(fr * L * (1 + self.fit), 1))
        return s


def select_diffusers(q, area, nc_target, max_area):
    terms = C.ref("air_terminals.json")["supply_diffusers"]
    for coverage in (True, False):  # second pass: flow/noise win over coverage area
        for n in range(1, 13):
            per = q / n
            if coverage and area / n > max_area:
                continue
            for t in terms:
                if t["min_ls"] <= per <= t["max_ls"]:
                    nc = t["nc_max"] - 15 * (t["max_ls"] - per) / (t["max_ls"] - t["min_ls"])
                    if nc <= nc_target:
                        return n, t, per, round(nc)
    t = terms[0]
    return 1, t, q, None


def grille(q, kind):
    g = C.ref("air_terminals.json")[kind]
    for w, h in g["sizes_mm"]:
        if q / 1000 / (w * h / 1e6 * g["free_area_ratio"]) <= g["face_velocity_max_m_s"]:
            return w, h
    return g["sizes_mm"][-1]


def obstacles(fl, served):
    obs = [(r["bbox_pt"], r["id"], r["space_type"]) for r in fl["rooms"] if r["space_type"] in ("shaft", "stair") and r["id"] not in served]
    obs += [(c, "column", "column") for c in fl.get("columns", [])]
    return obs


def hits(pts, obs, fl, ignore=()):
    out = []
    pad = G.pt(fl, 0.05)
    for i in range(len(pts) - 1):
        for rect, rid, typ in obs:
            if rid not in ignore and G.seg_hits_rect(pts[i], pts[i + 1], rect, pad):
                out.append(rid)
    return out


def layout_zone(B, z, fl, rooms_by_id, log, st_tbl, dd, served_rooms):
    """Trunk + branches + run-outs for one ducted zone. Returns segments, diffusers, conflicts."""
    U = tuple(z["unit"]["pos_pt"])
    takeoffs = []
    diffusers = []
    for rid, q in z["room_airflow_ls"].items():
        r = rooms_by_id[rid]
        nc_t = st_tbl.get(r["space_type"], {}).get("nc", 35)
        n, t, per, nc = select_diffusers(q, r["area_m2"], nc_t, dd["diffuser_max_area_m2"])
        pts = G.grid_points(r, fl, n)
        for pnt in pts:
            diffusers.append({"room": rid, "model": t["model"], "neck_mm": t["neck_mm"], "face_mm": t["face_mm"], "flow_ls": round(per, 1),
                              "nc": nc, "throw_m": round(t["throw_m"] * per / t["max_ls"], 1), "dp_pa": t["dp_pa"], "pos_pt": [round(pnt[0], 2), round(pnt[1], 2)]})
        tx = sum(p_[0] for p_ in pts) / n
        ty = sum(p_[1] for p_ in pts) / n
        takeoffs.append({"room": rid, "q": q, "pt": (tx, ty), "diffs": [d for d in diffusers if d["room"] == rid]})
        if nc is None:
            log.ask("Gate2", f"nc_{rid}", f"{rid}: no diffuser meets NC {nc_t} at {q:.0f} L/s - accept higher NC or use linear slots?")
    obs = obstacles(fl, served_rooms)
    best = None
    for axis in (0, 1):
        o = 1 - axis
        cands = {round(U[o], 2)} | {round(t["pt"][o], 2) for t in takeoffs} | {round(rooms_by_id[r]["centroid_pt"][o], 2) for r in z["rooms"]}
        for c in cands:
            segs_pts, conflicts = build_tree(U, takeoffs, axis, c)
            length = sum(G.polyline_len(sp[2]) for sp in segs_pts)
            ncon = 0
            for kind, q, pts, rid, _ in segs_pts:
                ncon += len(hits(pts, obs, fl, ignore=(rid,)))
            cost = length + ncon * G.pt(fl, 50.0)
            if best is None or cost < best[0]:
                best = (cost, axis, c, segs_pts)
    _, axis, c, segs_pts = best
    segs, conflicts = [], []
    for kind, q, pts, rid, down in segs_pts:
        shape = "rect" if kind in ("riser", "main", "branch") else "flex"
        if kind == "runout" and G.m(fl, G.polyline_len(pts)) > dd["branch_takeoff_flex_m"]:
            shape = "round"
        s = B.seg(z["id"], "supply", kind, pts, q, shape)
        s["serves"] = rid
        s["down"] = down
        h = hits(pts, obs, fl, ignore=(rid,))
        if h:
            s["conflict"] = sorted(set(h))
            conflicts.append({"segment": s["id"], "with": sorted(set(h))})
        segs.append(s)
    return segs, diffusers, conflicts, axis


def build_tree(U, takeoffs, axis, c):
    """Trunk along 'axis' (0 = x varies) at other-coordinate c. Returns [(kind, q, pts, room)]."""
    o = 1 - axis

    def P(a, b):  # a along axis, b across
        return (a, b) if axis == 0 else (b, a)
    out = []
    total = sum(t["q"] for t in takeoffs)
    start = P(U[axis], c)
    eps = 1.5  # pt; shorter pieces are dropped (fitting length)
    if abs(U[o] - c) > eps:
        out.append(("riser", total, [U, start], None, [t["room"] for t in takeoffs]))
    for side in (-1, 1):
        arm = sorted([t for t in takeoffs if (t["pt"][axis] - U[axis]) * side > 0 or (side == 1 and t["pt"][axis] == U[axis])],
                     key=lambda t: abs(t["pt"][axis] - U[axis]))
        prev = U[axis]
        for i, t in enumerate(arm):
            q = sum(x["q"] for x in arm[i:])
            a = t["pt"][axis]
            if abs(a - prev) > eps:
                out.append(("main", q, [P(prev, c), P(a, c)], None, [x["room"] for x in arm[i:]]))
            prev = a
    for t in takeoffs:
        a, b = t["pt"][axis], t["pt"][o]
        node = P(a, c)
        if abs(b - c) > eps:
            out.append(("branch", t["q"], [node, P(a, b)], t["room"], [t["room"]]))
        for d in t["diffs"]:
            dp = tuple(d["pos_pt"])
            if G.dist(dp, P(a, b)) > eps:
                out.append(("runout", d["flow_ls"], G.l_route(P(a, b), dp, horizontal_first=(axis == 1)), t["room"], [t["room"]]))
    return out, []


def path_dp(segs, diff):
    """Pressure drop from the unit to one diffuser along the segments that serve it."""
    total = 0.0
    for s in segs:
        if diff["room"] not in s.get("down", ()):
            continue
        if s["kind"] == "runout" and s["pts"][-1] != diff["pos_pt"]:
            continue
        total += s["dp_pa"]
    return total


def compute(work):
    global DS
    DS = C.ref("duct_sizing.json")
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    design = C.load(work, "design.json")
    vent = C.load(work, "ventilation.json")
    log = C.Log(work, "duct_sizing")
    st_tbl = C.ref("space_types.json")["types"]
    cls = "residential" if C.building_class(p) == "residential" else "commercial"
    dd = p["design"]["ducts"]
    fls = {f["id"]: f for f in rooms["floors"]}
    idx = G.room_index(rooms)
    air, exh = [], []
    builders = {}
    counters = {}

    used_wall = {}

    def free_wall_point(fl, q, edge):
        """Shift a louver along its wall so two louvers never share a spot."""
        lst = used_wall.setdefault(fl["id"], [])
        (ax, ay), (bx, by) = edge["p1"], edge["p2"]
        L = G.dist((ax, ay), (bx, by)) or 1
        ux, uy = (bx - ax) / L, (by - ay) / L
        step = G.pt(fl, 0.8)
        for k in (0, 1, -1, 2, -2, 3, -3):
            cand = (q[0] + ux * step * k, q[1] + uy * step * k)
            if all(G.dist(cand, u) > step * 0.9 for u in lst):
                lst.append(cand)
                return cand
        lst.append(q)
        return q

    def tag(kind, floor):
        k = (kind, floor)
        counters[k] = counters.get(k, 0) + 1
        return f"{kind}-{floor}-{counters[k]:02d}"

    for z in design["zones"]:
        fl = fls[z["floor"]]
        B = builders.setdefault(fl["id"], Builder(p, fl, log, cls, p["units"]))
        if z["kind"] != "ducted":
            continue
        rooms_by_id = {r["id"]: r for r in fl["rooms"]}
        segs, diffs, conflicts, axis = layout_zone(B, z, fl, rooms_by_id, log, st_tbl, dd, set(z["rooms"]))
        for d in diffs:
            d["tag"] = tag("SD", fl["id"])
        # return grille + plenum duct
        U = tuple(z["unit"]["pos_pt"])
        host = rooms_by_id[z["unit"]["host_room"]]
        q = z["unit"]["airflow_ls"]
        gw, gh = grille(q, "return_grilles")
        off = G.pt(fl, 1.2)
        rpt = (U[0], U[1] + off) if axis == 0 else (U[0] + off, U[1])
        if not G.point_in_poly(rpt, host["polygon_pt"]):
            rpt = (U[0], U[1] - off) if axis == 0 else (U[0] - off, U[1])
        rg = {"tag": tag("RG", fl["id"]), "room": host["id"], "w_mm": gw, "h_mm": gh, "flow_ls": q, "pos_pt": [round(rpt[0], 2), round(rpt[1], 2)],
              "type": "return grille with plenum box and filter"}
        rseg = B.seg(z["id"], "return", "main", [rpt, U], q, "rect", vkey="return")
        # fresh air
        vot = z["unit"]["oa_ls"]
        fa = None
        if vot > 0 and z["oa_method"].startswith("ducted"):
            qpt, edge, er = G.nearest_exterior(fl, U)
            if qpt:
                qpt = free_wall_point(fl, qpt, edge)
                lw, lh = grille(vot, "louvers")
                route = G.l_route(qpt, U, horizontal_first=(abs(edge["normal_page"][1]) > 0.5))
                fseg = B.seg(z["id"], "fresh_air", "main", route, vot, "round", fmax=DS["friction_target_pa_m"]["exhaust"], vkey="fresh_air")
                fa = {"louver": {"tag": tag("FAL", fl["id"]), "w_mm": lw, "h_mm": lh, "flow_ls": vot, "pos_pt": [round(qpt[0], 2), round(qpt[1], 2)],
                                 "room": er["id"], "normal": edge["normal_page"]},
                      "segments": [fseg], "dampers": ["VCD", "MD (motorised, interlocked with unit)"], "filter": "G4 panel filter in louver plenum"}
            else:
                log.ask("Gate2", f"fa_{z['id']}", f"{z['id']}: no exterior wall found for the fresh-air louver - where should fresh air be taken?")
        # pressure check
        worst = 0.0
        for d in diffs:
            worst = max(worst, path_dp(segs, d) + d["dp_pa"])
        esp_req = worst + rseg["dp_pa"] + dd["return_grille_pa"] + dd["unit_plenum_and_filter_pa"]
        esp_ok = esp_req <= z["unit"]["esp_pa"]
        if not esp_ok:
            log.ask("Gate2", f"esp_{z['id']}", f"{z['id']}: required ESP {esp_req:.0f} Pa > unit {z['unit']['esp_pa']} Pa - choose high-static unit or enlarge ducts?")
        for c in conflicts:
            log.ask("Gate2", f"conflict_{c['segment']}", f"{c['segment']} ({z['id']}) crosses {c['with']} - reroute needed (no clear path found).")
        transfers = [rid for rid in z["rooms"] if rid != host["id"] and idx[rid][1]["space_type"] not in ("corridor", "hall", "stair")]
        air.append({"zone": z["id"], "floor": fl["id"], "unit": z["unit"]["tag"], "trunk_axis": "x" if axis == 0 else "y", "segments": segs, "diffusers": diffs,
                    "return": {"grille": rg, "segments": [rseg]}, "fresh_air": fa, "vcd_branches": sorted({s["serves"] for s in segs if s["kind"] == "branch"}),
                    "transfer_grilles": transfers, "esp_required_pa": round(esp_req), "esp_available_pa": z["unit"]["esp_pa"], "esp_ok": esp_ok,
                    "conflicts": conflicts, "supply_total_ls": round(sum(d["flow_ls"] for d in diffs), 1)})

    # exhaust systems
    cat = C.ref("equipment_catalog.json")["exhaust_fan"]["models"]
    for rid, e in vent["exhaust"].items():
        fl, r = idx[rid]
        B = builders.setdefault(fl["id"], Builder(p, fl, log, cls, p["units"]))
        q = e["ls"]
        g = grille(q, "exhaust_grilles")
        gpt = tuple(r["centroid_pt"])
        own = [x for x in r.get("edges", []) if x["exterior_frac"] >= 0.25]
        if own:
            qpt, edge, er = G.nearest_exterior(fl, gpt, rooms=[r], min_frac=0.25)
        else:
            qpt, edge, er = G.nearest_exterior(fl, gpt)
        shafts = [s for s in fl["rooms"] if s["space_type"] == "shaft"]
        to_shaft = None
        if shafts:
            sh = min(shafts, key=lambda s: G.manhattan(gpt, s["centroid_pt"]))
            if not qpt or G.manhattan(gpt, sh["centroid_pt"]) < G.manhattan(gpt, qpt) * 0.7:
                to_shaft = sh
        if to_shaft:
            end = tuple(to_shaft["centroid_pt"])
            disch = {"type": "shaft", "room": to_shaft["id"], "note": "exhaust riser in shaft to roof cowl"}
        elif qpt:
            qpt = free_wall_point(fl, qpt, edge)
            end = qpt
            lw, lh = grille(q, "louvers")
            disch = {"type": "wall_louver", "tag": tag("EAL", fl["id"]), "w_mm": lw, "h_mm": lh, "room": er["id"], "normal": edge["normal_page"],
                     "pos_pt": [round(qpt[0], 2), round(qpt[1], 2)]}
        else:
            log.ask("Gate2", f"exh_{rid}", f"{rid}: no exterior wall or shaft for exhaust discharge - where should it go?")
            continue
        fan_pt = (gpt[0] + (end[0] - gpt[0]) * 0.25, gpt[1] + (end[1] - gpt[1]) * 0.25)
        route = G.l_route(gpt, end, horizontal_first=abs(end[0] - gpt[0]) > abs(end[1] - gpt[1]))
        seg = B.seg(rid, "exhaust", "main", route, q, "round", fmax=DS["friction_target_pa_m"]["exhaust"], vkey="exhaust")
        esp = seg["dp_pa"] + dd["exhaust_louver_backdraft_pa"] + dd["exhaust_grille_pa"]
        fm = next((m for m in cat if m["airflow_ls"] >= q and m["esp_pa"] >= esp), cat[-1])
        exh.append({"room": rid, "floor": fl["id"], "flow_ls": q, "rule": e["rule"], "clause": e["clause"],
                    "grille": {"tag": tag("EG", fl["id"]), "w_mm": g[0], "h_mm": g[1], "pos_pt": [round(gpt[0], 2), round(gpt[1], 2)]},
                    "fan": {"tag": tag("EF", fl["id"]), "model": fm["model"], "type": fm["type"], "airflow_ls": q, "esp_req_pa": round(esp), "esp_pa": fm["esp_pa"],
                            "power_w": fm["power_w"], "pos_pt": [round(fan_pt[0], 2), round(fan_pt[1], 2)], "backdraft_damper": True},
                    "segments": [seg], "discharge": disch})
    log.add("B-ducts", "duct_method", f"Ducts sized by equal friction {DS['friction_target_pa_m'][cls]} Pa/m with velocity limits {DS['velocity_limits_m_s'][cls]} m/s; "
            f"max duct depth {Builder(p, next(iter(fls.values())), log, cls, p['units']).max_depth:.0f} mm from ceiling void", C.clause(p, "duct_sizing"))
    log.add("B-ducts", "fittings", f"Fittings allowed as +{dd['fittings_equivalent_length_factor']:.0%} equivalent length; unit plenum/filter {dd['unit_plenum_and_filter_pa']} Pa", "designer default", confirm=True)
    log.add("B-ducts", "layout", "Duct routes are schematic trunk-and-branch lines over the plan; coordinate with structure (beams), lighting and other services", "designer judgement", confirm=True)
    log.add("B-ducts", "transfer", "Return air from rooms via door undercut / door transfer grilles to the return grille near the unit", C.clause(p, "duct_sizing"), confirm=True)
    design["air_systems"] = air
    design["exhaust_systems"] = exh
    C.save(work, "design.json", design)
    log.save()
    n_seg = sum(len(a["segments"]) for a in air)
    print(f"duct_sizing: {len(air)} supply systems ({n_seg} segments, {sum(len(a['diffusers']) for a in air)} diffusers), {len(exh)} exhaust systems")
    for a in air:
        print(f"  {a['zone']}: supply {a['supply_total_ls']} L/s, ESP req {a['esp_required_pa']} / avail {a['esp_available_pa']} Pa, conflicts {len(a['conflicts'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    compute(ap.parse_args().work)
