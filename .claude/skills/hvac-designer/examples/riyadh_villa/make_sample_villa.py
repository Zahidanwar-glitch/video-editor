"""Generate the sample villa architectural PDF used by the worked example.

A3 landscape, 1:100, three pages (ground floor, first floor, roof), drawn the way a
CAD export looks: filled wall poche, door leaves + swing arcs, window symbols with
W-tags, a window schedule, room names with areas, dimension strings, north arrow
and a title block.  Building 16.0 x 12.0 m, north rotated 20 deg from page-up.

Usage: python make_sample_villa.py [out.pdf]
"""
import math
import sys

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

PT = 72 / 25.4            # points per paper mm
SCALE = 100               # 1:100
OX, OY = 45.0, 60.0       # paper mm offset of building origin (bottom-left)
W, H = 16000, 12000       # building outer size, real mm
EXT, INT = 200, 100       # wall thickness
NORTH_DEG = 20            # north arrow, degrees clockwise from page-up

WINDOWS = {"W1": (1800, 1500), "W2": (1200, 1500), "W3": (600, 600), "W4": (2400, 2100)}

FLOORS = {
    "GROUND FLOOR PLAN": {
        "dwg": "A-101",
        "rooms": [
            ("MAJLIS", 0, 7000, 6000, 12000), ("ENTRANCE HALL", 6000, 7000, 9500, 12000),
            ("LIVING", 9500, 7000, 16000, 12000), ("DINING", 0, 2500, 5000, 7000),
            ("GUEST WC", 0, 0, 2500, 2500), ("STORE", 2500, 0, 5000, 2500),
            ("STAIR", 5000, 0, 8000, 4500), ("CORRIDOR", 5000, 4500, 8000, 7000),
            ("KITCHEN", 8000, 2000, 12500, 7000), ("LAUNDRY", 8000, 0, 12500, 2000),
            ("MAID ROOM", 12500, 3000, 16000, 7000), ("MAID WC", 12500, 0, 15000, 3000),
            ("SHAFT", 15000, 0, 16000, 3000),
        ],
        # (room name, side, offset from side start mm, window tag)  side: N/S/E/W of page
        "windows": [("MAJLIS", "top", 1200, "W1"), ("MAJLIS", "left", 1500, "W2"),
                    ("LIVING", "top", 2000, "W4"), ("LIVING", "right", 1800, "W1"),
                    ("DINING", "left", 1500, "W1"), ("GUEST WC", "bottom", 900, "W3"),
                    ("KITCHEN", "bottom", 0, None), ("MAID ROOM", "right", 1400, "W2"),
                    ("MAID WC", "bottom", 900, "W3"), ("LAUNDRY", "bottom", 1500, "W2")],
        "doors": [("ENTRANCE HALL", "top", 1200, 1200), ("MAJLIS", "right", 1500, 900),
                  ("LIVING", "left", 1500, 900), ("CORRIDOR", "top", 1000, 1000),
                  ("DINING", "right", 600, 900), ("CORRIDOR", "right", 600, 900),
                  ("STAIR", "top", 1000, 1000), ("GUEST WC", "top", 800, 800),
                  ("STORE", "top", 800, 800), ("LAUNDRY", "top", 1500, 800),
                  ("MAID ROOM", "left", 1500, 900), ("MAID WC", "top", 800, 800)],
    },
    "FIRST FLOOR PLAN": {
        "dwg": "A-102",
        "rooms": [
            ("MASTER BEDROOM", 0, 7000, 6000, 12000), ("MASTER BATH", 6000, 9000, 9000, 12000),
            ("DRESSING", 6000, 7000, 9000, 9000), ("BEDROOM 2", 9000, 7000, 13500, 12000),
            ("BATH 2", 13500, 9000, 16000, 12000), ("LINEN", 13500, 7000, 16000, 9000),
            ("FAMILY LIVING", 0, 0, 5000, 7000), ("STAIR", 5000, 0, 8000, 4500),
            ("LOBBY", 5000, 4500, 8000, 7000), ("BEDROOM 3", 8000, 2500, 12500, 7000),
            ("BATH 3", 8000, 0, 12500, 2500), ("BEDROOM 4", 12500, 3000, 16000, 7000),
            ("BATH 4", 12500, 0, 15000, 3000), ("SHAFT", 15000, 0, 16000, 3000),
        ],
        "windows": [("MASTER BEDROOM", "top", 2000, "W1"), ("MASTER BEDROOM", "left", 1600, "W2"),
                    ("MASTER BATH", "top", 1200, "W3"), ("BEDROOM 2", "top", 1400, "W1"),
                    ("BATH 2", "right", 1200, "W3"), ("FAMILY LIVING", "left", 2200, "W4"),
                    ("FAMILY LIVING", "bottom", 1600, "W2"), ("BEDROOM 3", "bottom", 0, None),
                    ("BATH 3", "bottom", 1800, "W3"), ("BEDROOM 4", "right", 1300, "W1"),
                    ("BATH 4", "bottom", 900, "W3")],
        "doors": [("MASTER BEDROOM", "right", 600, 900), ("DRESSING", "bottom", 1000, 800),
                  ("MASTER BATH", "bottom", 1000, 800), ("BEDROOM 2", "bottom", 600, 900),
                  ("BATH 2", "left", 600, 800), ("LOBBY", "left", 800, 1000),
                  ("LOBBY", "right", 800, 900), ("STAIR", "top", 1000, 1000),
                  ("BATH 3", "top", 800, 800), ("BEDROOM 4", "left", 1500, 900),
                  ("BATH 4", "top", 800, 800), ("LINEN", "left", 500, 800)],
    },
    "ROOF PLAN": {
        "dwg": "A-103",
        "rooms": [("ROOF", 0, 0, 16000, 12000), ("STAIR HEAD", 5000, 0, 8000, 4500)],
        "windows": [],
        "doors": [("STAIR HEAD", "top", 1000, 1000)],
        "parapet": True,
    },
}


