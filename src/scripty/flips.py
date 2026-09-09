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


# --- independent left-to-right ordering (run 2b) ---------------------------------------------------------------
# Anchored inventories echo the continuity sheet's left/right values on mirrored frames (15 of 16 positions repeated
# in scene030), so lateral evidence has to come from a look that never sees the sheet: one short Flash call per frame
# listing the prominent things from left to right. A mirrored frame reverses that order.
import hashlib
import json
from pathlib import Path

ORDER_PROMPT = """List, from LEFT to RIGHT as seen in this frame, the 3 to 6 most prominent people and large objects.
Use short generic names ('man in dark jacket', 'woman in coat', 'car', 'umbrella', 'lamp post'). Only things whose
horizontal position is unambiguous. JSON: {"left_to_right": ["...", "..."]}"""

CACHE = Path("data/flipsig")


def order_signature(image_path: Path, model: str | None = None) -> list[str]:
    from google.genai import types
    from .gemini import MODEL, client
    key = hashlib.sha1(image_path.read_bytes()).hexdigest()[:16]
    cache = CACHE / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    img = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg")
    last = None
    for attempt in range(3):
        try:
            res = client().models.generate_content(model=model or MODEL, contents=[ORDER_PROMPT, img], config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0, max_output_tokens=512))
            items = [str(x).strip().lower() for x in (json.loads(res.text or "{}").get("left_to_right") or [])][:8]
            CACHE.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(items))
            return items
        except Exception as e:
            last = e
    raise RuntimeError(f"order_signature failed for {image_path.name}: {last}")


def _words(s: str) -> set[str]:
    return {w for w in s.replace("'", "").split() if len(w) > 2 and w not in {"the", "and", "with", "in", "on", "of"}}


def _align(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    pairs = []
    used = set()
    for i, x in enumerate(a):
        best, bj = 0.0, -1
        for j, y in enumerate(b):
            if j in used:
                continue
            wx, wy = _words(x), _words(y)
            s = len(wx & wy) / max(1, len(wx | wy))
            if x == y or x in y or y in x:
                s = 1.0
            if s > best:
                best, bj = s, j
        if bj >= 0 and best >= 0.34:
            pairs.append((i, bj)); used.add(bj)
    return pairs


def reversal(a: list[str], b: list[str]) -> tuple[int, float]:
    """(aligned items, share of aligned item pairs whose left/right order is reversed between the two lists)."""
    pairs = _align(a, b)
    if len(pairs) < 3:
        return len(pairs), 0.0
    rev = tot = 0
    for p in range(len(pairs)):
        for q in range(p + 1, len(pairs)):
            (i1, j1), (i2, j2) = pairs[p], pairs[q]
            tot += 1
            rev += int((i1 - i2) * (j1 - j2) < 0)
    return len(pairs), rev / tot if tot else 0.0


def flip_candidates_llm(project: str, scene: str, reference: str = "A", workers: int = 6, min_items: int = 3, min_reversal: float = 0.75) -> list[dict]:
    import concurrent.futures as cf
    rows = db.query("SELECT take, shot, t_s, frame_id, image_path FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    by_key = {}
    for r in rows:
        by_key.setdefault((int(r["shot"]), round(float(r["t_s"]), 2)), []).append(r)
    pairs = [(a, b) for group in by_key.values() for a in group if a["take"] == reference for b in group if b["take"] != reference]
    need = {r["frame_id"]: Path(r["image_path"]) for a, b in pairs for r in (a, b)}
    sigs: dict[str, list[str]] = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(order_signature, p): fid for fid, p in need.items() if p.exists()}
        for fut in cf.as_completed(futs):
            try:
                sigs[futs[fut]] = fut.result()
            except Exception as e:
                print(f"[flips] {e}", flush=True)
    out = []
    for a, b in pairs:
        sa, sb = sigs.get(a["frame_id"]), sigs.get(b["frame_id"])
        if not sa or not sb:
            continue
        n, rev = reversal(sa, sb)
        if n >= min_items and rev >= min_reversal:
            out.append({"entity": "whole frame", "entity_kind": "screen_direction", "attribute": "orientation", "take_a": a["take"], "frame_a": a["frame_id"], "value_a": "left-to-right: " + ", ".join(sa[:5]),
                        "conf_a": 1.0, "take_b": b["take"], "frame_b": b["frame_id"], "value_b": f"mirror image? left-to-right: {', '.join(sb[:5])} ({n} items aligned, {rev:.0%} reversed)", "conf_b": round(rev, 2),
                        "sql_score": round(rev, 3), "pair_kind": "cross_take"})
    return out


# --- pairwise mirror check (run 2c) ---------------------------------------------------------------------------
# Ordering signatures name things inconsistently across two looks; asking one question about the pair is both
# cheaper and more direct. Every reference frame is compared with the other take's frame at the same moment.
MIRROR_PROMPT = """FRAME A and FRAME B come from two takes of the same scene at the same moment. Compare the compositions.
Answer "mirror" if one frame is a horizontal mirror image of the other (what is on the left of one is on the right of
the other, screen direction reversed, text or asymmetries flipped). Answer "same" if the composition is the same (small
differences in objects, colours or framing are fine). Answer "different" if the camera position or content differs.
JSON: {"relation": "mirror|same|different", "evidence": "one sentence"}"""


def mirror_check(frame_a: Path, frame_b: Path, model: str | None = None) -> dict:
    from google.genai import types
    from .gemini import MODEL, client
    key = hashlib.sha1(frame_a.read_bytes() + b"|" + frame_b.read_bytes()).hexdigest()[:16]
    cache = CACHE / f"pair-{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    parts = [MIRROR_PROMPT, "FRAME A:", types.Part.from_bytes(data=frame_a.read_bytes(), mime_type="image/jpeg"), "FRAME B:", types.Part.from_bytes(data=frame_b.read_bytes(), mime_type="image/jpeg")]
    last = None
    for attempt in range(3):
        try:
            res = client().models.generate_content(model=model or MODEL, contents=parts, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0, max_output_tokens=1024, thinking_config=types.ThinkingConfig(thinking_budget=0)))
            out = json.loads(res.text or "{}")
            out = {"relation": str(out.get("relation", "")).lower().strip(), "evidence": str(out.get("evidence", ""))[:300]}
            CACHE.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(out))
            return out
        except Exception as e:
            last = e
    raise RuntimeError(f"mirror_check failed for {frame_a.name}/{frame_b.name}: {last}")


