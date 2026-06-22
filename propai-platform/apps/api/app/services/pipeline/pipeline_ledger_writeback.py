"""Fix #3(감사 HIGH): 파이프라인 결정론 산출 → 분석원장 write-back.

배경(감사): ProjectPipeline의 /run·/report가 cost(원가)·feasibility(수지) 결정론 수치를
산출하지만 분석원장(analysis_ledger)에 적재하지 않았다. 어댑터(record_cost_estimate /
record_feasibility_result)는 v2_feasibility·cost 등 별도 엔드포인트에서만 호출돼, 통합
파이프라인의 권위수치가 SSOT 원장·모순탐지·lineage에서 누락됐다.

이 모듈은 그 단선을 닫는다: 파이프라인 stage data를 어댑터 인자로 정규화(순수 매퍼)하고,
체인 식별자가 있을 때만 best-effort로 원장에 적재한다(무중단·무날조 — 미상 필드는 None).
결정론 수치 자체는 변경하지 않는다(원장은 '추가' 일원화).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


def _num(v: Any) -> float | None:
    """숫자만 통과(문자 '—'/None/빈값은 None — 무날조)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _stage_data(stages: Any, name: str) -> dict[str, Any]:
    """stages(dict[str, StageResult] | dict[str, {data}] | PipelineState.stages) → stage data dict."""
    entry = stages.get(name) if isinstance(stages, dict) else getattr(stages, name, None)
    if entry is None:
        return {}
    data = getattr(entry, "data", None)
    if data is None and isinstance(entry, dict):
        data = entry.get("data")
    return data if isinstance(data, dict) else {}


def cost_stage_to_adapter(
    cost_data: dict[str, Any], design_data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """cost stage data → record_cost_estimate(summary, header) 인자.

    indirect는 total−direct 파생(둘 다 가용·total≥direct일 때만). 미상이면 None(무날조).
    total_gfa_sqm은 design 우선, 없으면 cost의 평수×3.3058에서 복원.
    """
    cb = cost_data.get("cost_breakdown") if isinstance(cost_data.get("cost_breakdown"), dict) else {}
    total = _num(cost_data.get("total_construction_cost")) or _num(cb.get("total_project_cost"))
    direct = _num(cost_data.get("direct_cost")) or _num(cb.get("direct_cost"))
    indirect: float | None = None
    if total is not None and direct is not None and total >= direct:
        indirect = total - direct

    gfa = _num(design_data.get("total_gfa_sqm")) or _num(design_data.get("total_floor_area_sqm"))
    if gfa is None:
        pyeong = _num(cost_data.get("total_gfa_pyeong"))
        gfa = round(pyeong * 3.3058) if pyeong else None

    summary = {
        "direct": direct,
        "indirect": indirect,
        "total": total,
        # 등급은 엔진이 준 값만 사용(없으면 None) — 임의 산정 금지.
        "confidence_grade": cost_data.get("confidence_grade"),
    }
    header = {
        "building_type": design_data.get("building_type") or design_data.get("building_use"),
        "structure_type": design_data.get("structure_type"),
        "total_gfa_sqm": gfa,
    }
    return summary, header


def feasibility_stage_to_adapter(
    feas_data: dict[str, Any], design_data: dict[str, Any]
) -> dict[str, Any]:
    """feasibility stage data → record_feasibility_result(result) 인자(별칭 정규화·무날조)."""

    def _nested_npv(key: str) -> float | None:
        sub = feas_data.get(key)
        return _num(sub.get("npv_won")) if isinstance(sub, dict) else None

    npv = _num(feas_data.get("npv_won")) or _nested_npv("dcf") or _nested_npv("cash_flow")
    return {
        "development_type": feas_data.get("development_type")
        or design_data.get("building_type")
        or design_data.get("building_use"),
        "total_revenue_won": _num(feas_data.get("total_revenue_won")) or _num(feas_data.get("total_revenue")),
        "net_profit_won": _num(feas_data.get("net_profit_won"))
        if feas_data.get("net_profit_won") is not None
        else _num(feas_data.get("net_profit")),
        "profit_rate_pct": _num(feas_data.get("profit_rate_pct")),
        "npv_won": npv,
        "grade": feas_data.get("grade"),
    }


def extract_chain_ids(stages: Any, *, fallback_address: str | None = None) -> dict[str, str | None]:
    """site_analysis stage → 체인 식별자(pnu/address). basic 중첩·평면 양형 수용."""
    site = _stage_data(stages, "site_analysis")
    basic = site.get("basic") if isinstance(site.get("basic"), dict) else {}
    pnu = site.get("pnu") or site.get("PNU") or basic.get("pnu") or basic.get("PNU")
    address = site.get("address") or basic.get("address") or fallback_address
    return {
        "pnu": str(pnu) if pnu else None,
        "address": str(address) if address else None,
    }


async def record_pipeline_results(
    *,
    stages: Any,
    address: str | None = None,
    project_id: str | None = None,
    tenant_id: str | None = None,
    created_by: str | None = None,
    cost_recorder: Callable[..., Awaitable[dict]] | None = None,
    feasibility_recorder: Callable[..., Awaitable[dict]] | None = None,
) -> dict[str, Any]:
    """파이프라인 cost/feasibility 결정론 산출을 원장에 best-effort 적재.

    - 체인 식별자(pnu/address/project_id) 중 하나도 없으면 익명 누적 방지 차 스킵.
    - 각 적재는 독립 try/except(하나 실패해도 다른 하나는 진행, 전체 무중단).
    - recorder는 테스트 주입 가능(기본=ledger_adapters 실어댑터, prior 모순+lineage 포함).
    반환: 성공 적재만 담은 dict({"cost": wb, "feasibility": wb}) — 실패/스킵은 키 생략(정직).
    """
    if cost_recorder is None or feasibility_recorder is None:
        from app.services.ledger import ledger_adapters as _adapters
        cost_recorder = cost_recorder or _adapters.record_cost_estimate
        feasibility_recorder = feasibility_recorder or _adapters.record_feasibility_result

    ids = extract_chain_ids(stages, fallback_address=address)
    pnu, addr = ids["pnu"], ids["address"]
    if not (pnu or addr or project_id):
        return {}  # 체인 식별자 없음 → 무의미한 익명 적재 스킵

    design_data = _stage_data(stages, "design")
    out: dict[str, Any] = {}

    cost_data = _stage_data(stages, "cost")
    if cost_data:
        summary, header = cost_stage_to_adapter(cost_data, design_data)
        if summary.get("total"):  # 총원가 없으면 적재 무의미 — 스킵
            try:
                out["cost"] = await cost_recorder(
                    summary=summary, header=header,
                    tenant_id=tenant_id, project_id=project_id, created_by=created_by)
            except Exception as e:  # noqa: BLE001 — 무중단(실패 시 키 미생성)이나 관측가능해야 함(불변규칙3)
                logger.warning("원장 cost 적재 실패 — skipped: %s", str(e)[:200])

    feas_data = _stage_data(stages, "feasibility")
    if feas_data:
        result = feasibility_stage_to_adapter(feas_data, design_data)
        if result.get("total_revenue_won") is not None or result.get("profit_rate_pct") is not None:
            try:
                out["feasibility"] = await feasibility_recorder(
                    result=result, tenant_id=tenant_id, project_id=project_id,
                    pnu=pnu, address=addr, created_by=created_by)
            except Exception as e:  # noqa: BLE001 — best-effort 무중단이나 관측가능해야 함(불변규칙3)
                logger.warning("원장 feasibility 적재 실패 — skipped: %s", str(e)[:200])

    return out
