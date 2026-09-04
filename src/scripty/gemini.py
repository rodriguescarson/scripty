"""Google GenAI client (Vertex AI by default; AI Studio key if GOOGLE_API_KEY is set and Vertex is off)."""
from __future__ import annotations

import os
from functools import lru_cache

from google import genai


@lru_cache(maxsize=1)
def client() -> genai.Client:
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true":
        return genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT", "mealstogo-76a00"), location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


MODEL = os.getenv("SCRIPTY_MODEL", "gemini-2.5-flash")
VERIFY_MODEL = os.getenv("SCRIPTY_VERIFY_MODEL", "gemini-2.5-pro")
