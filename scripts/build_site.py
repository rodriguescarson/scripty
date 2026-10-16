"""Write site/ — a static snapshot of a running Scripty app, deployable to any static host.

usage: python scripts/build_site.py http://localhost:8080
Frames must already be under site/frames/<project>/<scene>/<take>/; the snapshot rewrites
the app's frame URLs (bucket or /frames/) to that path. The ask-the-agent box is replaced by
a note, since there is no ClickHouse behind a static site.
"""
import json, re, sys, urllib.request
from pathlib import Path

base = sys.argv[1].rstrip("/")
root = Path(__file__).resolve().parents[1]
site = root / "site"
(site / "api" / "scene").mkdir(parents=True, exist_ok=True)


def get(path):
    with urllib.request.urlopen(f"{base}{path}", timeout=120) as r:
        return r.read().decode()


frame_url = re.compile(r'"(?:https://storage\.googleapis\.com/scripty-frames|/frames)/')
scenes = get("/api/scenes")
(site / "api" / "scenes.json").write_text(scenes)
(site / "api" / "eval.json").write_text(get("/api/eval"))
for s in json.loads(scenes):
    d = site / "api" / "scene" / s["project"]
    d.mkdir(parents=True, exist_ok=True)
    body = frame_url.sub('"/frames/', get(f"/api/scene/{s['project']}/{s['scene']}"))
    (d / f"{s['scene']}.json").write_text(body)
    print("scene", s["project"], s["scene"])

h = (root / "src/scripty/static/index.html").read_text()
for a, b in [
    ("fetch('/api/scenes')", "fetch('/api/scenes.json')"),
    ("fetch(`/api/scene/${encodeURIComponent(s.project)}/${encodeURIComponent(s.scene)}`)",
     "fetch(`/api/scene/${encodeURIComponent(s.project)}/${encodeURIComponent(s.scene)}.json`)"),
    ("fetch('/api/eval')", "fetch('/api/eval.json')"),
    ("Reload, or check /api/health.", "Reload."),
]:
    assert a in h, a
    h = h.replace(a, b)
start, end = h.index("async function ask(){"), h.index("$('#askbtn').addEventListener")
h = h[:start] + """async function ask(){
 const q=$('#q').value.trim(); if(!q)return;
 const a=$('#a'); a.hidden=false; a.className='answer warn';
 a.textContent='The agent is retired. During the hackathon this box sent your question to an ADK agent that ran SQL through mcp-clickhouse against the live ClickHouse database; that service is switched off. This page is a static snapshot of the findings and the evaluation. To run the agent yourself, clone github.com/rodriguescarson/scripty and follow the README.';
}
""" + h[end:]
(site / "index.html").write_text(h)
print("wrote", site)
