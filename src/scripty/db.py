"""ClickHouse client (clickhouse-connect over HTTP). Cloud Run-hosted single node or any cluster."""
from __future__ import annotations

import os
from functools import lru_cache

import clickhouse_connect

from .schema import DDL


@lru_cache(maxsize=1)
def client():
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    secure = os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true"
    port = int(os.getenv("CLICKHOUSE_PORT", "443" if secure else "8123"))
    return clickhouse_connect.get_client(host=host, port=port, username=os.getenv("CLICKHOUSE_USER", "default"), password=os.getenv("CLICKHOUSE_PASSWORD", ""), secure=secure, connect_timeout=20, send_receive_timeout=120)


def ensure_schema() -> None:
    c = client()
    for stmt in DDL:
        c.command(stmt)


def insert(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    client().insert(f"scripty.{table}", [[r.get(k) for k in cols] for r in rows], column_names=cols)
    return len(rows)


def query(sql: str, params: dict | None = None) -> list[dict]:
    res = client().query(sql, parameters=params or {})
    return [dict(zip(res.column_names, row)) for row in res.result_rows]
