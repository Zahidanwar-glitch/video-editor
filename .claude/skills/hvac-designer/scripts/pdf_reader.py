"""Step A - read an architectural plan PDF into a room schedule (rooms.json) for Gate 1.

Vector pages: walls/doors/windows are rasterised from the PDF vector paths (text excluded),
enclosed spaces are found by flood labelling (door swing arcs seal openings), and each
space is named from the text inside it. Windows come from W-tags + the window schedule,
orientation from the room's exterior edge and the north arrow.
Scanned pages: rendered to PNG and flagged 'needs_vision' - Claude reads them visually
and fills rooms.json by hand (see SKILL.md).

Nothing is guessed silently: every inference goes to assumptions.md, every gap to
open_questions.json.

CLI: python pdf_reader.py PLAN.pdf -w WORK [--scale 100] [--north 20] [--pages 1,2,3]
Outputs: WORK/rooms.json, WORK/gate1_rooms.md, WORK/gate1_<floor>.png, WORK/pages/*.png
"""
import argparse
import math
import os
import re

import numpy as np
import pymupdf as fitz
from PIL import Image, ImageDraw
from scipy import ndimage

import common as C
import scale_detect

FLOOR_RE = [
    (re.compile(r"BASEMENT\s*(\d*)", re.I), lambda m: f"B{m.group(1) or 1}", "Basement"),
    (re.compile(r"GROUND\s+FLOOR|\bG\.?F\.?\b", re.I), lambda m: "GF", "Ground Floor"),
    (re.compile(r"MEZZANINE", re.I), lambda m: "MZ", "Mezzanine"),
    (re.compile(r"FIRST\s+FLOOR|1ST\s+FLOOR", re.I), lambda m: "FF", "First Floor"),
    (re.compile(r"SECOND\s+FLOOR|2ND\s+FLOOR", re.I), lambda m: "SF", "Second Floor"),
    (re.compile(r"THIRD\s+FLOOR|3RD\s+FLOOR", re.I), lambda m: "TF", "Third Floor"),
    (re.compile(r"(\d+)(?:ST|ND|RD|TH)\s+FLOOR", re.I), lambda m: f"L{m.group(1)}", "Level"),
    (re.compile(r"TYPICAL\s+FLOOR", re.I), lambda m: "TYP", "Typical Floor"),
    (re.compile(r"ROOF\s+PLAN|ROOF\s+FLOOR", re.I), lambda m: "RF", "Roof"),
]
NON_ROOM = re.compile(r"PROJECT|DRAWING|SCALE|DWG|ARCHITECT|SCHEDULE|REV\b|TITLE|CLIENT|NOTES?:|PLAN\b|PARAPET|ALUMINIUM", re.I)
AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|sq\.?\s*m)", re.I)
WTAG_RE = re.compile(r"^(W[-_ ]?\d{1,3}[A-Z]?)$", re.I)
WSCHED_RE = re.compile(r"\b(W[-_ ]?\d{1,3}[A-Z]?)\s+(\d{3,4})\s*[xX×]\s*(\d{3,4})")
HEIGHT_RE = re.compile(r"(?:C\.?H\.?|CEILING(?:\s+HEIGHT)?)\s*[:=+]?\s*(\d+(?:\.\d+)?)", re.I)


# ------------------------------------------------------------------ helpers
def space_type(name):
    for pat, st in C.ref("room_name_map.json")["patterns"]:
        if re.search(pat, name, re.I):
            return st
    if re.search(r"roof|terrace|سطح", name, re.I):
        return "roof"
    return "unknown"


def is_scanned(page):
    n_draw = len(page.get_drawings())
    n_text = len(page.get_text("words"))
    img_area = sum((r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1])
                   for r in page.get_image_info())
    return n_draw < 30 and (img_area > 0.4 * page.rect.width * page.rect.height or n_text < 5)


