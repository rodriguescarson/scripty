"""Planted continuity errors with known ground truth.

We cannot get labelled continuity errors from real films without a rights problem and weeks of
labelling, so we plant them: take the sampled frames of a real scene (take A), make a jittered copy
(take CONTROL — crop/scale/brightness jitter, no semantic change) and a planted copy (take PLANTED)
where specific props are removed, moved or recoloured, using Gemini to locate the prop's bounding
box and OpenCV to edit. The edits are the labels. The control take is the null hypothesis: a detector
that flags it is measuring its own noise."""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from google.genai import types
from pydantic import BaseModel, Field

from .gemini import MODEL, client
from .shots import Frame


class Box(BaseModel):
    label: str = Field(description="short prop name, e.g. 'wine glass', 'telephone', 'hat', 'book'")
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax] normalised to 0-1000")
    movable: bool = Field(description="true if a person could plausibly move/remove it between takes")


class Boxes(BaseModel):
    items: list[Box]


BOX_PROMPT = """Detect the distinct, clearly visible hand-sized-to-furniture-sized props and wardrobe items in this film
frame (glasses, bottles, telephones, hats, books, lamps, cigarettes, bags, ties, jackets). Return up to 8 with tight
bounding boxes as [ymin, xmin, ymax, xmax] on a 0-1000 scale. Prefer objects on tables or held by people."""


def detect_boxes(image: Path, model: str = MODEL) -> list[Box]:
    for attempt in range(3):
        try:
            res = client().models.generate_content(model=model, contents=[BOX_PROMPT, types.Part.from_bytes(data=image.read_bytes(), mime_type="image/jpeg")], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Boxes, temperature=0.1))
            return Boxes.model_validate_json(res.text or "{}").items
        except Exception:
            time.sleep(2 * (attempt + 1))
    return []


def _px(box: list[int], w: int, h: int) -> tuple[int, int, int, int]:
    y0, x0, y1, x1 = box
    return max(0, int(x0 / 1000 * w)), max(0, int(y0 / 1000 * h)), min(w, int(x1 / 1000 * w)), min(h, int(y1 / 1000 * h))


def jitter(img: np.ndarray, rng: random.Random) -> np.ndarray:
    """Simulates a different take: slight reframing and exposure change, nothing semantic."""
    h, w = img.shape[:2]
    s = rng.uniform(0.96, 1.0)
    cw, ch = int(w * s), int(h * s)
    x0, y0 = rng.randint(0, w - cw), rng.randint(0, h - ch)
    out = cv2.resize(img[y0:y0 + ch, x0:x0 + cw], (w, h))
    out = cv2.convertScaleAbs(out, alpha=rng.uniform(0.94, 1.06), beta=rng.uniform(-8, 8))
    return out


def remove(img: np.ndarray, bb) -> np.ndarray:
    x0, y0, x1, y1 = bb
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = 255
    return cv2.inpaint(img, mask, 7, cv2.INPAINT_TELEA)


def move(img: np.ndarray, bb, rng: random.Random) -> np.ndarray:
    x0, y0, x1, y1 = bb
    patch = img[y0:y1, x0:x1].copy()
    out = remove(img, bb)
    h, w = img.shape[:2]
    dx = int((x1 - x0) * rng.choice([-1.4, 1.4]))
    nx0 = min(max(0, x0 + dx), w - (x1 - x0))
    out[y0:y1, nx0:nx0 + (x1 - x0)] = patch
    return out


def recolor(img: np.ndarray, bb, rng: random.Random) -> np.ndarray:
    x0, y0, x1, y1 = bb
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[y0:y1, x0:x1, 0] = (hsv[y0:y1, x0:x1, 0] + rng.choice([45, 90, 135])) % 180
    hsv[y0:y1, x0:x1, 1] = np.clip(hsv[y0:y1, x0:x1, 1] + 60, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def flip(img: np.ndarray) -> np.ndarray:
    return cv2.flip(img, 1)


@dataclass
class Label:
    take: str
    shot: int
    planted_kind: str  # removed | moved | recolored | flipped
    entity: str
    description: str


def plant_scene(frames: list[Frame], out_root: Path, scene: str, seed: int = 7, kinds=("removed", "moved", "recolored", "flipped")) -> tuple[list[Frame], list[Frame], list[Label]]:
    """Returns (control_frames, planted_frames, labels). Edits are applied per shot so the same object
    is consistently altered across that shot's frames (as a real continuity error would be)."""
    rng = random.Random(seed)
    control, planted, labels = [], [], []
    by_shot: dict[int, list[Frame]] = {}
    for f in frames:
        by_shot.setdefault(f.shot, []).append(f)
    for shot, fs in sorted(by_shot.items()):
        first = cv2.imread(str(fs[0].path))
        h, w = first.shape[:2]
        boxes = [b for b in detect_boxes(fs[0].path) if b.movable and (b.box_2d[3] - b.box_2d[1]) * (b.box_2d[2] - b.box_2d[0]) > 400]
        kind = rng.choice(kinds) if boxes or "flipped" in kinds else None
        if kind != "flipped" and not boxes:
            kind = "flipped" if "flipped" in kinds else None
        box = rng.choice(boxes) if boxes and kind != "flipped" else None
        for f in fs:
            img = cv2.imread(str(f.path))
            c = jitter(img, rng)
            cp = out_root / scene / "CONTROL" / f.path.name
            cp.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(cp), c, [cv2.IMWRITE_JPEG_QUALITY, 88])
            control.append(Frame(f.shot, f.t_s, cp))
            p = jitter(img, rng)
            if kind == "flipped":
                p = flip(p)
            elif box is not None:
                bb = _px(box.box_2d, w, h)
                p = {"removed": lambda: remove(p, bb), "moved": lambda: move(p, bb, rng), "recolored": lambda: recolor(p, bb, rng)}[kind]()
            pp = out_root / scene / "PLANTED" / f.path.name
            pp.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(pp), p, [cv2.IMWRITE_JPEG_QUALITY, 88])
            planted.append(Frame(f.shot, f.t_s, pp))
        if kind:
            labels.append(Label("PLANTED", shot, kind, (box.label if box else "whole frame"), f"shot {shot}: {kind} {(box.label if box else 'frame mirrored (screen direction)')}"))
    (out_root / scene / "labels.json").write_text(json.dumps([l.__dict__ for l in labels], indent=1))
    return control, planted, labels
