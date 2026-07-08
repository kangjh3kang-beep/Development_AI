"""자가성장 엔진 — platform_settings 동적설정 공용 리더(L1 산출물 소비 배선).

L1 자가수정(feature_flags)이 platform_settings 에 기록하는 값(threshold.*/feature.*/
prompt.*)을 런타임 판정 경로가 **실제로 읽게** 하는 단일 접근점이다.
과거엔 기록만 하고 읽는 곳이 없어(write-only dead-end) 자동보정이 무의미했다.

integrations/base_client.py 의 _read_relax_multipliers 검증 패턴을 일반화:
  - 프로세스-로컬 TTL 캐시(핫패스에서 매번 DB 조회 방지, monotonic 시계)
  - best-effort 폴백(DB 미가용·키 부재·예외 → default 그대로, 호출경로 불변)
  - 값 검증은 호출측 헬퍼(as_float 등)로 클램프

TODO(수렴): integrations/base_client.py 의 relax 전용 리더(_read_relax_multipliers)도
이 헬퍼로 수렴 가능하다(키 relax.<service> + 폴백 relax.global). base_client 는
현재 작업의 파일경계 밖이라 여기서는 신설만 하고, 수렴은 후속 스윕에서 진행한다.

사용법:
    # async 경로(분석 배치·L1 사이클 등) — 캐시 미스 시에만 DB 1회 조회.
    val = await dynamic_config.get_dynamic("threshold.fallback_warn_pct", db=db)

    # sync 경로(순수 판정 함수) — 캐시만 조회(DB 무접근). 배치 시작 시 prime 필요.
    val = dynamic_config.get_cached("threshold.fallback_warn_pct")
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

logger = logging.getLogger(__name__)

# TTL(초) — relax 리더(10초)보다 약간 길게. 설정은 L1 사이클(수십분 단위)로만
# 바뀌므로 30초 staleness 는 허용 범위이고, 판정 핫패스의 DB 왕복을 없앤다.
_DYNAMIC_TTL_SEC = 30.0

# (key, scope) → (값, 만료시각 monotonic). 값이 None(미존재/TTL만료)이어도 캐시해
# 키 부재 시 반복 DB 조회를 막는다(negative cache).
_cache: dict[tuple[str, str], tuple[Any, float]] = {}


def reset_cache() -> None:
    """TTL 캐시 전체 초기화(테스트·설정 즉시반영용)."""
    _cache.clear()


def _put(key: str, scope: str, value: Any, ttl: float = _DYNAMIC_TTL_SEC) -> None:
    """캐시 저장(best-effort). 테스트에서 프라임 용도로도 사용."""
    try:
        _cache[(key, scope)] = (value, time.monotonic() + ttl)
    except Exception:  # noqa: BLE001 — 캐시 실패가 호출경로를 깨면 안 됨.
        pass


def get_cached(key: str, default: Any = None, *, scope: str = "global") -> Any:
    """캐시에서만 읽는 sync 리더(DB 무접근) — 순수 판정 함수용.

    캐시 미스(프라임 전·단위테스트)면 default 그대로 → 판정 함수의 stdlib 단독
    검증성이 유지된다. 캐시된 값이 None(설정 미존재)이어도 default 반환.
    """
    try:
        cached = _cache.get((key, scope))
        if cached is not None and cached[1] > time.monotonic():
            return default if cached[0] is None else cached[0]
    except Exception:  # noqa: BLE001
        pass
    return default


async def get_dynamic(key: str, default: Any = None, *, scope: str = "global",
                      db: Any = None) -> Any:
    """platform_settings(key) 값을 TTL 캐시 우선으로 읽는다. 없으면 default.

    - 캐시 히트 → DB 미조회(핫패스 보호).
    - 캐시 미스 → db 가 주어지면 그 세션으로, 아니면 새 세션을 짧게 열어 1회 SELECT.
    - schema_guard.get_setting 이 TTL 만료 설정을 None 처리하므로 자동원복 의미 보존.
    - 어떤 예외에도 default 반환(best-effort — 호출경로 절대 비차단).
    """
    # 1) 프로세스-로컬 TTL 캐시 조회(best-effort).
    try:
        cached = _cache.get((key, scope))
        if cached is not None and cached[1] > time.monotonic():
            return default if cached[0] is None else cached[0]
    except Exception:  # noqa: BLE001 — 캐시 조회 실패는 DB 조회로 폴백.
        pass

    # 2) 미스/만료 → platform_settings 1회 조회(주어진 세션 또는 새 세션).
    try:
        from app.services.growth import schema_guard

        if db is not None:
            value = await schema_guard.get_setting(db, key, scope=scope)
        else:
            from app.core.database import async_session_factory

            async with async_session_factory() as _s:
                value = await schema_guard.get_setting(_s, key, scope=scope)
    except Exception as e:  # noqa: BLE001 — DB 미가용 등은 default 로 조용히 폴백.
        logger.debug("get_dynamic 실패(%s): %s", key, str(e)[:120])
        return default

    # 3) 캐시 저장(None 도 저장 = 키 부재 negative cache).
    _put(key, scope, value)
    return default if value is None else value


def as_float(value: Any, default: float) -> float:
    """설정값에서 유한 양수 float 를 안전하게 추출한다. 실패 시 default.

    L1 임계 자동보정은 {"value": 18.0, "previous": ...} 형태로 저장하므로
    dict 면 "value" 키를, 스칼라면 그대로 해석한다. NaN/무한/0 이하는 비정상으로
    보고 default(폭주·역효과 방지 — relax 리더의 클램프 정신 계승).
    """
    raw = value
    if isinstance(raw, dict):
        raw = raw.get("value")
    try:
        f = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f) or f <= 0:
        return default
    return f


__all__ = ["get_dynamic", "get_cached", "as_float", "reset_cache"]
