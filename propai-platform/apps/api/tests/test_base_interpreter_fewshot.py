"""base_interpreter._load_fewshot 단위테스트 — 자가학습 few-shot 주입(학습→출력 환류).

async_session_factory를 가짜로 대체해 learning_examples 조회를 모의한다.
테스트 간 _FEWSHOT_CACHE(모듈 TTL) 충돌을 피하려고 service명을 테스트별로 고유화한다.
"""

import asyncio

import app.services.ai.base_interpreter as bi


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


def test_load_fewshot_builds_block(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    _patch_session(monkeypatch, [("입력A 요약", "우수 출력A"), ("입력B 요약", "우수 출력B")])
    out = asyncio.run(bi._load_fewshot("avm_t1"))
    assert out is not None
    assert "참고: 승인된 우수 분석 사례" in out["text"]
    assert "입력A 요약" in out["text"] and "우수 출력A" in out["text"]
    assert "[사례 2]" in out["text"]
    # ★그라운딩 주의(현재 데이터에만 근거)가 반드시 포함 — 환각 유발 방지
    assert "현재 제공된 데이터에만 근거" in out["text"]
    assert len(out["sig"]) == 16


def test_load_fewshot_empty_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    _patch_session(monkeypatch, [])
    assert asyncio.run(bi._load_fewshot("market_t2")) is None


def test_load_fewshot_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", False)
    # 비활성이면 DB 접근 없이 즉시 None
    assert asyncio.run(bi._load_fewshot("cost_t3")) is None


def test_load_fewshot_empty_service_returns_none(monkeypatch):
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    assert asyncio.run(bi._load_fewshot("")) is None


def test_load_fewshot_never_raises(monkeypatch):
    # DB 팩토리가 터져도 None 반환(추론 비차단)
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    assert asyncio.run(bi._load_fewshot("esg_t4")) is None


def test_load_fewshot_caches_empty(monkeypatch):
    # 빈 결과도 캐시 → 두 번째 호출은 DB 접근 없이 None(반복 조회 방지)
    monkeypatch.setattr(bi, "_FEWSHOT_ENABLED", True)
    calls = {"n": 0}

    class _CountingCtx(_FakeSessionCtx):
        async def __aenter__(self):
            calls["n"] += 1
            return _FakeDB([])

    import app.core.database as dbm
    monkeypatch.setattr(dbm, "async_session_factory", lambda: _CountingCtx([]))
    assert asyncio.run(bi._load_fewshot("permit_t5")) is None
    assert asyncio.run(bi._load_fewshot("permit_t5")) is None
    assert calls["n"] == 1  # 두 번째는 캐시 히트(DB 미접근)
