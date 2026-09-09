"""Build docs/eval/<project>.json (the shape the app's evaluation panel reads) from <project>.progress.jsonl and
<project>.rescore.json. Used for run 2, whose progress file is written by scripty.rerun. Usage: python scripts/summarise.py <project> [run_no]"""
import json, sys, time
from pathlib import Path
project = sys.argv[1]; run_no = int(sys.argv[2]) if len(sys.argv) > 2 else 2
recs = [json.loads(l) for l in (Path("docs/eval") / f"{project}.progress.jsonl").read_text().splitlines() if l.strip()]
rs = json.loads((Path("docs/eval") / f"{project}.rescore.json").read_text())
plan, strict = rs["plan"], rs["strict"]
elapsed = round(sum(r.get("seconds", 0) for r in recs), 1)
ok = lambda m: (m["recall"] or 0) >= 0.6 and (m["precision"] or 0) >= 0.5 and (m["control_fpr_per_scene"] or 0) <= 1
out = {"run": run_no, "n_scenes": plan["scenes"], "n_labels": plan["labels"], "recall": plan["recall"], "precision": plan["precision"],
       "control_fpr_per_scene": plan["control_fpr_per_scene"], "by_kind": plan["by_kind"], "operating_point": {"verdict": "continuity_error", "min_confidence": 0.6},
       "pass": ok(plan), "pass_strict": ok(strict), "strict": {k: strict[k] for k in ("recall", "precision", "control_fpr_per_scene", "planted_positives")},
       "ran_at": time.strftime("%Y-%m-%d %H:%M IST"), "elapsed_s": elapsed, "failed_scenes": []}
(Path("docs/eval") / f"{project}.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: out[k] for k in ("n_scenes", "n_labels", "recall", "precision", "control_fpr_per_scene", "pass", "strict", "pass_strict")}))