def flip_candidates_pairwise(project: str, scene: str, reference: str = "A", workers: int = 6) -> list[dict]:
    import concurrent.futures as cf
    rows = db.query("SELECT take, shot, t_s, frame_id, image_path FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    by_key = {}
    for r in rows:
        by_key.setdefault((int(r["shot"]), round(float(r["t_s"]), 2)), []).append(r)
    pairs = [(a, b) for group in by_key.values() for a in group if a["take"] == reference for b in group if b["take"] != reference]
    out = []

    def one(ab):
        a, b = ab
        return a, b, mirror_check(Path(a["image_path"]), Path(b["image_path"]))

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in cf.as_completed([ex.submit(one, ab) for ab in pairs if Path(ab[0]["image_path"]).exists() and Path(ab[1]["image_path"]).exists()]):
            try:
                a, b, res = fut.result()
            except Exception as e:
                print(f"[flips] {e}", flush=True)
                continue
            if res.get("relation") == "mirror":
                out.append({"entity": "whole frame", "entity_kind": "screen_direction", "attribute": "orientation", "take_a": a["take"], "frame_a": a["frame_id"], "value_a": "as shot",
                            "conf_a": 1.0, "take_b": b["take"], "frame_b": b["frame_id"], "value_b": "mirror image (pairwise check: " + res.get("evidence", "")[:120] + ")", "conf_b": 0.9,
                            "sql_score": 0.9, "pair_kind": "cross_take"})
    return out


# --- deterministic mirror test (run 2, final) --------------------------------------------------------------------
# Gemini is mirror-blind: on scene030 all 15 planted A/PLANTED pairs are mirrored by pixel test and Flash answered
# "same" for 14 of them with confident evidence; Pro called the resulting position changes "same" too. So flopped
# shots are detected without a model: compare the other take's frame with the reference frame and with the
# reference frame mirrored, on a blurred 320x180 grayscale. A mirrored take is much closer to the mirrored reference.
def mirror_test(frame_a: Path, frame_b: Path) -> dict:
    import cv2
    import numpy as np
    def prep(p):
        g = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(cv2.resize(g, (320, 180)), (5, 5), 0).astype(np.float32)
    a, b = prep(frame_a), prep(frame_b)
    d_direct = float(np.mean(np.abs(a - b)))
    d_mirror = float(np.mean(np.abs(cv2.flip(a, 1) - b)))
    score = max(0.0, 1.0 - d_mirror / max(d_direct, 1e-6))
    return {"d_direct": round(d_direct, 2), "d_mirror": round(d_mirror, 2), "score": round(score, 3)}


def flip_findings_pixel(project: str, scene: str, reference: str = "A", min_score: float = 0.4) -> list[dict]:
    """Finding-shaped rows (verified=0: the verifier is not consulted because the model cannot see mirroring)."""
    import hashlib as _h
    rows = db.query("SELECT take, shot, t_s, frame_id, image_path FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    by_key = {}
    for r in rows:
        by_key.setdefault((int(r["shot"]), round(float(r["t_s"]), 2)), []).append(r)
    out = []
    for group in by_key.values():
        for a in group:
            if a["take"] != reference:
                continue
            for b in group:
                if b["take"] == reference or not Path(a["image_path"]).exists() or not Path(b["image_path"]).exists():
                    continue
                m = mirror_test(Path(a["image_path"]), Path(b["image_path"]))
                if m["score"] >= min_score:
                    fid = _h.sha1(f"{project}|{scene}|whole frame|orientation|{a['frame_id']}|{b['frame_id']}".encode()).hexdigest()[:12]
                    out.append({"project": project, "scene": scene, "finding_id": fid, "category": "screen_direction", "entity": "whole frame", "attribute": "orientation", "take_a": a["take"], "frame_a": a["frame_id"], "value_a": "as shot",
                                "take_b": b["take"], "frame_b": b["frame_id"], "value_b": "mirror image", "sql_score": m["score"], "verified": 0, "verdict": "continuity_error", "confidence": m["score"],
                                "explanation": f"Deterministic mirror test: the frame is {m['d_mirror']} from the mirrored reference and {m['d_direct']} from the reference itself (blurred 320x180 grayscale, mean abs diff). The verifier is not asked because the model cannot see mirroring."})
    return out
