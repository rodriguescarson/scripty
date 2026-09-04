"""Pick evaluation scenes from a whole film, deterministically.

Shots are clustered into scenes by background similarity (shot/reverse-shot dialogue shares a set),
then filtered to 30–150 s and 3–12 shots. No model, no hand-picking."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .shots import Shot, detect_shots


@dataclass
class Scene:
    index: int
    start_s: float
    end_s: float
    shots: list[Shot]

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s


def _shot_signature(cap, s: Shot, fps: float) -> np.ndarray:
    t = (s.start_s + s.end_s) / 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, frame = cap.read()
    if not ok:
        return np.zeros(32 * 32, np.float32)
    hsv = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 2], None, [32, 32], [0, 180, 0, 256])  # hue × value: survives black-and-white
    return cv2.normalize(h, h).flatten()


def cluster_scenes(video: Path, shots: list[Shot] | None = None, sim_threshold: float = 0.45, gap_s: float = 1.0) -> list[Scene]:
    shots = shots or detect_shots(video)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    sigs = [_shot_signature(cap, s, fps) for s in shots]
    cap.release()
    scenes: list[Scene] = []
    cur: list[Shot] = []
    for i, s in enumerate(shots):
        if not cur:
            cur = [s]
            continue
        # a shot belongs to the current scene if it resembles any of the last 4 shots' backgrounds (reverse angles alternate)
        recent = sigs[max(0, i - 4):i]
        best = max(1.0 - cv2.compareHist(sigs[i], r, cv2.HISTCMP_BHATTACHARYYA) for r in recent)
        if best >= sim_threshold and s.start_s - cur[-1].end_s <= gap_s:
            cur.append(s)
        else:
            scenes.append(Scene(len(scenes), cur[0].start_s, cur[-1].end_s, cur))
            cur = [s]
    if cur:
        scenes.append(Scene(len(scenes), cur[0].start_s, cur[-1].end_s, cur))
    return scenes


def select_eval_scenes(scenes: list[Scene], min_s: float = 30, max_s: float = 150, min_shots: int = 3, max_shots: int = 12, limit: int = 40) -> list[Scene]:
    ok = [sc for sc in scenes if min_s <= sc.duration <= max_s and min_shots <= len(sc.shots) <= max_shots]
    return ok[:limit]
