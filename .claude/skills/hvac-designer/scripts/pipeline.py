"""Run the hvac-designer steps by stage and write the gate summaries.

  python pipeline.py read    -w WORK --pdf PLAN.pdf   # Step A  -> Gate 1 (gate1_rooms.md + previews)
  python pipeline.py design  -w WORK                  # Step B  -> Gate 2 (gate2_summary.md)
  python pipeline.py outputs -w WORK                  # Step C  -> Gate 3 (gate3_summary.md, sheets, DXF, BOQ, checks)
  python pipeline.py report  -w WORK                  # final report (Word + PDF) and deliverables list
  python pipeline.py all     -w WORK --pdf PLAN.pdf   # everything, no stops (tests only)
"""
import argparse
import os
import shutil
import subprocess
import sys

import common as C

HERE = os.path.dirname(os.path.abspath(__file__))


def step(script, *args):
    print(f"\n== {script}")
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *args], cwd=HERE)
    if r.returncode:
        raise SystemExit(f"{script} stopped (exit {r.returncode}) - read the message above, ask the user, fix inputs, re-run this stage.")


def open_q(work):
    return [q for q in C.load(work, "open_questions.json", default={"items": []})["items"] if not q["answered"]]


def gate2(work):
    p = C.project(work)
    U = C.Units(p["units"])
    L = C.load(work, "loads.json")
    D = C.load(work, "design.json")
    V = C.load(work, "ventilation.json")
    s = L["summary"]
    out = ["# Gate 2 - loads, equipment and sizing (please review)", "",
           f"Block cooling peak **{U.power(s['block_peak_kw'])}** at {s['block_peak_hour']}:00 over {s['conditioned_area_m2']} m² "
           f"({s['block_peak_kw'] * 1000 / max(1, s['conditioned_area_m2']):.0f} W/m²); heating {U.power(s['heating_kw'])}. "
           f"Safety factor {D['sf_cooling']:.0%} applied at selection; T3 derate x{D['derate']}.", "", "## Room loads", ""]
    out.append(C.md_table(["Room", "Name", "Sens W", "Lat W", "Total W", "W/m²", "Peak", "Supply"],
                          [[r["id"], r["name"], r["sensible_w"], r["latent_w"], r["total_w"], r["w_per_m2"], f"{r['peak_hour']}:00", U.flow(r["supply_ls"])] for r in L["rooms"] if r["conditioned"]]))
    out += ["", "## Zones and equipment", ""]
    out.append(C.md_table(["Zone", "Rooms", "System", "Required", "Selected", "Derated", "Airflow", "OA", "Host"],
                          [[z["id"], ", ".join(z["rooms"]), z["system"], U.power(z["unit"]["req_total_kw"]), f"{z['unit']['tag']} {z['unit']['model']}",
                            U.power(z["unit"]["derated_kw"]), U.flow(z["unit"]["airflow_ls"]), f"{U.flow(z['unit']['oa_ls'])} ({z['unit']['oa_frac']:.0%})", z["unit"]["host_room"]] for z in D["zones"]]))
    out.append("")
    out.append(C.md_table(["Outdoor", "Model", "Serves", "Capacity"], [[o["tag"], o["model"], ", ".join(o["serves"]), U.power(o["cool_kw"])] for o in D["outdoor_units"]]))
    out += ["", f"Ventilation: OA {U.flow(V['totals']['oa_ls'])}, exhaust {U.flow(V['totals']['exhaust_ls'])}.", "", "## Duct sizing (mains and branches)", ""]
    rows = []
    for a in D.get("air_systems", []):
        for sg in a["segments"]:
            if sg["kind"] in ("main", "branch", "riser"):
                rows.append([a["zone"], sg["id"], sg["kind"], U.flow(sg["flow_ls"]), U.rect(sg["w_mm"], sg["h_mm"]), U.vel(sg["velocity_m_s"]), U.fric(sg["friction_pa_m"])])
        rows.append([a["zone"], "ESP", "", "", f"req {a['esp_required_pa']} / avail {a['esp_available_pa']} Pa", "", ""])
    out.append(C.md_table(["Zone", "Segment", "Type", "Flow", "Size", "Velocity", "Friction"], rows))
    out += ["", "## Diffusers", ""]
    out.append(C.md_table(["Tag", "Room", "Model", "Flow", "NC"], [[d["tag"], d["room"], d["model"], U.flow(d["flow_ls"]), d["nc"]] for a in D.get("air_systems", []) for d in a["diffusers"]]))
    out += ["", "## Piping", ""]
    out.append(C.md_table(["Run", "Liquid/Gas mm", "Length m", "Status"], [[r["tag"], f"{r['liquid_mm']}/{r['gas_mm']}", r["total_m"], "OK" if r["ok"] else "CHECK"] for r in D["pipes"]["refrigerant"]]))
    out.append("")
    out.append(C.md_table(["Drain", "To", "Ø mm", "Length m"], [[c["tag"], c["to"], c["dn_mm"], c["length_m"]] for c in D["pipes"]["condensate"]]))
    q = open_q(work)
    if q:
        out += ["", "## Open questions", ""] + [f"- {x['id']}: {x['question']}" for x in q]
    C.write_text(work, "gate2_summary.md", "\n".join(out) + "\n")
    print(f"\nGATE 2: review {os.path.join(work, 'gate2_summary.md')} ({len(q)} open questions)")


