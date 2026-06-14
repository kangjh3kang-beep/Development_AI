"""범용 LLM 분석 결과 영속 캐시.

플랫폼 원칙: 무거운 분석은 1회 → DB 저장 → 재사용.
사용자가 명시적으로 force_refresh를 요청할 때만 재분석한다.

패턴: ordinance_service.py의 _load_stored/_save_resolution 그대로 본뜸.
- 멱등 DDL(CREATE TABLE IF NOT EXISTS) + 프로세스 1회 ensure 플래그
- best-effort(실패해도 분석 결과 무손상)
- async_session_factory 직접 사용(외부 세션 의존 없음)
"""

import hashlib
import json
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── 테이블 DDL: kind(분석 종류) + cache_key(입력 해시) 복합 PK ──
_CACHE_DDL = (
    "CREATE TABLE IF NOT EXISTS analysis_cache ("
    "  kind varchar(40) NOT NULL,"
    "  cache_key varchar(200) NOT NULL,"
    "  payload jsonb NOT NULL,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  PRIMARY KEY (kind, cache_key)"
    ")"
)
# 프로세스 1회만 DDL 실행(재실행 방지)
_CACHE_READY = False


def _key(*parts: str) -> str:
    """여러 입력값을 '|'로 연결해 sha256 해시(앞 40자)로 변환.

    긴 주소·복잡한 옵션 조합도 안전하게 고정길이 키로 압축한다.
    """
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


async def _ensure_cache_table(db) -> None:
    """테이블이 없으면 생성. 프로세스당 1회만 실행."""
    global _CACHE_READY
    if _CACHE_READY:
        return
    await db.execute(text(_CACHE_DDL))
    await db.commit()
    _CACHE_READY = True


async def cache_get(kind: str, key: str) -> dict | None:
    """저장된 분석 결과를 반환(없으면 None).

    반환값에 _cache 필드를 부착해 클라이언트가 캐시 여부를 알 수 있게 한다.
    실패 시 None 반환(best-effort, 분석 흐름 무손상).
    """
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure_cache_table(db)
            row = (await db.execute(
                text(
                    "SELECT payload, created_at FROM analysis_cache"
                    " WHERE kind=:kind AND cache_key=:key"
                ),
                {"kind": kind, "key": key},
            )).first()
            if row is None:
                return None
            payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            # 캐시 메타정보를 별도 필드로 부착(기존 응답 구조 무손상)
            payload["_cache"] = {
                "cached": True,
                "created_at": str(row[1]),
            }
            return payload
    except Exception:  # noqa: BLE001 — 캐시 조회 실패는 실시간 분석으로 진행
        return None


async def cache_put(kind: str, key: str, payload: dict) -> None:
    """분석 결과를 DB에 upsert 저장.

    동일 (kind, key)가 이미 있으면 덮어쓴다(force_refresh 사용 사례).
    실패해도 분석 결과는 그대로 반환되므로 best-effort로 처리.
    """
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure_cache_table(db)
            await db.execute(
                text(
                    "INSERT INTO analysis_cache (kind, cache_key, payload, created_at)"
                    " VALUES (:kind, :key, CAST(:payload AS jsonb), now())"
                    " ON CONFLICT (kind, cache_key)"
                    " DO UPDATE SET payload=CAST(:payload AS jsonb), created_at=now()"
                ),
                {
                    "kind": kind,
                    "key": key,
                    "payload": json.dumps(payload, ensure_ascii=False, default=str),
                },
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — 저장 실패는 분석 결과를 손상하지 않는다
        pass
