"""Step C1 - HVAC sheets drawn over the architectural PDF (one sheet per floor + roof),
plus a controls schematic / equipment schedule sheet.

Each sheet = original page (faded) + a side panel with legend, schedule, north arrow,
scale, title block and the PRELIMINARY DESIGN note. HVAC items sit on PDF optional-content
layers named like the DXF layers (M-DUCT-SUPP, ...), so they can be toggled in a viewer.

CLI: python drawing_overlay.py -w WORK   -> WORK/out/HVAC_plans.pdf, WORK/out/preview_*.png
"""
import argparse
import math
import os
from datetime import date

import pymupdf as fitz

import common as C
import geom as G
import sheet_items as SI

DASH = {"solid": None, "dash": "[4 2] 0", "dot": "[1 1.5] 0"}


def draw_items(page, items, ocg, layers):
    for it in items:
        L = layers[it["layer"]]
        col = tuple(L["rgb"])
        oc = ocg[it["layer"]]
        k = it["kind"]
        if k == "band":
            sh = page.new_shape()
            w = it["width_pt"] / 2
            for (ax, ay), (bx, by) in zip(it["pts"], it["pts"][1:]):
                dx, dy = bx - ax, by - ay
                n = math.hypot(dx, dy) or 1
                nx, ny = -dy / n * w, dx / n * w
                ex, ey = dx / n * w, dy / n * w  # extend to make clean corners
                quad = [(ax - ex + nx, ay - ey + ny), (bx + ex + nx, by + ey + ny), (bx + ex - nx, by + ey - ny), (ax - ex - nx, ay - ey - ny)]
                sh.draw_polyline(quad + [quad[0]])
            sh.finish(color=col, fill=col, fill_opacity=0.18, width=0.5, dashes=DASH[it["style"]], oc=oc, closePath=True)
            sh.commit()
        elif k == "line":
            sh = page.new_shape()
            sh.draw_polyline(it["pts"])
            sh.finish(color=col, width=it.get("lw", 0.8), dashes=DASH[it.get("style", "solid")], oc=oc, closePath=False)
            sh.commit()
        elif k == "rect":
            cx, cy = it["center"]
            r = fitz.Rect(cx - it["w"] / 2, cy - it["h"] / 2, cx + it["w"] / 2, cy + it["h"] / 2)
            sh = page.new_shape()
            sh.draw_rect(r)
            sh.finish(color=col, fill=tuple(it["fill"]) if it.get("fill") else (1, 1, 1), fill_opacity=0.35 if it.get("fill") else 0.9, width=0.7, oc=oc)
            if it.get("cross"):
                sh.draw_line(r.tl, r.br)
                sh.draw_line(r.tr, r.bl)
                sh.finish(color=col, width=0.5, oc=oc)
            if it.get("diag"):
                sh.draw_line(r.tl, r.br)
                sh.finish(color=col, width=0.5, oc=oc)
            sh.commit()
        elif k == "circle":
            sh = page.new_shape()
            sh.draw_circle(it["center"], it["r"])
            sh.finish(color=col, fill=(1, 1, 1), width=0.7, oc=oc)
            sh.commit()
            if it.get("text"):
                fs = max(3.5, it["r"] * 1.3)
                page.insert_text((it["center"][0] - fs * 0.3, it["center"][1] + fs * 0.35), it["text"], fontsize=fs, color=col, oc=oc)
        elif k == "text":
            rot = it.get("angle", 0)
            page.insert_text(it["pos"], it["text"], fontsize=it["size_pt"], color=col if it["layer"] != "M-ANNO" else (0.1, 0.1, 0.1),
                             rotate=rot, oc=oc)


def north_arrow(page, c, deg, r=14):
    a = math.radians(deg)
    ux, uy = math.sin(a), -math.cos(a)
    px, py = -uy, ux
    tip = (c[0] + ux * r, c[1] + uy * r)
    b1 = (c[0] - ux * r * 0.6 + px * r * 0.4, c[1] - uy * r * 0.6 + py * r * 0.4)
    b2 = (c[0] - ux * r * 0.6 - px * r * 0.4, c[1] - uy * r * 0.6 - py * r * 0.4)
    page.draw_circle(c, r, color=(0, 0, 0), width=0.6)
    page.draw_polyline([tip, b1, b2, tip], color=(0, 0, 0), fill=(0, 0, 0), closePath=True)
    page.insert_text((tip[0] + ux * 8 - 3, tip[1] + uy * 8 + 3), "N", fontsize=9, color=(0, 0, 0))


