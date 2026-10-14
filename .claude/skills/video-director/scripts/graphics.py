"""Animated infographic overlays rendered as transparent PNG sequences (Pillow).

One consistent motion language for every graphic: 180 ms ease-out rise + fade in,
150 ms fade out, accent colour from the plan/style, rounded dark card for legibility.
Identical consecutive frames are hard-linked, so static holds cost almost nothing.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import find_font

IN_S, OUT_S = 0.18, 0.15


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def ease_out_back(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def hex_rgb(h: str, a: int = 255) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


class Fonts:
    def __init__(self, H: int):
        self.black = find_font("black")
        self.bold = find_font("bold")
        self.H = H
        self._cache: dict = {}

    def get(self, weight: str, frac: float) -> ImageFont.FreeTypeFont:
        size = max(10, int(self.H * frac))
        key = (weight, size)
        if key not in self._cache:
            path = self.black if weight == "black" else self.bold
            try:
                self._cache[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)
            except Exception:
                self._cache[key] = ImageFont.load_default()
        return self._cache[key]


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fmt_number(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}"


# ------------------------------------------------------------ card painters
# Each painter returns an RGBA image for local time t (seconds since the graphic appeared).

def paint_counter(g, t, W, H, F, accent):
    vertical = H > W
    base = min(W, H)
    dec = g.get("decimals", 0 if float(g["value"]).is_integer() else 1)
    p = ease_out(t / 0.8)
    val = g.get("from", 0) + (g["value"] - g.get("from", 0)) * p
    num = f"{g.get('prefix', '')}{fmt_number(val, dec)}{g.get('suffix', '')}"
    final = f"{g.get('prefix', '')}{fmt_number(g['value'], dec)}{g.get('suffix', '')}"
    fnum = F.get("black", 0.075 if vertical else 0.13)
    flab = F.get("bold", 0.024 if vertical else 0.042)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    label = g.get("label", "")
    lab_lines = wrap(tmp, label, flab, int(base * 0.8)) if label else []
    nw = tmp.textlength(final, font=fnum)
    lw = max([tmp.textlength(l, font=flab) for l in lab_lines] or [0])
    pad = int(base * 0.04)
    nh = fnum.getbbox("0%")[3]
    lh = int(flab.size * 1.25)
    cw, ch = int(max(nw, lw) + pad * 2), int(nh + pad * 2 + lh * len(lab_lines) + (pad // 2 if lab_lines else 0))
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=pad, fill=(12, 12, 16, 215))
    d.rectangle((0, ch - max(4, pad // 5), cw, ch), fill=hex_rgb(accent))
    d.text((cw / 2, pad), num, font=fnum, fill=hex_rgb(accent), anchor="ma")
    for k, l in enumerate(lab_lines):
        d.text((cw / 2, pad + nh + pad // 2 + k * lh), l, font=flab, fill=(255, 255, 255, 255), anchor="ma")
    return im


def paint_list(g, t, W, H, F, accent, item_offsets):
    vertical = H > W
    base = min(W, H)
    ft = F.get("black", 0.03 if vertical else 0.05)
    fi = F.get("bold", 0.026 if vertical else 0.042)
    pad = int(base * 0.04)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    items = g["items"]
    maxw = int(base * (0.78 if vertical else 0.55))
    wrapped = [wrap(tmp, it, fi, maxw - int(fi.size * 1.6)) for it in items]
    title = g.get("title", "")
    lh = int(fi.size * 1.3)
    th = int(ft.size * 1.4) if title else 0
    ch = pad * 2 + th + sum(len(w) * lh + pad // 2 for w in wrapped)
    cw = max([int(tmp.textlength(title, font=ft))] + [int(fi.size * 1.6 + max(tmp.textlength(l, font=fi) for l in w)) for w in wrapped]) + pad * 2
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=pad, fill=(12, 12, 16, 215))
    if title:
        d.text((pad, pad), title.upper(), font=ft, fill=hex_rgb(accent))
    y = pad + th
    for k, lines in enumerate(wrapped):
        appear = item_offsets[k] if k < len(item_offsets) else k * 0.6
        a = ease_out((t - appear) / 0.22)
        if a > 0:
            alpha = int(255 * a)
            dx = int((1 - a) * fi.size)
            r = fi.size * 0.42
            cx, cy = pad + r + dx, y + fi.size * 0.6
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hex_rgb(accent, alpha))
            d.text((cx, cy), str(k + 1), font=F.get("black", fi.size / H * 0.62), fill=(10, 10, 10, alpha), anchor="mm")
            for j, l in enumerate(lines):
                d.text((pad + fi.size * 1.6 + dx, y + j * lh), l, font=fi, fill=(255, 255, 255, alpha))
        y += len(lines) * lh + pad // 2
    return im


def paint_quote(g, t, W, H, F, accent):
    vertical = H > W
    base = min(W, H)
    fq = F.get("black", 0.04 if vertical else 0.06)
    fa = F.get("bold", 0.022 if vertical else 0.034)
    pad = int(base * 0.05)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = wrap(tmp, f"“{g['text']}”", fq, int(W * (0.8 if vertical else 0.6)))
    lh = int(fq.size * 1.2)
    attr = g.get("attribution")
    cw = int(max(tmp.textlength(l, font=fq) for l in lines)) + pad * 2
    ch = pad * 2 + lh * len(lines) + (int(fa.size * 1.6) if attr else 0)
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=pad // 2, fill=(12, 12, 16, 220))
    d.rectangle((0, 0, max(6, pad // 6), ch), fill=hex_rgb(accent))
    shown = int(len(" ".join(lines)) * ease_out(t / 0.5)) if t < 0.5 else 10 ** 9
    count = 0
    for k, l in enumerate(lines):
        vis = l[: max(0, shown - count)]
        count += len(l) + 1
        d.text((pad, pad + k * lh), vis, font=fq, fill=(255, 255, 255, 255))
    if attr:
        d.text((pad, pad + lh * len(lines) + fa.size * 0.4), f"— {attr}", font=fa, fill=hex_rgb(accent))
    return im


def paint_bar(g, t, W, H, F, accent):
    vertical = H > W
    base = min(W, H)
    fl = F.get("bold", 0.024 if vertical else 0.036)
    ft = F.get("black", 0.03 if vertical else 0.045)
    pad = int(base * 0.04)
    bars = g["bars"]
    vmax = max(b["value"] for b in bars) or 1
    cw = int(W * (0.84 if vertical else 0.5))
    bh = int(fl.size * 1.5)
    title = g.get("title", "")
    th = int(ft.size * 1.5) if title else 0
    ch = pad * 2 + th + len(bars) * (bh + fl.size + pad // 2)
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=pad, fill=(12, 12, 16, 215))
    if title:
        d.text((pad, pad), title, font=ft, fill=(255, 255, 255, 255))
    y = pad + th
    inner = cw - pad * 2
    for k, b in enumerate(bars):
        p = ease_out((t - 0.12 * k) / 0.7)
        d.text((pad, y), b["label"], font=fl, fill=(220, 220, 220, 255))
        y += fl.size + 4
        w = max(2, int(inner * 0.82 * b["value"] / vmax * p))
        col = hex_rgb(accent) if b["value"] == vmax else (150, 150, 160, 255)
        d.rounded_rectangle((pad, y, pad + w, y + bh - 6), radius=bh // 4, fill=col)
        dec = 0 if float(b["value"]).is_integer() else 1
        d.text((pad + w + 10, y + (bh - 6) / 2), f"{g.get('prefix', '')}{fmt_number(b['value'] * p, dec)}{g.get('suffix', '')}",
               font=fl, fill=(255, 255, 255, 255), anchor="lm")
        y += bh + pad // 2
    return im


def paint_title(g, t, W, H, F, accent):
    vertical = H > W
    ft = F.get("black", 0.06 if vertical else 0.09)
    fs = F.get("bold", 0.026 if vertical else 0.038)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = wrap(tmp, g.get("title", g.get("text", "")), ft, int(W * 0.86))
    lh = int(ft.size * 1.1)
    sub = g.get("subtitle")
    cw = int(W * 0.92)
    ch = lh * len(lines) + (int(fs.size * 1.8) if sub else 0) + 20
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k, l in enumerate(lines):
        d.text((cw / 2, k * lh), l, font=ft, fill=(255, 255, 255, 255), anchor="ma", stroke_width=max(2, ft.size // 18), stroke_fill=(0, 0, 0, 200))
    if sub:
        d.text((cw / 2, lh * len(lines) + fs.size * 0.5), sub, font=fs, fill=hex_rgb(accent), anchor="ma", stroke_width=2, stroke_fill=(0, 0, 0, 200))
    lw = int(cw * 0.25 * ease_out((t - 0.15) / 0.4))
    if lw > 0:
        d.rectangle((cw / 2 - lw / 2, ch - 8, cw / 2 + lw / 2, ch - 2), fill=hex_rgb(accent))
    return im


def paint_lower_third(g, t, W, H, F, accent):
    vertical = H > W
    base = min(W, H)
    fn = F.get("black", 0.03 if vertical else 0.042)
    fs = F.get("bold", 0.02 if vertical else 0.028)
    pad = int(base * 0.025)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    name, sub = g.get("title", g.get("text", "")), g.get("subtitle", "")
    w = int(max(tmp.textlength(name, font=fn), tmp.textlength(sub, font=fs) if sub else 0)) + pad * 3
    h = int(fn.size * 1.3 + (fs.size * 1.4 if sub else 0) + pad * 1.4)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    reveal = int(w * ease_out(t / 0.35))
    d.rectangle((0, 0, max(0, reveal), h), fill=(12, 12, 16, 225))
    d.rectangle((0, 0, max(6, pad // 3), h), fill=hex_rgb(accent))
    if t > 0.15:
        a = int(255 * ease_out((t - 0.15) / 0.2))
        d.text((pad * 1.6, pad * 0.7), name, font=fn, fill=(255, 255, 255, a))
        if sub:
            d.text((pad * 1.6, pad * 0.7 + fn.size * 1.3), sub, font=fs, fill=hex_rgb(accent, a))
    return im


def paint_callout(g, t, W, H, F, accent):
    vertical = H > W
    f = F.get("black", 0.032 if vertical else 0.048)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text = g.get("text", g.get("title", ""))
    lines = wrap(tmp, text.upper(), f, int(W * 0.7))
    pad = int(f.size * 0.45)
    lh = int(f.size * 1.15)
    w = int(max(tmp.textlength(l, font=f) for l in lines)) + pad * 2
    h = lh * len(lines) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=pad, fill=hex_rgb(accent))
    for k, l in enumerate(lines):
        d.text((w / 2, pad + k * lh), l, font=f, fill=(10, 10, 10, 255), anchor="ma")
    s = 0.6 + 0.4 * ease_out_back(t / 0.25)
    if s < 0.999:
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        im = canvas
    return im


PAINTERS = {"counter": paint_counter, "quote": paint_quote, "bar": paint_bar, "title": paint_title,
            "lower_third": paint_lower_third, "callout": paint_callout}


# ------------------------------------------------------------ placement + sequence

def place(g: dict, size: tuple[int, int], W: int, H: int, safe: dict, face: dict | None, caption_y: float | None) -> tuple[int, int]:
    """Pick a spot inside platform safe zones that avoids the face and the caption band."""
    cw, ch = size
    pos = g.get("position", "auto")
    top = int(H * safe["top"])
    bottom = int(H * (1 - safe["bottom"]))
    left = int(W * safe["left"])
    right = int(W * (1 - safe["right"]))
    if g["type"] == "lower_third":
        return left, bottom - ch - int(H * 0.04)
    if g["type"] == "title" and pos == "auto":
        pos = "center"
    face = face or {}
    if pos == "auto":
        if H > W:
            pos = "top"
            if face.get("cy") is not None:
                fh = face.get("h") or 0.25
                face_top, face_bot = (face["cy"] - fh * 0.75) * H, (face["cy"] + fh * 0.7) * H
                if top + int(H * 0.03) + ch > face_top:
                    low = int((caption_y or (1 - safe["bottom"])) * H - H * 0.06 - ch)
                    if low > face_bot:
                        return (W - cw) // 2, low
        else:
            fx = face.get("cx")
            pos = "right" if (fx is None or fx < 0.5) else "left"
    if pos == "top":
        return (W - cw) // 2, top + int(H * 0.03)
    if pos == "bottom":
        y = bottom - ch
        if caption_y is not None and y + ch > caption_y * H - H * 0.05:
            y = int(caption_y * H - H * 0.06 - ch)
        return (W - cw) // 2, y
    if pos == "center":
        return (W - cw) // 2, (H - ch) // 2
    y = max(top, (H - ch) // 2 - int(H * 0.08))
    if pos == "left":
        return left, y
    return right - cw, y


def render_graphic(g: dict, W: int, H: int, fps: float, dur: float, item_offsets: list[float], out_dir: Path,
                   accent: str, safe: dict, face: dict | None, caption_y: float | None) -> dict:
    """Write frames to out_dir; return overlay info {pattern, x, y, frames}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    F = Fonts(H)
    painter = PAINTERS.get(g["type"])
    n = max(1, int(math.ceil(dur * fps)))
    # measure final size once so placement is stable during animation
    sample = (paint_list(g, dur, W, H, F, accent, item_offsets) if g["type"] == "list" else painter(g, dur, W, H, F, accent))
    cw, ch = sample.size
    rise = int(H * 0.02)
    x, y = place(g, (cw, ch), W, H, safe, face, caption_y)
    prev_key, prev_file = None, None
    for i in range(n):
        t = i / fps
        a_in = ease_out(t / IN_S)
        a_out = min(1.0, max(0.0, (dur - t) / OUT_S))
        alpha = min(a_in, a_out)
        dy = int((1 - a_in) * rise)
        # content changes only while something animates; quantise to reuse frames
        anim_t = t if t < 1.6 or g["type"] == "list" else 1.6
        key = (round(anim_t, 2) if (t < 1.6 or g["type"] == "list") else "hold", round(alpha, 2), dy)
        f = out_dir / f"{i:05d}.png"
        if key == prev_key and prev_file is not None:
            try:
                os.link(prev_file, f)
            except OSError:
                f.write_bytes(prev_file.read_bytes())
            continue
        card = paint_list(g, t, W, H, F, accent, item_offsets) if g["type"] == "list" else painter(g, t, W, H, F, accent)
        if card.size != (cw, ch):
            card = card.resize((cw, ch))
        frame = Image.new("RGBA", (cw, ch + rise), (0, 0, 0, 0))
        if alpha < 1:
            r, gg, b, a = card.split()
            a = a.point(lambda v: int(v * alpha))
            card = Image.merge("RGBA", (r, gg, b, a))
        frame.paste(card, (0, dy))
        frame.save(f, compress_level=1)
        prev_key, prev_file = key, f
    return {"pattern": str(out_dir / "%05d.png"), "x": x, "y": y, "w": cw, "h": ch + rise, "frames": n}