def gate3(work):
    B = C.load(work, "boq.json")
    S = C.load(work, "sheets.json")
    K = C.load(work, "checks.json")
    out = ["# Gate 3 - drawings, BOQ and checks (please review before final export)", "", "## Sheets", ""]
    out.append(C.md_table(["Sheet", "Floor", "Tagged items", "Preview"], [[s["sheet"], s["floor"] or "controls", len(s["tags"]), f"out/preview_{s['sheet']}.png"] for s in S["sheets"]]))
    out += ["", "DXF: " + ", ".join(sorted(f for f in os.listdir(os.path.join(work, "out")) if f.endswith(".dxf"))), "", "## BOQ summary (quantities only)", ""]
    rows = []
    for sec in B["sections"]:
        tot = {}
        for r in sec["rows"]:
            tot[r["unit"]] = tot.get(r["unit"], 0) + r["qty"]
        rows.append([sec["title"], len(sec["rows"]), ", ".join(f"{v:.1f} {u}" for u, v in tot.items())])
    out.append(C.md_table(["Section", "Lines", "Totals (before allowance)"], rows))
    out += ["", "## Checks", "", C.md_table(["Check", "Status", "Detail"], [[c["check"], c["status"], c["detail"]] for c in K["checks"]])]
    C.write_text(work, "gate3_summary.md", "\n".join(out) + "\n")
    print(f"\nGATE 3: review {os.path.join(work, 'gate3_summary.md')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["read", "design", "outputs", "report", "all"])
    ap.add_argument("-w", "--work", required=True)
    ap.add_argument("--pdf")
    ap.add_argument("--scale")
    ap.add_argument("--north")
    a = ap.parse_args()
    w = os.path.abspath(a.work)
    if a.stage in ("read", "all"):
        if not a.pdf:
            raise SystemExit("--pdf is required for the read stage")
        extra = (["--scale", a.scale] if a.scale else []) + (["--north", a.north] if a.north else [])
        step("pdf_reader.py", os.path.abspath(a.pdf), "-w", w, *extra)
        print(f"\nGATE 1: review {os.path.join(w, 'gate1_rooms.md')} and gate1_*.png ({len(open_q(w))} open questions)")
    if a.stage in ("design", "all"):
        for s in ("loads.py", "zoning.py", "ventilation.py", "equipment_select.py", "duct_sizing.py", "pipe_sizing.py"):
            step(s, "-w", w)
        gate2(w)
    if a.stage in ("outputs", "all"):
        for s in ("drawing_overlay.py", "dxf_export.py", "boq.py", "checks.py"):
            step(s, "-w", w)
        gate3(w)
    if a.stage in ("report", "all"):
        step("report.py", "-w", w)
        shutil.copy(os.path.join(w, "assumptions.md"), os.path.join(w, "out", "assumptions.md"))
        print("\nDeliverables in", os.path.join(w, "out"))
        for f in sorted(os.listdir(os.path.join(w, "out"))):
            if not f.startswith("preview_"):
                print("  ", f)


if __name__ == "__main__":
    main()
