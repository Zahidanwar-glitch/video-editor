"""Plan geometry helpers (page points, y down). Real lengths via floor['mm_per_pt']."""
import math


def floors(rooms_json, include_roof=False):
    return [f for f in rooms_json["floors"] if not f.get("needs_vision") and (include_roof or f.get("kind") != "roof")]


def room_index(rooms_json):
    return {r["id"]: (f, r) for f in rooms_json["floors"] for r in f.get("rooms", [])}


def m(fl, d_pt):
    return d_pt * fl["mm_per_pt"] / 1000.0


def pt(fl, d_m):
    return d_m * 1000.0 / fl["mm_per_pt"]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def polyline_len(pts):
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_in_poly(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


def bbox_gap(a, b):
    """Gap between two bboxes along x and y (negative = overlap length)."""
    gx = max(a[0], b[0]) - min(a[2], b[2])
    gy = max(a[1], b[1]) - min(a[3], b[3])
    return gx, gy


def adjacent(r1, r2, fl, wall_tol_m=0.35, min_shared_m=0.6):
    gx, gy = bbox_gap(r1["bbox_pt"], r2["bbox_pt"])
    tol, shared, slack = pt(fl, wall_tol_m), pt(fl, min_shared_m), pt(fl, 0.15)
    return (-slack <= gx <= tol and -gy >= shared) or (-slack <= gy <= tol and -gx >= shared)


def proj_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return (a[0] + t * dx, a[1] + t * dy), t


def nearest_exterior(fl, p, rooms=None, min_frac=0.5, avoid_types=("stair", "shaft")):
    """Closest point on an exterior wall (inner face) -> (point, edge, room)."""
    best = None
    for r in rooms or fl["rooms"]:
        if r["space_type"] in avoid_types:
            continue
        for e in r.get("edges", []):
            if e["exterior_frac"] < min_frac:
                continue
            q, _ = proj_on_seg(p, e["p1"], e["p2"])
            d = manhattan(p, q)
            if best is None or d < best[0]:
                best = (d, q, e, r)
    return (best[1], best[2], best[3]) if best else (None, None, None)


def inset(p, edge, fl, d_m):
    """Move a point on an edge inward (opposite the outward normal) by d_m."""
    nx, ny = edge["normal_page"]
    k = pt(fl, d_m)
    return (p[0] - nx * k, p[1] - ny * k)


def outset(p, edge, fl, d_m):
    nx, ny = edge["normal_page"]
    k = pt(fl, d_m)
    return (p[0] + nx * k, p[1] + ny * k)


def l_route(a, b, horizontal_first=True):
    if abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6:
        return [a, b]
    mid = (b[0], a[1]) if horizontal_first else (a[0], b[1])
    return [a, mid, b]


def seg_hits_rect(a, b, rect, pad=0.0):
    """Orthogonal or general segment vs axis-aligned rect (x0,y0,x1,y1) intersection test."""
    x0, y0, x1, y1 = rect[0] + pad, rect[1] + pad, rect[2] - pad, rect[3] - pad
    if x1 <= x0 or y1 <= y0:
        return False
    # Liang-Barsky clipping
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for pp, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(pp) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def interior_wall_point(fl, room, offset_m=0.3):
    """A point just inside the longest interior (non-exterior) wall - for thermostats."""
    edges = [e for e in room.get("edges", []) if e["exterior_frac"] < 0.25] or room.get("edges", [])
    if not edges:
        return tuple(room["centroid_pt"])
    e = max(edges, key=lambda e: e["length_m"])
    mid = ((e["p1"][0] + e["p2"][0]) / 2, (e["p1"][1] + e["p2"][1]) / 2)
    return inset(mid, e, fl, offset_m)


def grid_points(room, fl, n):
    """n diffuser positions on a rows x cols grid inside the room bbox (kept inside polygon)."""
    x0, y0, x1, y1 = room["bbox_pt"]
    w, h = x1 - x0, y1 - y0
    best = None
    for rows in range(1, n + 1):
        cols = math.ceil(n / rows)
        score = abs((w / cols) - (h / rows))
        if best is None or score < best[0]:
            best = (score, rows, cols)
    _, rows, cols = best
    pts = []
    for i in range(rows):
        for j in range(cols):
            if len(pts) == n:
                break
            p = (x0 + w * (j + 0.5) / cols, y0 + h * (i + 0.5) / rows)
            if not point_in_poly(p, room["polygon_pt"]):
                c = room["centroid_pt"]
                p = ((p[0] + c[0]) / 2, (p[1] + c[1]) / 2)
            pts.append(p)
    return pts
