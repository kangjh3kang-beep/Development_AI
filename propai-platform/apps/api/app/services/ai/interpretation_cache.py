"""AI 해석 캐시 — 한 번 생성한 단계 해석을 영속 저장해 재열람 시 즉시 표시(LLM 재호출·비용 절감).

키 = sha256(stage + 정규화 data). 해석은 입력 데이터의 결정적 함수라 동일 입력=동일 해석.
런타임 idempotent DDL. 민감정보 아님(분석 파생) → 테넌트 무관 공유 캐시. TTL 30일.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DDL = (
    "CREATE TABLE IF NOT EXISTS interpretation_cache ("
    "  key text PRIMARY KEY, stage text, sections jsonb NOT NULL, created_at timestamptz DEFAULT now())"
)
_TTL = 30 * 24 * 3600


def cache_key(stage: str, data: dict[str, Any]) -> str:
    canon = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{stage}|{canon}".encode()).hexdigest()


async def get_cached(key: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text(_DDL)); await db.commit()
            row = (await db.execute(text(
                "SELECT sections, extract(epoch from created_at) AS ts "
                "FROM interpretation_cache WHERE key = :k"), {"k": key})).first()
            if row and row[0] and (time.time() - float(row[1] or 0)) < _TTL:
                return row[0]
    except Exception as e:  # noqa: BLE001
        logger.warning("해석 캐시 조회 실패", err=str(e)[:100])
    return None


async def put_cached(key: str, stage: str, sections: dict[str, Any]) -> None:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text(_DDL))
            await db.execute(text(
                "INSERT INTO interpretation_cache(key, stage, sections, created_at) "
                "VALUES (:k, :s, CAST(:v AS jsonb), now()) "
                "ON CONFLICT (key) DO UPDATE SET sections = EXCLUDED.sections, created_at = now()"),
                {"k": key, "s": stage, "v": json.dumps(sections, ensure_ascii=False)})
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("해석 캐시 저장 실패", err=str(e)[:100])
