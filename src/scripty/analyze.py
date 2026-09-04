"""Candidates by SQL, verdicts by a second look. Findings are what the supervisor reads."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
from pathlib import Path

from . import db
from .schema import CANDIDATES_SQL
from .verify import verify_pair


def candidates(project: str, scene: str, min_conf: float = 0.5, limit: int = 200) -> list[dict]:
    return db.query(CANDIDATES_SQL, {"project": project, "scene": scene, "min_conf": min_conf, "limit": limit})


def _frame_path(frame_id: str) -> Path:
    rows = db.query("SELECT image_path FROM scripty.frames FINAL WHERE frame_id = {f:String} LIMIT 1", {"f": frame_id})
    if not rows:
        raise KeyError(frame_id)
    return Path(rows[0]["image_path"])


def dedupe(cands: list[dict]) -> list[dict]:
    """One candidate per (entity, attribute, value pair) — the SQL returns every frame pair."""
    seen: set[tuple] = set()
    out = []
    for c in cands:
        key = (c["entity"].lower(), c["attribute"], c["value_a"].lower(), c["value_b"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def analyze_scene(project: str, scene: str, min_conf: float = 0.5, verify_top: int = 40, workers: int = 4, category_map=None) -> list[dict]:
    cands = dedupe(candidates(project, scene, min_conf=min_conf, limit=400))[:verify_top]
    findings = []

    def one(c):
        v = verify_pair(_frame_path(c["frame_a"]), _frame_path(c["frame_b"]), c["entity"], c["attribute"], c["value_a"], c["value_b"])
        return c, v

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in cf.as_completed([ex.submit(one, c) for c in cands]):
            try:
                c, v = fut.result()
            except Exception as e:
                continue
            fid = hashlib.sha1(f"{project}|{scene}|{c['entity']}|{c['attribute']}|{c['frame_a']}|{c['frame_b']}".encode()).hexdigest()[:12]
            findings.append({"project": project, "scene": scene, "finding_id": fid, "category": c["entity_kind"], "entity": c["entity"], "attribute": c["attribute"], "take_a": c["take_a"], "frame_a": c["frame_a"], "value_a": c["value_a"], "take_b": c["take_b"], "frame_b": c["frame_b"], "value_b": c["value_b"], "sql_score": float(c["sql_score"]), "verified": 1, "verdict": v.verdict, "confidence": float(v.confidence), "explanation": v.explanation})
    db.insert("findings", findings)
    return sorted(findings, key=lambda f: (f["verdict"] != "continuity_error", -f["confidence"]))