def legend(page, x, y, layers):
    page.insert_text((x, y), "LEGEND", fontsize=8, color=(0, 0, 0))
    rows = [("M-DUCT-SUPP", "band", "Supply duct (size, flow) / flex dashed"), ("M-DUCT-SUPP", "diff", "Supply diffuser SD"),
            ("M-DUCT-RETN", "band", "Return duct"), ("M-DUCT-RETN", "grille", "Return grille RG"),
            ("M-DUCT-FRSH", "dband", "Fresh air duct / louver FAL"), ("M-DUCT-EXHS", "dband", "Exhaust duct / grille EG / fan EF"),
            ("M-PIPE-REFG", "line", "Refrigerant pipe (liquid/gas mm)"), ("M-PIPE-COND", "dot", "Condensate drain"),
            ("M-PIPE-CHWS", "line", "Chilled water pipe"), ("M-EQPM", "unit", "Indoor / outdoor unit"), ("M-CTRL", "tstat", "Thermostat / controller")]
    yy = y + 12
    for lay, kind, text in rows:
        col = tuple(layers[lay]["rgb"])
        if kind in ("band", "dband"):
            page.draw_rect(fitz.Rect(x, yy - 5, x + 22, yy), color=col, fill=col, fill_opacity=0.18, width=0.5, dashes=DASH["dash" if kind == "dband" else "solid"])
        elif kind == "line":
            page.draw_line((x, yy - 2.5), (x + 22, yy - 2.5), color=col, width=1.2)
        elif kind == "dot":
            page.draw_line((x, yy - 2.5), (x + 22, yy - 2.5), color=col, width=1.0, dashes=DASH["dot"])
        elif kind == "diff":
            r = fitz.Rect(x + 7, yy - 7, x + 15, yy + 1)
            page.draw_rect(r, color=col, width=0.6)
            page.draw_line(r.tl, r.br, color=col, width=0.5)
            page.draw_line(r.tr, r.bl, color=col, width=0.5)
        elif kind == "grille":
            r = fitz.Rect(x + 5, yy - 6, x + 17, yy)
            page.draw_rect(r, color=col, width=0.6)
            page.draw_line(r.tl, r.br, color=col, width=0.5)
        elif kind == "unit":
            page.draw_rect(fitz.Rect(x + 3, yy - 6, x + 19, yy), color=col, fill=col, fill_opacity=0.35, width=0.6)
        elif kind == "tstat":
            page.draw_circle((x + 11, yy - 3), 3.5, color=col, width=0.6)
        page.insert_text((x + 27, yy), text, fontsize=6, color=(0, 0, 0))
        yy += 10
    return yy


def title_block(page, x, y, w, p, sheet_no, title, scale, note):
    proj = p["project"]
    h = 112
    page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.8)
    lines = [(f"PROJECT: {proj['name']}", 8), (f"LOCATION: {proj['location']['city']}, {proj['location']['country']}", 6.5),
             (f"SHEET: {title}", 7.5), (f"SHEET NO. {sheet_no}    REV P0    {date.today().isoformat()}", 6.5),
             (f"SCALE: {scale}    CODES: {p['codes']['label']}", 6), ("PREPARED WITH hvac-designer skill (automated)", 6)]
    yy = y + 12
    for t, fs in lines:
        page.insert_text((x + 5, yy), t[:62], fontsize=fs, color=(0, 0, 0))
        yy += fs + 5
    r = fitz.Rect(x + 4, yy - 2, x + w - 4, y + h - 4)
    page.draw_rect(r, color=(0.8, 0, 0), width=0.8)
    page.insert_textbox(r + (3, 2, -3, 0), note, fontsize=6.3, color=(0.8, 0, 0))


def schedule(page, x, y, design, floor_id, U):
    page.insert_text((x, y), "EQUIPMENT ON THIS SHEET", fontsize=7.5, color=(0, 0, 0))
    yy = y + 10
    for z in design["zones"]:
        if z["floor"] != floor_id:
            continue
        u = z["unit"]
        t = f"{u['tag']}  {u['model']}  {U.power(u['nominal_kw'])}  {U.flow(u['airflow_ls'])}  {z['id']}"
        page.insert_text((x, yy), t, fontsize=5.8, color=(0, 0, 0))
        yy += 8
    for o in design["outdoor_units"]:
        if o.get("floor") == floor_id:
            page.insert_text((x, yy), f"{o['tag']}  {o['model']}  {U.power(o['cool_kw'])}  serves {', '.join(o['serves'])}", fontsize=5.8, color=(0, 0, 0))
            yy += 8
    for e in design.get("exhaust_systems", []):
        if e["floor"] == floor_id:
            page.insert_text((x, yy), f"{e['fan']['tag']}  {e['fan']['model']}  {U.flow(e['flow_ls'])}  {e['room']}", fontsize=5.8, color=(0, 0, 0))
            yy += 8
    return yy


