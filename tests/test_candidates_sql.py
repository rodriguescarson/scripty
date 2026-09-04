"""The continuity query, run against a local ClickHouse if available (skipped otherwise)."""
import os
import shutil
import subprocess
import time

import pytest

from scripty.schema import CANDIDATES_SQL, DDL


@pytest.fixture(scope="module")
def local_ch():
    exe = os.path.join(os.path.dirname(__file__), "..", "build", "clickhouse")
    if not os.path.exists(exe):
        pytest.skip("no local clickhouse binary")
    d = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build", "ch-test"))
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    proc = subprocess.Popen([exe, "server", "--", "--path", d, "--http_port", "18123", "--tcp_port", "19000", "--listen_host", "127.0.0.1", "--logger.level", "error"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import clickhouse_connect
    for _ in range(60):
        try:
            c = clickhouse_connect.get_client(host="127.0.0.1", port=18123)
            c.command("SELECT 1")
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.skip("local clickhouse did not start")
    yield c
    proc.kill()


def test_candidates_find_cross_take_differences_only(local_ch):
    c = local_ch
    for stmt in DDL:
        c.command(stmt)
    rows = [
        ["p", "s1", "A", 0, 1.0, "fA1", "wine glass (left)", "prop", "level", "half full", 0.9, "center", "m"],
        ["p", "s1", "B", 0, 1.0, "fB1", "wine glass (left)", "prop", "level", "empty", 0.8, "center", "m"],
        ["p", "s1", "A", 0, 1.0, "fA1", "man's tie", "wardrobe", "state", "knotted", 0.9, "center", "m"],
        ["p", "s1", "B", 0, 1.0, "fB1", "man's tie", "wardrobe", "state", "knotted", 0.9, "center", "m"],
        ["p", "s1", "A", 0, 1.0, "fA1", "lamp", "set_dressing", "present", "yes", 0.3, "left", "m"],
        ["p", "s1", "B", 0, 1.0, "fB1", "lamp", "set_dressing", "present", "no", 0.3, "left", "m"],
    ]
    c.insert("scripty.inventory", rows, column_names=["project", "scene", "take", "shot", "t_s", "frame_id", "entity", "entity_kind", "attribute", "value", "confidence", "region", "model"])
    res = c.query(CANDIDATES_SQL, parameters={"project": "p", "scene": "s1", "min_conf": 0.5, "limit": 50})
    out = [dict(zip(res.column_names, r)) for r in res.result_rows]
    assert [o["entity"] for o in out] == ["wine glass (left)"]  # tie unchanged; lamp below confidence
    assert out[0]["value_a"] == "half full" and out[0]["value_b"] == "empty" and out[0]["take_a"] != out[0]["take_b"]
