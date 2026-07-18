"""시세추이 경량 엔드포인트(GET /market/trend) 테스트.

배경: 시세추이 차트가 보고서 생성(MOLIT 4유형+SGIS+KOSIS+LLM) 결과에만 의존해, 12~24개월
추이를 보려면 보고서 전체 재생성이 필요했다(낭비). GET /market/trend는 아파트 매매 월별
평당가만 산출한다(MarketReportService.build_trend_only → _apt_trend 공용 재사용, 신규 산식 0 —
market_report_trend_months 테스트가 검증하는 _resolve_trend_months/_apt_trend 재사용 원칙 위임).

검증 축:
  A. _trend_cache_is_fresh — TTL(6시간) 판정(신선/만료/메타없음/파싱실패).
  B. GET /market/trend — 캐시 미스(MOLIT 호출 1회+캐시 적재) → 히트(재호출 0) → 만료 시 재조회.
  C. months 클램프(1~24, _resolve_trend_months 재사용) — 상/하한.
  D. 응답 계약: {months, trend:[{ym, avg_per_pyeong}], source, cached}. lawd_cd 미해석 400.

DB 비의존: analysis_cache.cache_get/cache_put·MarketReportService.build_trend_only 모두
monkeypatch(경량·결정론, 실 Postgres·MOLIT 불요).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.routers import market_report as market_router

# ─────────────────────────────────────────────────────────────────────────
# A. _trend_cache_is_fresh — TTL(6시간) 판정
# ─────────────────────────────────────────────────────────────────────────


def test_trend_cache_is_fresh_none_and_empty_are_stale():
    assert market_router._trend_cache_is_fresh(None) is False
    assert market_router._trend_cache_is_fresh({}) is False
    assert market_router._trend_cache_is_fresh({"_cache": {}}) is False


def test_trend_cache_is_fresh_bad_timestamp_is_stale():
    assert market_router._trend_cache_is_fresh({"_cache": {"created_at": "not-a-date"}}) is False


def test_trend_cache_is_fresh_within_ttl_is_fresh():
    now = datetime.now(UTC)
    cached = {"_cache": {"created_at": str(now - timedelta(hours=1))}}
    assert market_router._trend_cache_is_fresh(cached) is True


def test_trend_cache_is_fresh_beyond_ttl_is_stale():
    now = datetime.now(UTC)
    cached = {"_cache": {"created_at": str(now - timedelta(hours=7))}}
    assert market_router._trend_cache_is_fresh(cached) is False


# ─────────────────────────────────────────────────────────────────────────
# 공용 테스트 인프라 — DB 비의존 fake cache(cache_get의 _cache 메타 부착 동작 재현)
# ─────────────────────────────────────────────────────────────────────────


class _FakeTrendCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}
        self.get_calls = 0
        self.put_calls = 0

    async def get(self, kind: str, key: str):
        self.get_calls += 1
        row = self.store.get((kind, key))
        if row is None:
            return None
        payload = dict(row["payload"])
        payload["_cache"] = {"cached": True, "created_at": row["created_at"]}
        return payload

    async def put(self, kind: str, key: str, payload: dict) -> None:
        self.put_calls += 1
        self.store[(kind, key)] = {
            "payload": dict(payload),
            "created_at": str(datetime.now(UTC)),
        }

    def seed(self, kind: str, key: str, payload: dict, *, created_at: datetime) -> None:
        self.store[(kind, key)] = {"payload": dict(payload), "created_at": str(created_at)}


def _build_app(monkeypatch, fake_cache: _FakeTrendCache, build_calls: dict) -> FastAPI:
    from app.services.market.market_report_service import MarketReportService

    async def _fake_build_trend_only(self, lawd_cd, months_n=12):
        build_calls["n"] += 1
        build_calls["last"] = (lawd_cd, months_n)
        return [
            {"ym": "202605", "avg": 50000, "avg_per_pyeong": 3000, "count": 5},
            {"ym": "202606", "avg": 51000, "avg_per_pyeong": 3100, "count": 6},
        ]

    monkeypatch.setattr(MarketReportService, "build_trend_only", _fake_build_trend_only)

    import app.services.common.analysis_cache as cache_mod
    monkeypatch.setattr(cache_mod, "cache_get", fake_cache.get)
    monkeypatch.setattr(cache_mod, "cache_put", fake_cache.put)

    app = FastAPI()
    app.include_router(market_router.router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="user")
    return app


# ─────────────────────────────────────────────────────────────────────────
# B/D. 캐시 미스 → 히트 → 만료 재조회, 응답 계약
# ─────────────────────────────────────────────────────────────────────────


def test_trend_cache_miss_calls_build_once_and_caches(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    r = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    assert build_calls["n"] == 1
    assert fake_cache.put_calls == 1
    assert body == {
        "months": 12,
        "trend": [
            {"ym": "202605", "avg_per_pyeong": 3000},
            {"ym": "202606", "avg_per_pyeong": 3100},
        ],
        "source": "molit",
        "cached": False,
    }


def test_trend_cache_hit_skips_molit_call(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    r1 = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 12})
    assert build_calls["n"] == 1

    r2 = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 12})
    assert r2.status_code == 200, r2.text
    assert build_calls["n"] == 1, "캐시 신선(6시간 이내)이면 MOLIT을 재호출하면 안 된다"
    assert r2.json()["cached"] is True
    assert r2.json()["source"] == "cache"
    assert r2.json()["trend"] == r1.json()["trend"]


def test_trend_cache_stale_beyond_ttl_refetches(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    from app.services.common.analysis_cache import _key
    cache_key = _key("11680", 12)
    fake_cache.seed(
        "market_trend", cache_key,
        {"months": 12, "trend": [{"ym": "202501", "avg_per_pyeong": 2000}], "source": "molit", "cached": False},
        created_at=datetime.now(UTC) - timedelta(hours=7),
    )

    r = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 12})
    assert r.status_code == 200, r.text
    assert build_calls["n"] == 1, "6시간 초과 캐시는 stale — 재조회해야 한다"
    assert r.json()["cached"] is False


# ─────────────────────────────────────────────────────────────────────────
# C. months 클램프(1~24, _resolve_trend_months 재사용)
# ─────────────────────────────────────────────────────────────────────────


def test_trend_months_clamped_to_upper_bound(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    r = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 999})
    assert r.status_code == 200, r.text
    assert r.json()["months"] == 24
    assert build_calls["last"][1] == 24


def test_trend_months_clamped_to_lower_bound(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    r = client.get("/api/v1/market/trend", params={"pnu": "1168010100", "months": 0})
    assert r.status_code == 200, r.text
    assert r.json()["months"] == 1


def test_trend_missing_location_returns_400(monkeypatch):
    build_calls = {"n": 0}
    fake_cache = _FakeTrendCache()
    app = _build_app(monkeypatch, fake_cache, build_calls)
    client = TestClient(app)

    r = client.get("/api/v1/market/trend", params={"months": 12})  # pnu·bcode 모두 없음
    assert r.status_code == 400
    assert build_calls["n"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