def controls_sheet(doc, design, p, layers, note, U):
    page = doc.new_page(width=1190.55, height=841.89)
    page.insert_text((40, 50), "HVAC CONTROLS SCHEMATIC AND EQUIPMENT SCHEDULE", fontsize=14, color=(0, 0, 0))
    y = 85
    box = lambda r, t, col: (page.draw_rect(r, color=col, width=0.8), page.insert_textbox(r + (3, 3, -3, -3), t, fontsize=6.5, color=(0, 0, 0)))
    odus = {t: o for o in design["outdoor_units"] for t in o["serves"]}
    for z in design["zones"]:
        u = z["unit"]
        t = z["thermostat"]
        c_eq, c_ct = tuple(layers["M-EQPM"]["rgb"]), tuple(layers["M-CTRL"]["rgb"])
        r1 = fitz.Rect(40, y, 190, y + 34)
        r2 = fitz.Rect(240, y, 420, y + 34)
        r3 = fitz.Rect(470, y, 640, y + 34)
        box(r1, f"{t['tag']} {t['type']}\nin {t['room']} - setpoint 24 °C, fan auto/low/med/high", c_ct)
        box(r2, f"{u['tag']} {u['model']} ({z['system']})\n{U.power(u['nominal_kw'])}, {U.flow(u['airflow_ls'])} - zone {z['id']}", c_eq)
        o = odus.get(u["tag"])
        box(r3, f"{o['tag']} {o['model']}\noutdoor - {o.get('floor', 'TBC')}" if o else "plant / outdoor unit TBC", c_eq)
        page.draw_line((190, y + 17), (240, y + 17), color=c_ct, width=0.8)
        page.insert_text((193, y + 14), "2-core comm.", fontsize=5, color=c_ct)
        page.draw_line((420, y + 17), (470, y + 17), color=c_eq, width=0.8)
        page.insert_text((423, y + 14), "power + comm.", fontsize=5, color=c_eq)
        extra = []
        if z["kind"] == "ducted" and u.get("oa_ls"):
            extra.append(f"Motorised FA damper interlocked to {u['tag']} fan (open when fan runs; closed when off) - {U.flow(u['oa_ls'])}")
        if z.get("fa_fan"):
            extra.append(f"{z['fa_fan']['tag']} through-wall FA fan interlocked with {u['tag']}")
        if extra:
            r4 = fitz.Rect(690, y, 1150, y + 34)
            box(r4, "\n".join(extra), tuple(layers["M-DUCT-FRSH"]["rgb"]))
            page.draw_line((640, y + 17), (690, y + 17), color=c_ct, width=0.6, dashes=DASH["dash"])
        y += 46
    y += 6
    page.insert_text((40, y), "EXHAUST FANS: switched with room lighting with 10 min run-on timer (bath/WC); kitchen fan on local switch; backdraft damper at each discharge.", fontsize=7, color=(0, 0, 0))
    y += 12
    page.insert_text((40, y), "Optional: central on/off + fault alarm to home automation / BMS via unit gateway (by specialist).", fontsize=7, color=(0, 0, 0))
    y += 24
    page.insert_text((40, y), "EQUIPMENT SCHEDULE", fontsize=10, color=(0, 0, 0))
    y += 14
    hdr = ["Tag", "Zone", "Type", "Model", "Cooling", "Required", "Airflow", "ESP Pa", "Heating", "Power kW", "Host / location"]
    xs = [40, 110, 170, 260, 320, 400, 480, 560, 610, 680, 750]
    for x_, h_ in zip(xs, hdr):
        page.insert_text((x_, y), h_, fontsize=6.5, color=(0, 0, 0))
    y += 4
    page.draw_line((40, y), (1150, y), color=(0, 0, 0), width=0.5)
    y += 9
    for z in design["zones"]:
        u = z["unit"]
        row = [u["tag"], z["id"], u["type"], u["model"], U.power(u["derated_kw"]), U.power(u["req_total_kw"]), U.flow(u["airflow_ls"]),
               str(u["esp_pa"]), U.power(u["heat_kw"]), str(u["power_kw"]), u["host_room"]]
        for x_, t_ in zip(xs, row):
            page.insert_text((x_, y), str(t_), fontsize=6.2, color=(0, 0, 0))
        y += 9
    for o in design["outdoor_units"]:
        row = [o["tag"], "-", o["system"], o["model"], U.power(o["cool_kw"]), "-", "-", "-", "-", str(o["power_kw"]), o.get("floor", "TBC")]
        for x_, t_ in zip(xs, row):
            page.insert_text((x_, y), str(t_), fontsize=6.2, color=(0, 0, 0))
        y += 9
    for e in design.get("exhaust_systems", []):
        f = e["fan"]
        row = [f["tag"], e["room"], "exhaust fan " + f["type"], f["model"], "-", "-", U.flow(e["flow_ls"]), str(f["esp_pa"]), "-", str(f["power_w"] / 1000), e["floor"]]
        for x_, t_ in zip(xs, row):
            page.insert_text((x_, y), str(t_), fontsize=6.2, color=(0, 0, 0))
        y += 9
    title_block(page, 1190.55 - 280, 841.89 - 130, 260, p, "M-901", "CONTROLS SCHEMATIC & SCHEDULE", "NTS", note)
    return page


