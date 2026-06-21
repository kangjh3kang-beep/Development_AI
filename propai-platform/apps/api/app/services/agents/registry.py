"""Phase 3 — 도메인 → SpecialistAgent 레지스트리 + 계층1 결정론 도구 어댑터."""
from __future__ import annotations

from typing import Any

from app.services.agents.specialist_agent import SpecialistAgent


def _permit_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 인허가 가부 도구(check_permit_feasibility) → findings/summary.

    dev_type은 코드("M06"=일반분양 등), zone_type은 용도지역명. 수치/판정은 결정론 매트릭스에서만.
    """
    from app.services.feasibility.permit_validator import check_permit_feasibility
    res = check_permit_feasibility(data.get("dev_type", ""), data.get("zone_type", ""))
    status = "pass" if res.get("is_permitted") else "fail"
    return {
        "findings": [{"check_id": "PERMIT", "status": status,
                      "current": res.get("type_name"), "limit": None,
                      "note": res.get("reason")}],
        "summary": {"is_permitted": res.get("is_permitted"),
                    "permit_complexity": res.get("permit_complexity"),
                    "type_name": res.get("type_name")},
    }


def _build_permit() -> SpecialistAgent:
    return SpecialistAgent(domain="permit", task_type="feasibility",
                           tool=_permit_tool, interpreter=None)


def _zoning_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 용도지역 허용유형 도구(get_permitted_types) → findings/summary."""
    from app.services.feasibility.permit_validator import DEVELOPMENT_TYPE_NAMES, get_permitted_types
    zone = data.get("zone_type", "")
    permitted = get_permitted_types(zone)
    return {
        "findings": [{"check_id": "ZONING", "status": "info",
                      "current": len(permitted), "limit": None,
                      "note": f"{zone} 허용 개발유형 {len(permitted)}종"}],
        "summary": {"zone_type": zone, "permitted": permitted, "permitted_count": len(permitted),
                    "permitted_names": [DEVELOPMENT_TYPE_NAMES.get(t, t) for t in permitted]},
    }


def _far_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 실효용적률 도구(calc_effective_far) → findings/summary. 수치=결정론 산정만."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far
    res = calc_effective_far(data.get("base") or {}, data.get("zone_type", ""),
                             data.get("land_area", 0.0))
    far = res.get("effective_far_pct")
    legal_max = res.get("legal_max_far_pct")
    over = far is not None and legal_max is not None and float(far) > float(legal_max)
    return {
        "findings": [{"check_id": "FAR", "status": "fail" if over else "pass",
                      "current": far, "limit": legal_max}],
        "summary": {"effective_far_pct": far, "effective_bcr_pct": res.get("effective_bcr_pct"),
                    "legal_max_far_pct": legal_max, "far_basis": res.get("far_basis")},
    }


def _build_zoning() -> SpecialistAgent:
    return SpecialistAgent(domain="zoning", task_type="permitted_types",
                           tool=_zoning_tool, interpreter=None)


def _build_far() -> SpecialistAgent:
    return SpecialistAgent(domain="far", task_type="effective_far",
                           tool=_far_tool, interpreter=None)


# ── Phase 3.2 잔여: cost·market 도구 + 다관점 패널 어댑터 ──

