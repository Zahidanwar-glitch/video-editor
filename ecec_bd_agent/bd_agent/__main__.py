"""CLI for the ECEC BD Intelligence Agent.

  python -m bd_agent run [--inbox FILE ...] [--date YYYY-MM-DD] [--weekly]
  python -m bd_agent set-status OPP-XXXXXXXX APPROVED [--note "..."]
  python -m bd_agent list [--top 20]
  python -m bd_agent show OPP-XXXXXXXX
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from . import capture, pipeline
from .store import DATA, load_config, load_db, load_kb, now_ast, save_db


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bd_agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="daily pipeline")
    r.add_argument("--inbox", nargs="*", help="inbox JSON files (default: data/inbox/<date>_*.json)")
    r.add_argument("--date")
    r.add_argument("--weekly", action="store_true", default=None)
    s = sub.add_parser("set-status")
    s.add_argument("id"); s.add_argument("status"); s.add_argument("--note", default="")
    lst = sub.add_parser("list"); lst.add_argument("--top", type=int, default=20)
    sh = sub.add_parser("show"); sh.add_argument("id")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        today = date.fromisoformat(a.date) if a.date else now_ast().date()
        files = [Path(f) for f in a.inbox] if a.inbox else sorted((DATA / "inbox").glob(f"{today.isoformat()}_*.json"))
        res = pipeline.run(files, today, a.weekly)
        print(json.dumps(res, indent=2, default=str))
    elif a.cmd == "set-status":
        db = load_db()
        print(pipeline.set_status(db, a.id, a.status, by="cli", note=a.note))
        opp = db["opportunities"][a.id]
        if a.status.upper() == "APPROVED" and "fit" in opp:
            opp["capture_plan"] = capture.write_capture_plan(opp, load_config(), load_kb(), now_ast().date())
            print("Capture plan:", opp["capture_plan"])
        save_db(db)
    elif a.cmd == "list":
        db = load_db()
        for o in sorted(db["opportunities"].values(), key=lambda o: o.get("priority_rank", 999))[: a.top]:
            if "decision" in o:
                print(f"{o.get('priority_rank', '-'):>3} {o['id']} {o['decision']['recommendation']:<16} fit {o['fit']['score']:>5} "
                      f"risk {o['risk']['score']:>5} win {o['win']['probability']:>5.0%}  {o['status']:<10} {o['project'][:70]}")
    elif a.cmd == "show":
        db = load_db()
        print(json.dumps(db["opportunities"].get(a.id) or db["rejected"].get(a.id), indent=2, default=str))


if __name__ == "__main__":
    main()
