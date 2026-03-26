"""멀티테넌트 Redis 캐시 관리.

모든 키에 ``propai:{tenant_id}:`` 접두사를 부여하여
테넌트 간 키 충돌을 원천 차단한다.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from apps.api.config import get_settings


class TenantCache:
    """테넌트 격리 Redis 캐시.

    Parameters
    ----------
    tenant_id : UUID
        현재 테넌트 식별자. 모든 키 앞에 ``propai:{tenant_id}:`` 접두사가 붙는다.
    """

    _PREFIX = "propai"

    def __init__(self, tenant_id: UUID) -> None:
        self.tenant_id = tenant_id
        settings = get_settings()
        self._redis: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.redis_url,
            decode_responses=True,
        )

    def _key(self, key: str) -> str:
        """테넌트 격리 접두사가 포함된 전체 키를 반환한다."""
        return f"{self._PREFIX}:{self.tenant_id}:{key}"

    async def get(self, key: str) -> Any | None:
        """캐시에서 값을 조회한다. 없으면 ``None``."""
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
    ) -> None:
        """캐시에 값을 저장한다.

        Parameters
        ----------
        key : str
            캐시 키 (접두사 자동 부여).
        value : Any
            JSON 직렬화 가능한 값.
        ttl : int
            만료 시간(초). 기본 3600초(1시간).
        """
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        await self._redis.set(self._key(key), serialized, ex=ttl)

    async def delete(self, key: str) -> None:
        """캐시에서 키를 삭제한다."""
        await self._redis.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        """키 존재 여부를 확인한다."""
        return bool(await self._redis.exists(self._key(key)))

    async def flush_tenant(self) -> None:
        """현재 테넌트의 모든 캐시를 삭제한다.

        SCAN 기반으로 접두사 매칭 후 일괄 삭제하므로
        다른 테넌트의 키에는 영향을 주지 않는다.
        """
        pattern = f"{self._PREFIX}:{self.tenant_id}:*"
        cursor: int | str = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=int(cursor), match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def close(self) -> None:
        """Redis 연결을 정리한다."""
        await self._redis.aclose()