def P(x_mm_real, y_mm_real):
    """Real building mm -> PDF points (reportlab, origin bottom-left)."""
    return ((OX + x_mm_real / SCALE) * PT, (OY + y_mm_real / SCALE) * PT)


def L(mm_real):
    return mm_real / SCALE * PT


def room_side(r, side):
    """Return (x1,y1,x2,y2) of a room side, running left->right / bottom->top."""
    _, x0, y0, x1, y1 = r
    return {"top": (x0, y1, x1, y1), "bottom": (x0, y0, x1, y0),
            "left": (x0, y0, x0, y1), "right": (x1, y0, x1, y1)}[side]


def is_ext(x1, y1, x2, y2):
    return (y1 == y2 and y1 in (0, H)) or (x1 == x2 and x1 in (0, W))


def wall_rect(x1, y1, x2, y2, t, ext):
    """Rectangle for a wall on a grid line; exterior walls sit inside the outer face."""
    if y1 == y2:  # horizontal
        if ext:
            ya = 0 if y1 == 0 else H - t
            return (min(x1, x2), ya, max(x1, x2), ya + t)
        return (min(x1, x2) - t / 2, y1 - t / 2, max(x1, x2) + t / 2, y1 + t / 2)
    if ext:
        xa = 0 if x1 == 0 else W - t
        return (xa, min(y1, y2), xa + t, max(y1, y2))
    return (x1 - t / 2, min(y1, y2) - t / 2, x1 + t / 2, max(y1, y2) + t / 2)


def build_walls(rooms):
    """Merge room edges into wall segments per grid line (interval union)."""
    lines = {}
    for r in rooms:
        for s in ("top", "bottom", "left", "right"):
            x1, y1, x2, y2 = room_side(r, s)
            key = ("h", y1) if y1 == y2 else ("v", x1)
            a, b = (x1, x2) if y1 == y2 else (y1, y2)
            lines.setdefault(key, []).append((a, b))
    segs = []
    for (k, c), ivs in lines.items():
        ivs.sort()
        cur = list(ivs[0])
        for a, b in ivs[1:]:
            if a <= cur[1]:
                cur[1] = max(cur[1], b)
            else:
                segs.append((k, c, cur[0], cur[1]))
                cur = [a, b]
        segs.append((k, c, cur[0], cur[1]))
    return segs


def subtract(a, b, holes):
    out, pos = [], a
    for h0, h1 in sorted(holes):
        if h1 <= pos or h0 >= b:
            continue
        if h0 > pos:
            out.append((pos, h0))
        pos = max(pos, h1)
    if pos < b:
        out.append((pos, b))
    return out


