"""Recompute the pre-registered metrics from docs/eval/<project>.progress.jsonl under two matchers:
  plan  — as written in EVAL_PLAN.md (entity words OR category), no shot constraint  [what the run recorded]
  strict — same shot AND (entity-word overlap OR flipped↔screen-direction attribute)   [tightened after the pilot
           showed the category fallback lets one wardrobe finding 'match' every wardrobe label]
Both are published. Usage: python scripts/rescore.py <project>"""
import json, sys
from pathlib import Path
from scripty import db

project = sys.argv[1]
prog = Path("docs/eval") / f"{project}.progress.jsonl"
recs = [json.loads(l) for l in prog.read_text().splitlines() if l.strip()]
shot_of = {r["frame_id"]: int(r["shot"]) for r in db.query("SELECT frame_id, shot FROM scripty.frames FINAL WHERE project = %(p)s", {"p": project})}
FLIP_ATTRS = {"screen_direction", "side", "position", "orientation", "character_position"}
STOP = {"the", "and", "with", "left", "right", "background", "foreground", "camera", "front", "back"}


def words(s):
    return {w for w in s.lower().replace("(", " ").replace(")", " ").replace("'", "").split() if len(w) > 3 and w not in STOP}


def match_plan(f, l):
    if l["planted_kind"] == "flipped":
        return f["attribute"] in FLIP_ATTRS or f["category"] in FLIP_ATTRS
    return bool(words(l["entity"]) & words(f["entity"])) or f["category"] in ("prop", "set_dressing", "wardrobe")


def match_strict(f, l):
    sa, sb = shot_of.get(f["frame_a"]), shot_of.get(f["frame_b"])
    if l["shot"] not in (sa, sb):
        return False
    if l["planted_kind"] == "flipped":
        return f["attribute"] in FLIP_ATTRS or f["category"] in FLIP_ATTRS
    return bool(words(l["entity"]) & words(f["entity"]))


def score(matcher):
    hits = tp = pos = 0; labels = 0; by_kind = {}
    for r in recs:
        # pre-registered pairs only: A vs PLANTED (same shot, same moment). PLANTED-vs-PLANTED cross-shot pairs are not planted evidence.
        planted_pos = [f for f in r["findings"] if f["verdict"] == "continuity_error" and f["confidence"] >= 0.6 and {f["take_a"], f["take_b"]} == {"A", "PLANTED"}]
        for l in r["labels"]:
            labels += 1
            h = any(matcher(f, l) for f in planted_pos)
            hits += h
            k = by_kind.setdefault(l["planted_kind"], {"n": 0, "hit": 0}); k["n"] += 1; k["hit"] += int(h)
        pos += len(planted_pos)
        tp += sum(1 for f in planted_pos if any(matcher(f, l) for l in r["labels"]))
    ctrl = sum(sum(1 for f in r["findings"] if f["verdict"] == "continuity_error" and f["confidence"] >= 0.6 and {f["take_a"], f["take_b"]} == {"A", "CONTROL"}) for r in recs)
    return {"scenes": len(recs), "labels": labels, "recall": round(hits / labels, 3) if labels else None, "precision": round(tp / pos, 3) if pos else None, "planted_positives": pos, "control_fpr_per_scene": round(ctrl / len(recs), 3) if recs else None, "by_kind": by_kind}


out = {"plan": score(match_plan), "strict": score(match_strict)}
print(json.dumps(out, indent=1))
Path("docs/eval").mkdir(exist_ok=True)
(Path("docs/eval") / f"{project}.rescore.json").write_text(json.dumps(out, indent=1))
