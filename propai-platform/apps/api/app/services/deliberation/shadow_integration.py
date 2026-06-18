"""중심엔진 수렴 — 도메인 분석의 best-effort shadow 비교 오케스트레이션(운영 무중단).

도메인(comprehensive/design_audit/area 등)이 자신의 platform_verdict + 엔진 입력(payload)을 넘기면,
엔진을 best-effort로 호출해 대표 verdict를 뽑아 shadow_service.record로 divergence를 적재한다.
**불변식**: 설정 off(deliberation_shadow_enabled=False)·엔진 미설정·매핑 부적합·임의 실패 시 None을 반환하고
어떤 예외도 도메인 흐름으로 전파하지 않는다(관측 전용·운영 무중단). 충분한 일치 관측 후 authoritative 승격.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.services.deliberation import shadow_service
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
    build_input_dump,
    prevalidate,
)
from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# 엔진 findings verdict → 보수적 대표 등급(최악 우선). 도메인 단일 verdict와 비교용.
_SEVERITY = {"non_compliant": 3, "needs_review": 2, "compliant": 1, "": 0}


def engine_overall_verdict(result: dict[str, Any]) -> str | None:
    """엔진 AnalysisResult(dict)의 findings 중 **최악 등급**을 대표 판정으로(보수적). findings 없으면 None."""
    if not isinstance(result, dict):
        return None
    worst, worst_sev = None, -1
    for f in result.get("findings") or []:
        v = shadow_service.norm_verdict((f or {}).get("verdict"))
        sev = _SEVERITY.get(v, 0)
        if sev > worst_sev:
            worst, worst_sev = v, sev
    return worst


async def shadow_compare(*, tenant_id: str, domain: str, platform_verdict: Any,
                         engine_payload: dict[str, Any], platform_value: Any = None) -> dict[str, Any] | None:
    """best-effort shadow 비교·적재. 도메인 흐름 절대 방해 금지(off/실패 시 None)."""
    s = get_settings()
    if not getattr(s, "deliberation_shadow_enabled", False) or not s.deliberation_engine_url:
        return None
    try:
        dump = build_input_dump(engine_payload)
        if prevalidate(dump):
            logger.info("shadow_skip_prevalidate", domain=domain)  # 매핑 부적합 — 관측 생략(무영향)
            return None
        # 하드닝된 엔진 caller 재사용(breaker·X-Tenant-Id·timeout). 비결정 경로로 호출.
        from apps.api.app.routers.deliberation import _engine_post_analyze
        result, reason = await _engine_post_analyze(dump, deterministic=False, tenant=tenant_id)
        if result is None:
            logger.info("shadow_skip_engine", domain=domain, reason=reason)
            return None
        engine_verdict = engine_overall_verdict(result)
        return await shadow_service.record(
            tenant_id=tenant_id, domain=domain, platform_verdict=platform_verdict,
            engine_verdict=engine_verdict, input_hash=analysis_input_hash(dump),
            platform_value=platform_value, detail={"engine_reason": reason})
    except Exception as exc:  # noqa: BLE001 — shadow는 관측 전용, 도메인 흐름 보호 최우선
        logger.warning("shadow_compare_failed", domain=domain, err=str(exc)[:200])
        return None
