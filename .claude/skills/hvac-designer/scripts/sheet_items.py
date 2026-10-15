"""Turn design.json into drawing primitives per sheet (page points, y down).

One source for both the PDF overlay and the DXF export, so both show the same items
and checks can compare drawn tags with the BOQ.
Primitive kinds: band (duct: centre polyline + real width), line, rect, circle, cross, text.
"""
import common as C
import geom as G


def _txt_pt(fl, paper_mm):
    """Paper text height (mm) -> points (independent of scale)."""
    return paper_mm * 72 / 25.4


def items_for(floor_id, design, rooms, units):
    U = C.Units(units)
    fls = {f["id"]: f for f in rooms["floors"]}
    fl = fls[floor_id]
    th = C.ref("drawing_standards.json")["text_height_paper_mm"]
    out = []
    T = lambda pos, text, layer="M-ANNO", size="tag", angle=0: out.append(
        {"kind": "text", "layer": layer, "pos": list(pos), "text": text, "size_pt": _txt_pt(fl, th[size]), "angle": angle})

    def band(seg, layer, style="solid"):
        w = seg.get("w_mm") or seg.get("d_mm") or 150
        out.append({"kind": "band", "layer": layer, "pts": seg["pts"], "width_pt": G.pt(fl, w / 1000), "style": style, "id": seg["id"]})
        if seg["length_m"] >= 1.0 and seg["kind"] in ("main", "branch", "riser"):
            a, b = seg["pts"][0], seg["pts"][-1]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            horiz = abs(a[1] - b[1]) < abs(a[0] - b[0])
            size = U.rect(seg["w_mm"], seg["h_mm"]) if seg["shape"] == "rect" else ("Ø" + U.size(seg["d_mm"]))
            off = G.pt(fl, w / 2000 + 0.15)
            pos = (mid[0], mid[1] - off) if horiz else (mid[0] + off, mid[1])
            T(pos, f"{size} {U.flow(seg['flow_ls'])}", layer="M-ANNO", size="size", angle=0 if horiz else 90)

    def rect(center, w_m, h_m, layer, tag=None, fill=None, cross=False, diag=False):
        out.append({"kind": "rect", "layer": layer, "center": list(center), "w": G.pt(fl, w_m), "h": G.pt(fl, h_m),
                    "tag": tag, "fill": fill, "cross": cross, "diag": diag})

    for a in design.get("air_systems", []):
        if a["floor"] != floor_id:
            continue
        for s in a["segments"]:
            band(s, "M-DUCT-SUPP", "dash" if s["shape"] == "flex" else "solid")
        for d in a["diffusers"]:
            f = d["face_mm"] / 1000
            rect(d["pos_pt"], f, f, "M-DUCT-SUPP", tag=d["tag"], cross=True)
            T((d["pos_pt"][0] + G.pt(fl, f / 2 + 0.1), d["pos_pt"][1] + G.pt(fl, f / 2 + 0.25)), f"{d['tag']} {U.flow(d['flow_ls'])}")
        rg = a["return"]["grille"]
        rect(rg["pos_pt"], rg["w_mm"] / 1000, rg["h_mm"] / 1000, "M-DUCT-RETN", tag=rg["tag"], diag=True)
        T((rg["pos_pt"][0] + G.pt(fl, rg["w_mm"] / 2000 + 0.1), rg["pos_pt"][1] + G.pt(fl, 0.5)), f"{rg['tag']} {U.rect(rg['w_mm'], rg['h_mm'])}")
        for s in a["return"]["segments"]:
            band(s, "M-DUCT-RETN")
        fa = a.get("fresh_air")
        if fa:
            for s in fa["segments"]:
                band(s, "M-DUCT-FRSH", "dash")
            lv = fa["louver"]
            nx, ny = lv["normal"]
            w = lv["w_mm"] / 1000
            rect(lv["pos_pt"], w if abs(ny) > 0.5 else 0.15, 0.15 if abs(ny) > 0.5 else w, "M-DUCT-FRSH", tag=lv["tag"], fill=(0.0, 0.65, 0.65))
            T((lv["pos_pt"][0] + nx * G.pt(fl, 0.6), lv["pos_pt"][1] + ny * G.pt(fl, 0.6)), f"{lv['tag']} FA {U.flow(lv['flow_ls'])}")
    for z in design["zones"]:
        if z["floor"] != floor_id:
            continue
        u = z["unit"]
        fw, fd = u.get("footprint_m", [1.0, 0.5])
        if u["type"] == "wall_split":
            room = next(r for r in fl["rooms"] if r["id"] == u["host_room"])
            e = min(room["edges"], key=lambda e: G.dist(u["pos_pt"], G.proj_on_seg(u["pos_pt"], e["p1"], e["p2"])[0]))
            horiz = abs(e["p1"][1] - e["p2"][1]) < abs(e["p1"][0] - e["p2"][0])
            rect(u["pos_pt"], fw if horiz else fd, fd if horiz else fw, "M-EQPM", tag=u["tag"], fill=(0.8, 0, 0))
        else:
            ax = next((a["trunk_axis"] for a in design.get("air_systems", []) if a["unit"] == u["tag"]), "x")
            rect(u["pos_pt"], fw if ax == "x" else fd, fd if ax == "x" else fw, "M-EQPM", tag=u["tag"], fill=(0.8, 0, 0))
        T((u["pos_pt"][0] - G.pt(fl, 0.6), u["pos_pt"][1] - G.pt(fl, 0.55)), f"{u['tag']} {u['model']} {U.power(u['nominal_kw'])}", layer="M-EQPM")
        t = z["thermostat"]
        out.append({"kind": "circle", "layer": "M-CTRL", "center": t["pos_pt"], "r": G.pt(fl, 0.15), "tag": t["tag"], "text": "T"})
        T((t["pos_pt"][0] + G.pt(fl, 0.25), t["pos_pt"][1] + G.pt(fl, 0.1)), t["tag"], layer="M-CTRL")
        if z.get("fa_fan"):
            f = z["fa_fan"]
            rect(f["pos_pt"], 0.3, 0.3, "M-DUCT-FRSH", tag=f["tag"], cross=True)
            T((f["pos_pt"][0] + G.pt(fl, 0.3), f["pos_pt"][1] - G.pt(fl, 0.3)), f"{f['tag']} {U.flow(f['airflow_ls'])}")
    for e in design.get("exhaust_systems", []):
        if e["floor"] != floor_id:
            continue
        for s in e["segments"]:
            band(s, "M-DUCT-EXHS", "dash")
        g = e["grille"]
        rect(g["pos_pt"], g["w_mm"] / 1000, g["h_mm"] / 1000, "M-DUCT-EXHS", tag=g["tag"], diag=True)
        T((g["pos_pt"][0] - G.pt(fl, 0.4), g["pos_pt"][1] + G.pt(fl, 0.45)), f"{g['tag']} {U.flow(e['flow_ls'])}")
        f = e["fan"]
        out.append({"kind": "circle", "layer": "M-DUCT-EXHS", "center": f["pos_pt"], "r": G.pt(fl, 0.18), "tag": f["tag"], "text": "X"})
        T((f["pos_pt"][0] + G.pt(fl, 0.25), f["pos_pt"][1] - G.pt(fl, 0.25)), f"{f['tag']} {f['model']}")
        dsc = e["discharge"]
        if dsc["type"] == "wall_louver":
            nx, ny = dsc["normal"]
            w = dsc["w_mm"] / 1000
            rect(dsc["pos_pt"], w if abs(ny) > 0.5 else 0.15, 0.15 if abs(ny) > 0.5 else w, "M-DUCT-EXHS", tag=dsc["tag"], fill=(0.75, 0, 0.6))
            T((dsc["pos_pt"][0] + nx * G.pt(fl, 0.6) - G.pt(fl, 0.3), dsc["pos_pt"][1] + ny * G.pt(fl, 0.6)), dsc["tag"])
        else:
            T(e["segments"][0]["pts"][-1], "EA UP TO ROOF")
    P = design.get("pipes", {})
    risers_drawn = set()
    for r in P.get("refrigerant", []):
        if r["floor"] == floor_id and r["pts_floor"]:
            out.append({"kind": "line", "layer": "M-PIPE-REFG", "pts": r["pts_floor"], "style": "solid", "lw": 1.2, "tag": r["tag"]})
            a = r["pts_floor"][len(r["pts_floor"]) // 2]
            T((a[0] + G.pt(fl, 0.2), a[1] - G.pt(fl, 0.2)), f"{r['tag']} {r['liquid_mm']}/{r['gas_mm']}", layer="M-PIPE-REFG", size="size")
            key = tuple(r["riser_pt"])
            if key not in risers_drawn:
                risers_drawn.add(key)
                out.append({"kind": "circle", "layer": "M-PIPE-REFG", "center": r["riser_pt"], "r": G.pt(fl, 0.2), "text": "R"})
                T((r["riser_pt"][0] + G.pt(fl, 0.3), r["riser_pt"][1] + G.pt(fl, 0.6)), "REFG RISER TO ROOF", layer="M-PIPE-REFG", size="size")
        if fl.get("kind") == "roof" and r["pts_roof"]:
            out.append({"kind": "line", "layer": "M-PIPE-REFG", "pts": r["pts_roof"], "style": "solid", "lw": 1.2, "tag": r["tag"]})
    for c in P.get("condensate", []):
        if c["floor"] == floor_id:
            out.append({"kind": "line", "layer": "M-PIPE-COND", "pts": c["pts"], "style": "dot", "lw": 1.0, "tag": c["tag"]})
            a = c["pts"][-1]
            T((a[0] + G.pt(fl, 0.15), a[1] + G.pt(fl, 0.35)), f"{c['tag']} Ø{U.size(c['dn_mm'])}", layer="M-PIPE-COND", size="size")
    for c in P.get("chw", []):
        if c["floor"] == floor_id and c["pts_floor"]:
            out.append({"kind": "line", "layer": "M-PIPE-CHWS", "pts": c["pts_floor"], "style": "solid", "lw": 1.4, "tag": c["tag"]})
    if fl.get("kind") == "roof":
        for o in design["outdoor_units"]:
            if o.get("floor") == floor_id and o.get("pos_pt"):
                w, d = o.get("footprint_m", [1.0, 0.4])
                rect(o["pos_pt"], w, d, "M-EQPM", tag=o["tag"], fill=(0.8, 0, 0))
                T((o["pos_pt"][0] - G.pt(fl, w / 2), o["pos_pt"][1] + G.pt(fl, d / 2 + 0.35)), f"{o['tag']} {o['model']} {U.power(o['cool_kw'])}", layer="M-EQPM")
    return declutter(out)


def _text_box(it, pos):
    w = len(it["text"]) * it["size_pt"] * 0.52
    h = it["size_pt"]
    x, y = pos
    if it.get("angle") == 90:
        return (x - h, y - w, x, y)
    return (x, y - h, x + w, y + 0.2 * h)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def declutter(items):
    """Greedy label placement: nudge each text off symbols and earlier labels."""
    obst = []
    for it in items:
        if it["kind"] == "rect":
            cx, cy = it["center"]
            obst.append((cx - it["w"] / 2, cy - it["h"] / 2, cx + it["w"] / 2, cy + it["h"] / 2))
        elif it["kind"] == "circle":
            cx, cy = it["center"]
            obst.append((cx - it["r"], cy - it["r"], cx + it["r"], cy + it["r"]))
    placed = []
    for it in items:
        if it["kind"] != "text":
            continue
        h = it["size_pt"] * 1.25
        x0, y0 = it["pos"]
        tries = [(0, 0)] + [(dx, dy * h) for dy in (-1, 1, -2, 2, -3, 3) for dx in (0,)] + [(dx * h * 4, dy * h) for dx in (-1, 1) for dy in (0, -1, 1)]
        best = None
        for dx, dy in tries:
            pos = (x0 + dx, y0 + dy)
            bb = _text_box(it, pos)
            n = sum(_overlap(bb, o) for o in placed) * 3 + sum(_overlap(bb, o) for o in obst)
            if best is None or n < best[0]:
                best = (n, pos, bb)
            if n == 0:
                break
        it["pos"] = [best[1][0], best[1][1]]
        placed.append(best[2])
    return items


def drawn_tags(items):
    return {i["tag"] for i in items if i.get("tag")}