def bez(p0, c1, c2, p3, t):
    return ((1 - t) ** 3 * p0.x + 3 * (1 - t) ** 2 * t * c1.x + 3 * (1 - t) * t * t * c2.x + t ** 3 * p3.x,
            (1 - t) ** 3 * p0.y + 3 * (1 - t) ** 2 * t * c1.y + 3 * (1 - t) * t * t * c2.y + t ** 3 * p3.y)


def circumcenter(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def door_arc(curves, mm_pt):
    """A quarter arc of door-leaf radius -> (centre, start, end, mid) in pt, else None."""
    p_start = (curves[0][1].x, curves[0][1].y)
    p_end = (curves[-1][4].x, curves[-1][4].y)
    k = len(curves) // 2
    mid = bez(*curves[k][1:5], 0.0 if len(curves) % 2 == 0 else 0.5)
    cen = circumcenter(p_start, mid, p_end)
    if not cen:
        return None
    r = math.hypot(p_start[0] - cen[0], p_start[1] - cen[1])
    a1 = math.atan2(p_start[1] - cen[1], p_start[0] - cen[0])
    a2 = math.atan2(p_end[1] - cen[1], p_end[0] - cen[0])
    sweep = abs((math.degrees(a2 - a1) + 180) % 360 - 180)
    if 450 <= r * mm_pt <= 1600 and 70 <= sweep <= 110:
        return {"centre": cen, "start": p_start, "end": p_end, "mid": mid, "r": r}
    return None


def rasterise(page, zoom, mm_pt=None):
    """Vector paths -> binary 'ink' mask (True = wall/line), text excluded.
    Door swing arcs are closed with their two radii so openings are sealed; returns (mask, doors)."""
    doors = []
    w, h = int(page.rect.width * zoom) + 1, int(page.rect.height * zoom) + 1
    img = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(img)

    def z(p):
        return (p.x * zoom, p.y * zoom)

    for p in page.get_drawings():
        fill, stroke = p.get("fill"), p.get("color")
        lw = max(1, int(round((p.get("width") or 0.5) * zoom)))
        poly = []
        curves = [it for it in p["items"] if it[0] == "c"]
        if curves and fill is None and mm_pt:
            d = door_arc(curves, mm_pt)
            if d:
                doors.append(d)
                for q in (d["start"], d["end"]):
                    dr.line([(d["centre"][0] * zoom, d["centre"][1] * zoom), (q[0] * zoom, q[1] * zoom)], fill=255, width=lw)
        for it in p["items"]:
            k = it[0]
            if k == "l":
                pts = [z(it[1]), z(it[2])]
            elif k == "re":
                r = it[1]
                pts = [(r.x0 * zoom, r.y0 * zoom), (r.x1 * zoom, r.y0 * zoom),
                       (r.x1 * zoom, r.y1 * zoom), (r.x0 * zoom, r.y1 * zoom), (r.x0 * zoom, r.y0 * zoom)]
            elif k == "qu":
                q = it[1]
                pts = [z(q.ul), z(q.ur), z(q.lr), z(q.ll), z(q.ul)]
            elif k == "c":
                p0, c1, c2, p3 = it[1], it[2], it[3], it[4]
                pts = [tuple(v * zoom for v in bez(p0, c1, c2, p3, i / 8)) for i in range(9)]
            else:
                continue
            poly += pts
            if stroke is not None and sum(stroke) < 2.7:
                dr.line(pts, fill=255, width=lw)
        if fill is not None and len(poly) >= 3:
            dr.polygon(poly, fill=255 if sum(fill) < 2.7 else 0)
    return np.array(img) > 0, doors


def trace_polygon(mask):
    """Outer boundary of a binary mask as a simplified polygon (pixel coords)."""
    m = np.pad(mask, 1)
    edges = {}
    ys, xs = np.nonzero(m[1:, :] != m[:-1, :])   # horizontal edges between rows
    for y, x in zip(ys, xs):
        a, b = ((x, y + 1), (x + 1, y + 1)) if m[y + 1, x] else ((x + 1, y + 1), (x, y + 1))
        edges.setdefault(a, []).append(b)
    ys, xs = np.nonzero(m[:, 1:] != m[:, :-1])   # vertical edges between columns
    for y, x in zip(ys, xs):
        a, b = ((x + 1, y + 1), (x + 1, y)) if m[y, x + 1] else ((x + 1, y), (x + 1, y + 1))
        edges.setdefault(a, []).append(b)
    best = []
    while edges:
        start = next(iter(edges))
        loop, cur = [start], start
        while True:
            nxt = edges[cur].pop()
            if not edges[cur]:
                del edges[cur]
            if nxt == start:
                break
            loop.append(nxt)
            cur = nxt
            if cur not in edges:
                break
        if len(loop) > len(best):
            best = loop
    pts = [(x - 1, y - 1) for x, y in best]
    return douglas_peucker(pts + [pts[0]], 2.5)[:-1] if pts else []


def douglas_peucker(pts, tol):
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x1 * y0 - y1 * x0) / n if n > 1e-9 else math.hypot(pts[i][0] - x0, pts[i][1] - y0)
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        return douglas_peucker(pts[:idx + 1], tol)[:-1] + douglas_peucker(pts[idx:], tol)
    return [pts[0], pts[-1]]


