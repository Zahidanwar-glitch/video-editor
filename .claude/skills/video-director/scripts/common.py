"""Shared helpers: ffmpeg wrappers, probing, caching, fonts and timeline mapping."""
from __future__ import annotations

import hashlib
import json
import shutil
from functools import lru_cache
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
STYLES_DIR = SKILL_DIR / "styles"

PLATFORMS = {
    "youtube": {"aspect": "16:9", "width": 1920, "height": 1080, "lufs": -14, "safe": {"top": 0.05, "bottom": 0.10, "left": 0.05, "right": 0.05}},
    "shorts": {"aspect": "9:16", "width": 1080, "height": 1920, "lufs": -14, "safe": {"top": 0.12, "bottom": 0.22, "left": 0.06, "right": 0.14}},
    "reels": {"aspect": "9:16", "width": 1080, "height": 1920, "lufs": -14, "safe": {"top": 0.14, "bottom": 0.25, "left": 0.06, "right": 0.14}},
    "tiktok": {"aspect": "9:16", "width": 1080, "height": 1920, "lufs": -14, "safe": {"top": 0.10, "bottom": 0.25, "left": 0.06, "right": 0.16}},
    "square": {"aspect": "1:1", "width": 1080, "height": 1080, "lufs": -14, "safe": {"top": 0.06, "bottom": 0.10, "left": 0.06, "right": 0.06}},
    "podcast": {"aspect": "16:9", "width": 1920, "height": 1080, "lufs": -16, "safe": {"top": 0.05, "bottom": 0.10, "left": 0.05, "right": 0.05}},
}

# (family, fontconfig weight): 210 black, 205 extrabold, 200 bold, 80 regular
FONT_FAMILIES = ["Montserrat", "Poppins", "Inter", "Roboto", "Open Sans", "DejaVu Sans", "FreeSans", "Arial"]
FONT_WEIGHTS = {"black": [210, 205, 200], "bold": [200, 205], "regular": [80]}


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH. Install FFmpeg (with libass) first.")


def run(cmd: list[str], *, capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=capture, text=True)
    if check and proc.returncode != 0:
        tail = (proc.stderr or "")[-3000:]
        raise FFmpegError(f"Command failed ({proc.returncode}): {' '.join(cmd[:8])} ...\n{tail}")
    return proc


def ffmpeg(args: list[str], **kw) -> subprocess.CompletedProcess:
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args], **kw)


def probe(path: str | Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    info = {"path": str(path), "duration": float(data["format"].get("duration", 0) or 0), "has_audio": a is not None, "has_video": v is not None}
    if v:
        num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
        fps = float(num) / float(den) if float(den) else 30.0
        rfr_num, rfr_den = (v.get("r_frame_rate") or "30/1").split("/")
        rfr = float(rfr_num) / float(rfr_den) if float(rfr_den) else fps
        w, h = int(v["width"]), int(v["height"])
        rotation = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rotation = int(sd["rotation"])
        rotation = int(v.get("tags", {}).get("rotate", rotation) or rotation)
        if abs(rotation) % 180 == 90:
            w, h = h, w
        info.update({"width": w, "height": h, "fps": round(fps, 3), "variable_frame_rate": abs(rfr - fps) > 0.5,
                     "video_codec": v.get("codec_name"), "rotation": rotation})
    if a:
        info.update({"sample_rate": int(a.get("sample_rate", 48000)), "channels": int(a.get("channels", 2)), "audio_codec": a.get("codec_name")})
    return info


def file_fingerprint(path: str | Path, chunk: int = 4 * 1024 * 1024) -> str:
    """Fast content hash: size + first/last chunk. Good enough to key the analysis cache."""
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(p, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk:
            f.seek(max(0, size - chunk))
            h.update(f.read(chunk))
    return h.hexdigest()[:16]


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_style(name: str | None) -> dict:
    if not name:
        name = "clean"
    path = STYLES_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in STYLES_DIR.glob("*.json")))
        raise SystemExit(f"Unknown style '{name}'. Available: {available}")
    return load_json(path)


