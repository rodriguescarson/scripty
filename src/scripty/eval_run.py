"""Runs the pre-registered evaluation (docs/EVAL_PLAN.md) over a film and writes docs/eval/<project>.json."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import db
from .analyze import analyze_scene
from .ingest import ingest_frames
from .plant import plant_scene
from .scenes import cluster_scenes, select_eval_scenes
from .shots import sample_frames

OPERATING = {"verdict": "continuity_error", "min_confidence": 0.6}
KIND_MATCH = {"flipped": ("screen_direction", "side", "position", "orientation", "character_position")}


def _matches(finding: dict, label: dict) -> bool:
    if label["planted_kind"] == "flipped":
        return finding["attribute"] in KIND_MATCH["flipped"] or finding["category"] in KIND_MATCH["flipped"]
    ent = label["entity"].lower()
    return any(w in finding["entity"].lower() for w in ent.split() if len(w) > 3) or finding["category"] in ("prop", "set_dressing", "wardrobe")


def run(video: Path, project: str, frames_dir: Path, out_dir: Path, max_scenes: int = 40, every_s: float = 3.0, max_per_shot: int = 3, workers: int = 6, resume: bool = False) -> dict:
    t0 = time.time()
    scenes = select_eval_scenes(cluster_scenes(video), limit=max_scenes)
    db.ensure_schema()
    if not resume:
        db.purge_project(project)
        p = out_dir / f"{project}.progress.jsonl"
        if p.exists():
            p.unlink()
    per_scene = []
    progress = out_dir / f"{project}.progress.jsonl"
    done = {}
    if progress.exists() and resume:
        for line in progress.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["scene"]] = rec
    failures = []
    for sc in scenes:
        scene = f"scene{sc.index:03d}"
        if scene in done:
            per_scene.append(done[scene])
            continue
        try:
            rec = _run_scene(video, project, sc, scene, frames_dir, every_s, max_per_shot, workers)
        except Exception as e:  # one scene must never kill a two-hour run
            failures.append({"scene": scene, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            print(f"{scene}: FAILED {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        per_scene.append(rec)
        out_dir.mkdir(parents=True, exist_ok=True)
        with progress.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    return _summarise(project, video, t0, per_scene, failures, out_dir)


def _run_scene(video, project, sc, scene, frames_dir, every_s, max_per_shot, workers) -> dict:
    if True:
        a_frames = sample_frames(video, sc.shots, frames_dir / project / scene / "A", every_s=every_s, max_per_shot=max_per_shot)
        control, planted, labels = plant_scene(a_frames, frames_dir / project, scene)
        db.insert("eval_labels", [{"project": project, "scene": scene, "take": l.take, "entity": l.entity, "attribute": l.planted_kind, "planted_kind": l.planted_kind, "description": l.description} for l in labels])
        ingest_frames(project, scene, "A", a_frames, workers=workers)
        ingest_frames(project, scene, "CONTROL", control, workers=workers, reference_take="A")
        ingest_frames(project, scene, "PLANTED", planted, workers=workers, reference_take="A")
        findings = analyze_scene(project, scene, verify_top=60, workers=4)
        pos = [f for f in findings if f["verdict"] == OPERATING["verdict"] and f["confidence"] >= OPERATING["min_confidence"]]
        planted_pos = [f for f in pos if {f["take_a"], f["take_b"]} == {"A", "PLANTED"} or "PLANTED" in (f["take_a"], f["take_b"])]
        control_pos = [f for f in pos if {f["take_a"], f["take_b"]} == {"A", "CONTROL"}]
        within_a = [f for f in findings if f["take_a"] == "A" and f["take_b"] == "A"]
        lab = [l.__dict__ for l in labels]
        hits = [any(_matches(f, l) for f in planted_pos) for l in lab]
        tp = sum(1 for f in planted_pos if any(_matches(f, l) for l in lab))
        rec = {"scene": scene, "start_s": sc.start_s, "end_s": sc.end_s, "shots": len(sc.shots), "frames_A": len(a_frames), "labels": lab, "recall_hits": sum(hits), "planted_positives": len(planted_pos), "planted_tp": tp, "control_positives": len(control_pos), "within_A_error_rate": (sum(1 for f in within_a if f["verdict"] == "continuity_error") / len(within_a)) if within_a else None, "findings": findings}
        print(f"{scene}: labels {len(lab)} hits {sum(hits)} | planted positives {len(planted_pos)} tp {tp} | control positives {len(control_pos)}", flush=True)
        return rec


def _summarise(project, video, t0, per_scene, failures, out_dir) -> dict:
    labels_total = sum(len(s["labels"]) for s in per_scene)
    recall = (sum(s["recall_hits"] for s in per_scene) / labels_total) if labels_total else None
    ppos = sum(s["planted_positives"] for s in per_scene)
    precision = (sum(s["planted_tp"] for s in per_scene) / ppos) if ppos else None
    control_fpr = (sum(s["control_positives"] for s in per_scene) / len(per_scene)) if per_scene else None
    by_kind = {}
    for s in per_scene:
        for l, hit in zip(s["labels"], [any(_matches(f, l) for f in [f for f in s["findings"] if f["verdict"] == "continuity_error" and f["confidence"] >= 0.6 and "PLANTED" in (f["take_a"], f["take_b"])]) for l in s["labels"]]):
            k = by_kind.setdefault(l["planted_kind"], {"n": 0, "hit": 0})
            k["n"] += 1
            k["hit"] += int(hit)
    passed = bool(recall is not None and precision is not None and control_fpr is not None and recall >= 0.6 and precision >= 0.5 and control_fpr <= 1.0)
    out = {"project": project, "video": str(video), "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": round(time.time() - t0), "operating_point": OPERATING, "n_scenes": len(per_scene), "n_labels": labels_total, "recall": recall, "precision": precision, "control_fpr_per_scene": control_fpr, "by_kind": by_kind, "pass": passed, "failed_scenes": failures, "per_scene": [{k: v for k, v in s.items() if k != "findings"} for s in per_scene]}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{project}.json").write_text(json.dumps(out, indent=1, default=str))
    try:
        from .durability import backup
        print("backup:", backup(project), flush=True)
    except Exception as e:
        print("backup failed:", str(e)[:200], flush=True)
    return out