def text_lines(page):
    return scale_detect.text_lines(page)


def find_north(page, lines):
    """North arrow: a lone 'N' near a filled triangle/arrow; angle clockwise from page-up."""
    ns = [l for l in lines if l["text"].strip().upper() in ("N", "NORTH")]
    if not ns:
        return None
    tri = []
    for p in page.get_drawings():
        if p.get("fill") is None:
            continue
        pts = []
        for it in p["items"]:
            if it[0] == "l":
                pts += [it[1], it[2]]
        if 3 <= len(pts) <= 8:
            xs = [q.x for q in pts]
            ys = [q.y for q in pts]
            if max(xs) - min(xs) < 40 and max(ys) - min(ys) < 40:
                tri.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    best = None
    for n in ns:
        nx = (n["bbox"][0] + n["bbox"][2]) / 2
        ny = (n["bbox"][1] + n["bbox"][3]) / 2
        for tx, ty in tri:
            d = math.hypot(nx - tx, ny - ty)
            if d < 40 and (best is None or d < best[0]):
                best = (d, math.degrees(math.atan2(nx - tx, -(ny - ty))) % 360)
    return round(best[1], 1) if best else None


def detect_floor(lines, idx):
    for ln in sorted(lines, key=lambda l: -l["size"]):
        for rx, fid, fname in FLOOR_RE:
            m = rx.search(ln["text"])
            if m:
                return fid(m), fname, ln["text"]
    return f"P{idx}", f"Page {idx}", None


