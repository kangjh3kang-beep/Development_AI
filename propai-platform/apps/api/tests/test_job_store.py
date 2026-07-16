"""공용 잡 스토어(JobStore) 단위 테스트.

커버리지:
  · 인메모리 폴백 — put/get 왕복·삭제·미존재
  · TTL lazy 프루닝 — get/put 시 만료 잡 제거(② GET 프루닝 요건 포함)
  · 네임스페이스 격리 — Redis 키 프리픽스 + 백킹 dict 분리
  · 폴백 앵커 — Redis 미가용(from_url 실패) 시 memory 백엔드로 확정되고 ops 정상 동작
  · Redis 경로 — SETEX(네임스페이스 키·TTL)·JSON 왕복·default=str 정규화(대역 클라이언트)

테스트 환경엔 Redis 서버가 없어 실제 배선은 인메모리로 폴백된다. 결정론을 위해
_backend를 강제 지정하거나 redis.asyncio.from_url을 실패시켜 네트워크 의존을 제거한다.
"""

from __future__ import annotations

import datetime
import json
import time

from app.services.common.job_store import JobStore


def _boom(*_a, **_k):
    raise RuntimeError("redis unavailable")


class _FakeRedis:
    """Redis 경로 검증용 인메모리 대역(setex/get/delete/ping/aclose)."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def ping(self):
        return True

    async def setex(self, key, ttl, val):
        self.store[key] = (val, ttl)

    async def get(self, key):
        rec = self.store.get(key)
        return rec[0] if rec else None

    async def delete(self, key):
        self.store.pop(key, None)

    async def aclose(self):
        return None


def _memory_store(ns: str = "job:test:", **kw) -> JobStore:
    """프로브를 생략하고 memory 백엔드로 고정한 스토어(결정론·무네트워크)."""
    s = JobStore(ns, **kw)
    s._backend = "memory"  # 테스트 환경 Redis 부재 확정 — 프로브(0.5s 타임아웃) 생략
    return s


def _redis_store(ns: str = "job:reg:") -> tuple[JobStore, _FakeRedis]:
    """redis 백엔드로 고정하고 대역 클라이언트를 주입한 스토어."""
    s = JobStore(ns)
    fake = _FakeRedis()
    s._backend = "redis"
    s._client = fake
    return s, fake


class TestInMemoryFallback:
    async def test_put_get_roundtrip_reuses_backing(self):
        backing: dict = {}
        s = _memory_store(memory_backing=backing)
        await s.put("j1", {"status": "pending", "user_id": "u1"}, 3600)
        got = await s.get("j1")
        assert got is not None
        assert got["status"] == "pending"
        assert got["user_id"] == "u1"
        # 주입한 백킹 dict를 그대로 사용(라우터 전역 dict 재사용 계약).
        assert "j1" in backing

    async def test_get_missing_returns_none(self):
        s = _memory_store()
        assert await s.get("does-not-exist") is None

    async def test_delete_removes(self):
        s = _memory_store()
        await s.put("j", {"status": "done"}, 3600)
        await s.delete("j")
        assert await s.get("j") is None

    async def test_fresh_entry_not_pruned(self):
        s = _memory_store()
        await s.put("j", {"status": "pending"}, 3600)
        got = await s.get("j")
        assert got is not None and got["status"] == "pending"

    async def test_ttl_expiry_lazy_prune_on_get(self):
        backing: dict = {}
        s = _memory_store(memory_backing=backing)
        await s.put("old", {"status": "done"}, 1)
        # ts를 TTL(1s) 이전으로 백데이트 → 다음 get에서 lazy 프루닝 대상.
        backing["old"]["ts"] = time.time() - 10
        assert await s.get("old") is None
        assert "old" not in backing  # ② GET 시에도 만료 잡 제거 확인

    async def test_ttl_expiry_lazy_prune_on_put(self):
        backing: dict = {}
        s = _memory_store(memory_backing=backing)
        await s.put("old", {"status": "done"}, 1)
        backing["old"]["ts"] = time.time() - 10
        # 다른 잡 put 시 프루닝이 함께 돌아 만료 잡 제거(대형 결과 dict 잔존 방지).
        await s.put("fresh", {"status": "pending"}, 3600)
        assert "old" not in backing
        assert "fresh" in backing

    async def test_externally_injected_fresh_kept(self):
        # 라우터/테스트가 백킹 dict에 직접 주입한 항목(_ttl_s 없음)도 default_ttl로 판정.
        backing = {"x": {"status": "done", "user_id": "u", "ts": time.time()}}
        s = _memory_store(memory_backing=backing, default_ttl_s=3600)
        got = await s.get("x")
        assert got is not None and got["user_id"] == "u"

    async def test_externally_injected_stale_pruned(self):
        backing = {"x": {"status": "done", "ts": time.time() - 99999}}
        s = _memory_store(memory_backing=backing, default_ttl_s=3600)
        assert await s.get("x") is None

    async def test_put_does_not_mutate_caller_dict(self):
        s = _memory_store()
        payload = {"status": "pending", "user_id": "u"}
        await s.put("j", payload, 3600)
        # 스토어는 방어적 복사 후 ts/_ttl_s를 부착 → 호출부 원본은 오염되지 않음.
        assert "ts" not in payload and "_ttl_s" not in payload


class TestNamespaceIsolation:
    def test_rkey_applies_prefix(self):
        s = JobStore("job:design_audit:")
        assert s._rkey("abc") == "job:design_audit:abc"

    async def test_separate_backings_isolated(self):
        a = _memory_store("job:a:", memory_backing={})
        b = _memory_store("job:b:", memory_backing={})
        await a.put("dup", {"status": "A"}, 3600)
        await b.put("dup", {"status": "B"}, 3600)
        assert (await a.get("dup"))["status"] == "A"
        assert (await b.get("dup"))["status"] == "B"

    async def test_redis_keys_namespaced_per_store(self):
        # 같은 job_id라도 네임스페이스가 다르면 Redis 키가 분리된다(교차 조회 불가).
        a, fa = _redis_store("job:audit:")
        b, fb = _redis_store("job:registry:")
        await a.put("j", {"who": "audit"}, 3600)
        await b.put("j", {"who": "registry"}, 3600)
        assert "job:audit:j" in fa.store
        assert "job:registry:j" in fb.store


class TestRedisFallbackAnchor:
    """Redis 미가용 시 폴백 발동 자체를 앵커(테스트 환경엔 Redis 서버 부재)."""

    async def test_probe_none_forces_memory_backend(self, monkeypatch):
        import redis.asyncio as aioredis

        # from_url 자체를 실패시켜 '미설치/미가용'을 결정론적으로 재현.
        monkeypatch.setattr(aioredis, "from_url", _boom)
        s = JobStore("job:anchor:")
        client = await s._get_client()
        assert client is None
        assert s._backend == "memory"

    async def test_ops_work_after_fallback(self, monkeypatch):
        import redis.asyncio as aioredis

        monkeypatch.setattr(aioredis, "from_url", _boom)
        backing: dict = {}
        s = JobStore("job:anchor2:", memory_backing=backing)
        await s.put("j", {"status": "pending", "user_id": "u"}, 3600)
        got = await s.get("j")
        assert got is not None and got["user_id"] == "u"
        assert s._backend == "memory"  # 폴백 확정
        assert "j" in backing


class TestRedisPath:
    async def test_put_setex_namespaced_key_and_ttl(self):
        s, fake = _redis_store("job:reg:")
        await s.put("j1", {"status": "done", "n": 3}, 1800)
        assert "job:reg:j1" in fake.store
        val, ttl = fake.store["job:reg:j1"]
        assert ttl == 1800
        assert json.loads(val)["status"] == "done"

    async def test_get_json_roundtrip(self):
        s, _fake = _redis_store()
        await s.put("j", {"status": "pending", "user_id": "u9"}, 3600)
        got = await s.get("j")
        assert got is not None and got["user_id"] == "u9"

    async def test_delete_removes_namespaced(self):
        s, _fake = _redis_store()
        await s.put("j", {"a": 1}, 3600)
        await s.delete("j")
        assert await s.get("j") is None

    async def test_default_str_serialization_non_native(self):
        # datetime 등 비-네이티브 객체도 default=str로 안전 저장(직렬화 예외 없음).
        s, _fake = _redis_store()
        await s.put("j", {"when": datetime.datetime(2026, 7, 17)}, 3600)
        got = await s.get("j")
        assert got is not None and isinstance(got["when"], str)

    async def test_get_missing_returns_none(self):
        s, _fake = _redis_store()
        assert await s.get("absent") is None
