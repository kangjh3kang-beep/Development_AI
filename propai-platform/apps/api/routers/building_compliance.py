"""v44.0 건축 법규 검증 / 자동 보정 API 라우터 (G96~G99).

CAD 설계 데이터의 건폐율·용적률·높이·구조 법규 준수 여부를 검증하고,
위반 시 자동 보정 대안을 생성한다.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.session import get_db
from apps.api.services.building_compliance_service import BuildingComplianceService

router = APIRouter()


class DesignPayload(BaseModel):
    """CAD 설계 데이터 요청 본문."""

    points: list[dict[str, Any]] = Field(default_factory=list)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    surfaces: list[dict[str, Any]] = Field(default_factory=list)
    floor_count: int = 1
    building_height_m: float = 0.0
    scale: float = 10.0


class CheckRequest(BaseModel):
    project_id: str
    design: DesignPayload


class AutoCorrectRequest(BaseModel):
    project_id: str
    design: DesignPayload
    violation_type: str


# ── 응답 스키마 ──


class ComplianceCheckResult(BaseModel):
    """건축 법규 검증 결과."""
    model_config = ConfigDict(extra="allow")

    project_id: str | None = None
    violations: list[dict[str, Any]] = Field(default_factory=list)
    compliant: bool = False


class AutoCorrectResult(BaseModel):
    """자동 보정 결과."""
    model_config = ConfigDict(extra="allow")

    violation_type: str = ""
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


def _severity_to_status(severity: str) -> str:
    s = (severity or "").lower()
    if s in ("critical", "high", "error", "violation"):
        return "fail"
    if s in ("warning", "medium", "low"):
        return "warning"
    return "warning"


@router.post("/check", response_model=ComplianceCheckResult)
async def check_compliance(
    req: CheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """설계 데이터의 건축 법규 준수 여부를 검증한다."""
    svc = BuildingComplianceService(db=db)
    raw = await svc.check_compliance(
        project_id=req.project_id,
        design_raw=req.design.model_dump(),
    )

    violations = raw.get("violations", []) or []
    compliant = bool(raw.get("compliant", False))

    # ── 프론트(ComplianceCheckResponse) 계약으로 변환 ──
    checks = [
        {
            "rule_code": v.get("type", ""),
            "rule_name": v.get("type", "법규 항목"),
            "status": _severity_to_status(v.get("severity", "")),
            "detail": (
                f"{v.get('message', '')} "
                f"(현재 {v.get('current_value')}, 한도 {v.get('limit_value')})"
            ).strip(),
            "regulation_ref": v.get("type", ""),
        }
        for v in violations
    ]
    overall_status = "pass" if compliant else (
        "fail" if any(c["status"] == "fail" for c in checks) else "warning"
    )

    # 규칙기반 기본 요약
    summary = (
        "모든 건축 법규 항목을 충족합니다."
        if compliant
        else f"{len(violations)}건의 법규 위반/주의 항목이 발견되었습니다."
    )

    # ── permit_interpreter LLM 해석 → summary 확장 (graceful fallback) ──
    try:
        from app.services.ai.permit_interpreter import PermitInterpreter

        design = req.design.model_dump()

        # P3 법규 근거 주입: 용도지역 법정 한도(국토계획법 시행령)를 evidence로 부착.
        # ZONE_LIMITS(building_compliance_service 모듈상수, sync·외부키불필요·단일출처).
        # 키는 코드(1R/2R/3R/GC/NC/QI/QR)·필드는 비율(0~1)/배수라 한글명→코드 매핑 후
        # %로 환산한다. zone_type을 못 맞추면 evidence 미부착(graceful).
        permit_evidence = None
        zone_type = design.get("zone_type")
        if zone_type:
            try:
                from apps.api.services.building_compliance_service import ZONE_LIMITS

                _ZONE_NAME_TO_CODE = {
                    "제1종일반주거": "1R",
                    "제2종일반주거": "2R",
                    "제3종일반주거": "3R",
                    "일반상업": "GC",
                    "근린상업": "NC",
                    "준공업": "QI",
                    "준주거": "QR",
                }
                code = zone_type if zone_type in ZONE_LIMITS else next(
                    (c for name, c in _ZONE_NAME_TO_CODE.items() if name in zone_type),
                    None,
                )
                lim = ZONE_LIMITS.get(code) if code else None
                if lim:
                    permit_evidence = (
                        f"- 용도지역 법정 한도({zone_type}, 국토계획법 시행령): "
                        f"건폐율 상한 {lim.building_coverage_ratio * 100:.0f}%, "
                        f"용적률 상한 {lim.floor_area_ratio * 100:.0f}%, "
                        f"최고높이 {lim.max_height_m:.0f}m. "
                        "이 법정 한도를 기준으로 위반·완화 가능성을 판단할 것."
                    )
            except Exception:  # noqa: BLE001
                permit_evidence = None

        interp = await PermitInterpreter().generate_interpretation({
            "overall_feasibility": overall_status,
            "violation_count": sum(1 for c in checks if c["status"] == "fail"),
            "warning_count": sum(1 for c in checks if c["status"] == "warning"),
            "total_gfa_sqm": None,
            "zone_type": zone_type,
            "violations": [
                {
                    "rule_name": v.get("type"),
                    "severity": v.get("severity"),
                    "current_value": v.get("current_value"),
                    "limit_value": v.get("limit_value"),
                    "description": v.get("message"),
                    "legal_basis": v.get("type"),
                }
                for v in violations
            ],
            "floor_count": design.get("floor_count"),
            "building_height_m": design.get("building_height_m"),
        }, evidence_text=permit_evidence)
        if isinstance(interp, dict) and interp:
            _labels = {
                "permit_assessment": "인허가 난이도",
                "exception_analysis": "예외 조항",
                "relaxation_options": "완화 가능성",
                "timeline_estimate": "소요 기간",
                "risk_factors": "리스크 요인",
                "strategy_recommendation": "전략 제안",
            }
            sections = [
                f"[{_labels[k]}] {interp[k]}" for k in _labels if interp.get(k)
            ]
            if sections:
                summary = summary + "\n\n" + "\n\n".join(sections)
    except Exception:
        pass

    return {
        "project_id": req.project_id,
        "violations": violations,
        "compliant": compliant,
        "overall_status": overall_status,
        "checks": checks,
        "summary": summary,
    }


@router.post("/auto-correct", response_model=AutoCorrectResult)
async def auto_correct(
    req: AutoCorrectRequest,
    db: AsyncSession = Depends(get_db),
):
    """법규 위반 항목에 대한 자동 보정 대안을 생성한다."""
    svc = BuildingComplianceService(db=db)
    return await svc.auto_correct(
        project_id=req.project_id,
        design_raw=req.design.model_dump(),
        violation_type=req.violation_type,
    )
