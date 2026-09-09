"""The spend guard on /api/ask.

The endpoint is public and every call runs a paid model, so the property that
matters is not "requests are counted" but "a refused request never reaches the
model". These tests assert that directly by making the model raise.
"""
import importlib

import pytest


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.setenv("SCRIPTY_PER_IP_ASKS", "3")
    monkeypatch.setenv("SCRIPTY_PER_IP_WINDOW_S", "60")
    monkeypatch.setenv("SCRIPTY_DAILY_ASKS", "5")
    import scripty.budget as b
    return importlib.reload(b)


def test_per_caller_window_closes(budget):
    for _ in range(3):
        budget.check("1.2.3.4")
    with pytest.raises(budget.OverBudget) as e:
        budget.check("1.2.3.4")
    assert e.value.retry_after > 0


def test_one_caller_does_not_exhaust_another(budget):
    for _ in range(3):
        budget.check("1.2.3.4")
    budget.check("5.6.7.8")  # must not raise


def test_daily_cap_binds_across_callers(budget):
    """The per-IP limit cannot see a crowd; the daily cap is what bounds it."""
    for i in range(5):
        budget.check(f"10.0.0.{i}")
    with pytest.raises(budget.OverBudget):
        budget.check("10.0.0.99")


def test_window_expires(budget, monkeypatch):
    t = [1_000_000.0]
    monkeypatch.setattr(budget.time, "time", lambda: t[0])
    for _ in range(3):
        budget.check("1.2.3.4")
    with pytest.raises(budget.OverBudget):
        budget.check("1.2.3.4")
    t[0] += 61
    budget.check("1.2.3.4")  # the window has rolled off


def test_refused_request_never_calls_the_model(budget, monkeypatch):
    from fastapi.testclient import TestClient

    import scripty.app as app_mod
    importlib.reload(app_mod)
    monkeypatch.setattr(app_mod.budget, "PER_IP_ASKS", 1)
    monkeypatch.setattr(app_mod.budget, "DAILY_ASKS", 99)

    called = []

    async def _boom(q):
        called.append(q)
        raise AssertionError("the model must not be reached for a refused request")

    monkeypatch.setattr(app_mod, "ask_async", _boom)
    app_mod.budget._hits.clear()

    c = TestClient(app_mod.app, raise_server_exceptions=False)
    h = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    first = c.post("/api/ask", json={"question": "hi"}, headers=h)
    assert called == ["hi"] or first.status_code == 500  # the one allowed call did reach it
    second = c.post("/api/ask", json={"question": "again"}, headers=h)
    assert second.status_code == 429
    assert second.json()["rate_limited"] is True
    assert int(second.headers["Retry-After"]) > 0
    assert len(called) <= 1


def test_zero_is_a_working_kill_switch(monkeypatch):
    """SCRIPTY_PER_IP_ASKS=0 turns the endpoint off without a redeploy.

    Worth a test because the obvious implementation reads q[0] on an empty
    deque and 500s instead of refusing.
    """
    import importlib

    monkeypatch.setenv("SCRIPTY_PER_IP_ASKS", "0")
    import scripty.budget as b
    b = importlib.reload(b)
    with pytest.raises(b.OverBudget) as e:
        b.check("1.2.3.4")
    assert "switched off" in e.value.detail
    assert e.value.retry_after > 0