def render(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    design = C.load(work, "design.json")
    std = C.ref("drawing_standards.json")
    layers = std["layers"]
    note = p["design"]["drawing"]["preliminary_note"]
    U = C.Units(p["units"])
    src = fitz.open(C.source_pdf(work, rooms))
    out = fitz.open()
    ocg = {name: out.add_ocg(name, on=True) for name in layers}
    panel = p["design"]["drawing"]["side_panel_pt"]
    sheets = []
    floors = [f for f in rooms["floors"] if not f.get("needs_vision")]
    for i, fl in enumerate(floors, 1):
        sp = src[fl["page"] - 1]
        W, H = sp.rect.width, sp.rect.height
        page = out.new_page(width=W + panel, height=H)
        page.show_pdf_page(fitz.Rect(0, 0, W, H), src, fl["page"] - 1, oc=ocg["A-ARCH-REF"])
        page.draw_rect(fitz.Rect(0, 0, W, H), color=None, fill=(1, 1, 1), fill_opacity=0.45, width=0)
        items = SI.items_for(fl["id"], design, rooms, p["units"])
        draw_items(page, items, ocg, layers)
        x = W + 12
        page.draw_line((W, 0), (W, H), color=(0, 0, 0), width=0.8)
        page.insert_text((x, 30), f"HVAC LAYOUT - {fl['name'].upper()}", fontsize=10, color=(0, 0, 0))
        north_arrow(page, (x + 20, 62), fl["north_deg"])
        page.insert_text((x + 45, 58), f"North {fl['north_deg']:.0f}° from page-up", fontsize=6, color=(0, 0, 0))
        page.insert_text((x + 45, 68), f"Scale 1:{fl['scale']:.0f} (as architectural sheet)", fontsize=6, color=(0, 0, 0))
        yy = legend(page, x, 95, layers)
        yy = schedule(page, x, yy + 10, design, fl["id"], U)
        page.insert_text((x, yy + 6), "NOTES", fontsize=7, color=(0, 0, 0))
        notes = ["Duct sizes W x H mm (clear internal); Ø = round.", "Ducts at high level in ceiling void; coordinate with beams.",
                 "Door undercut 20 mm / transfer grilles for return air.", "Refrigerant/condensate routes are indicative."]
        for k, t in enumerate(notes):
            page.insert_text((x, yy + 16 + k * 8), "- " + t, fontsize=5.6, color=(0, 0, 0))
        sheet_no = f"M-{100 + i}"
        title_block(page, W + 6, H - 125, panel - 12, p, sheet_no, f"HVAC LAYOUT - {fl['name']}", f"1:{fl['scale']:.0f}", note)
        page.insert_text((20, H - 14), note, fontsize=7, color=(0.8, 0, 0))
        sheets.append({"sheet": sheet_no, "floor": fl["id"], "tags": sorted(SI.drawn_tags(items)), "items": len(items)})
    controls_sheet(out, design, p, layers, note, U)
    sheets.append({"sheet": "M-901", "floor": None, "tags": [], "items": 0})
    os.makedirs(os.path.join(work, "out"), exist_ok=True)
    path = os.path.join(work, "out", "HVAC_plans.pdf")
    out.set_metadata({"title": f"HVAC plans - {p['project']['name']} (PRELIMINARY)", "author": "hvac-designer skill"})
    out.save(path, garbage=3, deflate=True)
    for k, pg in enumerate(out):
        pg.get_pixmap(dpi=90).save(os.path.join(work, "out", f"preview_{sheets[k]['sheet']}.png"))
    C.save(work, "sheets.json", {"sheets": sheets})
    print(f"drawing_overlay: {path} ({len(sheets)} sheets)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    render(ap.parse_args().work)
