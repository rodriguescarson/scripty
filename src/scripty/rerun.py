"""Run 2 (post-hoc): re-inventory the CONTROL and PLANTED takes of every completed run-1 scene against the full
attribute sheet, then re-verify with the v2 candidates. Reference-take (A) inventories and every frame image are
reused unchanged; labels are the run-1 labels. Results land under a new project name so run 1 stays intact.

Usage: python -m scripty.rerun <src_project> <dst_project> [--scenes scene030,scene007] [--verify-top 90]"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import db
from .analyze import analyze_scene
from .ingest import ingest_frames
from .shots import Frame


def copy_rows(table: str, src: str, dst: str, scene: str, where: str = "") -> int:
    rows = db.query(f"SELECT * FROM scripty.{table} FINAL WHERE project = {{p:String}} AND scene = {{s:String}} {where}", {"p": src, "s": scene})
    for r in rows:
        r["project"] = dst
        r.pop("created_at", None)
    db.insert(table, rows)
    return len(rows)


def rerun_scene(src: str, dst: str, rec: dict, verify_top: int, workers: int, reuse_inventory: bool = False) -> dict:
    scene = rec["scene"]
    t0 = time.time()
    have = db.query("SELECT count() AS n FROM scripty.inventory FINAL WHERE project = {p:String} AND scene = {s:String} AND take = 'PLANTED'", {"p": dst, "s": scene})[0]["n"] if reuse_inventory else 0
    ing = {"CONTROL": {"inventory_rows": 0, "failures": []}, "PLANTED": {"inventory_rows": 0, "failures": []}}
    if have:
        n_frames = n_inv = 0
        db.client().command("ALTER TABLE scripty.findings DELETE WHERE project = %(p)s AND scene = %(s)s", parameters={"p": dst, "s": scene})
    else:
        n_frames = copy_rows("frames", src, dst, scene)
        n_inv = copy_rows("inventory", src, dst, scene, "AND take = 'A'")
        # frames come from the planted files on disk, not run 1's frames table: run 1 silently dropped every frame
        # whose inventory call failed (scene030: 16 of 36 PLANTED frames), so its table is not the full planted set
        a_dir = Path(db.query("SELECT any(image_path) AS p FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String} AND take = 'A'", {"p": src, "s": scene})[0]["p"]).parent
        for take in ("CONTROL", "PLANTED"):
            fl = [Frame(shot=int(f.name[4:7]), t_s=float(f.name[9:16]), path=f) for f in sorted((a_dir.parent / take).glob("shot*_t*.jpg"))]
            ing[take] = ingest_frames(dst, scene, take, fl, workers=workers, reference_take="A", reference_mode="v2")
            ing[take]["frames_on_disk"] = len(fl)
    findings = analyze_scene(dst, scene, verify_top=verify_top, workers=4, version=2)
    pos = lambda t: [f for f in findings if f["verdict"] == "continuity_error" and f["confidence"] >= 0.6 and {f["take_a"], f["take_b"]} == {"A", t}]
    out = {k: rec[k] for k in ("scene", "start_s", "end_s", "shots", "frames_A", "labels") if k in rec}
    out.update({"run": 2, "reinventoried": {t: ing[t]["inventory_rows"] for t in ing}, "inventory_failures": sum(len(ing[t]["failures"]) for t in ing),
                "planted_positives": len(pos("PLANTED")), "control_positives": len(pos("CONTROL")), "findings": findings, "seconds": round(time.time() - t0, 1), "copied": {"frames": n_frames, "inventory_A": n_inv}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--scenes", default=""); ap.add_argument("--verify-top", type=int, default=90); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--reuse-inventory", action="store_true", help="skip copy/re-inventory when the destination already has the scene's PLANTED rows; re-verify only")
    a = ap.parse_args()
    db.ensure_schema()
    recs = [json.loads(l) for l in (Path("docs/eval") / f"{a.src}.progress.jsonl").read_text().splitlines() if l.strip()]
    want = set(a.scenes.split(",")) if a.scenes else None
    prog = Path("docs/eval") / f"{a.dst}.progress.jsonl"
    done = {json.loads(l)["scene"] for l in prog.read_text().splitlines() if l.strip()} if (a.resume and prog.exists()) else set()
    if not a.resume and prog.exists():
        prog.unlink()
    for rec in recs:
        if (want and rec["scene"] not in want) or rec["scene"] in done:
            continue
        try:
            out = rerun_scene(a.src, a.dst, rec, a.verify_top, a.workers, reuse_inventory=a.reuse_inventory)
        except Exception as e:  # keep going; the scene is listed as failed
            print(f"{rec['scene']}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
            continue
        with prog.open("a") as fh:
            fh.write(json.dumps(out) + "\n")
        print(f"{out['scene']}: labels {len(out.get('labels', []))} | planted positives {out['planted_positives']} | control positives {out['control_positives']} | {out['seconds']}s", flush=True)
    from .durability import backup
    backup(a.dst)


if __name__ == "__main__":
    main()
