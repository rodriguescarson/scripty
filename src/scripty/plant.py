"""Planted continuity errors with known ground truth.

We cannot get labelled continuity errors from real films without a rights problem and weeks of
labelling, so we plant them: take the sampled frames of a real scene (take A), make a jittered copy
(take CONTROL — crop/scale/brightness jitter, no semantic change) and a planted copy (take PLANTED)
where specific props are removed, moved or recoloured, using Gemini to locate the prop's bounding
box and OpenCV to edit. The edits are the labels. The control take is the null hypothesis: a detector
that flags it is measuring its own noise."""
from __future__ import annotations

import json
import os
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
    category: str = Field(description="one of: prop (hand-held or table object), garment (worn clothing), set_dressing (furniture, lamp, poster, curtain)")


class Boxes(BaseModel):
    items: list[Box]


BOX_PROMPT = """Detect the distinct, clearly visible hand-sized-to-furniture-sized props and wardrobe items in this film
frame (glasses, bottles, telephones, hats, books, lamps, cigarettes, bags, ties, jackets). Return up to 8 with tight
bounding boxes as [ymin, xmin, ymax, xmax] on a 0-1000 scale. Prefer objects on tables or held by people."""


class CropCheck(BaseModel):
    label: str = Field(description="what this crop shows, two or three words")
    matches: bool = Field(description="true if the crop clearly shows the expected object")


def _crop_matches(img: np.ndarray, bb, expected: str, model: str = MODEL) -> bool:
    """Self-validation: crop the box and ask a second, cheap look whether it shows the expected object."""
    x0, y0, x1, y1 = bb
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    try:
        res = client().models.generate_content(model=model, contents=[f"Does this crop clearly show: {expected}? Answer with the schema.", types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg")], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=CropCheck, temperature=0.0))
        return bool(CropCheck.model_validate_json(res.text or "{}").matches)
    except Exception:
        return False


def detect_boxes(image: Path, model: str | None = None, validate: bool = True) -> list[Box]:
    """Boxes from the stronger model, each validated by cropping it and asking whether it shows the label.
    A mislocated box (the pilot put a 'shirt' on a man's cheek) is rejected instead of planted."""
    model = model or os.getenv("SCRIPTY_BOX_MODEL", "gemini-2.5-pro")
    items: list[Box] = []
    for attempt in range(3):
        try:
            res = client().models.generate_content(model=model, contents=[BOX_PROMPT, types.Part.from_bytes(data=image.read_bytes(), mime_type="image/jpeg")], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Boxes, temperature=0.1))
            items = Boxes.model_validate_json(res.text or "{}").items
            break
        except Exception:
            time.sleep(2 * (attempt + 1))
    if not validate or not items:
        return items
    img = cv2.imread(str(image))
    h, w = img.shape[:2]
    out = []
    for b in items:
        bb = _px(b.box_2d, w, h)
        area = (bb[2] - bb[0]) * (bb[3] - bb[1]) / float(w * h)
        if 0.003 <= area <= 0.12 and _crop_matches(img, bb, b.label):
            out.append(b)
    return out


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


def _soft_mask(shape, bb, feather: int = 9) -> np.ndarray:
    """Elliptical, feathered mask inside the box — edits blend instead of leaving a rectangle."""
    x0, y0, x1, y1 = bb
    m = np.zeros(shape[:2], np.uint8)
    cv2.ellipse(m, ((x0 + x1) // 2, (y0 + y1) // 2), (max(1, (x1 - x0) // 2), max(1, (y1 - y0) // 2)), 0, 0, 360, 255, -1)
    return cv2.GaussianBlur(m, (feather * 2 + 1, feather * 2 + 1), 0)


def remove(img: np.ndarray, bb) -> np.ndarray:
    x0, y0, x1, y1 = bb
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    filled = cv2.inpaint(img, mask, 9, cv2.INPAINT_TELEA)
    a = (_soft_mask(img.shape, (max(0, x0 - 4), max(0, y0 - 4), x1 + 4, y1 + 4), 7).astype(np.float32) / 255.0)[..., None]
    return (filled * a + img * (1 - a)).astype(np.uint8)


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
    """Hue rotation on the object only: the box is feathered and skin-toned pixels are left alone."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    shifted = hsv.copy()
    shifted[..., 0] = (shifted[..., 0] + rng.choice([60, 90, 120])) % 180
    shifted[..., 1] = np.clip(shifted[..., 1] + 40, 0, 255)
    out = cv2.cvtColor(shifted.astype(np.uint8), cv2.COLOR_HSV2BGR)
    a = _soft_mask(img.shape, bb, 9).astype(np.float32) / 255.0
    skin = ((hsv[..., 0] >= 3) & (hsv[..., 0] <= 22) & (hsv[..., 1] >= 40) & (hsv[..., 1] <= 170) & (hsv[..., 2] >= 80))
    a[skin] = 0.0
    a = a[..., None]
    return (out * a + img * (1 - a)).astype(np.uint8)


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
        kind = rng.choice(kinds)
        # remove/move only things that are not worn (inpainting a jacket off a person is not a continuity error, it is a glitch)
        pool = [b for b in boxes if b.category != "garment"] if kind in ("removed", "moved") else boxes
        if kind != "flipped" and not pool:
            kind = "recolored" if boxes else ("flipped" if "flipped" in kinds else None)
            pool = boxes
        box = rng.choice(pool) if pool and kind != "flipped" else None
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
