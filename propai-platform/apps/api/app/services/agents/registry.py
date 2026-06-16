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


_FACTORIES = {"permit": _build_permit, "zoning": _build_zoning, "far": _build_far}
AVAILABLE_DOMAINS = tuple(_FACTORIES.keys())


def get_specialist(domain: str) -> SpecialistAgent:
    """도메인 키 → SpecialistAgent 인스턴스. 미등록은 KeyError(정직)."""
    if domain not in _FACTORIES:
        raise KeyError(f"unknown specialist domain: {domain}")
    return _FACTORIES[domain]()
