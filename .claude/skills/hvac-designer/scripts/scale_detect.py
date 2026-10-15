"""Find the drawing scale of a vector PDF page.

Methods (all run, then reconciled):
  1. title block / note text  "SCALE 1:100", "1/100", "SC 1:50"
  2. dimension strings        numeric text (mm) next to a parallel dimension line
  3. user known dimension     --known "16000" (a dimension text whose real length is known)
Result: {"denominator", "method", "confidence", "candidates", "mm_per_pt"}.
Confidence 'high' needs two methods agreeing within 3 %; otherwise the caller must ask.

CLI: python scale_detect.py plan.pdf [--page 1]
"""
import argparse
import json
import re
import statistics

import pymupdf as fitz

STD_SCALES = [10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 1000]
PT_MM = 25.4 / 72
SCALE_RE = re.compile(r"(?:SCALE|SC\.?)\s*[:=]?\s*1\s*[:/]\s*(\d{1,4})", re.I)
BARE_RE = re.compile(r"^1\s*:\s*(\d{1,4})$")
DIM_RE = re.compile(r"^\d{3,5}$")
DIM_M_RE = re.compile(r"^\d{1,2}[.,]\d{1,2}$")  # metres with decimal (e.g. 3,27 / 2.48)


def text_lines(page):
    out = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            txt = " ".join(s["text"] for s in ln["spans"]).strip()
            if txt:
                out.append({"text": txt, "bbox": ln["bbox"], "dir": ln["dir"],
                            "size": max(s["size"] for s in ln["spans"])})
    return out


def segments(page):
    segs = []
    for p in page.get_drawings():
        for it in p["items"]:
            if it[0] == "l":
                segs.append((it[1].x, it[1].y, it[2].x, it[2].y))
            elif it[0] == "re":
                r = it[1]
                segs += [(r.x0, r.y0, r.x1, r.y0), (r.x0, r.y1, r.x1, r.y1),
                         (r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)]
    return segs


def from_text(lines):
    found = []
    for ln in lines:
        m = SCALE_RE.search(ln["text"]) or BARE_RE.match(ln["text"].strip())
        if m:
            found.append({"denominator": int(m.group(1)), "source": ln["text"]})
    return found


def from_dimensions(lines, segs):
    """Pair each numeric (mm) text with the closest parallel line whose midpoint it sits on."""
    ratios = []
    for ln in lines:
        t = ln["text"].strip()
        if DIM_RE.match(t.replace(",", "")):
            val = float(t.replace(",", ""))
        elif DIM_M_RE.match(t):
            val = float(t.replace(",", ".")) * 1000.0
        else:
            continue
        x0, y0, x1, y1 = ln["bbox"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        vertical = abs(ln["dir"][1]) > 0.7
        best = None
        for sx0, sy0, sx1, sy1 in segs:
            if vertical:
                if abs(sx0 - sx1) > 0.5:
                    continue
                length = abs(sy1 - sy0)
                if length < 5 or not (min(sy0, sy1) <= cy <= max(sy0, sy1)):
                    continue
                d = abs(sx0 - cx)
                mid_off = abs((sy0 + sy1) / 2 - cy)
            else:
                if abs(sy0 - sy1) > 0.5:
                    continue
                length = abs(sx1 - sx0)
                if length < 5 or not (min(sx0, sx1) <= cx <= max(sx0, sx1)):
                    continue
                d = abs(sy0 - cy)
                mid_off = abs((sx0 + sx1) / 2 - cx)
            if d > 12 or mid_off > 0.15 * length:
                continue
            if best is None or d < best[0]:
                best = (d, length)
        if best:
            ratios.append(val / (best[1] * PT_MM))
    return ratios


def snap(den):
    s = min(STD_SCALES, key=lambda k: abs(k - den) / k)
    return s, abs(s - den) / s


def detect(page, known=None):
    lines = text_lines(page)
    segs = segments(page)
    title = from_text(lines)
    dims = from_dimensions(lines, segs)
    cands = {"title_block": title, "dimension_ratios": [round(r, 2) for r in dims[:40]]}
    dim_den = None
    if len(dims) >= 2:
        med = statistics.median(dims)
        close = [r for r in dims if abs(r - med) / med < 0.05]
        if len(close) >= max(2, len(dims) // 3):
            dim_den = statistics.median(close)
    res = {"candidates": cands, "denominator": None, "method": None, "confidence": "none"}
    t_den = title[0]["denominator"] if title else None
    if known:
        res.update(denominator=known, method="user", confidence="high")
    elif t_den and dim_den:
        s, err = snap(dim_den)
        agree = abs(dim_den - t_den) / t_den < 0.03
        res.update(denominator=t_den, method="title+dimensions" if agree else "title (dimensions disagree)",
                   confidence="high" if agree else "low", dimension_estimate=round(dim_den, 1))
    elif t_den:
        res.update(denominator=t_den, method="title only", confidence="medium")
    elif dim_den:
        s, err = snap(dim_den)
        res.update(denominator=s, method="dimensions only", confidence="medium" if err < 0.03 else "low",
                   dimension_estimate=round(dim_den, 1))
    if res["denominator"]:
        res["mm_per_pt"] = PT_MM * res["denominator"]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--known", type=float, help="force scale denominator (user-confirmed)")
    a = ap.parse_args()
    doc = fitz.open(a.pdf)
    print(json.dumps(detect(doc[a.page - 1], a.known), indent=2))


if __name__ == "__main__":
    main()
