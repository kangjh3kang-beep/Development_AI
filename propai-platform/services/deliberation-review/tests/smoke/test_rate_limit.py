"""security — 레이트리밋(분당 클라이언트별 상한). 리미터 로직(결정론 clock) + 미들웨어 429/면제."""
from __future__ import annotations

from app.core.rate_limit import FixedWindowRateLimiter


def test_limiter_blocks_over_limit():
    t = [1000.0]
    lim = FixedWindowRateLimiter(2, clock=lambda: t[0])
    assert lim.check("a") is True   # 1
    assert lim.check("a") is True   # 2
    assert lim.check("a") is False  # 3 > 2 → 차단
    assert lim.check("b") is True   # 다른 키는 독립 카운터


def test_limiter_resets_next_window():
    t = [1000.0]
    lim = FixedWindowRateLimiter(1, clock=lambda: t[0])
    assert lim.check("a") is True
    assert lim.check("a") is False
    t[0] += 60.0  # 다음 분 창 → 리셋
    assert lim.check("a") is True


def test_limiter_disabled_when_zero():
    lim = FixedWindowRateLimiter(0)
    assert lim.enabled is False
    for _ in range(50):
        assert lim.check("anyone") is True  # 비활성 — 무한 허용


def test_middleware_returns_429_over_limit(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import settings

    monkeypatch.setattr(settings, "REQUESTS_PER_MINUTE", 1)
    client = TestClient(create_app())
    statuses = [client.get("/nonexistent").status_code for _ in range(5)]
    assert 429 in statuses  # 상한 초과 → 차단(미들웨어가 라우팅 전 적용)


def test_middleware_exempts_health(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import settings

    monkeypatch.setattr(settings, "REQUESTS_PER_MINUTE", 1)
    client = TestClient(create_app())
    # /health는 가용성 프로브 → 폭주해도 레이트리밋 면제.
    assert all(client.get("/health").status_code == 200 for _ in range(5))
