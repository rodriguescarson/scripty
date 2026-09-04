"""Scripty web app: scene board, findings with side-by-side evidence, the agent, and the evaluation."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .agent import ask_async

ROOT = Path(__file__).resolve().parents[2]
FRAMES_DIR = Path(os.getenv("SCRIPTY_FRAMES_DIR", ROOT / "data" / "frames"))
FRAMES_BASE_URL = os.getenv("SCRIPTY_FRAMES_BASE_URL", "")  # e.g. https://storage.googleapis.com/scripty-frames
EVAL_DIR = ROOT / "docs" / "eval"

app = FastAPI(title="Scripty")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def frame_url(image_path: str) -> str:
    p = Path(image_path)
    try:
        rel = p.relative_to(FRAMES_DIR)
    except ValueError:
        rel = Path(*p.parts[-4:])
    return f"{FRAMES_BASE_URL}/{rel.as_posix()}" if FRAMES_BASE_URL else f"/frames/{rel.as_posix()}"


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "static" / "index.html").read_text()


@app.get("/frames/{rel:path}")
def frame(rel: str):
    p = (FRAMES_DIR / rel).resolve()
    if not str(p).startswith(str(FRAMES_DIR.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/scenes")
def scenes():
    rows = db.query("""SELECT project, scene, count() AS frames, uniqExact(take) AS takes, uniqExact(shot) AS shots,
                       min(t_s) AS start_s, max(t_s) AS end_s FROM scripty.frames FINAL GROUP BY project, scene ORDER BY project, scene""")
    f = db.query("""SELECT project, scene, countIf(verdict = 'continuity_error' AND confidence >= 0.6) AS errors, count() AS findings FROM scripty.findings FINAL GROUP BY project, scene""")
    fm = {(x["project"], x["scene"]): x for x in f}
    for r in rows:
        r.update({"errors": fm.get((r["project"], r["scene"]), {}).get("errors", 0), "findings": fm.get((r["project"], r["scene"]), {}).get("findings", 0)})
    return rows


@app.get("/api/scene/{project}/{scene}")
def scene(project: str, scene: str):
    frames = db.query("SELECT take, shot, t_s, frame_id, image_path FROM scripty.frames FINAL WHERE project = {p:String} AND scene = {s:String} ORDER BY take, shot, t_s", {"p": project, "s": scene})
    for fr in frames:
        fr["url"] = frame_url(fr.pop("image_path"))
    findings = db.query("SELECT * FROM scripty.findings FINAL WHERE project = {p:String} AND scene = {s:String} ORDER BY (verdict != 'continuity_error'), confidence DESC", {"p": project, "s": scene})
    paths = {fr["frame_id"]: fr["url"] for fr in frames}
    for f in findings:
        f["url_a"] = paths.get(f["frame_a"]); f["url_b"] = paths.get(f["frame_b"])
    labels = db.query("SELECT take, entity, planted_kind, description FROM scripty.eval_labels FINAL WHERE project = {p:String} AND scene = {s:String}", {"p": project, "s": scene})
    inventory_counts = db.query("SELECT take, count() AS rows, uniqExact(entity) AS entities FROM scripty.inventory FINAL WHERE project = {p:String} AND scene = {s:String} GROUP BY take", {"p": project, "s": scene})
    return {"project": project, "scene": scene, "frames": frames, "findings": findings, "labels": labels, "inventory": inventory_counts}


class Ask(BaseModel):
    question: str


@app.post("/api/ask")
async def ask(body: Ask):
    answer, calls = await ask_async(body.question)
    return {"answer": answer, "tool_calls": calls}


@app.get("/api/eval")
def eval_results():
    out = {}
    if EVAL_DIR.exists():
        for p in sorted(EVAL_DIR.glob("*.json")):
            out[p.stem] = json.loads(p.read_text())
    return out


@app.get("/api/health")
def health():
    try:
        v = db.query("SELECT version() AS v")[0]["v"]
        return {"ok": True, "clickhouse": v}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)
