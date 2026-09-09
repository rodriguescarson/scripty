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


COLORS = "black, white, grey, silver, beige, brown, red, orange, yellow, green, blue, navy, purple, pink, gold, clear"
POSITIONS = "top-left, top-center, top-right, middle-left, center, middle-right, bottom-left, bottom-center, bottom-right"

PROMPT = """You are a film script supervisor's continuity assistant. Inventory this single frame for continuity.
List every element that could cause a continuity error between takes or shots of the SAME scene: props (and their
position/state/count), wardrobe (buttons, ties, jackets, jewellery, hats), hair and makeup, set dressing, liquid
levels in glasses/bottles, cigarettes/candles (burn length), clocks, screen direction and which side of frame each
character is on, what each character is holding and in which hand.

Rules: name entities so the SAME object gets the SAME entity string in every frame of this scene (anchor to the
character or the fixed set: "glass (left of the woman in red)", "man's tie", "wall clock"). Controlled vocabulary:
colors ONLY from [""" + COLORS + """]; positions ONLY from [""" + POSITIONS + """] optionally followed by ' on <surface>';
states from [open, closed, on, off, lit, unlit, full, half full, empty, buttoned, unbuttoned, knotted, loose, worn,
removed, held, resting]; sides from [camera-left, camera-right, center]; counts as digits. One value per row, no
prose, no synonyms. Do not describe the story. Skip things that legitimately change during a scene (facial expression,
mouth open/closed, gestures). 8–25 items."""

REFERENCE_SUFFIX = """

REFERENCE INVENTORY from the reference take of this same shot (continuity sheet). Report EVERY entity below using
EXACTLY the same entity string, with its current attribute value in this frame (use the value "absent" for attribute
"present" if the entity is not visible here). Then add any new continuity-relevant entities not on the sheet.
Reference entities: {refs}"""


REFERENCE_SUFFIX_V2 = """

CONTINUITY SHEET from the reference take of this same shot. For EVERY entity below, output one row for EVERY attribute
listed for it, with the value as seen in THIS frame (same controlled vocabulary; repeat the value if unchanged, give the
new value if it differs; use "absent" for attribute "present" if the entity is not visible here and then skip its other
attributes). Use EXACTLY the same entity strings. The 8–25 item limit above does NOT apply here: output one row per
sheet attribute even if that is 60–120 rows, then add any new continuity-relevant entities not on the sheet.
Sheet: {refs}"""


def inventory_frame(image_path: Path, model: str = MODEL, retries: int = 3, reference: list[str] | None = None, reference_rows: list[str] | None = None) -> Inventory:
    img = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg")
    max_tokens = 4096
    if reference_rows:
        prompt = PROMPT + REFERENCE_SUFFIX_V2.format(refs=" | ".join(reference_rows[:60]))
        max_tokens = 16384
    else:
        prompt = PROMPT + (REFERENCE_SUFFIX.format(refs="; ".join(sorted(set(reference))[:40])) if reference else "")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            res = client().models.generate_content(
                model=model,
                contents=[prompt, img],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Inventory, temperature=0.1, max_output_tokens=max_tokens),
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


def normalize_entity(e: str) -> str:
    return " ".join(e.lower().replace("'s", "s").replace("'", "").split())
