"""Print a scene's labels, verdict counts, top findings and control noise. Usage: python scripts/inspect_scene.py <project> <scene>"""
import sys
from scripty import db
project, scene = sys.argv[1], sys.argv[2]
print("labels:", [(l["planted_kind"], l["entity"]) for l in db.query("SELECT planted_kind, entity FROM scripty.eval_labels FINAL WHERE project=%(p)s AND scene=%(s)s", {"p": project, "s": scene})])
print("verdicts:", db.query("SELECT verdict, count() c FROM scripty.findings FINAL WHERE project=%(p)s AND scene=%(s)s GROUP BY verdict", {"p": project, "s": scene}))
for f in db.query("SELECT verdict, confidence, take_a, take_b, entity, attribute, value_a, value_b, explanation FROM scripty.findings FINAL WHERE project=%(p)s AND scene=%(s)s ORDER BY (verdict!='continuity_error'), confidence DESC LIMIT 12", {"p": project, "s": scene}):
    print(f"  {f['verdict']:18} {f['confidence']:.2f} {f['take_a']}→{f['take_b']} {f['entity'][:30]}/{f['attribute']}: {f['value_a'][:16]} → {f['value_b'][:16]} | {f['explanation'][:100]}")