# ------------------------------------------------------------------ main page reader
def read_page(page, idx, den, north, log, work):
    lines = text_lines(page)
    fid, fname, ftitle = detect_floor(lines, idx)
    mm_pt = scale_detect.PT_MM * den
    zoom = max(1.0, min(mm_pt / 15.0, 7000 / page.rect.width))
    mm_px = mm_pt / zoom
    px_m2 = (mm_px / 1000) ** 2
    ink, doors = rasterise(page, zoom, mm_pt)
    lab, n = ndimage.label(~ink)
    objs = ndimage.find_objects(lab)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(n + 1))
    sizes[0] = 0
    H, W = lab.shape
    edge_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    # the exterior is the largest region (inside the sheet border) plus anything touching the page edge
    exterior = {int(np.argmax(sizes))} | {int(e) for e in edge_labels if e}

    def label_at(x_pt, y_pt):
        px, py = int(x_pt * zoom), int(y_pt * zoom)
        return int(lab[py, px]) if 0 <= py < H and 0 <= px < W else 0

    # assign text to regions
    labels_txt, area_txt = {}, {}
    wtags, wsched, heights = [], {}, []
    for ln in lines:
        t = ln["text"].strip()
        cx = (ln["bbox"][0] + ln["bbox"][2]) / 2
        cy = (ln["bbox"][1] + ln["bbox"][3]) / 2
        r = label_at(cx, cy)
        for m in WSCHED_RE.finditer(t):
            wsched[norm_tag(m.group(1))] = (int(m.group(2)), int(m.group(3)))
        if WTAG_RE.match(t):
            wtags.append({"tag": norm_tag(t), "pt": (cx, cy)})
            continue
        hm = HEIGHT_RE.search(t)
        if hm:
            heights.append(float(hm.group(1)))
        if r in exterior or r == 0:
            continue
        am = AREA_RE.search(t)
        if am:
            area_txt.setdefault(r, float(am.group(1)))
            continue
        if NON_ROOM.search(t) or not re.search(r"[A-Za-z؀-ۿ]", t) or len(t) > 40:
            continue
        labels_txt.setdefault(r, []).append((ln["size"], t, cx, cy))

    # door swing sectors belong to the room the leaf swings into (point just beyond the arc)
    region_of = {r: r for r in labels_txt}
    for d in doors:
        (cx, cy), (mx, my), r = d["centre"], d["mid"], d["r"]
        ux, uy = (mx - cx) / r, (my - cy) / r
        sector = label_at(cx + ux * r * 0.5, cy + uy * r * 0.5)
        host = label_at(cx + ux * (r + 3 / zoom * 2), cy + uy * (r + 3 / zoom * 2))
        if sector and sector not in labels_txt and host in labels_txt:
            region_of[sector] = host
    # other small unlabelled regions -> the labelled neighbour they touch most
    min_room_px = 1.5 / px_m2
    for r in range(1, n + 1):
        if r in region_of or r in exterior or sizes[r] == 0 or sizes[r] >= min_room_px:
            continue
        sl = tuple(slice(max(0, s.start - 3), s.stop + 3) for s in objs[r - 1])
        dil = ndimage.binary_dilation(lab[sl] == r, iterations=3)
        cand = [int(v) for v in lab[sl][dil] if v in labels_txt]
        if cand:
            region_of[r] = max(set(cand), key=cand.count)

    rooms = []
    for r, txts in labels_txt.items():
        members = [k for k, v in region_of.items() if v == r]
        y0 = max(0, min(objs[k - 1][0].start for k in members) - 4)
        y1 = min(H, max(objs[k - 1][0].stop for k in members) + 4)
        x0 = max(0, min(objs[k - 1][1].start for k in members) - 4)
        x1 = min(W, max(objs[k - 1][1].stop for k in members) + 4)
        sub = lab[y0:y1, x0:x1]
        m = np.isin(sub, members)
        m = ndimage.binary_fill_holes(ndimage.binary_closing(m, iterations=2) | m)
        # strokes are rasterised >= 1 px wide: give the room back one pixel of ink on its boundary
        grown = ndimage.binary_dilation(m, iterations=1) & ink[y0:y1, x0:x1]
        m = m | grown
        area = float(m.sum() * px_m2)
        txts.sort(key=lambda t: -t[0])
        names = [t[1] for t in txts]
        name = names[0]
        if len(names) > 1 and txts[0][0] == txts[1][0]:
            log.ask("Gate1", f"multi_label_{fid}_{name}", f"{fname}: one enclosed space carries several names {names} - an opening may be unsealed. Split or confirm.")
        ys, xs = np.nonzero(m)
        poly = [((x + x0) / zoom, (y + y0) / zoom) for x, y in trace_polygon(m)]
        bb = (xs.min() + x0, ys.min() + y0, xs.max() + x0 + 1, ys.max() + y0 + 1)
        st = space_type(name)
        at = area_txt.get(r)
        room = {
            "name": name, "space_type": st,
            "area_m2": round(area, 2), "area_text_m2": at,
            "bbox_pt": [round(v / zoom, 2) for v in bb],
            "centroid_pt": [round((xs.mean() + x0) / zoom, 2), round((ys.mean() + y0) / zoom, 2)],
            "polygon_pt": [[round(x, 2), round(y, 2)] for x, y in poly],
            "rectangular": bool(area / ((bb[2] - bb[0]) * (bb[3] - bb[1]) * px_m2) > 0.93),
            "_mask": (y0, x0, m), "_label": r,
        }
        if at and st != "roof" and abs(at - area) / at > 0.05:
            log.ask("Gate1", f"area_mismatch_{fid}_{name}", f"{fname} {name}: measured {area:.2f} m² vs plan text {at:.2f} m² (>5 % difference). Which is right?")
        if st == "unknown":
            log.ask("Gate1", f"type_{fid}_{name}", f"{fname}: room '{name}' - what is its use (space type)?")
        rooms.append(room)

    # unnamed enclosed spaces inside the building outline
    if rooms:
        bx0 = min(r["bbox_pt"][0] for r in rooms) * zoom
        by0 = min(r["bbox_pt"][1] for r in rooms) * zoom
        bx1 = max(r["bbox_pt"][2] for r in rooms) * zoom
        by1 = max(r["bbox_pt"][3] for r in rooms) * zoom
        unnamed = []
        for r in range(1, n + 1):
            if r in exterior or r in region_of or sizes[r] * px_m2 < 1.5:
                continue
            sl = objs[r - 1]
            cy_, cx_ = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
            thin = min(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) * mm_px < 500
            if bx0 <= cx_ <= bx1 and by0 <= cy_ <= by1 and not thin:
                unnamed.append(round(float(sizes[r] * px_m2), 2))
        if unnamed:
            log.ask("Gate1", f"unnamed_{fid}", f"{fname}: {len(unnamed)} enclosed space(s) without a name (areas m²: {unnamed}). Name them or confirm they are voids.")

    room_labels = {k for k, v in region_of.items()}
    ext_mask = np.isin(lab, list(exterior))
    probe = int(round(500 / mm_px)) + 2

    def in_room(room, qx, qy):
        y0, x0, m = room["_mask"]
        yy, xx = qy - y0, qx - x0
        return 0 <= yy < m.shape[0] and 0 <= xx < m.shape[1] and bool(m[yy, xx])

    # exterior edges per room: probe outward from each polygon edge
    for room in rooms:
        edges = []
        poly = room["polygon_pt"]
        for i in range(len(poly)):
            (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
            L_pt = math.hypot(bx - ax, by - ay)
            if L_pt * mm_pt < 250:
                continue
            nx, ny = (by - ay) / L_pt, -(bx - ax) / L_pt
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if in_room(room, int((mx + nx * 4 / zoom) * zoom), int((my + ny * 4 / zoom) * zoom)):
                nx, ny = -nx, -ny
            hits, samples = 0, 12
            for k in range(samples):
                f = (k + 0.5) / samples
                sx, sy = (ax + (bx - ax) * f) * zoom, (ay + (by - ay) * f) * zoom
                for step in range(2, probe):
                    qx, qy = int(sx + nx * step), int(sy + ny * step)
                    if not (0 <= qy < H and 0 <= qx < W):
                        break
                    if ext_mask[qy, qx]:
                        hits += 1
                        break
                    lq = lab[qy, qx]
                    if lq and lq in room_labels and not in_room(room, qx, qy):
                        break  # reached another room
            frac = hits / samples
            comp = (math.degrees(math.atan2(nx, -ny)) - north) % 360
            edges.append({"p1": [round(ax, 2), round(ay, 2)], "p2": [round(bx, 2), round(by, 2)],
                          "length_m": round(L_pt * mm_pt / 1000, 2), "exterior_frac": round(frac, 2),
                          "bearing": round(comp, 1), "orientation": C.orient_from_bearing(comp),
                          "normal_page": [round(nx, 3), round(ny, 3)]})
        room["edges"] = edges
        agg = {}
        for e in edges:
            if e["exterior_frac"] >= 0.25:
                agg[e["orientation"]] = agg.get(e["orientation"], 0) + e["length_m"] * e["exterior_frac"]
        room["exterior_walls"] = [{"orientation": o, "length_m": round(v, 2)} for o, v in agg.items()]

    # windows: tag -> nearest exterior edge
    for w in wtags:
        best = None
        for room in rooms:
            for e in room["edges"]:
                if e["exterior_frac"] < 0.25:
                    continue
                d = seg_dist(w["pt"], e["p1"], e["p2"]) * mm_pt
                if d < 1500 and (best is None or d < best[0]):
                    best = (d, room, e)
        if not best:
            log.ask("Gate1", f"wtag_{fid}_{w['tag']}_{int(w['pt'][0])}", f"{fname}: window tag {w['tag']} at ({w['pt'][0]:.0f},{w['pt'][1]:.0f}) pt is not next to an exterior wall - which room?")
            continue
        size = wsched.get(w["tag"])
        if not size:
            log.ask("Gate1", f"wsize_{w['tag']}", f"Window {w['tag']}: size not found in a window schedule - give width x height (mm).")
        _, room, e = best
        room.setdefault("windows", []).append({
            "tag": w["tag"], "orientation": e["orientation"], "bearing": e["bearing"],
            "width_m": size[0] / 1000 if size else None, "height_m": size[1] / 1000 if size else None,
            "at_pt": [round(w["pt"][0], 1), round(w["pt"][1], 1)]})
    if not wtags and fid != "RF":
        log.ask("Gate1", f"no_windows_{fid}", f"{fname}: no window tags found. Give window sizes per room, or approve a glazing-ratio assumption.")

    # columns: small filled near-square rectangles
    cols = []
    for p in page.get_drawings():
        if p.get("fill") is None or sum(p["fill"]) > 2.7:
            continue
        r = p["rect"]
        wmm, hmm = r.width * mm_pt, r.height * mm_pt
        if 250 <= min(wmm, hmm) and max(wmm, hmm) <= 1200 and max(wmm, hmm) / max(1e-6, min(wmm, hmm)) < 1.6:
            cols.append([round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)])

    rooms.sort(key=lambda r: (round(r["centroid_pt"][1] / 60), r["centroid_pt"][0]))
    for i, r in enumerate(rooms, 1):
        r["id"] = f"{fid}-{i:02d}"
    footprint = np.zeros_like(ink)
    for r in rooms:
        if r["space_type"] != "roof":
            y0, x0, m = r["_mask"]
            footprint[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] |= m
    footprint = ndimage.binary_closing(footprint, iterations=int(300 / mm_px) + 1)
    return {"id": fid, "name": fname, "title": ftitle, "page": idx, "kind": "roof" if fid == "RF" else "floor",
            "zoom": zoom, "mm_per_pt": mm_pt, "page_size_pt": [page.rect.width, page.rect.height],
            "rooms": rooms, "columns": cols, "doors_found": len(doors),
            "window_schedule": {k: list(v) for k, v in wsched.items()},
            "heights_found_m": heights, "_footprint": footprint}


