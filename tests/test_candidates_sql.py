"""The continuity query, run against the configured ClickHouse (the Cloud Run node when .env is loaded)
in a throwaway project name; skipped when no cluster is reachable."""
import os
import uuid

import pytest

from scripty.schema import CANDIDATES_SQL


@pytest.fixture(scope="module")
def ch():
    if not os.getenv("CLICKHOUSE_HOST"):
        pytest.skip("CLICKHOUSE_HOST not set")
    from scripty import db
    try:
        db.ensure_schema()
    except Exception as e:
        pytest.skip(f"cluster unreachable: {e}")
    project = f"pytest_{uuid.uuid4().hex[:8]}"
    yield db, project
    db.client().command(f"ALTER TABLE scripty.inventory DELETE WHERE project = '{project}'")


def test_candidates_find_cross_take_differences_only(ch):
    db, project = ch
    cols = ["project", "scene", "take", "shot", "t_s", "frame_id", "entity", "entity_kind", "attribute", "value", "confidence", "region", "model"]
    rows = [
        [project, "s1", "A", 0, 1.0, "fA1", "wine glass (left)", "prop", "level", "half full", 0.9, "center", "m"],
        [project, "s1", "B", 0, 1.0, "fB1", "wine glass (left)", "prop", "level", "empty", 0.8, "center", "m"],
        [project, "s1", "A", 0, 1.0, "fA1", "man's tie", "wardrobe", "state", "knotted", 0.9, "center", "m"],
        [project, "s1", "B", 0, 1.0, "fB1", "man's tie", "wardrobe", "state", "knotted", 0.9, "center", "m"],
        [project, "s1", "A", 0, 1.0, "fA1", "lamp", "set_dressing", "present", "yes", 0.3, "left", "m"],
        [project, "s1", "B", 0, 1.0, "fB1", "lamp", "set_dressing", "present", "no", 0.3, "left", "m"],
        [project, "s1", "A", 0, 1.0, "fA1", "logo", "set_dressing", "position", "bottom-left", 0.9, "left", "m"],
        [project, "s1", "B", 0, 1.0, "fB1", "logo", "set_dressing", "position", "bottom-left corner", 0.9, "left", "m"],
        [project, "s1", "A", 1, 9.0, "fA9", "wine glass (left)", "prop", "level", "empty", 0.9, "center", "m"],
    ]
    db.client().insert("scripty.inventory", rows, column_names=cols)
    out = db.query(CANDIDATES_SQL, {"project": project, "scene": "s1", "min_conf": 0.5, "limit": 50, "t_tol": 1.5, "reference": "A"})
    ents = [(o["entity"], o["pair_kind"]) for o in out]
    assert ("wine glass (left)", "cross_take") in ents
    assert ("wine glass (left)", "cross_shot") in ents
    assert all(o["entity"] not in ("man's tie", "lamp", "logo") for o in out)
    assert ents[0][1] == "cross_take"
