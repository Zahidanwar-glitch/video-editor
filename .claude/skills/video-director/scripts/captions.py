"""Build styled, word-synced ASS captions on the OUTPUT timeline."""
from __future__ import annotations

import bisect
import re
from pathlib import Path

from common import Piece, find_font, font_family

HARD_FILLERS = {"um", "uh", "erm", "er", "ah", "uhm", "umm", "uhh", "hmm", "mm", "mhm", "eh"}


def ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def output_words(words: list[dict], pieces: list[Piece], src: str, drop_fillers: bool) -> list[dict]:
    """Words on the output timeline. Works per piece, so repeated material (a teased hook) is captioned every time."""
    ws = sorted((w for w in words if not (drop_fillers and re.sub(r"[^\w']+", "", w["w"].lower()) in HARD_FILLERS)),
                key=lambda w: w["start"])
    starts = [w["start"] for w in ws]
    out = []
    for p in pieces:
        if p.src != src:
            continue
        for w in ws[bisect.bisect_left(starts, p.a - 5):bisect.bisect_right(starts, p.b)]:
            mid = (w["start"] + w["end"]) / 2
            if not (p.a <= mid <= p.b):
                continue  # the word was cut (or belongs to a neighbouring piece)
            a = p.out_start + max(w["start"], p.a) - p.a
            b = p.out_start + min(w["end"], p.b) - p.a
            out.append({"w": w["w"], "start": a, "end": max(b, a + 0.05)})
    return sorted(out, key=lambda w: w["start"])


def group_lines(words: list[dict], max_words: int, max_chars: int) -> list[list[dict]]:
    lines: list[list[dict]] = []
    cur: list[dict] = []
    for k, w in enumerate(words):
        if cur:
            chars = len(" ".join(x["w"] for x in cur + [w]))
            gap = w["start"] - cur[-1]["end"]
            if len(cur) >= max_words or chars > max_chars or gap > 0.5:
                lines.append(cur)
                cur = []
        cur.append(w)
        if re.search(r"[.!?,;:]$", w["w"]) and len(cur) >= max(1, max_words // 2):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def build_ass(plan: dict, pieces: list[Piece], words: list[dict], out_path: Path) -> tuple[Path | None, dict]:
    cap = plan.get("captions") or {}
    if not cap.get("enabled") or not words:
        return None, {}
    W, H = plan["output"]["width"], plan["output"]["height"]
    style = cap.get("style", "word_pop")
    font_file = find_font("black", cap.get("font"))
    family = font_family(font_file)
    size = int(H * cap.get("size", 0.05)) if H >= W else int(H * cap.get("size", 0.05) * 1.35)
    color = cap.get("color", "#FFFFFF")
    hi = cap.get("highlight_color", "#FFD400")
    outline = cap.get("outline", 4) * H / 1920 * (1.6 if H < W else 1)
    upper = cap.get("uppercase", False)
    emph = {e.lower().strip(".,!?") for e in cap.get("emphasis_words", [])}
    max_words = cap.get("max_words", 3)
    max_chars = cap.get("max_chars", 22 if H > W else 42)
    x, y = W // 2, int(H * cap.get("position_y", 0.7 if H > W else 0.86))
    border_style = 3 if style == "minimal" else 1
    back = ass_color("#000000", 0x60) if style == "minimal" else ass_color("#000000", 0x80)

    ow = output_words(words, pieces, plan["source"], cap.get("drop_fillers", True))
    lines = group_lines(ow, max_words, max_chars)

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{family},{size},{ass_color(color)},{ass_color(hi)},{ass_color('#000000')},{back},-1,0,0,0,100,100,0,0,{border_style},{outline:.1f},{2 if border_style == 1 else 0},5,{int(W * 0.06)},{int(W * 0.06)},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    timings = []
    for li, line in enumerate(lines):
        nxt_start = lines[li + 1][0]["start"] if li + 1 < len(lines) else line[-1]["end"] + 0.6
        line_end = min(max(line[-1]["end"] + 0.15, line[0]["start"] + 0.4), nxt_start)
        texts = [(_esc(w["w"].upper() if upper else w["w"])) for w in line]
        is_emph = [w["w"].lower().strip(".,!?\"'") in emph for w in line]
        pos = f"\\an5\\pos({x},{y})"
        timings.append({"start": round(line[0]["start"], 3), "end": round(line_end, 3), "text": " ".join(texts)})
        if style in ("line", "minimal"):
            body = " ".join(f"{{\\c{ass_color(hi)}}}{t}{{\\c{ass_color(color)}}}" if e else t for t, e in zip(texts, is_emph))
            events.append(f"Dialogue: 0,{ass_time(line[0]['start'])},{ass_time(line_end)},Cap,,0,0,0,,{{{pos}\\fad(60,60)}}{body}")
            continue
        for k, w in enumerate(line):
            a = w["start"] if k else line[0]["start"]
            b = line[k + 1]["start"] if k + 1 < len(line) else line_end
            if b <= a:
                continue
            parts = []
            for j, t in enumerate(texts):
                active = j == k
                filled = j <= k if style == "karaoke" else active
                c = hi if (filled or is_emph[j]) else color
                if active and style == "word_pop":
                    parts.append(f"{{\\c{ass_color(c)}\\fscx112\\fscy112}}{t}{{\\fscx100\\fscy100}}")
                else:
                    parts.append(f"{{\\c{ass_color(c)}}}{t}")
            intro = "\\fscx85\\fscy85\\t(0,70,\\fscx100\\fscy100)" if k == 0 else ""
            events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{{{pos}{intro}}}" + " ".join(parts))
    out_path.write_text(head + "\n".join(events) + "\n", encoding="utf-8")
    return out_path, {"font_file": font_file, "family": family, "lines": timings, "box": {"y": y, "height": size * 1.4}}
