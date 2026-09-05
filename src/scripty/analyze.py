"""Candidates by SQL, verdicts by a second look. Findings are what the supervisor reads."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
from pathlib import Path

from . import db
from .schema import CANDIDATES_SQL
from .verify import verify_pair


def candidates(project: str, scene: str, min_conf: float = 0.5, limit: int = 200, t_tol: float = 1.5, reference: str = "A") -> list[dict]:
    return db.query(CANDIDATES_SQL, {"project": project, "scene": scene, "min_conf": min_conf, "limit": limit, "t_tol": t_tol, "reference": reference})


def frame_paths(project: str, scene: str) -> dict[str, Path]:
    """All frame paths for a scene in one query — looked up before any thread pool starts."""
    rows = db.query("SELECT frame_id, image_path FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    return {r["frame_id"]: Path(r["image_path"]) for r in rows}


def counterpart_frames(project: str, scene: str) -> dict[tuple, str]:
    """(take, shot, t_s) → frame_id, to resolve the image for an inferred-absence pair (frame_b is empty)."""
    rows = db.query("SELECT take, shot, t_s, frame_id FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    return {(r["take"], int(r["shot"]), round(float(r["t_s"]), 2)): r["frame_id"] for r in rows}


def dedupe(cands: list[dict]) -> list[dict]:
    """One candidate per (entity, attribute, value pair) — the SQL returns every frame pair."""
    seen: set[tuple] = set()
    out = []
    for c in cands:
        key = (c["entity"].lower(), c["attribute"], c["value_a"].lower(), c["value_b"].lower(), c["take_a"], c["take_b"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def analyze_scene(project: str, scene: str, min_conf: float = 0.5, verify_top: int = 80, workers: int = 4, category_map=None, reference: str = "A") -> list[dict]:
    """Verify every cross-take candidate (A vs each other take, same shot and moment) up to `verify_top`;
    cross-shot pairs within a take only fill whatever budget is left."""
    allc = dedupe(candidates(project, scene, min_conf=min_conf, limit=600, reference=reference))
    cross_take = [c for c in allc if c["pair_kind"] == "cross_take"]
    cross_shot = [c for c in allc if c["pair_kind"] != "cross_take"]
    cands = (cross_take + cross_shot)[:verify_top]
    paths = frame_paths(project, scene)  # one query, before any thread starts
    counterpart = counterpart_frames(project, scene)
    shot_t = {r["frame_id"]: (int(r["shot"]), round(float(r["t_s"]), 2)) for r in db.query("SELECT frame_id, shot, t_s FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})}
    for c in cands:
        if not c["frame_b"]:  # inferred absence: the other take's frame at the same shot and moment
            st = shot_t.get(c["frame_a"])
            if st:
                c["frame_b"] = counterpart.get((c["take_b"], st[0], st[1]), "")
    findings: list[dict] = []
    errors: list[str] = []

    def one(c):
        pa, pb = paths.get(c["frame_a"]), paths.get(c["frame_b"])
        if pa is None or pb is None or not pa.exists() or not pb.exists():
            raise FileNotFoundError(f"{c['frame_a']} / {c['frame_b']}")
        v = verify_pair(pa, pb, c["entity"], c["attribute"], c["value_a"], c["value_b"])
        return c, v

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in cf.as_completed([ex.submit(one, c) for c in cands]):
            try:
                c, v = fut.result()
            except Exception as e:
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                continue
            fid = hashlib.sha1(f"{project}|{scene}|{c['entity']}|{c['attribute']}|{c['frame_a']}|{c['frame_b']}".encode()).hexdigest()[:12]
            findings.append({"project": project, "scene": scene, "finding_id": fid, "category": c["entity_kind"], "entity": c["entity"], "attribute": c["attribute"], "take_a": c["take_a"], "frame_a": c["frame_a"], "value_a": c["value_a"], "take_b": c["take_b"], "frame_b": c["frame_b"], "value_b": c["value_b"], "sql_score": float(c["sql_score"]), "verified": 1, "verdict": v.verdict, "confidence": float(v.confidence), "explanation": v.explanation})
    db.insert("findings", findings)
    if errors:
        print(f"[analyze] {project}/{scene}: {len(errors)} verifications failed, e.g. {errors[0]}", flush=True)
    return sorted(findings, key=lambda f: (f["verdict"] != "continuity_error", -f["confidence"]))
