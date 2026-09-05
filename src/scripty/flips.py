"""Flopped-shot detector (run 2). A mirrored frame reverses the left/right order of everything in it, so instead of
hoping one entity's coarse position change survives verification, compare the lateral side of every entity the two
takes agree on and flag the frame pair when most of them swapped. Candidates go through the same visual verifier."""
from __future__ import annotations

from . import db

LEFT = ("top-left", "middle-left", "bottom-left", "camera-left")
RIGHT = ("top-right", "middle-right", "bottom-right", "camera-right")


def _side(value: str) -> str | None:
    v = value.lower().split(" on ")[0].strip()
    if v in LEFT:
        return "L"
    if v in RIGHT:
        return "R"
    return None


def flip_candidates(project: str, scene: str, reference: str = "A", min_lateral: int = 2, min_share: float = 0.8) -> list[dict]:
    rows = db.query("""SELECT take, shot, t_s, frame_id, entity, attribute, value, confidence FROM scripty.inventory FINAL
        WHERE project = {p:String} AND scene = {s:String} AND attribute IN ('position','side') AND confidence >= 0.5""", {"p": project, "s": scene})
    by_frame: dict[tuple, dict[str, str]] = {}
    meta: dict[tuple, tuple] = {}
    for r in rows:
        side = _side(r["value"])
        if side is None:
            continue
        key = (r["take"], int(r["shot"]), round(float(r["t_s"]), 2))
        by_frame.setdefault(key, {})[r["entity"]] = side
        meta[key] = (r["frame_id"], r["take"])
    out = []
    for key, sides_a in by_frame.items():
        if key[0] != reference:
            continue
        for other, sides_b in by_frame.items():
            if other[0] == reference or other[1:] != key[1:]:
                continue
            common = [e for e in sides_a if e in sides_b]
            if len(common) < min_lateral:
                continue
            swapped = sum(1 for e in common if sides_a[e] != sides_b[e])
            if swapped >= min_lateral and swapped / len(common) >= min_share:
                out.append({"entity": "whole frame", "entity_kind": "screen_direction", "attribute": "orientation", "take_a": key[0], "frame_a": meta[key][0], "value_a": "as shot",
                            "conf_a": 1.0, "take_b": other[0], "frame_b": meta[other][0], "value_b": f"mirror image ({swapped} of {len(common)} left/right positions swapped)", "conf_b": round(swapped / len(common), 2),
                            "sql_score": round(swapped / len(common), 3), "pair_kind": "cross_take"})
    return out
