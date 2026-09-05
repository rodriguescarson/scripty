"""ClickHouse client (clickhouse-connect over HTTP). Cloud Run-hosted single node or any cluster."""
from __future__ import annotations

import os
import threading

import clickhouse_connect

from .schema import DDL

_local = threading.local()


def client():
    """One clickhouse-connect client per thread: the HTTP client is not safe for concurrent queries."""
    c = getattr(_local, "client", None)
    if c is not None:
        return c
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    secure = os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true"
    port = int(os.getenv("CLICKHOUSE_PORT", "443" if secure else "8123"))
    _local.client = clickhouse_connect.get_client(host=host, port=port, username=os.getenv("CLICKHOUSE_USER", "default"), password=os.getenv("CLICKHOUSE_PASSWORD", ""), secure=secure, connect_timeout=20, send_receive_timeout=120)
    return _local.client


def _retry(fn, attempts: int = 4):
    """The node is a single Cloud Run instance behind HTTPS: transient 5xx/timeouts happen. Retry with backoff."""
    import time
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            last = e
            transient = any(k in msg for k in ("500", "Server Error", "503", "502", "504", "timed out", "Timeout", "Connection", "RemoteDisconnected", "reset by peer", "Max retries", "Temporary"))
            if i < attempts - 1 and transient:
                _local.client = None  # drop the connection; a fresh one is made on the next call
                time.sleep(2 * (i + 1))
                continue
            raise
    raise last  # pragma: no cover


_schema_done = False


def ensure_schema() -> None:
    global _schema_done
    if _schema_done:
        return
    for stmt in DDL:
        _retry(lambda s=stmt: client().command(s))
    _schema_done = True


def insert(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    data = [[r.get(k) for k in cols] for r in rows]
    _retry(lambda: client().insert(f"scripty.{table}", data, column_names=cols))
    return len(rows)


def query(sql: str, params: dict | None = None) -> list[dict]:
    res = _retry(lambda: client().query(sql, parameters=params or {}))
    return [dict(zip(res.column_names, row)) for row in res.result_rows]


def purge_project(project: str) -> None:
    """Remove every row of a project (fresh evaluation runs must not mix with stale ones)."""
    for t in ("frames", "inventory", "findings", "eval_labels"):
        client().command(f"ALTER TABLE scripty.{t} DELETE WHERE project = %(p)s", {"p": project})


# ---------------------------------------------------------------------------
# Durability. The Cloud Run node's disk is ephemeral: a redeploy or crash empties it. Every
# project is exported to JSONL in the frames bucket after ingest, and the app restores on
# boot if the tables are empty — no Gemini call is ever repeated to rebuild the database.
# ---------------------------------------------------------------------------
TABLES = ("frames", "inventory", "findings", "eval_labels")


def export_project(project: str, out_dir) -> dict:
    import json
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in TABLES:
        rows = query(f"SELECT * FROM scripty.{t} FINAL WHERE project = %(p)s", {"p": project})
        with (out_dir / f"{t}.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
        counts[t] = len(rows)
    return counts


def restore_dir(in_dir) -> dict:
    import json
    from pathlib import Path
    in_dir = Path(in_dir)
    counts = {}
    ensure_schema()
    for t in TABLES:
        p = in_dir / f"{t}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        for r in rows:
            for k in ("ingested_at", "extracted_at", "created_at"):
                r.pop(k, None)
        counts[t] = insert(t, rows)
    return counts


def is_empty() -> bool:
    return query("SELECT count() AS c FROM scripty.frames")[0]["c"] == 0
