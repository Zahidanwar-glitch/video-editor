"""Persistence: JSON database, de-duplication and the append-only audit log."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

AST = timezone(timedelta(hours=3), "AST")

STATUSES = [
    "NEW", "QUALIFIED", "UNDER REVIEW", "APPROVED", "IN PURSUIT", "SUBMITTED",
    "WON", "LOST", "NO BID", "CANCELLED", "CLOSED", "REJECTED",
]
TERMINAL = {"WON", "LOST", "NO BID", "CANCELLED", "CLOSED", "REJECTED"}


def now_ast() -> datetime:
    return datetime.now(AST)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    tmp.replace(path)


def load_config() -> dict:
    return load_json(CONFIG / "scoring_config.json", {})


def config_hash() -> str:
    raw = (CONFIG / "scoring_config.json").read_bytes()
    return hashlib.sha256(raw).hexdigest()[:12]


def load_kb() -> dict:
    return load_json(DATA / "knowledge_base.json", {})


def load_db() -> dict:
    return load_json(DATA / "opportunities.json", {"opportunities": {}, "rejected": {}})


def save_db(db: dict) -> None:
    save_json(DATA / "opportunities.json", db)


def audit(event: str, **fields) -> None:
    """Append-only, one JSON object per line. Never rewrite this file."""
    rec = {"ts": now_ast().isoformat(timespec="seconds"), "event": event, **fields}
    path = DATA / "audit_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------- de-duplication

_STOP = {
    "the", "and", "of", "for", "to", "in", "a", "an", "project", "projects", "services",
    "service", "consultancy", "consulting", "consultant", "works", "package", "phase",
    "contract", "tender", "rfp", "eoi", "ksa", "saudi", "arabia", "uae", "qatar", "–", "-",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOP and len(w) > 1}


def opp_id(item: dict) -> str:
    key = f"{item.get('country','')}|{item.get('client','')}|{item.get('project','')}".lower()
    return "OPP-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()


_REF = re.compile(r"\b(?:[A-Z]{2,}(?:[/-][A-Z0-9]+){2,}|\d{6,})\b")


def tender_refs(item: dict) -> set[str]:
    """Tender reference numbers (e.g. PWA/STC/25/2026, DMT-RFP-26-049, 2122600157)."""
    return set(_REF.findall(f"{item.get('project', '')} {item.get('description', '')}"))


def similarity(a: dict, b: dict) -> float:
    if (a.get("country") or "").lower() != (b.get("country") or "").lower():
        return 0.0
    ra, rb = tender_refs(a), tender_refs(b)
    if ra and rb:
        return 1.0 if ra & rb else 0.0  # distinct tender numbers are never duplicates
    ta = _tokens(a.get("project", "")) | _tokens(a.get("client", ""))
    tb = _tokens(b.get("project", "")) | _tokens(b.get("client", ""))
    if not ta or not tb:
        return 0.0
    jac = len(ta & tb) / len(ta | tb)
    # shared portal/list URLs are common, so the same source only confirms a likely match
    if a.get("source") and a.get("source") == b.get("source") and jac >= 0.35:
        return 1.0
    return jac


def find_duplicate(item: dict, existing: dict, threshold: float = 0.6) -> str | None:
    best_id, best = None, 0.0
    for oid, rec in existing.items():
        s = similarity(item, rec)
        if s > best:
            best_id, best = oid, s
    return best_id if best >= threshold else None
