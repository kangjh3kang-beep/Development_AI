"""시장조사보고서 캐시(POST /market/report) + 비동기 잡(POST/GET /market/report/jobs) 배선.

검증 축:
  (a) _aggregate_trade_stats — report['trade'] 기반 trade_count/avg_price_10k 집계(기존
      result['stats'](존재하지 않는 키) 참조 결함 수정 앵커 — 항상 None 이던 trade_count 교정).
  (b) _market_report_signature_parts — build_signature_parts(단일 소유자) 위임, 결정적.
  (c) POST /report 캐시 미스→적재→히트(재분석 0)→refresh=True(재분석 강제) — TestClient 실HTTP.
  (d) POST /report/jobs 캐시 적중 시 즉시 done(job_id=None) — 잡 생략.
  (e) POST /report/jobs 캐시 미스 → pending 잡 발급 → 백그라운드 실행 완료 → GET 폴링 done+result
      (잡 완료 = 히스토리 엔트리: record_user_analysis 호출 검증).
  (f) GET /report/jobs/{id} 소유권 스코프 — 타인 조회 404(IDOR fail-closed).

DB 비의존: analysis_cache.cache_get/cache_put·ledger_adapters.record_user_analysis·
MarketReportService.build_report를 모두 monkeypatch(경량·결정론, 실 Postgres 불요).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.routers import market_report as market_router
from apps.api.routers.market_report import MarketReportRequest

# ─────────────────────────────────────────────────────────────────────────
# (a) _aggregate_trade_stats — 기존 result['stats'] 오참조 버그 수정 앵커
# ─────────────────────────────────────────────────────────────────────────

def test_aggregate_trade_stats_empty_trade_is_honest_none():
    assert market_router._aggregate_trade_stats({}) == (None, None)
    assert market_router._aggregate_trade_stats(None) == (None, None)


def test_aggregate_trade_stats_weighted_average():
    trade = {
        "아파트": {"count": 8, "avg": 6000},
        "연립다세대": {"count": 2, "avg": 3000},
    }
    count, avg = market_router._aggregate_trade_stats(trade)
    assert count == 10
    # (8*6000 + 2*3000) / 10 = 5400
    assert avg == 5400.0


def test_aggregate_trade_stats_all_zero_count_is_zero_not_none():
    trade = {"아파트": {"count": 0, "avg": 0}}
    count, avg = market_router._aggregate_trade_stats(trade)
    assert count == 0
    assert avg is None


# ─────────────────────────────────────────────────────────────────────────
# (b) _market_report_signature_parts — build_signature_parts 위임(단일 소유자)
# ─────────────────────────────────────────────────────────────────────────

def test_market_report_signature_parts_delegates_and_is_deterministic():
    req1 = MarketReportRequest(address="서울 강남 역삼동  123", pnu="1168010100", use_llm=True,
                                options={"b": 1, "a": 2})
    req2 = MarketReportRequest(address="서울 강남 역삼동 123", pnu="1168010100", use_llm=True,
                                options={"a": 2, "b": 1})  # 공백 정규화 + 키 순서만 다름
    parts1 = market_router._market_report_signature_parts(req1, "1168010100")
    parts2 = market_router._market_report_signature_parts(req2, "1168010100")
    assert parts1 == parts2  # 정규화·옵션 키 순서 무관 결정성


def test_market_report_signature_parts_reflects_llm_and_parcels():
    req_a = MarketReportRequest(address="서울", pnu="1168010100", use_llm=True)
    req_b = MarketReportRequest(address="서울", pnu="1168010100", use_llm=False)
    parts_a = market_router._market_report_signature_parts(req_a, "1168010100")
    parts_b = market_router._market_report_signature_parts(req_b, "1168010100")
    assert parts_a != parts_b
    assert parts_a[3] == "True" and parts_b[3] == "False"


# ─────────────────────────────────────────────────────────────────────────
# 공용 테스트 인프라 — DB 비의존 fake cache/ledger
# ─────────────────────────────────────────────────────────────────────────

class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}
        self.get_calls = 0
        self.put_calls = 0

    async def get(self, kind: str, key: str):
        self.get_calls += 1
        return self.store.get((kind, key))

    async def put(self, kind: str, key: str, payload: dict) -> None:
        self.put_calls += 1
        self.store[(kind, key)] = dict(payload)


class _FakeLedger:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_user_analysis(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "content_hash": f"hash-{len(self.calls)}"}


class _User:
    user_id = uuid.uuid4()
    tenant_id = "t1"
    role = "user"


def _patch_common(monkeypatch, *, build_calls: dict, fake_cache: _FakeCache, fake_ledger: _FakeLedger):
    from app.services.market.market_report_service import MarketReportService

    async def _fake_build_report(self, address, lawd_cd, pnu, use_llm=True, options=None, parcels=None):
        build_calls["n"] += 1
        return {
            "address": address, "lawd_cd": lawd_cd, "pnu": pnu,
            "trade": {"아파트": {"count": 10, "avg": 5000}},
        }

    monkeypatch.setattr(MarketReportService, "build_report", _fake_build_report)

    import app.services.common.analysis_cache as cache_mod
    monkeypatch.setattr(cache_mod, "cache_get", fake_cache.get)
    monkeypatch.setattr(cache_mod, "cache_put", fake_cache.put)

    import app.services.ledger.ledger_adapters as la_mod
    monkeypatch.setattr(la_mod, "record_user_analysis", fake_ledger.record_user_analysis)

    # JobStore Redis 프로브 생략(테스트 환경 무네트워크·결정론 — test_job_store.py 관행 미러).
    import time as _t
    market_router._MARKET_STORE._backend = "memory"
    market_router._MARKET_STORE._backend_checked_at = _t.time()


def _build_app(monkeypatch, **fakes) -> FastAPI:
    from app.services.billing import billing_service

    async def _not_blocked(*_a, **_k):
        return False

    monkeypatch.setattr(billing_service, "is_blocked", _not_blocked, raising=False)
    monkeypatch.setattr(billing_service, "team_limit_exceeded", _not_blocked, raising=False)
    _patch_common(monkeypatch, **fakes)

    app = FastAPI()
    app.include_router(market_router.router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    return app


# ─────────────────────────────────────────────────────────────────────────
# (c) POST /report — 캐시 미스→히트→refresh 강제 재분석(실HTTP, TestClient)
# ─────────────────────────────────────────────────────────────────────────

def test_report_cache_miss_then_hit_skips_rebuild(monkeypatch):
    build_calls = {"n": 0}
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    app = _build_app(monkeypatch, build_calls=build_calls, fake_cache=fake_cache, fake_ledger=fake_ledger)
    client = TestClient(app)
    body = {"address": "서울 강남 역삼동", "pnu": "1168010100", "use_llm": False}

    r1 = client.post("/api/v1/market/report", json=body)
    assert r1.status_code == 200, r1.text
    assert build_calls["n"] == 1
    assert fake_cache.put_calls == 1

    r2 = client.post("/api/v1/market/report", json=body)
    assert r2.status_code == 200, r2.text
    assert build_calls["n"] == 1, "캐시 히트는 재분석을 발화하면 안 된다"
    assert r2.json() == r1.json()


def test_report_refresh_true_forces_rebuild(monkeypatch):
    build_calls = {"n": 0}
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    app = _build_app(monkeypatch, build_calls=build_calls, fake_cache=fake_cache, fake_ledger=fake_ledger)
    client = TestClient(app)
    body = {"address": "서울 강남 역삼동", "pnu": "1168010100", "use_llm": False}

    client.post("/api/v1/market/report", json=body)
    assert build_calls["n"] == 1

    r2 = client.post("/api/v1/market/report", json={**body, "refresh": True})
    assert r2.status_code == 200, r2.text
    assert build_calls["n"] == 2, "refresh=True는 저장본을 무시하고 재분석해야 한다"


def test_report_records_ledger_with_signature_materials(monkeypatch):
    build_calls = {"n": 0}
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    app = _build_app(monkeypatch, build_calls=build_calls, fake_cache=fake_cache, fake_ledger=fake_ledger)
    client = TestClient(app)
    client.post("/api/v1/market/report",
                 json={"address": "서울 강남", "pnu": "1168010100", "use_llm": True})

    assert len(fake_ledger.calls) == 1
    call = fake_ledger.calls[0]
    assert call["analysis_type"] == "market_report"
    # ★변동감지 표준키 재료 additive 전달(단일 소유자 ledger_adapters가 조합).
    assert call["parcel_count"] == 1
    assert call["use_llm"] is True
    # 버그 수정 검증: trade_count/avg_price_10k가 (더는 죽은 'stats' 키가 아니라) 'trade'에서 집계됨.
    assert call["summary"]["trade_count"] == 10
    assert call["summary"]["avg_price_10k"] == 5000.0


# ─────────────────────────────────────────────────────────────────────────
# (d)(e) POST /report/jobs — 캐시 적중 즉시 done / 미스 시 pending→완료
# ─────────────────────────────────────────────────────────────────────────

async def test_job_submit_cache_hit_returns_done_without_job(monkeypatch):
    build_calls = {"n": 0}
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    _patch_common(monkeypatch, build_calls=build_calls, fake_cache=fake_cache, fake_ledger=fake_ledger)

    req = MarketReportRequest(address="서울 강남", pnu="1168010100", use_llm=False)
    pnu = "1168010100"
    from app.services.common.analysis_cache import _key
    cache_key = _key(*market_router._market_report_signature_parts(req, pnu))
    fake_cache.store[("market_report", cache_key)] = {"address": "서울 강남", "cached": True}

    current = CurrentUser(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="user")
    out = await market_router.market_report_submit(req, current)
    assert out == {"job_id": None, "status": "done", "result": {"address": "서울 강남", "cached": True}}
    assert build_calls["n"] == 0, "캐시 적중이면 잡을 발급하지 않는다"


async def test_job_submit_cache_miss_then_background_run_completes_and_records_history(monkeypatch):
    build_calls = {"n": 0}
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    _patch_common(monkeypatch, build_calls=build_calls, fake_cache=fake_cache, fake_ledger=fake_ledger)

    req = MarketReportRequest(address="서울 강남", pnu="1168010100", use_llm=False)
    owner = uuid.uuid4()
    current = CurrentUser(user_id=owner, tenant_id=uuid.uuid4(), role="user")

    out = await market_router.market_report_submit(req, current)
    job_id = out["job_id"]
    assert job_id is not None and out["status"] == "pending"

    # 백그라운드 실행을 직접 구동(create_tracked_task의 asyncio 스케줄 타이밍에 의존하지 않고
    # 결정론적으로 완료시킨다 — registry_jobs 테스트와 동일 관행: 실행 경로 자체는 실코드 재사용).
    lawd_cd, pnu = market_router._resolve(req)
    from app.services.common.analysis_cache import _key
    cache_key = _key(*market_router._market_report_signature_parts(req, pnu))
    await market_router._run_market_report_job(job_id, req, lawd_cd, pnu, str(current.tenant_id), cache_key)

    j = await market_router._MARKET_STORE.get(job_id)
    assert j["status"] == "done"
    assert j["result"]["address"] == "서울 강남"
    assert build_calls["n"] == 1
    # 잡 완료 = 히스토리 엔트리(record_user_analysis 호출) — 성장루프 조인키 계약.
    assert len(fake_ledger.calls) == 1
    assert fake_ledger.calls[0]["analysis_type"] == "market_report"
    # 캐시에도 적재되어야 후속 폴링·재요청이 재분석 없이 서비스된다.
    assert fake_cache.put_calls == 1

    market_router._MARKET_JOBS.pop(job_id, None)  # 전역 dict 오염 방지(타 테스트 격리)


# ─────────────────────────────────────────────────────────────────────────
# (f) GET /report/jobs/{id} — 소유권 스코프(IDOR fail-closed)
# ─────────────────────────────────────────────────────────────────────────

def test_job_status_owner_ok_other_user_404(monkeypatch):
    fake_cache, fake_ledger = _FakeCache(), _FakeLedger()
    _patch_common(monkeypatch, build_calls={"n": 0}, fake_cache=fake_cache, fake_ledger=fake_ledger)

    import time as _t

    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    job_id = uuid.uuid4().hex
    market_router._MARKET_JOBS[job_id] = {
        "status": "done", "result": {"ok": True}, "user_id": str(owner_id), "ts": _t.time(),
    }

    app = FastAPI()
    app.include_router(market_router.router)

    def _client_for(user_id):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=user_id, tenant_id=uuid.uuid4(), role="user")
        return TestClient(app)

    r_owner = _client_for(owner_id).get(f"/api/v1/market/report/jobs/{job_id}")
    assert r_owner.status_code == 200
    assert r_owner.json()["status"] == "done"

    r_other = _client_for(other_id).get(f"/api/v1/market/report/jobs/{job_id}")
    assert r_other.status_code == 404  # IDOR fail-closed(존재 비노출)

    market_router._MARKET_JOBS.pop(job_id, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