@lru_cache(maxsize=None)
def find_font(weight: str = "black", preferred: str | None = None) -> str | None:
    """Return a font file path. Tries the preferred family/file first, then common families at the wanted weight."""
    local = SKILL_DIR / "assets" / "fonts"
    if preferred:
        for cand in (Path(preferred), local / preferred, local / f"{preferred}.ttf", local / f"{preferred}.otf"):
            if cand.is_file():
                return str(cand)
    if not shutil.which("fc-match"):
        return None
    families = ([preferred] if preferred else []) + FONT_FAMILIES
    for fam in families:
        for wt in FONT_WEIGHTS.get(weight, FONT_WEIGHTS["bold"]):
            res = run(["fc-match", "-f", "%{family}|%{weight}|%{file}", f"{fam}:weight={wt}"], check=False).stdout.strip()
            parts = res.split("|")
            if len(parts) == 3 and fam.lower() in parts[0].lower() and Path(parts[2]).exists():
                try:
                    if abs(int(parts[1]) - wt) <= 5:
                        return parts[2]
                except ValueError:
                    pass
    res = run(["fc-match", "-f", "%{file}", "sans:bold"], check=False).stdout.strip()
    return res if res and Path(res).exists() else None


@lru_cache(maxsize=None)
def font_family(path: str | None) -> str:
    if path and shutil.which("fc-query"):
        res = run(["fc-query", "-f", "%{family}", path], check=False).stdout.strip()
        if res:
            return res.split(",")[-1].strip()  # most specific name, e.g. "Inter Black"
    return "Sans"


def parse_aspect(aspect: str) -> float:
    a, b = aspect.split(":")
    return float(a) / float(b)


# ---------------------------------------------------------------- timeline

@dataclass
class Piece:
    src: str
    a: float  # source in-point (s)
    b: float  # source out-point (s)
    out_start: float = 0.0
    segment_index: int = 0
    zooms: list = field(default_factory=list)
    reframe_x: float | None = None  # 0..1 horizontal centre for the crop

    @property
    def dur(self) -> float:
        return self.b - self.a


def subtract_ranges(a: float, b: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    parts = [(a, b)]
    for ca, cb in sorted(cuts):
        nxt = []
        for pa, pb in parts:
            if cb <= pa or ca >= pb:
                nxt.append((pa, pb))
                continue
            if ca > pa:
                nxt.append((pa, ca))
            if cb < pb:
                nxt.append((cb, pb))
        parts = nxt
    return parts


def build_pieces(plan: dict, min_piece: float = 0.12) -> list[Piece]:
    default_src = plan["source"]
    cuts_by_src: dict[str, list[tuple[float, float]]] = {}
    for c in plan.get("cuts_removed", []):
        cuts_by_src.setdefault(c.get("src", default_src), []).append((float(c["start"]), float(c["end"])))
    pieces: list[Piece] = []
    t = 0.0
    for i, seg in enumerate(plan["segments"]):
        src = seg.get("src", default_src)
        for pa, pb in subtract_ranges(float(seg["in"]), float(seg["out"]), cuts_by_src.get(src, [])):
            if pb - pa < min_piece:
                continue
            pieces.append(Piece(src=src, a=pa, b=pb, out_start=t, segment_index=i, reframe_x=seg.get("reframe_x")))
            t += pb - pa
    return pieces


def map_time(pieces: list[Piece], src: str, t: float, snap_forward: bool = True) -> float | None:
    """Map a source timestamp to output time. Removed moments snap to the next kept frame."""
    best = None
    for p in pieces:
        if p.src != src:
            continue
        if p.a - 1e-6 <= t <= p.b + 1e-6:
            return p.out_start + (t - p.a)
        if snap_forward and p.a > t and (best is None or p.a < best.a):
            best = p
    if best is not None and best.a - t < 1.0:
        return best.out_start
    return None


def total_duration(pieces: list[Piece]) -> float:
    return sum(p.dur for p in pieces)
