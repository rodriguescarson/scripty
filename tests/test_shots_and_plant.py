import random
from pathlib import Path

import cv2
import numpy as np

from scripty.plant import flip, jitter, move, recolor, remove
from scripty.shots import detect_shots, sample_frames


def _synthetic_video(path: Path, fps=24, secs=(2.0, 2.0, 2.0)):
    w, h = 320, 180
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    colors = [(30, 30, 200), (30, 200, 30), (200, 30, 30)]
    for i, s in enumerate(secs):
        for _ in range(int(fps * s)):
            frame = np.full((h, w, 3), colors[i], np.uint8)
            cv2.rectangle(frame, (40 + 30 * i, 60), (100 + 30 * i, 120), (255, 255, 255), -1)
            vw.write(frame)
    vw.release()


def test_detects_three_hard_cuts(tmp_path):
    v = tmp_path / "v.mp4"
    _synthetic_video(v)
    shots = detect_shots(v)
    assert len(shots) == 3, [(s.start_s, s.end_s) for s in shots]
    frames = sample_frames(v, shots, tmp_path / "frames", every_s=1.0)
    assert len(frames) >= 6 and all(f.path.exists() for f in frames)


def test_plant_edits_change_pixels_only_where_intended():
    img = np.full((180, 320, 3), 120, np.uint8)
    cv2.rectangle(img, (100, 60), (140, 100), (0, 0, 255), -1)
    rng = random.Random(1)
    bb = (100, 60, 140, 100)
    r = remove(img, bb)
    assert int(np.abs(r[60:100, 100:140].astype(int) - img[60:100, 100:140].astype(int)).mean()) > 20
    assert np.array_equal(r[:50, :50], img[:50, :50])
    m = move(img, bb, rng)
    assert not np.array_equal(m, img)
    c = recolor(img, bb, rng)
    assert np.array_equal(c[:50, :50], img[:50, :50]) and not np.array_equal(c[60:100, 100:140], img[60:100, 100:140])
    f = flip(img)
    assert np.array_equal(f[:, ::-1], img)
    j = jitter(img, rng)
    assert j.shape == img.shape
