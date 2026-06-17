"""INC-11 — 외부 1차출처 응답 캐시(source_cache) 검증.

캐시는 데이터 확보 단계만 — 적중 시 동일 입력→동일 출력(결정론 영향 0), 미스/실패→graceful None(무음0,
None 미캐시→재시도 허용), secret 비유출(cache_key 제외), snapshot 결속, DB warm/flush 영속.
"""
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.cache import source_cache as sc


def _resp(payload, headers=None):
    class _R:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    r = _R()
    r.headers = headers or {}
    return r


def test_cache_hit_fetches_once_and_same_output(monkeypatch):
    # 적중 → 재호출 없음(쿼터/지연/비용 제거) + 동일 출력(결정론).
    calls = {"n": 0}

    def _get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        return _resp({"v": 1})

    monkeypatch.setattr(httpx, "get", _get)
    a = sc.cached_get("ad", "http://x/y", {"q": "1"})
    b = sc.cached_get("ad", "http://x/y", {"q": "1"})
    assert a == b == {"v": 1}
    assert calls["n"] == 1


def test_secret_excluded_from_cache_key(monkeypatch):
    # 시크릿(key)만 다르고 논리 params 동일 → 동일 cache_key → 적중(키 회전 무관·시크릿 비유출).
    calls = {"n": 0}

    def _get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        return _resp({"v": 2})

    monkeypatch.setattr(httpx, "get", _get)
    sc.cached_get("ad", "http://x", {"key": "K1", "pnu": "P"}, secret_param_keys=("key",))
    sc.cached_get("ad", "http://x", {"key": "K2", "pnu": "P"}, secret_param_keys=("key",))
    assert calls["n"] == 1
    # cache_key 자체에 시크릿 미포함(설명가능성/비유출).
    k1 = sc.cache_key("ad", "http://x", {"pnu": "P"})
    assert sc.get(k1) is not None


def test_none_not_cached_allows_retry(monkeypatch):
    # 실패 → None(미캐시). 이후 성공 → 정상(재시도 허용, 무음 단정 금지).
    state = {"fail": True}

    def _get(url, params=None, timeout=None, headers=None):
        if state["fail"]:
            raise httpx.ConnectError("boom")
        return _resp({"ok": True})

    monkeypatch.setattr(httpx, "get", _get)
    assert sc.cached_get("ad", "http://x", {"q": "1"}) is None
    state["fail"] = False
    assert sc.cached_get("ad", "http://x", {"q": "1"}) == {"ok": True}


def test_ttl_expiry():
    # fetched_at 기준 TTL 초과 → 미스(만료). 미만료는 적중.
    key = sc.cache_key("ad", "http://x", {"q": "1"})
    sc.put(sc.SourceCacheEntry(
        cache_key=key, adapter="ad", endpoint="http://x", params_hash="h", payload={"v": 9},
        fetched_at=datetime.now(timezone.utc) - timedelta(seconds=10)))
    assert sc.get(key, ttl_seconds=100) is not None
    assert sc.get(key, ttl_seconds=1) is None


def test_adapter_routes_through_cache(monkeypatch):
    # 어댑터(MOLIT)가 캐시 경유 — 동일 PNU 2회 조회 시 httpx 1회(분석마다 재호출 제거).
    monkeypatch.setenv("MOLIT_API_KEY", "test-key")
    from app.adapters.regulation.molit_building import MolitBuildingSource

    calls = {"n": 0}

    def _get(url, params=None, timeout=None):
        calls["n"] += 1
        return _resp({"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": {
            "vlRat": "250", "bcRat": "60", "totArea": "100", "mainPurpsCdNm": "X"}}}}})

    monkeypatch.setattr(httpx, "get", _get)
    src = MolitBuildingSource()
    pnu = "1" * 19
    d1 = src.building_basis(pnu)
    d2 = src.building_basis(pnu)
    assert d1 == d2 and d1["far_pct"] == 250.0
    assert calls["n"] == 1


def test_no_key_skips_cache(monkeypatch):
    # 키 없음 → fetch 전 graceful None(캐시 미접근). 기존 무음0 경로 보존.
    monkeypatch.setenv("MOLIT_API_KEY", "")
    from app.adapters.regulation.molit_building import MolitBuildingSource

    def _boom(*a, **k):
        raise AssertionError("키 없음인데 httpx 호출됨")

    monkeypatch.setattr(httpx, "get", _boom)
    assert MolitBuildingSource().building_basis("1" * 19) is None


def test_expired_entry_evicted_on_get():
    # 만료 항목은 get 시 _store에서 회수(메모리 누적 방지).
    sc.clear()
    key = sc.cache_key("ad", "http://x", {"q": "exp"})
    sc.put(sc.SourceCacheEntry(
        cache_key=key, adapter="ad", endpoint="http://x", params_hash="h", payload={"v": 1},
        fetched_at=datetime.now(timezone.utc) - timedelta(seconds=10)), dirty=False)
    assert sc.get(key, ttl_seconds=1) is None
    assert key not in sc._store


async def test_flush_preserves_dirty_on_commit_failure():
    # commit 실패 → dirty 보존(다음 분석 재flush). best-effort라 분석엔 무영향이나 영속 신뢰성 유지.
    import pytest

    sc.clear()
    key = sc.cache_key("ad", "http://x", {"q": "failcommit"})
    sc.put(sc.SourceCacheEntry(
        cache_key=key, adapter="ad", endpoint="http://x", params_hash="h", payload={"v": 1},
        fetched_at=datetime.now(timezone.utc)), dirty=True)

    class _FailSession:
        async def execute(self, stmt):
            return None

        async def commit(self):
            raise RuntimeError("commit boom")

    with pytest.raises(RuntimeError):
        await sc.flush_to_db(_FailSession())
    assert key in sc._dirty  # 선제 clear 아님 — commit 성공분만 해제하므로 보존됨


async def test_db_warm_flush_roundtrip(db):
    # L1 dirty → flush_to_db(L2 영속) → L1 clear → warm_from_db(재적재, snapshot 결속) → 적중(fetch 없이).
    from sqlalchemy import delete

    from app.db.models.cache_models import ExternalSourceCacheModel

    sc.clear()
    key = sc.cache_key("ad", "http://x", {"pnu": "ROUNDTRIP-INC11"})
    await db.execute(delete(ExternalSourceCacheModel).where(
        ExternalSourceCacheModel.cache_key == key))
    await db.commit()
    sc.put(sc.SourceCacheEntry(
        cache_key=key, adapter="ad", endpoint="http://x", params_hash="h", payload={"v": 42},
        fetched_at=datetime.now(timezone.utc), snapshot_id="snap-rt-inc11", status="OK"), dirty=True)

    assert await sc.flush_to_db(db) >= 1
    sc.clear()
    assert sc.get(key) is None  # L1 비움

    assert await sc.warm_from_db(db, "snap-rt-inc11") >= 1
    hit = sc.get(key)
    assert hit is not None and hit.payload == {"v": 42}

    await db.execute(delete(ExternalSourceCacheModel).where(
        ExternalSourceCacheModel.cache_key == key))
    await db.commit()
