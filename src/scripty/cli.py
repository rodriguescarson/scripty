"""scripty — ingest takes, analyze scenes, run the planted-error evaluation, serve the app."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scripty")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest"); i.add_argument("--project", required=True); i.add_argument("--scene", required=True); i.add_argument("--take", required=True); i.add_argument("video"); i.add_argument("--frames-dir", default="data/frames"); i.add_argument("--every", type=float, default=2.0)
    a = sub.add_parser("analyze"); a.add_argument("--project", required=True); a.add_argument("--scene", required=True); a.add_argument("--top", type=int, default=40)
    s = sub.add_parser("shots"); s.add_argument("video"); s.add_argument("--threshold", type=float, default=0.55)
    ns = ap.parse_args(argv)
    if ns.cmd == "ingest":
        from .ingest import ingest_take
        print(json.dumps(ingest_take(ns.project, ns.scene, ns.take, Path(ns.video), Path(ns.frames_dir), every_s=ns.every), indent=1))
    elif ns.cmd == "analyze":
        from .analyze import analyze_scene
        for f in analyze_scene(ns.project, ns.scene, verify_top=ns.top):
            print(f"{f['verdict']:18} {f['confidence']:.2f} {f['entity']} / {f['attribute']}: {f['value_a']} → {f['value_b']}  [{f['take_a']}→{f['take_b']}]")
    elif ns.cmd == "shots":
        from .shots import detect_shots
        for sh in detect_shots(Path(ns.video), threshold=ns.threshold):
            print(f"shot {sh.index:03d} {sh.start_s:8.2f} → {sh.end_s:8.2f} ({sh.end_s - sh.start_s:5.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