def draw_floor(c, title, spec):
    rooms = spec["rooms"]
    byname = {r[0]: r for r in rooms}
    openings = []  # (orient, coord, a, b, kind, data)
    for name, side, off, tag in spec["windows"]:
        if tag is None:
            continue
        x1, y1, x2, y2 = room_side(byname[name], side)
        wdt = WINDOWS[tag][0]
        if y1 == y2:
            a = x1 + off
            openings.append(("h", y1, a, a + wdt, "win", (tag, side)))
        else:
            a = y1 + off
            openings.append(("v", x1, a, a + wdt, "win", (tag, side)))
    for name, side, off, wdt in spec["doors"]:
        x1, y1, x2, y2 = room_side(byname[name], side)
        if y1 == y2:
            openings.append(("h", y1, x1 + off, x1 + off + wdt, "door", (name, side)))
        else:
            openings.append(("v", x1, y1 + off, y1 + off + wdt, "door", (name, side)))

    # walls (poche)
    c.setFillGray(0.25)
    c.setStrokeGray(0.0)
    c.setLineWidth(0.3)
    for k, coord, a, b in build_walls(rooms):
        holes = [(o[2], o[3]) for o in openings if o[0] == k and o[1] == coord]
        for s0, s1 in subtract(a, b, holes):
            if k == "h":
                ext = coord in (0, H)
                t = EXT if ext else INT
                x0, y0, x1, y1 = wall_rect(s0, coord, s1, coord, t, ext)
            else:
                ext = coord in (0, W)
                t = EXT if ext else INT
                x0, y0, x1, y1 = wall_rect(coord, s0, coord, s1, t, ext)
            px, py = P(x0, y0)
            c.rect(px, py, L(x1 - x0), L(y1 - y0), stroke=1, fill=1)

    def swing(hx, hy, r, start, extent):
        """Door swing as a true (bezier) arc centred on the hinge."""
        path = c.beginPath()
        a0 = math.radians(start)
        path.moveTo(*P(hx + r * math.cos(a0), hy + r * math.sin(a0)))
        x1, y1 = P(hx - r, hy - r)
        x2, y2 = P(hx + r, hy + r)
        path.arcTo(x1, y1, x2, y2, startAng=start, extent=extent)
        c.drawPath(path, stroke=1, fill=0)

    # openings
    c.setLineWidth(0.25)
    for k, coord, a, b, kind, data in openings:
        ext = (k == "h" and coord in (0, H)) or (k == "v" and coord in (0, W))
        t = EXT if ext else INT
        if kind == "win":
            tag, side = data
            if k == "h":
                y0 = 0 if coord == 0 else H - t
                for f in (0, 0.5, 1):
                    c.line(*P(a, y0 + f * t), *P(b, y0 + f * t))
                c.line(*P(a, y0), *P(a, y0 + t))
                c.line(*P(b, y0), *P(b, y0 + t))
                ty = -650 if coord == 0 else H + 400
                c.setFont("Helvetica", 6)
                c.drawCentredString(*P((a + b) / 2, ty), tag)
            else:
                x0 = 0 if coord == 0 else W - t
                for f in (0, 0.5, 1):
                    c.line(*P(x0 + f * t, a), *P(x0 + f * t, b))
                c.line(*P(x0, a), *P(x0 + t, a))
                c.line(*P(x0, b), *P(x0 + t, b))
                tx = -650 if coord == 0 else W + 650
                c.setFont("Helvetica", 6)
                c.drawCentredString(*P(tx, (a + b) / 2 - 80), tag)
        else:
            # door leaf opens into the named room; hinge at 'a'
            name, side = data
            r = byname[name]
            inward = {"top": -1, "bottom": 1, "left": 1, "right": -1}[side]
            wdt = b - a
            if k == "h":
                face = (coord - t / 2 if inward < 0 else coord + t / 2) if not ext else (coord - t if coord == H else coord + t)
                hx, hy = a, face
                tip = (a, face + inward * wdt)
                c.line(*P(hx, hy), *P(*tip))
                swing(hx, hy, wdt, 0, 90 * inward)
            else:
                face = (coord - t / 2 if inward < 0 else coord + t / 2) if not ext else (coord - t if coord == W else coord + t)
                hx, hy = face, a
                tip = (face + inward * wdt, a)
                c.line(*P(hx, hy), *P(*tip))
                swing(hx, hy, wdt, 90, -90 * inward)

    if spec.get("parapet"):
        c.setFont("Helvetica-Oblique", 6)
        c.drawCentredString(*P(W / 2, H - 700), "PARAPET 1.2 m HIGH")

    # room names + net areas
    for name, x0, y0, x1, y1 in rooms:
        tx = x0 + (EXT if x0 == 0 else INT / 2)
        tx1 = x1 - (EXT if x1 == W else INT / 2)
        ty = y0 + (EXT if y0 == 0 else INT / 2)
        ty1 = y1 - (EXT if y1 == H else INT / 2)
        area = (tx1 - tx) * (ty1 - ty) / 1e6
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        c.setFont("Helvetica-Bold", 6.5 if (x1 - x0) > 1500 else 4.5)
        c.drawCentredString(*P(cx, cy + 100), name)
        c.setFont("Helvetica", 5.5 if (x1 - x0) > 1500 else 4)
        c.drawCentredString(*P(cx, cy - 300), f"{area:.2f} m²")

    # dimensions: overall bottom and left, chain on top
    c.setLineWidth(0.2)
    c.setFont("Helvetica", 6)

    def hdim(xa, xb, y):
        c.line(*P(xa, y), *P(xb, y))
        for x in (xa, xb):
            c.line(*P(x - 150, y - 150), *P(x + 150, y + 150))
            c.line(*P(x, y - 300), *P(x, y + 300))
        c.drawCentredString(*P((xa + xb) / 2, y + 120), f"{xb - xa:.0f}")

    def vdim(ya, yb, x):
        c.line(*P(x, ya), *P(x, yb))
        for y in (ya, yb):
            c.line(*P(x - 150, y - 150), *P(x + 150, y + 150))
            c.line(*P(x - 300, y), *P(x + 300, y))
        c.saveState()
        px, py = P(x - 150, (ya + yb) / 2)
        c.translate(px, py)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{yb - ya:.0f}")
        c.restoreState()

    hdim(0, W, -1800)
    vdim(0, H, -1800)
    xs = sorted({r[1] for r in rooms if r[4] == H or r[2] >= 7000} | {W})
    top = [x for x in xs]
    for xa, xb in zip(top, top[1:]):
        hdim(xa, xb, H + 1300)

    # north arrow (top right of drawing area)
    ax, ay = P(W + 3500, H - 1000)
    r = 7 * PT / 2
    c.setLineWidth(0.4)
    c.circle(ax, ay, r, stroke=1, fill=0)
    ang = math.radians(NORTH_DEG)
    ux, uy = math.sin(ang), math.cos(ang)
    px_, py_ = -uy, ux
    tip = (ax + ux * r, ay + uy * r)
    b1 = (ax - ux * r * 0.6 + px_ * r * 0.35, ay - uy * r * 0.6 + py_ * r * 0.35)
    b2 = (ax - ux * r * 0.6 - px_ * r * 0.35, ay - uy * r * 0.6 - py_ * r * 0.35)
    path = c.beginPath()
    path.moveTo(*tip); path.lineTo(*b1); path.lineTo(*b2); path.close()
    c.setFillGray(0)
    c.drawPath(path, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(ax + ux * (r + 9) - 0, ay + uy * (r + 9) - 3, "N")

    # window schedule
    if spec["windows"]:
        sx, sy = (OX + 205) * PT, (OY + 60) * PT
        c.setFont("Helvetica-Bold", 7)
        c.drawString(sx, sy, "WINDOW SCHEDULE")
        c.setFont("Helvetica", 6)
        for i, (tag, (ww, hh)) in enumerate(WINDOWS.items()):
            c.drawString(sx, sy - (i + 1) * 10, f"{tag}   {ww} x {hh}   ALUMINIUM, DOUBLE GLAZED, SILL 900")

    # title block
    pw, ph = landscape(A3)
    bx, by, bw, bh = pw - 120 * PT, 12 * PT, 108 * PT, 42 * PT
    c.setLineWidth(0.8)
    c.rect(bx, by, bw, bh)
    c.rect(10 * PT, 10 * PT, pw - 20 * PT, ph - 20 * PT)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(bx + 4 * PT, by + bh - 7 * PT, "PROJECT: SAMPLE VILLA - RIYADH")
    c.setFont("Helvetica", 7)
    c.drawString(bx + 4 * PT, by + bh - 14 * PT, f"DRAWING: {title}")
    c.drawString(bx + 4 * PT, by + bh - 21 * PT, "SCALE 1:100 @ A3")
    c.drawString(bx + 4 * PT, by + bh - 28 * PT, f"DWG NO. {spec['dwg']}   REV 0")
    c.drawString(bx + 4 * PT, by + bh - 35 * PT, "ARCHITECT: SAMPLE ARCHITECTS (TEST DATA)")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(OX * PT, (OY + H / SCALE + 30) * PT, title)


def main(out):
    c = canvas.Canvas(out, pagesize=landscape(A3))
    c.setTitle("Sample Villa - Architectural Plans")
    for title, spec in FLOORS.items():
        draw_floor(c, title, spec)
        c.showPage()
    c.save()
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_villa.pdf")
