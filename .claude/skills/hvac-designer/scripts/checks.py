"""Step C4 - design checks before Gate 3.

1 every room served (conditioned -> supply/unit, wet rooms -> exhaust)
2 no duct crossing a shaft/stair/column left unresolved
3 airflow balance (diffusers = unit, return = unit, OA <= supply, building OA vs exhaust)
4 every item tagged, tags unique
5 every drawn item is in the BOQ
6 unit ESP, refrigerant length/height, diffuser NC, open questions

CLI: python checks.py -w WORK   -> checks.json, checks.md
"""
import argparse

import common as C
import geom as G
import sheet_items as SI


def run(work):
    p = C.project(work)
    rooms = C.load(work, "rooms.json")
    design = C.load(work, "design.json")
    vent = C.load(work, "ventilation.json")
    boq = C.load(work, "boq.json")
    zones = C.load(work, "zones.json")
    log = C.Log(work, "checks")
    res = []

    def add(name, status, detail):
        res.append({"check": name, "status": status, "detail": detail})

    # 1 rooms served
    served = {r for z in design["zones"] for r in z["rooms"]}
    with_diff = {d["room"] for a in design.get("air_systems", []) for d in a["diffusers"]}
    exh = {e["room"] for e in design.get("exhaust_systems", [])}
    miss = []
    for f in G.floors(rooms):
        for r in f["rooms"]:
            st = C.ref("space_types.json")["types"].get(r["space_type"], {})
            if r.get("is_conditioned") and r["id"] not in served:
                miss.append(f"{r['id']} not cooled")
            z = next((z for z in design["zones"] if r["id"] in z["rooms"]), None)
            if z and z["kind"] == "ducted" and r["id"] not in with_diff:
                miss.append(f"{r['id']} in ducted zone but no diffuser")
            if st.get("exhaust") and r["id"] not in exh:
                miss.append(f"{r['id']} needs exhaust")
    add("Every room served", "PASS" if not miss else "FAIL", "; ".join(miss) or
        f"{len(served)} conditioned rooms served, {len(exh)} exhaust rooms; not served by design (stores/shafts): {', '.join(zones['unconditioned']) or 'none'}")

    # 2 conflicts
    conf = [c for a in design.get("air_systems", []) for c in a["conflicts"]]
    add("No duct crossing shaft/stair/column unresolved", "PASS" if not conf else "FAIL",
        "; ".join(f"{c['segment']} x {c['with']}" for c in conf) or "trunk routes chosen clear of shafts, stairs (not served) and columns; beams not on plan - coordinate")

    # 3 balance
    bal = []
    for a in design.get("air_systems", []):
        z = next(z for z in design["zones"] if z["id"] == a["zone"])
        q = z["unit"]["airflow_ls"]
        if abs(a["supply_total_ls"] - q) / q > 0.05:
            bal.append(f"{a['zone']} diffusers {a['supply_total_ls']} vs unit {q} L/s")
        if a["return"]["grille"]["flow_ls"] != q:
            bal.append(f"{a['zone']} return {a['return']['grille']['flow_ls']} vs {q}")
        if z["unit"]["oa_ls"] > q:
            bal.append(f"{a['zone']} OA > supply")
    t = vent["totals"]
    add("Airflows balance", "PASS" if not bal else "FAIL",
        "; ".join(bal) or f"supply = unit airflow in all ducted zones; building OA {t['oa_ls']} L/s vs exhaust {t['exhaust_ls']} L/s (net {t['balance_ls']:+.0f} L/s)")

    # 4 tags
    all_tags = []
    for z in design["zones"]:
        all_tags += [z["unit"]["tag"], z["thermostat"]["tag"]] + ([z["fa_fan"]["tag"]] if z.get("fa_fan") else [])
    all_tags += [o["tag"] for o in design["outdoor_units"]]
    for a in design.get("air_systems", []):
        all_tags += [d["tag"] for d in a["diffusers"]] + [a["return"]["grille"]["tag"]]
        if a.get("fresh_air"):
            all_tags.append(a["fresh_air"]["louver"]["tag"])
    for e in design.get("exhaust_systems", []):
        all_tags += [e["grille"]["tag"], e["fan"]["tag"]] + ([e["discharge"]["tag"]] if e["discharge"].get("tag") else [])
    dup = sorted({x for x in all_tags if all_tags.count(x) > 1})
    untagged = [x for x in all_tags if not x]
    add("All items tagged (unique)", "PASS" if not dup and not untagged else "FAIL", f"{len(all_tags)} tags" + (f"; duplicates {dup}" if dup else ""))

    # 5 drawn in BOQ
    drawn = set()
    for f in rooms["floors"]:
        if not f.get("needs_vision"):
            drawn |= SI.drawn_tags(SI.items_for(f["id"], design, rooms, p["units"]))
    pipe_tags = {x["tag"] for x in design.get("pipes", {}).get("refrigerant", [])} | {x["tag"] for x in design.get("pipes", {}).get("chw", [])}
    missing = sorted(t for t in drawn - set(boq["tags"]) if t not in pipe_tags)
    piped = sorted(t for t in drawn & pipe_tags)
    add("Every drawing item in BOQ", "PASS" if not missing else "FAIL",
        (f"missing: {missing}" if missing else f"{len(drawn)} drawn tags all in BOQ") + (f" (pipe runs {len(piped)} measured by size in section G)" if piped else ""))

    # 6 engineering checks
    esp = [f"{a['zone']} needs {a['esp_required_pa']} Pa > {a['esp_available_pa']} Pa" for a in design.get("air_systems", []) if not a["esp_ok"]]
    add("Unit external static pressure", "PASS" if not esp else "WARN", "; ".join(esp) or "all ducted units have ESP margin")
    rl = [f"{r['tag']} {r['total_m']} m" for r in design.get("pipes", {}).get("refrigerant", []) if not r["ok"]]
    add("Refrigerant length / height limits", "PASS" if not rl else "WARN", "; ".join(rl) or "within generic limits (verify with brand)")
    nc = [f"{d['tag']} NC{d['nc']}" for a in design.get("air_systems", []) for d in a["diffusers"] if d["nc"] is None]
    add("Diffuser noise (NC)", "PASS" if not nc else "WARN", "; ".join(nc) or "all diffusers at or below room NC target")
    oaf = [f"{z['id']} OA {z['unit']['oa_frac']:.0%}" for z in design["zones"] if z["kind"] == "ducted" and z["unit"]["oa_frac"] > p["design"]["ventilation"]["max_oa_fraction_without_pretreat"]]
    add("Fresh-air fraction", "PASS" if not oaf else "WARN", "; ".join(oaf) or "OA fraction within limit for untreated fresh air")
    openq = [q for q in log.questions if not q["answered"]]
    add("Open questions", "PASS" if not openq else "WARN", f"{len(openq)} open - see assumptions.md" if openq else "none")
    C.save(work, "checks.json", {"checks": res})
    md = ["# Design checks", "", C.md_table(["Check", "Status", "Detail"], [[r["check"], r["status"], r["detail"]] for r in res])]
    C.write_text(work, "checks.md", "\n".join(md) + "\n")
    for r in res:
        print(f"  [{r['status']}] {r['check']}: {r['detail'][:110]}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    run(ap.parse_args().work)
