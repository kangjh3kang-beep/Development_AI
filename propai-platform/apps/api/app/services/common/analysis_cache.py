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
from datetime import UTC

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


# ── LLM 폴백 캐시오염 방지(2026-07-22 라이브 실측) ────────────────────────────
# 규제분석에서 간헐 LLM 파싱 실패의 폴백("AI 해석 일시 미제공")이 영속 캐시에 박제되어,
# 이후 모든 조회가 refresh 전까지 영원히 폴백을 반환하는 결함이 실측됐다(자가치유 불가).
# 동일 패턴이 permits·market_report에도 존재 — 판정 술어를 여기 한 곳으로 공용화한다.

# 오염 캐시 재시도 유예(초) — 즉시 miss 취급하면 폴백이 반복되는 동안 호출마다 LLM 재시도
# 비용(토큰 과금·수십 초 지연)이 발생하므로, 유예 내에는 캐시본을 그대로 반환해 폭주를 막는다.
LLM_FALLBACK_RETRY_SEC = 300


def llm_fallback_present(payload) -> bool:
    """캐시된 분석 결과에 'LLM 해석 폴백(미생성)' 마커가 있는지 판정.

    알려진 마커(각 서비스의 폴백 계약): regulation `ai.generated=False` ·
    permits `ai=False`(불리언) · market_report `narrative.generated=False`.
    마커가 '없는' 경우(use_llm=False 경로 등)는 폴백으로 보지 않는다(무해).
    """
    if not isinstance(payload, dict):
        return False
    ai = payload.get("ai")
    if ai is False:
        return True
    if isinstance(ai, dict) and ai.get("generated") is False:
        return True
    narrative = payload.get("narrative")
    if isinstance(narrative, dict) and narrative.get("generated") is False:
        return True
    return False


def llm_fallback_stale(cached) -> bool:
    """오염(LLM 폴백) 캐시이면서 재시도 유예가 지났는지 — True면 miss로 취급해 자가치유.

    라우터 사용 계약: `if cached is not None and not (use_llm and llm_fallback_stale(cached)):
    return cached`. 재분석이 성공하면 cache_put(upsert)이 오염본을 덮어써 치유가 완결되고,
    또 실패하면 폴백이 다시 저장되며 created_at이 갱신돼 유예가 재설정된다(재시도 폭주 방지).
    """
    if not llm_fallback_present(cached):
        return False
    created = None
    meta = cached.get("_cache") if isinstance(cached, dict) else None
    if isinstance(meta, dict):
        created = meta.get("created_at")
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(created))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age_sec = (datetime.now(UTC) - dt).total_seconds()
        return age_sec >= LLM_FALLBACK_RETRY_SEC
    except Exception:  # noqa: BLE001 — 메타 결손/파싱 실패는 재시도 허용(치유 우선)
        return True
