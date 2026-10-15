"""Shared helpers: reference data, project files, assumption log, open questions,
psychrometrics and display units. No design values live here - they are all in
../references and are read through ref()."""
import csv
import json
import math
import os
import re
from datetime import date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(SKILL_DIR, "references")
_cache = {}


# ---------------------------------------------------------------- files
def ref(name):
    """Load a reference file (json or csv) by file name."""
    if name not in _cache:
        path = os.path.join(REF_DIR, name)
        if name.endswith(".csv"):
            with open(path, newline="", encoding="utf-8") as f:
                _cache[name] = list(csv.DictReader(f))
        else:
            with open(path, encoding="utf-8") as f:
                _cache[name] = json.load(f)
    return _cache[name]


def load(work, name, default=None):
    path = os.path.join(work, name)
    if not os.path.exists(path):
        if default is not None:
            return default
        raise SystemExit(f"Missing {path} - run the previous step first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(work, name, data):
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def write_text(work, name, text):
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def source_pdf(work, rooms):
    """rooms.json stores the plan path relative to the work dir (portable)."""
    p = rooms["source_pdf"]
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(work, p))


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------- assumptions / questions
class Log:
    """assumptions.json + assumptions.md and open_questions.json in the work dir.
    Every default or inference a script uses must go through add()."""

    def __init__(self, work, src=None):
        """src = the calling script; its earlier (unanswered) entries are dropped so a re-run starts clean."""
        self.work, self.src = work, src
        self.items = [i for i in load(work, "assumptions.json", default={"items": []})["items"] if not src or i.get("src") != src]
        self.questions = [q for q in load(work, "open_questions.json", default={"items": []})["items"]
                          if not src or q.get("src") != src or q["answered"]]
        # answers the user gave to earlier questions: project.json {"answers": {key: "text"}}
        self.answers = load(work, "project.json", default={}).get("answers", {})
        for q in self.questions:  # answers given later in project.json close stored questions
            if q["key"] in self.answers and not q["answered"]:
                q["answered"] = True
                self.add(q["step"], f"answer_{q['key']}", f"{q['question']} -> USER ANSWER: {self.answers[q['key']]}", "user", confirm=False)

    def add(self, step, key, text, source="", confirm=False):
        for it in self.items:
            if it["key"] == key:
                it.update(text=text, source=source, confirm=confirm, step=step)
                break
        else:
            self.items.append({"id": "", "step": step, "key": key, "src": self.src,
                               "text": text, "source": source, "confirm": confirm})

    def ask(self, step, key, question, why=""):
        if key in self.answers:
            self.add(step, f"answer_{key}", f"{question} -> USER ANSWER: {self.answers[key]}", "user", confirm=False)
            return
        if not any(q["key"] == key for q in self.questions):
            self.questions.append({"id": "", "step": step, "key": key, "src": self.src,
                                   "question": question, "why": why, "answered": False})

    def resolve(self, key):
        for q in self.questions:
            if q["key"] == key:
                q["answered"] = True

    def save(self):
        for i, it in enumerate(self.items, 1):
            it["id"] = f"A{i:03d}"
        for i, q in enumerate(self.questions, 1):
            q["id"] = f"Q{i:03d}"
        save(self.work, "assumptions.json", {"items": self.items})
        save(self.work, "open_questions.json", {"items": self.questions})
        lines = ["# Assumptions log", "",
                 f"Generated {date.today().isoformat()}. Items marked **confirm** need the engineer's confirmation.", "",
                 "| ID | Step | Assumption | Source | Status |", "|---|---|---|---|---|"]
        for it in self.items:
            st = "**confirm**" if it["confirm"] else "default"
            lines.append(f"| {it['id']} | {it['step']} | {it['text']} | {it['source']} | {st} |")
        open_q = [q for q in self.questions if not q["answered"]]
        if open_q:
            lines += ["", "## Open questions", ""]
            lines += [f"- **{q['id']}** ({q['step']}): {q['question']} {q['why']}" for q in open_q]
        write_text(self.work, "assumptions.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------- project & code set
def code_set_for(country):
    tbl = ref("codes_by_country.json")
    return tbl["country_to_code_set"].get(country.strip().lower(), "DEFAULT")


def climate_for(city, country):
    for row in ref("climate_data.csv"):
        if row["city"].lower() == city.strip().lower() and row["country"].lower() == country.strip().lower():
            return {k: (float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v) for k, v in row.items()}
    for row in ref("climate_data.csv"):
        if row["city"].lower() == city.strip().lower():
            return {k: (float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v) for k, v in row.items()}
    return None


def project(work):
    """project.json merged with design defaults. Records which defaults were used."""
    p = load(work, "project.json")
    p["design"] = deep_merge(ref("design_defaults.json"), p.get("design", {}))
    cs = p["project"].get("code_set") or code_set_for(p["project"]["location"]["country"])
    p["project"]["code_set"] = cs
    p["codes"] = ref("codes_by_country.json")["code_sets"][cs]
    p["units"] = p["project"].get("units") or p["codes"]["units"]
    return p


def clause(p, rule):
    return p["codes"]["clauses"].get(rule, "designer judgement")


def building_class(p):
    return "residential" if p["project"]["building_type"] in ("villa", "house", "apartment", "residential") else "non_residential"


# ---------------------------------------------------------------- psychrometrics (SI)
def p_atm_kpa(elev_m):
    return 101.325 * (1 - 2.25577e-5 * elev_m) ** 5.2559


def p_ws_kpa(t):
    """Saturation pressure over water, kPa (Magnus-Tetens, adequate 0-60 C)."""
    return 0.61094 * math.exp(17.625 * t / (t + 243.04))


def w_from_rh(t, rh_pct, p):
    pw = rh_pct / 100 * p_ws_kpa(t)
    return 0.622 * pw / (p - pw)


def w_from_wb(tdb, twb, p):
    ws = 0.622 * p_ws_kpa(twb) / (p - p_ws_kpa(twb))
    return ((2501 - 2.326 * twb) * ws - 1.006 * (tdb - twb)) / (2501 + 1.86 * tdb - 4.186 * twb)


def air_factors(elev_m):
    """Sensible (W per L/s.K) and latent (W per L/s per kg/kg) factors at site pressure."""
    r = p_atm_kpa(elev_m) / 101.325
    return 1.23 * r, 3010.0 * r


# ---------------------------------------------------------------- display units
class Units:
    def __init__(self, system):
        self.sys = system
        self.t = ref("units.json")[system]

    def _c(self, kind, v):
        u, f = self.t[kind]
        return v * f, u

    def flow(self, ls, d=0):
        v, u = self._c("flow", ls)
        return f"{v:,.{d}f} {u}"

    def power(self, kw, d=1):
        if self.sys == "IP":
            return f"{kw * 3412.14:,.0f} Btu/h"
        return f"{kw:,.{d}f} kW"

    def size(self, mm):
        if self.sys == "IP":
            return f"{mm * 0.0393701:.0f}\""
        return f"{mm:.0f}"

    def rect(self, w, h):
        if self.sys == "IP":
            return f"{w * 0.0393701:.0f}\"x{h * 0.0393701:.0f}\""
        return f"{w:.0f}x{h:.0f}"

    def length(self, m, d=1):
        v, u = self._c("length", m)
        return f"{v:,.{d}f} {u}"

    def area(self, m2, d=1):
        v, u = self._c("area", m2)
        return f"{v:,.{d}f} {u}"

    def temp(self, c, d=1):
        return f"{c * 9 / 5 + 32:.{d}f} °F" if self.sys == "IP" else f"{c:.{d}f} °C"

    def pa(self, pa, d=0):
        if self.sys == "IP":
            return f"{pa * 0.00401463:.2f} in.wg"
        return f"{pa:.{d}f} Pa"

    def fric(self, pam):
        if self.sys == "IP":
            return f"{pam * 0.122367:.3f} in/100ft"
        return f"{pam:.2f} Pa/m"

    def vel(self, ms):
        if self.sys == "IP":
            return f"{ms * 196.85:.0f} fpm"
        return f"{ms:.2f} m/s"

    def u_val(self, u):
        return f"{u * 0.17611:.3f} Btu/h·ft²·°F" if self.sys == "IP" else f"{u:.2f} W/m²K"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


ORIENTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def orient_from_bearing(deg):
    return ORIENTS[int(((deg % 360) + 22.5) // 45) % 8]
