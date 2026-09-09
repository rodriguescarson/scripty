"""Spend guards for the one endpoint that can cost money.

``/api/ask`` runs an ADK agent over Gemini 2.5 Pro on every call, and the app is
public: the URL is on a Devpost entry. Nothing else here reaches a paid API, so
this is the only surface where a stranger can spend real money.

Two limits, because they fail in different ways. The per-caller bucket stops one
client hammering the endpoint; the daily cap bounds the damage when the callers
are many, which is the case a per-IP limit cannot see. Both are in-process, so
with several instances the effective ceiling is the cap times the instance count
-- max-instances is 3, so the true daily worst case is 3x DAILY_ASKS, and that
is deliberate rather than overlooked. A shared counter would need a round trip
to ClickHouse on a path whose whole point is to be cheap.

Limits are read from the environment so they can be tightened on a running
service without a redeploy.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

PER_IP_ASKS = int(os.getenv("SCRIPTY_PER_IP_ASKS", "5"))
PER_IP_WINDOW_S = int(os.getenv("SCRIPTY_PER_IP_WINDOW_S", "600"))
DAILY_ASKS = int(os.getenv("SCRIPTY_DAILY_ASKS", "150"))

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)
_day: tuple[int, int] = (-1, 0)  # (day number, asks so far today)


class OverBudget(Exception):
    """Raised instead of calling the model. Carries what the caller should be told."""

    def __init__(self, detail: str, retry_after: int):
        super().__init__(detail)
        self.detail = detail
        self.retry_after = retry_after


def _prune(q: deque[float], now: float) -> None:
    while q and now - q[0] > PER_IP_WINDOW_S:
        q.popleft()


def check(client: str) -> None:
    """Record one ask from ``client``, or raise :class:`OverBudget`.

    Called before the model, never after: a request that is refused must not
    have cost anything.
    """
    global _day
    now = time.time()
    today = int(now // 86_400)
    with _lock:
        if _day[0] != today:
            _day = (today, 0)
            _hits.clear()  # a new day is also a fresh window for every caller
        if _day[1] >= DAILY_ASKS:
            midnight = (today + 1) * 86_400
            raise OverBudget(
                "This demo answers a limited number of questions per day and has reached it. "
                "The board, the findings and the evaluation are all still live; only the agent is paused.",
                max(1, int(midnight - now)),
            )
        q = _hits[client]
        _prune(q, now)
        if len(q) >= PER_IP_ASKS:
            # q is empty when PER_IP_ASKS is 0, which is the kill switch for this
            # endpoint: it must answer 429, not raise IndexError off q[0].
            waited = now - q[0] if q else 0.0
            raise OverBudget(
                f"Up to {PER_IP_ASKS} questions every {PER_IP_WINDOW_S // 60} minutes from one address."
                if PER_IP_ASKS
                else "The agent is switched off on this deployment. Everything else on the page still works.",
                max(1, int(PER_IP_WINDOW_S - waited)),
            )
        q.append(now)
        _day = (today, _day[1] + 1)


def state() -> dict:
    """What the health endpoint reports. No addresses, only counts."""
    with _lock:
        return {
            "asks_today": _day[1] if _day[0] == int(time.time() // 86_400) else 0,
            "daily_cap": DAILY_ASKS,
            "per_ip": f"{PER_IP_ASKS}/{PER_IP_WINDOW_S}s",
            "callers_in_window": len(_hits),
        }
