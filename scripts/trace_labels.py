"""For each non-flip planted label of a scene, show what the pipeline saw at every stage: inventory rows in A and
PLANTED at that shot (entity-word match), v2 candidates mentioning it, and findings with verdicts.
Usage: python scripts/trace_labels.py <project> <scene> [labels_project]"""
import json, sys
from pathlib import Path
from scripty import db
from scripty.analyze import candidates, dedupe

P, S = sys.argv[1], sys.argv[2]
LP = sys.argv[3] if len(sys.argv) > 3 else "charade"
labs = json.load(open(f"data/frames/{LP}/{S}/labels.json"))
STOP = {"the", "and", "with", "left", "right", "whole", "frame"}
words = lambda s: {w for w in s.lower().replace("(", " ").replace(")", " ").replace("/", " ").split() if len(w) > 3 and w not in STOP}
inv = db.query("SELECT i.take AS take, f.shot AS shot, round(f.t_s, 2) AS t_s, i.entity AS entity, i.attribute AS attribute, i.value AS value FROM scripty.inventory i FINAL JOIN scripty.frames f FINAL ON f.frame_id = i.frame_id WHERE i.project = %(p)s AND i.scene = %(s)s ORDER BY shot, t_s, entity, attribute, take", {"p": P, "s": S})
shot_of = {r["frame_id"]: int(r["shot"]) for r in db.query("SELECT frame_id, shot FROM scripty.frames FINAL WHERE project = %(p)s AND scene = %(s)s", {"p": P, "s": S})}
cands = dedupe(candidates(P, S, min_conf=0.5, limit=600, version=2))
fnd = db.query("SELECT * FROM scripty.findings FINAL WHERE project = %(p)s AND scene = %(s)s", {"p": P, "s": S})
for l in labs:
    if l["planted_kind"] == "flipped":
        continue
    w = words(l["entity"])
    print(f"\n=== [{l['planted_kind']}] shot {l['shot']} '{l['entity']}'")
    rows = [r for r in inv if int(r["shot"]) == l["shot"] and words(r["entity"]) & w]
    for r in rows[:14]:
        print(f"   inv {r['take']:8s} t={r['t_s']:7.2f} {r['entity']} / {r['attribute']} = {r['value']}")
    cs = [c for c in cands if words(c["entity"]) & w and {c["take_a"], c["take_b"]} == {"A", "PLANTED"} and l["shot"] in (shot_of.get(c["frame_a"]), shot_of.get(c["frame_b"]))]
    for c in cs[:6]:
        print(f"   cand {c['take_a']}->{c['take_b']} {c['entity']} / {c['attribute']}: {c['value_a']} -> {c['value_b']} (rank {cands.index(c)})")
    fs = [f for f in fnd if words(f["entity"]) & w and {f["take_a"], f["take_b"]} == {"A", "PLANTED"} and l["shot"] in (shot_of.get(f["frame_a"]), shot_of.get(f["frame_b"]))]
    for f in fs[:6]:
        print(f"   find {f['entity']} / {f['attribute']}: {f['value_a']} -> {f['value_b']} => {f['verdict']} {f['confidence']:.2f} | {f['explanation'][:110]}")
    if not rows: print("   (no inventory rows match the label entity words at this shot)")
