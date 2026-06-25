"""SpecialistAgent 결정론 도메인 일괄 디스패치 공용 헬퍼(모세혈관 배선 SSOT).

분석 서비스(comprehensive 부지분석·decision_brief 통합브리프 등)가 **동일 방식**으로 결정론
SpecialistAgent를 호출해 findings·원장 cite·prior 모순을 수집한다. 한 곳(이 헬퍼)을 고치면
모든 소비처가 따라오도록 dispatch·graceful·status 표준화 로직을 일원화한다(국소 중복 금지).

- 도메인별·전체 graceful: 실패는 status='unavailable' 엔트리로 정직 표면화(조용한 누락 금지),
  배선 전체 예외는 []로 흡수(분석 본체 무손상).
- LLM·과금은 도메인 spec에 달림(zoning/permit/far = interpreter/panel 미장착 = 0).
- 반환: [{domain, status:'ok', task_type, summary, findings, contradictions, ledger}
         | {domain, status:'unavailable', reason}]
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_specialist_domains(
    domains: dict[str, dict[str, Any]],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    address: str | None = None,
    pnu: str | None = None,
) -> list[dict[str, Any]]:
    """domains({도메인키: 도구입력 data})를 결정론 SpecialistAgent로 일괄 디스패치.

    호출 측이 도메인별 입력(zone_type·dev_type 등)을 구성해 넘긴다. 입력 추출/검증은 호출 측 책임.
    """
    if not domains:
        return []
    try:
        from apps.api.core.coordinator import AgentCoordinator

        coord = AgentCoordinator()
        ctx = {"tenant_id": tenant_id, "project_id": project_id, "address": address, "pnu": pnu}
        results = await asyncio.gather(
            *(coord.dispatch(dom, data, **ctx) for dom, data in domains.items()),
            return_exceptions=True,
        )
    except Exception as e:  # noqa: BLE001 — 배선 전체 실패는 빈 list(분석 본체 무손상)
        logger.warning("specialist 배선 전체 스킵(graceful): %s", str(e)[:200])
        return []

    out: list[dict[str, Any]] = []
    for dom, r in zip(domains.keys(), results):
        if isinstance(r, Exception) or not isinstance(r, dict) or not r.get("ok"):
            # ★정직: 시도했으나 실패한 도메인은 '미시도'와 구분되도록 unavailable 엔트리로 표면화.
            reason = (
                str(r)[:120] if isinstance(r, Exception)
                else (r.get("message") if isinstance(r, dict) else None)
            ) or "교차검증 불가"
            logger.warning("specialist dispatch 스킵(graceful) domain=%s: %s", dom, str(reason)[:160])
            out.append({"domain": dom, "status": "unavailable", "reason": reason})
            continue
        out.append({
            "domain": dom,
            "status": "ok",
            "task_type": r.get("task_type"),
            "summary": r.get("summary") or {},
            "findings": r.get("findings") or [],
            "contradictions": r.get("contradictions"),
            "ledger": r.get("ledger"),
        })
    return out
