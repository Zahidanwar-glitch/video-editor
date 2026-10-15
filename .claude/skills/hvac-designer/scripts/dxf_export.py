"""Step C2 - export each floor as DXF (ezdxf), real-world millimetres, standard layers
M-DUCT-SUPP, M-DUCT-RETN, M-DUCT-FRSH, M-DUCT-EXHS, M-PIPE-REFG, M-PIPE-CHWS, M-PIPE-COND,
M-EQPM, M-CTRL, M-ANNO, plus the architectural background on A-ARCH-REF.

CLI: python dxf_export.py -w WORK   -> WORK/out/HVAC_<floor>.dxf
"""
import argparse
import math
import os

import ezdxf
import pymupdf as fitz

import common as C
import sheet_items as SI

LT = {"solid": "CONTINUOUS", "dash": "DASHED", "dot": "DOT"}


def export(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    design = C.load(work, "design.json")
    layers = C.ref("drawing_standards.json")["layers"]
    note = p["design"]["drawing"]["preliminary_note"]
    src = fitz.open(C.source_pdf(work, rooms))
    os.makedirs(os.path.join(work, "out"), exist_ok=True)
    files = []
    for fl in [f for f in rooms["floors"] if not f.get("needs_vision")]:
        k = fl["mm_per_pt"]
        H = fl["page_size_pt"][1]
        X = lambda pt: (pt[0] * k, (H - pt[1]) * k)
        doc = ezdxf.new("R2018", setup=True)
        doc.units = ezdxf.units.MM
        for name, L in layers.items():
            doc.layers.add(name, color=L["aci"], linetype=L["linetype"] if L["linetype"] in doc.linetypes else "CONTINUOUS")
        msp = doc.modelspace()
        # architectural background (vector paths of the source page)
        page = src[fl["page"] - 1]
        drawings = page.get_drawings()
        rp = C.ref("design_defaults.json")["drawing"]
        heavy = len(drawings) > rp["dxf_background_heavy_paths"]
        min_pt = rp["dxf_background_min_segment_m"] * 1000 / k
        skipped = 0
        for d in drawings:
            if heavy and d["rect"].width < min_pt and d["rect"].height < min_pt:
                skipped += 1  # hatching / tiny symbols on traced drawings
                continue
            for it in d["items"]:
                if it[0] == "l":
                    msp.add_line(X(it[1]), X(it[2]), dxfattribs={"layer": "A-ARCH-REF"})
                elif it[0] == "re":
                    r = it[1]
                    msp.add_lwpolyline([X((r.x0, r.y0)), X((r.x1, r.y0)), X((r.x1, r.y1)), X((r.x0, r.y1))], close=True, dxfattribs={"layer": "A-ARCH-REF"})
                elif it[0] == "c":
                    pts = [it[1], it[2], it[3], it[4]]
                    msp.add_spline([X(q) for q in pts], dxfattribs={"layer": "A-ARCH-REF"})
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = " ".join(s["text"] for s in ln["spans"]).strip()
                if t:
                    sz = max(s["size"] for s in ln["spans"])
                    ang = math.degrees(math.atan2(-ln["dir"][1], ln["dir"][0]))
                    msp.add_text(t, height=sz * k * 0.7, rotation=ang, dxfattribs={"layer": "A-ARCH-REF"}).set_placement(X((ln["bbox"][0], ln["bbox"][3])))
        for it in SI.items_for(fl["id"], design, rooms, p["units"]):
            lay = it["layer"]
            if it["kind"] == "band":
                w = it["width_pt"] / 2
                for (ax, ay), (bx, by) in zip(it["pts"], it["pts"][1:]):
                    dx, dy = bx - ax, by - ay
                    n = math.hypot(dx, dy) or 1
                    nx, ny = -dy / n * w, dx / n * w
                    quad = [(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]
                    msp.add_lwpolyline([X(q) for q in quad], close=True, dxfattribs={"layer": lay, "linetype": LT[it["style"]]})
            elif it["kind"] == "line":
                msp.add_lwpolyline([X(q) for q in it["pts"]], dxfattribs={"layer": lay, "linetype": LT[it.get("style", "solid")]})
            elif it["kind"] == "rect":
                cx, cy = it["center"]
                w, h = it["w"] / 2, it["h"] / 2
                c = [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
                msp.add_lwpolyline([X(q) for q in c], close=True, dxfattribs={"layer": lay})
                if it.get("cross"):
                    msp.add_line(X(c[0]), X(c[2]), dxfattribs={"layer": lay})
                    msp.add_line(X(c[1]), X(c[3]), dxfattribs={"layer": lay})
                if it.get("diag"):
                    msp.add_line(X(c[0]), X(c[2]), dxfattribs={"layer": lay})
                if it.get("tag"):
                    msp.add_text(it["tag"], height=it["h"] * k * 0.15 + 50, dxfattribs={"layer": "M-ANNO"}).set_placement(X((cx, cy)))
            elif it["kind"] == "circle":
                msp.add_circle(X(it["center"]), it["r"] * k, dxfattribs={"layer": lay})
                if it.get("text"):
                    msp.add_text(it["text"], height=it["r"] * k, dxfattribs={"layer": lay}).set_placement(X(it["center"]), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
            elif it["kind"] == "text":
                msp.add_text(it["text"], height=it["size_pt"] * 25.4 / 72 * fl["scale"], rotation=it.get("angle", 0),
                             dxfattribs={"layer": lay if lay != "M-ANNO" else "M-ANNO"}).set_placement(X(it["pos"]))
        # title / note under the plan
        y0 = -20 * fl["scale"]
        for i, t in enumerate([f"HVAC LAYOUT - {fl['name'].upper()} - {p['project']['name']}", f"Scale 1:{fl['scale']:.0f}, units mm, north {fl['north_deg']:.0f} deg clockwise from sheet-up", note]):
            msp.add_text(t, height=3.5 * fl["scale"] * (1.0 if i < 2 else 0.9), dxfattribs={"layer": "M-ANNO", "color": 1 if i == 2 else 256}).set_placement((0, y0 - i * 6 * fl["scale"]))
        if skipped:
            print(f"  {fl['id']}: background simplified - {skipped} small paths (< {rp['dxf_background_min_segment_m']} m) left out of A-ARCH-REF")
        path = os.path.join(work, "out", f"HVAC_{fl['id']}.dxf")
        doc.saveas(path)
        files.append(path)
    print("dxf_export: " + ", ".join(os.path.basename(f) for f in files))
    return files


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    export(ap.parse_args().work)
