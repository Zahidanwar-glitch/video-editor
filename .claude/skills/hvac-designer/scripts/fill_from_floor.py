"""Gate 1 helper - copy rooms from a reference floor into a floor where they did not read
(typical / mirrored flats, identical floors). Footprints are aligned by their top-left
corner; a room is copied only where the target floor has no room at that spot.

CLI: python fill_from_floor.py -w WORK --target GF --source FF [--all]   (--all = copy every missing room)
Logged as an assumption; the copied rooms carry "copied_from".
"""
import argparse

import common as C
import geom as G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--work", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--source", required=True)
    a = ap.parse_args()
    rooms = C.load(a.work, "rooms.json")
    log = C.Log(a.work, "fill_from_floor")
    fls = {f["id"]: f for f in rooms["floors"]}
    tgt, src = fls[a.target], fls[a.source]
    def origin(f):
        rs = [r for r in f["rooms"] if r["space_type"] not in ("outdoor", "roof")]
        return min(r["bbox_pt"][0] for r in rs), min(r["bbox_pt"][1] for r in rs)
    (sx, sy), (tx, ty) = origin(src), origin(tgt)
    dx, dy = tx - sx, ty - sy
    n = len(tgt["rooms"])
    added = []
    for r in src["rooms"]:
        c = (r["centroid_pt"][0] + dx, r["centroid_pt"][1] + dy)
        if any(G.point_in_poly(c, t["polygon_pt"]) for t in tgt["rooms"]):
            continue
        n += 1
        new = {k: v for k, v in r.items() if k != "id"}
        new["id"] = f"{tgt['id']}-{n:02d}"
        new["copied_from"] = r["id"]
        new["centroid_pt"] = [round(c[0], 2), round(c[1], 2)]
        new["bbox_pt"] = [round(r["bbox_pt"][0] + dx, 2), round(r["bbox_pt"][1] + dy, 2), round(r["bbox_pt"][2] + dx, 2), round(r["bbox_pt"][3] + dy, 2)]
        new["polygon_pt"] = [[round(x + dx, 2), round(y + dy, 2)] for x, y in r["polygon_pt"]]
        new["edges"] = [dict(e, p1=[round(e["p1"][0] + dx, 2), round(e["p1"][1] + dy, 2)], p2=[round(e["p2"][0] + dx, 2), round(e["p2"][1] + dy, 2)]) for e in r["edges"]]
        new["windows"] = [dict(w, at_pt=[round(w["at_pt"][0] + dx, 1), round(w["at_pt"][1] + dy, 1)]) for w in r.get("windows", [])]
        new["height_m"] = tgt["rooms"][0].get("height_m") if tgt["rooms"] else r.get("height_m")
        new["floor_to_floor_m"] = tgt["rooms"][0].get("floor_to_floor_m") if tgt["rooms"] else r.get("floor_to_floor_m")
        tgt["rooms"].append(new)
        added.append(f"{new['id']} {new['name']} ({r['id']})")
    for q in list(log.questions):
        if q["key"] == f"unnamed_{tgt['page']}":
            pass
    log.add("Gate1", f"fill_{tgt['id']}", f"{tgt['name']}: {len(added)} rooms copied from {src['name']} where the plan did not read (typical flats): {', '.join(added)}", "user instruction", confirm=True)
    C.save(a.work, "rooms.json", rooms)
    log.save()
    print(f"{tgt['id']}: added {len(added)} rooms from {src['id']}")


if __name__ == "__main__":
    main()
