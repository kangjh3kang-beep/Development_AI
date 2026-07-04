"""SpecialistAgent 결정론 도메인 일괄 디스패치 공용 헬퍼(모세혈관 배선 SSOT).

분석 서비스(comprehensive 부지분석·decision_brief 통합브리프 등)가 **동일 방식**으로 결정론
SpecialistAgent를 호출해 findings·원장 cite·prior 모순을 동기 수집한다. 한 곳(이 헬퍼)을 고치면
모든 소비처가 따라오도록 dispatch·graceful·status 표준화 로직을 일원화한다(국소 중복 금지).

★전수감사 #2 배경: 종합분석은 그간 run_domain_specialists_task.delay(fire-and-forget·비동기
  성장뇌 적재 전용)만 있어 SpecialistAgent 결과가 분석 응답에 **미반영**이었고, registry의 심의/설계
  도메인은 호출처가 0인 고아였다. 이 헬퍼로 '결과 분석 반영(동기)'을 '성장뇌 적재(비동기 .delay)'와
  분리해 양쪽을 병행한다 — 동기 수집은 화면 교차검증(result["specialists"])에, .delay는 노하우 적재에.

- 도메인별·전체 graceful: 실패는 status='unavailable' 엔트리로 정직 표면화(조용한 누락 금지),
  배선 전체 예외는 []로 흡수(분석 본체 무손상).
- LLM·과금은 도메인 spec에 달림(zoning/permit/far = interpreter/panel 미장착 = 0·무과금).
- 반환: [{domain, status:'ok', task_type, summary, findings, contradictions, ledger}
         | {domain, status:'unavailable', reason}]
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_sync_specialist_domains(
    *,
    zone_type: str,
    base: dict[str, Any],
    land_area: float,
    address: str | None,
    engine_set: bool,
) -> dict[str, dict[str, Any]]:
    """동기 SpecialistAgent 교차검증 도메인 입력 빌더(전수감사 #2·테스트 가능 순수함수).

    항상 결정론 도메인(zoning 허용용도·far 실효검증)을 포함한다. 심의/설계는 외부 심의엔진 URL이
    설정된 경우(engine_set=True)에만 추가한다 — 미설정 시 즉시 unavailable이 될 도메인을 디스패치
    목록에 넣어 불필요한 호출·지연을 만들지 않기 위함이며, 엔진 가용 시 registry 심의/설계 고아가
    실호출로 해소된다. 순수 dict 빌더라 게이트 분기를 단위테스트로 고정한다(무거운 import 무관).
    """
    domains: dict[str, dict[str, Any]] = {
        "zoning": {"zone_type": zone_type},
        "far": {"base": base, "zone_type": zone_type, "land_area": land_area},
    }
    if engine_set:
        domains["심의"] = {"zone_type": zone_type, "address": address}
        domains["설계"] = {"zone_type": zone_type, "address": address}
    return domains


async def run_specialist_domains(
    domains: dict[str, dict[str, Any]],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    address: str | None = None,
    pnu: str | None = None,
) -> list[dict[str, Any]]:
    """domains({도메인키: 도구입력 data})를 결정론 SpecialistAgent로 동기 일괄 디스패치.

    호출 측이 도메인별 입력(zone_type·dev_type 등)을 구성해 넘긴다. 입력 추출/검증은 호출 측 책임.
    각 도메인은 병렬(asyncio.gather)로 실행하되, 한 도메인 실패가 전체를 깨지 않는다(정직 강등).
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
    for dom, r in zip(domains.keys(), results, strict=False):
        if isinstance(r, Exception) or not isinstance(r, dict) or not r.get("ok"):
            # ★정직: 시도했으나 실패한 도메인은 '미시도'와 구분되도록 unavailable 엔트리로 표면화.
            reason = (
                str(r)[:120] if isinstance(r, Exception)
                else (r.get("message") if isinstance(r, dict) else None)
            ) or "교차검증 불가"
            logger.warning("specialist dispatch 스킵(graceful) domain=%s: %s", dom, str(reason)[:160])
            out.append({"domain": dom, "status": "unavailable", "reason": reason})
            continue
        summary = r.get("summary") if isinstance(r.get("summary"), dict) else {}
        # ★정직 강등: 도구가 명시적으로 미가용(available=False)을 보고하면(예: 외부 심의엔진 URL 미설정·
        #   처리불가) ok=True여도 'unavailable'로 표면화한다. 그러지 않으면 '빈 findings + status:ok'
        #   카드가 '교차검증 통과'로 오인되는 반쪽출하가 된다(엔진은 아무 일도 안 했음).
        if summary.get("available") is False:
            out.append({"domain": dom, "status": "unavailable",
                        "reason": summary.get("reason") or "엔진 미가용"})
            continue
        out.append({
            "domain": dom,
            "status": "ok",
            "task_type": r.get("task_type"),
            "summary": summary,
            "findings": r.get("findings") or [],
            "contradictions": r.get("contradictions"),
            "ledger": r.get("ledger"),
        })
    return out
