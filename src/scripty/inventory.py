"""Frame inventory: Gemini reads one frame and returns every continuity-relevant entity as
(entity, attribute, value) rows. Deterministic schema, low temperature, one call per frame.

This is the only place a model looks at pixels in the ingest path. Everything downstream is SQL."""
from __future__ import annotations

import json
import time
from pathlib import Path

from google.genai import types
from pydantic import BaseModel, Field

from .gemini import MODEL, client


class Item(BaseModel):
    entity: str = Field(description="stable, specific name a script supervisor would use, e.g. 'wine glass (left of Regina)', 'Peter's tie', 'wall clock', 'cigarette (Regina)'")
    entity_kind: str = Field(description="one of: prop, wardrobe, hair_makeup, set_dressing, liquid_level, screen_direction, character_position, other")
    attribute: str = Field(description="one of: present, position, state, color, count, level, side, held_by, orientation, other")
    value: str = Field(description="short canonical value, e.g. 'on table left', 'half full', 'unbuttoned', 'red', '2', 'facing camera-left'")
    confidence: float = Field(ge=0, le=1)
    region: str = Field(description="rough location in frame: 'top-left', 'center', 'bottom-right', etc.")


class Inventory(BaseModel):
    shot_description: str = Field(description="one sentence: framing, who is in frame, where")
    items: list[Item]


PROMPT = """You are a film script supervisor's continuity assistant. Inventory this single frame for continuity.
List every element that could cause a continuity error between takes or shots of the SAME scene: props (and their
position/state/count), wardrobe (buttons, ties, jackets, jewellery, hats), hair and makeup, set dressing, liquid
levels in glasses/bottles, cigarettes/candles (burn length), clocks, screen direction and which side of frame each
character is on, what each character is holding and in which hand.

Rules: name entities so the SAME object gets the SAME entity string in every frame of this scene (anchor to the
character or the fixed set: "glass (left of the woman in red)", "man's tie", "wall clock"). Use short canonical
values. Do not describe the story. Skip things that legitimately change during a scene (facial expression, mouth
open/closed, gestures). 8–25 items."""


def inventory_frame(image_path: Path, model: str = MODEL, retries: int = 3) -> Inventory:
    img = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            res = client().models.generate_content(
                model=model,
                contents=[PROMPT, img],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Inventory, temperature=0.1, max_output_tokens=4096),
            )
            return Inventory.model_validate_json(res.text or "{}")
        except Exception as e:  # 429/503/parse — retry with backoff
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"inventory failed for {image_path.name}: {last}")


def rows_from_inventory(inv: Inventory, *, project: str, scene: str, take: str, shot: int, t_s: float, frame_id: str, model: str = MODEL) -> list[dict]:
    return [
        {"project": project, "scene": scene, "take": take, "shot": shot, "t_s": t_s, "frame_id": frame_id, "entity": it.entity.strip(), "entity_kind": it.entity_kind, "attribute": it.attribute, "value": it.value.strip(), "confidence": float(it.confidence), "region": it.region, "model": model}
        for it in inv.items
    ]
