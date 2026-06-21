"""전문가 패널(교차리뷰) 결과 캐시 — 토큰 절감(R3).

검증루프②(expert_panel)는 페르소나당 1회만 호출하고, 동일 (persona_key, project_id,
address_hash) 조합은 TTL 동안 캐시 결과를 재사용한다. in-process dict(프로세스 단일워커
운영 가정) — redis 불필요. 실패해도 분석은 계속(graceful).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

_TTL_SECONDS = 1800  # 30분
_STORE: dict[str, tuple[float, dict[str, Any]]] = {}


def _addr_hash(address: str | None) -> str:
    return hashlib.sha256((address or "").strip().encode("utf-8")).hexdigest()[:16]


def make_key(persona_key: str, project_id: str | None, address: str | None) -> str:
    return f"{persona_key}:{project_id or '-'}:{_addr_hash(address)}"


def get(key: str) -> dict[str, Any] | None:
    item = _STORE.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > _TTL_SECONDS:
        _STORE.pop(key, None)
        return None
    return val


def put(key: str, value: dict[str, Any]) -> None:
    _STORE[key] = (time.time(), value)
