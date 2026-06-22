"""base_interpreter._load_fewshot 단위테스트 — 자가학습 few-shot 주입(학습→출력 환류).

async_session_factory를 가짜로 대체해 learning_examples 조회를 모의한다.
★테넌트 스코핑: _load_fewshot은 get_current_tenant_id()의 현재 테넌트 예시만 사용하므로
테스트는 set_current_tenant_id로 테넌트를 주입한다(없으면 None 반환=교차테넌트 차단).
테스트 간 _FEWSHOT_CACHE(모듈 TTL) 충돌을 피하려 service명을 테스트별로 고유화한다.
"""

import asyncio

import app.services.ai.base_interpreter as bi
from app.core.request_context import set_current_tenant_id


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _FakeResult(self._rows)


class _FakeSessionCtx:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return _FakeDB(self._rows)

    async def __aexit__(self, *a):
        return False


def _patch_session(monkeypatch, rows):
    import app.core.database as dbm
    monkeypatch.setattr(dbm, "async_session_factory", lambda: _FakeSessionCtx(rows))


def _run_with_tenant(coro_factory, tenant):
    """테넌트 컨텍스트를 설정하고 코루틴 실행(후 원복) — contextvar 누수 방지."""
    set_current_tenant_id(tenant)
    try:
        return asyncio.run(coro_factory())
    finally:
        set_current_tenant_id(None)


def test_load_fewshot_builds_block(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    _patch_session(monkeypatch, [("입력A 요약", "우수 출력A"), ("입력B 요약", "우수 출력B")])
    out = _run_with_tenant(lambda: bi._load_fewshot("avm_t1"), "T1")
    assert out is not None
    assert "참고: 승인된 우수 분석 사례" in out["text"]
    assert "입력A 요약" in out["text"] and "우수 출력A" in out["text"]
    assert "[사례 2]" in out["text"]
    # ★그라운딩 주의(현재 데이터에만 근거)가 반드시 포함 — 환각 유발 방지
    assert "현재 제공된 데이터에만 근거" in out["text"]
    assert len(out["sig"]) == 16


def test_load_fewshot_no_tenant_returns_none(monkeypatch):
    # ★테넌트 컨텍스트 없으면 예시 있어도 None(교차테넌트 누출 차단·by-construction)
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    _patch_session(monkeypatch, [("입력", "출력")])
    set_current_tenant_id(None)
    assert asyncio.run(bi._load_fewshot("avm_notenant")) is None


def test_load_fewshot_empty_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    _patch_session(monkeypatch, [])
    assert _run_with_tenant(lambda: bi._load_fewshot("market_t2"), "T1") is None


def test_load_fewshot_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", False)
    # 비활성이면 테넌트/DB 접근 없이 즉시 None
    assert _run_with_tenant(lambda: bi._load_fewshot("cost_t3"), "T1") is None


def test_load_fewshot_empty_service_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    assert _run_with_tenant(lambda: bi._load_fewshot(""), "T1") is None


def test_load_fewshot_never_raises(monkeypatch):
    # DB 팩토리가 터져도 None 반환(추론 비차단)
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    assert _run_with_tenant(lambda: bi._load_fewshot("esg_t4"), "T1") is None


def test_load_fewshot_caches_empty_per_tenant(monkeypatch):
    # 빈 결과도 (service,tenant)별 캐시 → 두 번째 호출은 DB 접근 없이 None
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    calls = {"n": 0}

    class _CountingCtx(_FakeSessionCtx):
        async def __aenter__(self):
            calls["n"] += 1
            return _FakeDB([])

    import app.core.database as dbm
    monkeypatch.setattr(dbm, "async_session_factory", lambda: _CountingCtx([]))
    assert _run_with_tenant(lambda: bi._load_fewshot("permit_t5"), "T1") is None
    assert _run_with_tenant(lambda: bi._load_fewshot("permit_t5"), "T1") is None
    assert calls["n"] == 1  # 두 번째는 캐시 히트(DB 미접근)


def test_load_fewshot_cache_separated_by_tenant(monkeypatch):
    # 동일 service라도 테넌트가 다르면 캐시 분리(교차테넌트 캐시 혼선 차단)
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    calls = {"n": 0}

    class _CountingCtx(_FakeSessionCtx):
        async def __aenter__(self):
            calls["n"] += 1
            return _FakeDB([])

    import app.core.database as dbm
    monkeypatch.setattr(dbm, "async_session_factory", lambda: _CountingCtx([]))
    assert _run_with_tenant(lambda: bi._load_fewshot("svc_multi"), "TA") is None
    assert _run_with_tenant(lambda: bi._load_fewshot("svc_multi"), "TB") is None
    assert calls["n"] == 2  # 테넌트별 별도 조회(캐시 키 분리)
