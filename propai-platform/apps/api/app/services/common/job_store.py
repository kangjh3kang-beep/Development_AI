"""공용 비동기 잡(작업) 스토어 — Redis 우선·인메모리 폴백.

design_audit(`_AUDIT_JOBS`)·registry(`_JOBS`) 등 여러 라우터가 각자 들고 있던
**프로세스-로컬 in-memory dict**를 단일 공용 계약(get/put/delete)으로 통일한다.

왜(R1 잔여 봉합):
  단일 워커 배포에서는 in-memory dict로 충분하지만, **블루그린 컷오버** 중 신 컨테이너로
  트래픽이 넘어가면 구 컨테이너에서 발급된 in-flight 잡을 신 컨테이너가 폴링할 때 404가 난다
  (프로세스 경계를 넘지 못함). Redis가 설정돼 있으면 SETEX 네이티브 만료로 잡을 프로세스 밖
  (컷오버·다중 워커)에서도 공유해 이 단절을 봉합한다.

무악화(★핵심):
  Redis 미설정/연결 실패 시 **인메모리 dict로 폴백**해 현재 단일 워커 동작을 그대로 보존한다
  (현재와 동일 동작). 폴백 사실은 프로세스 1회만 로그한다.

연결 관례 재사용(신규 커넥션 풀 미신설):
  저장소 정본(`app/services/ai/base_interpreter._redis_get/_set`)이 쓰는
  `redis.asyncio.from_url(settings.REDIS_URL)` 관례를 그대로 재사용한다. 최초 1회 프로브로
  백엔드(redis|memory)를 확정하고 클라이언트를 재사용한다(폴백 확정 후엔 재프로브 없음 →
  Redis 부재 환경에서 매 폴링마다 연결 타임아웃이 반복되지 않는다).

TTL:
  · Redis 경로 — SETEX(ttl_s)로 네이티브 만료(별도 프루닝 불필요).
  · 인메모리 폴백 — 값에 저장한 `ts`(마지막 기록 시각)+`_ttl_s`를 기준으로 get/put 시
    lazy 프루닝한다(만료 잡 잔존 방지 — GET 정지 시 대형 결과 dict가 남던 결함 포함 해소).

직렬화(JSON-safe):
  Redis 경로는 `json.dumps(..., default=str)`(analysis_cache·base_interpreter 관례)로
  직렬화한다 — 혹시 섞일 datetime/UUID/Decimal 등 비-네이티브 객체도 문자열로 안전 저장한다
  (상태 폴링 결과는 어차피 HTTP에서 JSON 직렬화되므로 손실 없음). 인메모리 경로는 원본 파이썬
  객체를 그대로 보관한다.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 폴백(인메모리) 확정 로그는 프로세스 전역 1회만(스토어가 여러 개여도 소음 억제).
_FALLBACK_LOGGED = False


class JobStore:
    """네임스페이스 스코프 비동기 잡 스토어(Redis 우선·인메모리 폴백).

    계약:
      · ``await get(job_id) -> dict | None``
      · ``await put(job_id, data: dict, ttl_s: int) -> None``
      · ``await delete(job_id) -> None``

    Args:
        namespace: Redis 키 프리픽스(예: ``"job:design_audit:"``·``"job:registry:"``).
            서로 다른 라우터의 잡이 같은 Redis 인스턴스에서 충돌하지 않게 격리한다.
        memory_backing: 인메모리 폴백이 사용할 백킹 dict. 라우터의 기존 전역 잡 dict
            (`_AUDIT_JOBS`/`_JOBS`)를 그대로 주입하면 폴백 경로 동작이 바이트까지 보존되고,
            기존 테스트(전역 dict 직접 조작)도 자연 통과한다. 미지정 시 새 dict 생성.
        default_ttl_s: 인메모리 프루닝 기본 TTL(값에 `_ttl_s`가 없을 때 — 외부에서 직접
            주입된 항목 등).
    """

    def __init__(
        self,
        namespace: str,
        *,
        memory_backing: dict[str, dict[str, Any]] | None = None,
        default_ttl_s: int = 3600,
    ) -> None:
        self._ns = namespace
        self._mem: dict[str, dict[str, Any]] = (
            memory_backing if memory_backing is not None else {}
        )
        self._default_ttl = int(default_ttl_s)
        # 백엔드 결정 캐시: None=미결정, "redis", "memory".
        self._backend: str | None = None
        self._backend_checked_at: float = 0.0
        self._client: Any = None  # redis 모드 시 재사용 클라이언트

    def _rkey(self, job_id: str) -> str:
        return f"{self._ns}{job_id}"

    # ── 백엔드 선택(최초 1회 프로브 후 캐시) ──────────────────────────────────
    async def _probe_redis(self) -> Any:
        """Redis 연결 가능 시 클라이언트, 아니면 None(base_interpreter 관례 재사용)."""
        client = None
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415

            from app.core.config import settings  # noqa: PLC0415

            client = aioredis.from_url(
                settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            await client.ping()
            return client
        except Exception:  # noqa: BLE001 — 미설정/연결실패 모두 폴백(무악화)
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.aclose()
            return None

    # memory 폴백 확정 후 재프로브 간격(초) — 블루그린 컷오버 등 Redis "순단 중 부팅"이
    # 프로세스 수명 내내 memory 고착되지 않도록(R1 적발). 순단 복구 후 첫 접근에서 redis 승격.
    _REPROBE_INTERVAL_S = 60.0

    async def _get_client(self) -> Any:
        """redis 모드면 재사용 클라이언트, memory 모드면 None(단, 주기 재프로브)."""
        global _FALLBACK_LOGGED
        if self._backend == "memory":
            if time.time() - self._backend_checked_at < self._REPROBE_INTERVAL_S:
                return None
            # 재프로브 창 — 실패하면 다시 memory 로(아래 공통 경로).
            self._backend = None
        if self._backend == "redis":
            return self._client
        self._backend_checked_at = time.time()
        client = await self._probe_redis()
        if client is not None:
            self._backend = "redis"
            self._client = client
            return client
        self._backend = "memory"
        if not _FALLBACK_LOGGED:
            logger.info(
                "job_store: Redis 미가용 — 인메모리 폴백(단일 워커 동작 보존, 무악화)"
            )
            _FALLBACK_LOGGED = True
        return None

    # ── 인메모리 lazy 프루닝(get/put 시) ──────────────────────────────────────
    def _prune_mem(self) -> None:
        now = time.time()
        expired = [
            k
            for k, v in self._mem.items()
            if not isinstance(v, dict)
            or now - float(v.get("ts", 0) or 0) > float(v.get("_ttl_s", self._default_ttl))
        ]
        for k in expired:
            self._mem.pop(k, None)

    # ── 공용 계약 ─────────────────────────────────────────────────────────────
    async def get(self, job_id: str) -> dict[str, Any] | None:
        client = await self._get_client()
        if client is not None:
            try:
                raw = await client.get(self._rkey(job_id))
            except Exception:  # noqa: BLE001 — Redis 조회 실패는 best-effort(미존재 취급)
                return None
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return None
        # 인메모리 폴백: get 시에도 만료분 정리(② GET 프루닝 요건 충족).
        self._prune_mem()
        return self._mem.get(job_id)

    async def put(self, job_id: str, data: dict[str, Any], ttl_s: int) -> None:
        # ★두 백엔드가 '동일한 JSON'을 저장하도록 선(先)정규화(R1 적발) — 종전엔 Redis 만
        #   default=str 로 Decimal→"문자열"·datetime→비ISO 가 되어 프로덕션에서만 타입이 갈렸다.
        #   jsonable_encoder 는 FastAPI 응답 직렬화와 동일 규칙(Decimal→number·datetime→ISO).
        from fastapi.encoders import jsonable_encoder

        payload = jsonable_encoder(data)
        client = await self._get_client()
        if client is not None:
            try:
                await client.setex(
                    self._rkey(job_id),
                    max(1, int(ttl_s)),
                    json.dumps(payload, ensure_ascii=False),
                )
                return
            except Exception:  # noqa: BLE001 — Redis 순단 시 memory 미러로 fail-open(R1 적발:
                pass  #   종전 무음 폐기는 봉합하려던 404 를 재도입했다)
        # 인메모리(폴백 또는 Redis put 실패 미러): ts/_ttl_s 부착(lazy 프루닝 기준) 후 저장.
        entry = dict(payload)
        entry["ts"] = time.time()
        entry["_ttl_s"] = int(ttl_s)
        self._prune_mem()
        self._mem[job_id] = entry

    async def delete(self, job_id: str) -> None:
        client = await self._get_client()
        if client is not None:
            with contextlib.suppress(Exception):
                await client.delete(self._rkey(job_id))
            return
        self._mem.pop(job_id, None)
