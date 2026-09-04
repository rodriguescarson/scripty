"""Ingest a take: shots → sampled frames → per-frame inventory → ClickHouse rows."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
from pathlib import Path

from . import db
from .inventory import inventory_frame, rows_from_inventory
from .shots import Frame, detect_shots, sample_frames


def frame_id(project: str, scene: str, take: str, shot: int, t_s: float) -> str:
    return hashlib.sha1(f"{project}|{scene}|{take}|{shot}|{t_s:.2f}".encode()).hexdigest()[:12]


def reference_entities(project: str, scene: str, reference_take: str) -> dict[int, list[str]]:
    """Entity names already inventoried for the reference take, per shot — the continuity sheet."""
    rows = db.query("SELECT shot, groupUniqArray(entity) AS ents FROM scripty.inventory FINAL WHERE project = {p:String} AND scene = {s:String} AND take = {t:String} GROUP BY shot", {"p": project, "s": scene, "t": reference_take})
    return {int(r["shot"]): list(r["ents"]) for r in rows}


def ingest_frames(project: str, scene: str, take: str, frames: list[Frame], workers: int = 6, reference_take: str | None = None) -> dict:
    """Inventory a list of already-sampled frames (used by both video takes and planted frame sets).
    With `reference_take`, every frame is inventoried against that take's entity list for the same shot."""
    frame_rows, inv_rows, failures = [], [], []
    refs = reference_entities(project, scene, reference_take) if reference_take else {}

    def one(f: Frame):
        fid = frame_id(project, scene, take, f.shot, f.t_s)
        inv = inventory_frame(f.path, reference=refs.get(f.shot))
        return fid, f, inv

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in cf.as_completed([ex.submit(one, f) for f in frames]):
            try:
                fid, f, inv = fut.result()
            except Exception as e:
                failures.append(str(e)[:200])
                continue
            import cv2
            img = cv2.imread(str(f.path))
            h, w = (img.shape[:2] if img is not None else (0, 0))
            frame_rows.append({"project": project, "scene": scene, "take": take, "shot": f.shot, "t_s": f.t_s, "frame_id": fid, "image_path": str(f.path), "width": w, "height": h})
            rows = rows_from_inventory(inv, project=project, scene=scene, take=take, shot=f.shot, t_s=f.t_s, frame_id=fid)
            from .inventory import normalize_entity
            for r in rows:
                r["entity"] = normalize_entity(r["entity"])
            inv_rows.extend(rows)
    db.ensure_schema()
    db.insert("frames", frame_rows)
    db.insert("inventory", inv_rows)
    return {"frames": len(frame_rows), "inventory_rows": len(inv_rows), "failures": failures}


def ingest_take(project: str, scene: str, take: str, video: Path, frames_dir: Path, every_s: float = 2.0, max_per_shot: int = 6, workers: int = 6) -> dict:
    shots = detect_shots(video)
    frames = sample_frames(video, shots, frames_dir / project / scene / take, every_s=every_s, max_per_shot=max_per_shot)
    out = ingest_frames(project, scene, take, frames, workers=workers)
    out.update({"shots": len(shots), "take": take})
    return out