def norm_tag(t):
    return re.sub(r"[\s_\-]", "", t.upper())


def seg_dist(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def preview(doc, fl, work):
    """Gate 1 annotated preview PNG."""
    page = doc[fl["page"] - 1]
    tmp = fitz.open()
    tmp.insert_pdf(doc, from_page=fl["page"] - 1, to_page=fl["page"] - 1)
    pg = tmp[0]
    colors = [(0.95, 0.5, 0.2), (0.2, 0.6, 0.95), (0.3, 0.8, 0.4), (0.85, 0.3, 0.75), (0.95, 0.8, 0.2)]
    for i, r in enumerate(fl["rooms"]):
        col = (0.75, 0.75, 0.75) if not r.get("is_conditioned", True) else colors[i % len(colors)]
        pg.draw_polyline([fitz.Point(*p) for p in r["polygon_pt"] + [r["polygon_pt"][0]]],
                         color=col, fill=col, fill_opacity=0.25, width=1.2)
        cx, cy = r["centroid_pt"]
        pg.insert_text((cx - 30, cy + 16), f"{r['id']}  {r['area_m2']:.1f} m2", fontsize=6, color=(0.7, 0, 0))
        for e in r["edges"]:
            if e["exterior_frac"] >= 0.25:
                (ax, ay), (bx, by) = e["p1"], e["p2"]
                pg.draw_line((ax, ay), (bx, by), color=(0.9, 0.1, 0.1), width=2.2)
                pg.insert_text(((ax + bx) / 2 + e["normal_page"][0] * 14 - 4, (ay + by) / 2 + e["normal_page"][1] * 14 + 2),
                               e["orientation"], fontsize=6, color=(0.9, 0.1, 0.1))
        for w in r.get("windows", []):
            pg.draw_circle(w["at_pt"], 6, color=(0, 0.4, 0.9), width=1)
    pg.insert_text((30, 30), f"GATE 1 PREVIEW - {fl['name']} - scale 1:{fl['scale']} - north {fl['north_deg']} deg - red = exterior wall + facing",
                   fontsize=9, color=(0.7, 0, 0))
    path = os.path.join(work, f"gate1_{fl['id']}.png")
    pg.get_pixmap(dpi=110).save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-w", "--work", required=True)
    ap.add_argument("--scale", type=float, help="confirmed scale denominator (overrides detection)")
    ap.add_argument("--north", type=float, help="confirmed north angle, deg clockwise from page-up")
    ap.add_argument("--pages", help="comma list of 1-based pages (default all)")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.work, "pages"), exist_ok=True)
    log = C.Log(a.work, "pdf_reader")
    proj = C.load(a.work, "project.json", default={})
    floors_cfg = {f["id"]: f for f in proj.get("project", {}).get("floors", [])}
    doc = fitz.open(a.pdf)
    pages = [int(x) for x in a.pages.split(",")] if a.pages else list(range(1, len(doc) + 1))
    out = {"source_pdf": os.path.relpath(os.path.abspath(a.pdf), os.path.abspath(a.work)), "floors": []}
    north_all = []
    for i in pages:
        page = doc[i - 1]
        page.get_pixmap(dpi=100).save(os.path.join(a.work, "pages", f"page_{i}.png"))
        if is_scanned(page):
            out["floors"].append({"id": f"P{i}", "page": i, "needs_vision": True, "rooms": [],
                                  "image": f"pages/page_{i}.png"})
            log.ask("Gate1", f"scanned_{i}", f"Page {i} is a scanned image: read it visually, confirm the scale from a known dimension, and enter rooms by hand.")
            continue
        sc = scale_detect.detect(page, a.scale)
        if not sc["denominator"]:
            log.ask("Gate1", f"scale_{i}", f"Page {i}: drawing scale not found. Give the scale (e.g. 1:100) or one known dimension.")
            continue
        if sc["confidence"] != "high":
            log.ask("Gate1", f"scale_{i}", f"Page {i}: scale 1:{sc['denominator']} found by '{sc['method']}' only - please confirm.")
        log.add("A-read", f"scale_{i}", f"Page {i} scale 1:{sc['denominator']} ({sc['method']}, confidence {sc['confidence']})", "scale_detect.py", confirm=sc["confidence"] != "high")
        north = a.north
        if north is None:
            north = find_north(page, text_lines(page))
            if north is None:
                north = 0.0
                log.ask("Gate1", f"north_{i}", f"Page {i}: north arrow not found - give north direction (degrees clockwise from page-up).")
            log.add("A-read", f"north_{i}", f"Page {i} north = {north} deg clockwise from page-up (detected from north arrow)", "pdf_reader.py", confirm=False)
        north_all.append(north)
        fl = read_page(page, i, sc["denominator"], north, log, a.work)
        fl["scale"] = sc["denominator"]
        fl["north_deg"] = north
        fl["scale_detail"] = sc
        out["floors"].append(fl)

    # roof exposure (room area not covered by the next floor's footprint) and heights
    real = [f for f in out["floors"] if not f.get("needs_vision")]
    order = [f for f in real if f["kind"] == "floor"]
    for k, fl in enumerate(order):
        upper = order[k + 1] if k + 1 < len(order) else None
        cfg = floors_cfg.get(fl["id"], {})
        for r in fl["rooms"]:
            if upper is None:
                cov = 0.0
            else:
                fp = upper["_footprint"]
                y0, x0, m = r["_mask"]
                sub = fp[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
                h, w = sub.shape
                cov = float((m[:h, :w] & sub).sum() / max(1, m.sum()))
            r["roof_exposed_frac"] = round(1 - cov, 2) if cov < 0.97 else 0.0
            r["ground_contact"] = k == 0 and fl["id"] in ("GF", "B1")
            st = C.ref("space_types.json")["types"].get(r["space_type"], {})
            r["is_conditioned"] = bool(st.get("conditioned", True))
            r["height_m"] = cfg.get("ceiling_height_m") or (fl["heights_found_m"][0] if fl["heights_found_m"] else None)
            r["floor_to_floor_m"] = cfg.get("floor_to_floor_m")
        if not cfg.get("ceiling_height_m") and not fl["heights_found_m"]:
            log.ask("Gate1", f"height_{fl['id']}", f"{fl['name']}: ceiling height and floor-to-floor height not given on the plan - please confirm.")
    if len({round(n) for n in north_all}) > 1:
        log.ask("Gate1", "north_mismatch", f"North angle differs between pages {north_all} - confirm.")

    for fl in real:
        for r in fl["rooms"]:
            r.pop("_mask", None)
            r.pop("_label", None)
        fl.pop("_footprint", None)
        fl["preview"] = os.path.basename(preview(doc, fl, a.work))
    C.save(a.work, "rooms.json", out)
    log.save()
    gate1_md(out, a.work, log)
    print(f"rooms.json: {sum(len(f['rooms']) for f in out['floors'])} rooms on {len(out['floors'])} pages; "
          f"{sum(1 for q in log.questions if not q['answered'])} open questions")


def gate1_md(out, work, log):
    lines = ["# Gate 1 - Room schedule (please review)", ""]
    for fl in out["floors"]:
        if fl.get("needs_vision"):
            lines += [f"## Page {fl['page']}: scanned - read visually", ""]
            continue
        lines += [f"## {fl['name']} (page {fl['page']}, scale 1:{fl['scale']}, north {fl['north_deg']}°) - preview `{fl['preview']}`", ""]
        rows = []
        for r in fl["rooms"]:
            ext = ", ".join(f"{e['orientation']} {e['length_m']:.1f}m" for e in r["exterior_walls"]) or "-"
            win = ", ".join(f"{w['tag']} {w['orientation']}" for w in r.get("windows", [])) or "-"
            rows.append([r["id"], r["name"], r["space_type"], f"{r['area_m2']:.2f}",
                         r.get("area_text_m2") or "-", r.get("height_m") or "?", ext, win,
                         f"{r.get('roof_exposed_frac', 0):.0%}", "yes" if r.get("is_conditioned") else "no"])
        lines.append(C.md_table(["ID", "Name", "Type", "Area m²", "Plan m²", "Ceiling m", "Exterior walls", "Windows", "Roof exp.", "Cond."], rows))
        lines.append("")
    q = [x for x in log.questions if not x["answered"]]
    if q:
        lines += ["## Open questions", ""] + [f"- {x['id']}: {x['question']}" for x in q]
    C.write_text(work, "gate1_rooms.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
