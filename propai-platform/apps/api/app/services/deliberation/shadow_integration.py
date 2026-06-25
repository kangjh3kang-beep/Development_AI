"""중심엔진 수렴 — 도메인 분석의 best-effort shadow 비교 오케스트레이션(운영 무중단).

도메인(comprehensive/design_audit/area 등)이 자신의 platform_verdict + 엔진 입력(payload)을 넘기면,
엔진을 best-effort로 호출해 대표 verdict를 뽑아 shadow_service.record로 divergence를 적재한다.
**불변식**: 설정 off(deliberation_shadow_enabled=False)·엔진 미설정·매핑 부적합·임의 실패 시 None을 반환하고
어떤 예외도 도메인 흐름으로 전파하지 않는다(관측 전용·운영 무중단). 충분한 일치 관측 후 authoritative 승격.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.services.deliberation import shadow_service
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
    build_input_dump,
    prevalidate,
)
from apps.api.config import get_settings
from apps.api.integrations.base_client import CircuitBreaker

logger = structlog.get_logger(__name__)

# 엔진 findings verdict → 보수적 대표 등급(최악 우선). 도메인 단일 verdict와 비교용.
_SEVERITY = {"non_compliant": 3, "needs_review": 2, "compliant": 1, "": 0}

# ★shadow 전용 breaker — 관측 실패가 권위 BFF(/deliberation/analyze)의 운영 회로를 열지 못하게 격리.
_shadow_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)
# fire-and-forget 태스크 GC 방지(강참조 보관 후 완료 시 해제).
_bg_tasks: set[asyncio.Task] = set()


def _norm_tenant(t: Any) -> str:
    """테넌트 표기 정규화(32자 무대시 소문자) — 도메인별 hex/대시형 불일치로 per-tenant 집계 분열 방지."""
    return str(t or "").replace("-", "").lower()


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


def fire_shadow_compare(**kwargs: Any) -> asyncio.Task | None:
    """비차단 스케줄(fire-and-forget) — 도메인 응답 경로를 엔진 RTT로 막지 않음(관측 전용 무중단 핵심).
    이벤트루프 없으면 None. 반환 task는 테스트에서 await 가능(GC 방지 위해 강참조 보관)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    task = loop.create_task(shadow_compare(**kwargs))
    _bg_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _bg_tasks.discard(t)
        exc = None if t.cancelled() else t.exception()
        if exc is not None:  # shadow_compare는 자체 never-raise이나 스케줄 단계 예외는 여기서 표면화(무음 유실 방지)
            logger.warning("shadow_task_unhandled", err=str(exc)[:200])

    task.add_done_callback(_on_done)
    return task


def observe(domain: str, tenant_id: str | None, mapped: tuple[str, dict[str, Any], Any] | None) -> asyncio.Task | None:
    """후킹 공통 글루 — 매퍼 결과((verdict,payload,value)|None)+테넌트로 fire(비차단). 도메인 라우터가 직접
    fire 인자를 조립하던 가변부를 단일 함수로 모아 후킹 회귀(domain 오타·인자 누락)를 테스트로 고정한다.
    mapped/tenant 없으면 no-op(None)."""
    if not mapped or not tenant_id:
        return None
    verdict, payload, value = mapped
    return fire_shadow_compare(tenant_id=tenant_id, domain=domain,
                               platform_verdict=verdict, engine_payload=payload, platform_value=value)


async def shadow_compare(*, tenant_id: str, domain: str, platform_verdict: Any,
                         engine_payload: dict[str, Any], platform_value: Any = None) -> dict[str, Any] | None:
    """best-effort shadow 비교·적재. 도메인 흐름 절대 방해 금지(off/실패/타임아웃 시 None).

    ⚠️ quant_rel_err: 현재 통합 경로는 engine_value를 추출하지 않으므로 항상 None(verdict가 1차 비교축).
    엔진 정량 추출은 후속 — platform_value는 관측 보조 신호로만 적재.
    """
    s = get_settings()
    if not getattr(s, "deliberation_shadow_enabled", False) or not s.deliberation_engine_url:
        return None
    tenant = _norm_tenant(tenant_id)
    try:
        dump = build_input_dump(engine_payload)
        if prevalidate(dump):
            logger.info("shadow_skip_prevalidate", domain=domain)  # 매핑 부적합 — 관측 생략(무영향)
            return None
        # 하드닝된 엔진 caller 재사용하되 ★shadow 전용 breaker + 짧은 타임아웃으로 격리·상한(운영 무영향).
        from apps.api.app.routers.deliberation import _engine_post_analyze
        budget = float(getattr(s, "deliberation_shadow_engine_timeout_s", 5.0))
        result, reason = await asyncio.wait_for(
            _engine_post_analyze(dump, deterministic=False, tenant=tenant, breaker=_shadow_breaker),
            timeout=budget)
        if result is None:
            logger.info("shadow_skip_engine", domain=domain, reason=reason)
            return None
        engine_verdict = engine_overall_verdict(result)
        return await shadow_service.record(
            tenant_id=tenant, domain=domain, platform_verdict=platform_verdict,
            engine_verdict=engine_verdict, input_hash=analysis_input_hash(dump),
            platform_value=platform_value, detail={"engine_reason": reason})
    except Exception as exc:  # noqa: BLE001 — shadow는 관측 전용, 도메인 흐름 보호 최우선(타임아웃 포함)
        logger.warning("shadow_compare_failed", domain=domain, err=str(exc)[:200])
        return None
