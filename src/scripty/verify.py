"""Pairwise verification. Given two frames and a candidate (entity, attribute, value A vs value B) the SQL
found, a stronger model looks at both frames and rules: continuity_error / intentional_change / same /
uncertain. This is the step every published attempt at this problem got stuck on; we measure it instead of
claiming it."""
from __future__ import annotations

import time
from pathlib import Path

from google.genai import types
from pydantic import BaseModel, Field

from .gemini import VERIFY_MODEL, client


class Verdict(BaseModel):
    verdict: str = Field(description="one of: continuity_error, intentional_change, same, uncertain")
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(description="two sentences citing what is visible in frame A and frame B")


PROMPT = """You are verifying a possible continuity error between two frames from takes/shots of the SAME scene.
Candidate: entity "{entity}", attribute "{attribute}": frame A shows "{value_a}", frame B shows "{value_b}".
Look at both frames. Decide:
- continuity_error: the same object/wardrobe/set element differs in a way that would be a mistake if both frames were cut together (e.g. glass level jumps up, tie knot changes, prop moves with no action explaining it).
- intentional_change: the difference is explained by the action (a character drinks, moves the prop, takes off a hat) or by a legitimately different moment in the scene.
- same: no real difference; the candidate is a labelling inconsistency.
- uncertain: cannot tell from these frames.
Be strict: only say continuity_error when the frames clearly contradict each other on that attribute."""


def verify_pair(frame_a: Path, frame_b: Path, entity: str, attribute: str, value_a: str, value_b: str, model: str = VERIFY_MODEL, retries: int = 3) -> Verdict:
    parts = [PROMPT.format(entity=entity, attribute=attribute, value_a=value_a, value_b=value_b), "FRAME A:", types.Part.from_bytes(data=frame_a.read_bytes(), mime_type="image/jpeg"), "FRAME B:", types.Part.from_bytes(data=frame_b.read_bytes(), mime_type="image/jpeg")]
    last: Exception | None = None
    for attempt in range(retries):
        try:
            res = client().models.generate_content(model=model, contents=parts, config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Verdict, temperature=0.1, max_output_tokens=1024))
            return Verdict.model_validate_json(res.text or "{}")
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"verify failed: {last}")