def _cost_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 공사비 도구(CONSTRUCTION_COST_PER_SQM) → findings/summary. 수치=상수×면적만."""
    from app.services.land_intelligence.comprehensive_analysis_service import CONSTRUCTION_COST_PER_SQM
    dev_type = data.get("dev_type", "")
    gfa = float(data.get("gfa_sqm") or data.get("total_gfa_sqm") or 0)
    per_sqm = CONSTRUCTION_COST_PER_SQM.get(dev_type, 2_400_000)
    total = gfa * per_sqm
    return {
        "findings": [{"check_id": "COST", "status": "info", "current": total, "limit": None}],
        "summary": {"gfa_sqm": gfa, "cost_per_sqm": per_sqm,
                    "total_construction_cost": total, "dev_type": dev_type},
    }


def _market_tool(data: dict[str, Any]) -> dict[str, Any]:
    """결정론: 제공된 시장 신호를 findings로 표면화(수치 생성 X — 입력 그대로). 판단은 panel이 담당."""
    op = data.get("official_price_per_sqm")
    findings: list[dict[str, Any]] = []
    if isinstance(op, (int, float)) and not isinstance(op, bool) and op > 0:
        findings.append({"check_id": "MARKET_PRICE", "status": "info", "current": float(op), "limit": None})
    return {"findings": findings, "summary": {"official_price_per_sqm": op, "signal_count": len(findings)}}


async def _default_panel(domain: str, context: dict[str, Any]) -> dict[str, Any]:
    """ExpertPanelService 다관점(GROUNDING_RULE+할루시네이션 게이트). LLM 부재 시 graceful fallback 구조."""
    from app.services.expert_panel.expert_panel_service import ExpertPanelService
    return await ExpertPanelService().analyze(domain, context, mode="single")


def _build_cost() -> SpecialistAgent:
    return SpecialistAgent(domain="cost", task_type="construction_cost",
                           tool=_cost_tool, interpreter=None, panel=_default_panel)


def _build_market() -> SpecialistAgent:
    return SpecialistAgent(domain="market", task_type="market_analysis",
                           tool=_market_tool, interpreter=None, panel=_default_panel)


# ── 심의: 심의분석엔진(deliberation-review) BFF 도메인 — 인·허가/심의 프로세스 ──

def _stage_basis(stage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """단계 criteria의 legal_basis(법령명·조항·요지) + 1차출처 링크를 집계(설명가능성 전파, 중복 제거)."""
    basis: list[dict[str, Any]] = []
    links: list[str] = []
    for c in (stage.get("criteria") or []):
        for lb in (c.get("legal_basis") or []):
            entry = {"law": lb.get("law"), "article": lb.get("article"), "summary": lb.get("summary")}
            if entry not in basis:
                basis.append(entry)
            src = lb.get("source")
            if src and src not in links:
                links.append(src)
    return basis, links


def _map_permit_response(res: dict[str, Any]) -> dict[str, Any]:
    """심의엔진 PermitProcessResult → SpecialistAgent findings/summary 정규화(결정론 매핑, 수치 생성 X).

    ★설명가능성 전파(EX2): 각 finding에 근거(basis: 법령명·조항·요지)+링크(links: 1차출처 URL) 기본 동반."""
    findings: list[dict[str, Any]] = []
    for st in (res.get("stages") or []):
        basis, links = _stage_basis(st)
        findings.append({"check_id": st.get("stage_id"), "status": st.get("conformance"),
                         "current": st.get("verification_status"), "limit": None,
                         "note": st.get("name"), "basis": basis, "links": links})
    return {"findings": findings,
            "summary": {"available": True, "spec_id": res.get("spec_id"),
                        "overall_conformance": res.get("overall_conformance"),
                        "overall_verification": res.get("overall_verification"),
                        "run_id": res.get("run_id")}}


async def _deliberation_tool(data: dict[str, Any]) -> dict[str, Any]:
    """심의 도메인 — 심의엔진 /api/v1/permit/process 호출(인·허가/심의 프로세스). 수치/판정은 엔진 결정론 산출만.

    엔진 URL 미설정 시 graceful(미연동 — findings 비움 + reason). 라이브 실패도 표면화(무음 단정 금지)."""
    from app.core.config import get_settings
    s = get_settings()
    base = (getattr(s, "DELIBERATION_ENGINE_URL", "") or "").rstrip("/")
    if not base:
        return {"findings": [], "summary": {"available": False, "reason": "engine_url_unset"}}
    token = getattr(s, "DELIBERATION_ENGINE_TOKEN", "") or ""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as cli:
            r = await cli.post(f"{base}/api/v1/permit/process", json=data, headers=headers)
            r.raise_for_status()
            res = r.json()
    except Exception as exc:  # noqa: BLE001 — 라이브 실패는 graceful 표면화(무음 단정 금지)
        return {"findings": [],
                "summary": {"available": False, "reason": f"engine_call_failed:{type(exc).__name__}"}}
    return _map_permit_response(res if isinstance(res, dict) else {})


def _build_deliberation() -> SpecialistAgent:
    return SpecialistAgent(domain="심의", task_type="permit_process",
                           tool=_deliberation_tool, interpreter=None)


_FACTORIES = {"permit": _build_permit, "zoning": _build_zoning, "far": _build_far,
              "cost": _build_cost, "market": _build_market, "심의": _build_deliberation}
AVAILABLE_DOMAINS = tuple(_FACTORIES.keys())


def get_specialist(domain: str) -> SpecialistAgent:
    """도메인 키 → SpecialistAgent 인스턴스. 미등록은 KeyError(정직)."""
    if domain not in _FACTORIES:
        raise KeyError(f"unknown specialist domain: {domain}")
    return _FACTORIES[domain]()
