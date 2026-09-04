"""Shot boundaries and frame sampling. OpenCV only, deterministic, no model.

A "take" is a clip; a "shot" is a run of frames between hard cuts (HSV histogram distance
over a threshold). Frames are sampled at the start, middle and end of each shot plus every
`every_s` seconds, which is what a script supervisor's continuity photos actually cover."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Shot:
    index: int
    start_s: float
    end_s: float


@dataclass
class Frame:
    shot: int
    t_s: float
    path: Path


def _hist(frame) -> tuple[np.ndarray, np.ndarray]:
    """Two signatures: hue/saturation (colour films) and value (works for black-and-white, where H and S are flat)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hs = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    v = cv2.calcHist([hsv], [2], None, [64], [0, 256])
    return cv2.normalize(hs, hs).flatten(), cv2.normalize(v, v).flatten()


def _dist(a, b) -> float:
    return max(cv2.compareHist(a[0], b[0], cv2.HISTCMP_BHATTACHARYYA), cv2.compareHist(a[1], b[1], cv2.HISTCMP_BHATTACHARYYA))


def detect_shots(video: Path, threshold: float = 0.55, min_len_s: float = 0.8, step: int = 2) -> list[Shot]:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    shots: list[Shot] = []
    prev = None
    start = 0.0
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(frame, (320, 180))
            h = _hist(small)
            t = i / fps
            if prev is not None:
                d = _dist(prev, h)
                if d > threshold and (t - start) >= min_len_s:
                    shots.append(Shot(len(shots), start, t))
                    start = t
            prev = h
        i += 1
    end = (n / fps) if n else (i / fps)
    if end - start >= min_len_s or not shots:
        shots.append(Shot(len(shots), start, end))
    cap.release()
    return shots


def sample_frames(video: Path, shots: list[Shot], out_dir: Path, every_s: float = 2.0, max_per_shot: int = 6, width: int = 1024) -> list[Frame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames: list[Frame] = []
    for s in shots:
        ts = {s.start_s + 0.15, (s.start_s + s.end_s) / 2, max(s.start_s, s.end_s - 0.15)}
        t = s.start_s + every_s
        while t < s.end_s - 0.15:
            ts.add(t)
            t += every_s
        for t in sorted(ts)[:max_per_shot]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            if w > width:
                frame = cv2.resize(frame, (width, int(h * width / w)))
            p = out_dir / f"shot{s.index:03d}_t{t:07.2f}.jpg"
            cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
            frames.append(Frame(s.index, round(t, 2), p))
    cap.release()
    return frames


def cut_clip(video: Path, start_s: float, end_s: float, out: Path) -> Path:
    """Lossless-ish clip extraction via OpenCV re-encode (ffmpeg is used where available)."""
    import shutil, subprocess
    out.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start_s:.3f}", "-to", f"{end_s:.3f}", "-i", str(video), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(out)], check=True)
        return out
    raise RuntimeError("ffmpeg required")
