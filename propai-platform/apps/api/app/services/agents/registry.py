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


_FACTORIES = {"permit": _build_permit}
AVAILABLE_DOMAINS = tuple(_FACTORIES.keys())


def get_specialist(domain: str) -> SpecialistAgent:
    """도메인 키 → SpecialistAgent 인스턴스. 미등록은 KeyError(정직)."""
    if domain not in _FACTORIES:
        raise KeyError(f"unknown specialist domain: {domain}")
    return _FACTORIES[domain]()
