import sys
from pathlib import Path

from .eval_run import run

if __name__ == "__main__":
    video, project = Path(sys.argv[1]), sys.argv[2]
    max_scenes = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    out = run(video, project, Path("data/frames"), Path("docs/eval"), max_scenes=max_scenes)
    print({k: out[k] for k in ("n_scenes", "n_labels", "recall", "precision", "control_fpr_per_scene", "pass", "elapsed_s")})
