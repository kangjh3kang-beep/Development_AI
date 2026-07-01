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


# ── WP-P: 법령 근거 레지스트리 연동(additive·graceful) ──────────────────────
# 인허가 룰체크의 legal_basis 자유문자열은 그대로 유지하고, 레지스트리에 검증 등록된
# 근거만 legal_refs[]로 가산한다. 레지스트리 미등록 근거(건축법 제46·47조, 제60조,
# 장애인등편의법 등)는 매핑하지 않음 — 텍스트만 표기(할루시네이션 링크 금지).

# BuildingCodeRuleEngine 8룰(rule_id) → 레지스트리 키.
_RULE_LEGAL_REF_KEYS: dict[str, list[str]] = {
    "BL-001": ["bcr_limit"],                              # 건폐율 — 국토계획법 시행령 §84
    "BL-002": ["far_limit"],                              # 용적률 — 국토계획법 시행령 §85
    "BL-003": ["daylight_height"],                        # 높이제한 — 건축법 §61(§60 미등록)
    "BL-004": [],                                          # 건축선 후퇴 — §46·47 미등록(텍스트만)
    "BL-005": ["parking_min", "parking_min_dec"],         # 주차 — 주차장법 §19 + 시행령 §6
    "BL-006": ["daylight_height", "daylight_height_dec"],  # 일조 — 건축법 §61 + 시행령 §86
    "BL-007": ["evacuation"],                              # 피난·방화 — 건축법 §49(모법)
    "BL-008": [],                                          # 장애인 편의 — 미등록(텍스트만)
}

# 설계정합 검증(/check) 위반유형(type) → 레지스트리 키.
_VIOLATION_LEGAL_REF_KEYS: dict[str, list[str]] = {
    "building_coverage": ["bcr_limit"],
    "floor_area_ratio": ["far_limit"],
    "height": [],                          # 가로구역 높이(건축법 §60) 미등록 — 텍스트만
    "setback": ["site_open_space"],        # 대지 안의 공지 — 건축법 §58
    "sunlight": ["daylight_height"],       # 일조 — 건축법 §61
    "structure": ["structure_safety"],     # 구조내력 — 건축법 §48
}

# 설계 전 검토(_pre_design_review) rule_code → 레지스트리 키.
_PRE_DESIGN_LEGAL_REF_KEYS: dict[str, list[str]] = {
    "건폐율 상한": ["bcr_limit"],
    "용적률 상한": ["far_limit"],
    "buildable_scale": ["bcr_limit", "far_limit"],
    # "최고 높이"·"zone_unknown" — 정확한 근거키 미등록 → 미매핑(텍스트만).
}

# 주택법 사업계획승인 대상 건물유형(부분일치).
_HOUSING_TYPES = ("아파트", "공동주택", "다세대주택", "연립주택", "도시형생활주택")


def _legal_refs_for(keys: list[str]) -> list[dict[str, Any]]:
    """레지스트리 키 → legal_refs 직렬화. 미등록 키는 레지스트리가 자동 스킵.

    URL은 전적으로 get_legal_refs 출력만 사용(여기서 URL 조립 금지). 예외 시 빈 배열
    (graceful — 기존 응답 무손상).
    """
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys)
    except Exception:  # noqa: BLE001
        return []


def _permit_base_keys(building_type: str | None) -> list[str]:
    """인허가 공통 근거키 — 건축허가(건축법 §11) + 주택유형이면 주택법 사업계획승인(§15)."""
    keys = ["building_permit"]
    bt = (building_type or "").strip()
    if bt and any(t in bt for t in _HOUSING_TYPES):
        keys.append("housing_project_approval")
    return keys


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
    design: DesignPayload | None = None  # 있으면 설계단계 정합 검증, 없으면 설계 전 검토
    # ── 설계 전 검토 입력(부지분석 기반) ──
    building_type: str | None = None
    address: str | None = None
    area_sqm: float | None = None      # 대지면적
    floors: int | None = None
    zone_code: str | None = None       # 부지분석 용도지역(siteAnalysis.zoneCode)
    planned_bcr: float | None = None   # 설계값 있으면 비교(designData.bcr, %)
    planned_far: float | None = None   # designData.far, %
    planned_height_m: float | None = None
    # 다필지 통합 개발 시 필지 목록(2개 이상이면 면적가중 통합면적·우세용도로 보정).
    #   행 계약(프론트 전송 키): {address, area_sqm, zone_type, farPct, bcrPct, farLegalPct, bcrLegalPct}.
    #   미전달/1필지면 기존 단일필지 동작 그대로(무회귀).
    parcels: list[dict] | None = None


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


async def _integrate_parcels(parcels: list[dict] | None) -> dict[str, Any] | None:
    """다필지(2개 이상) 면적가중 통합집계 → {parcel_count,total_area_sqm,dominant_zone,...} 또는 None.

    ★공용 단일경유: /zoning/integrated-analysis와 동일한 ComprehensiveAnalysisService.
    _integrated_context(면적가중 _aggregate_integrated_zoning 재사용) — 산식 복제 0.
    함수 내부 지역 import로 순환참조 회피. dict 행만 통과, 1필지 이하/실패면 None(단일 경로 무회귀).
    """
    _rows = [p for p in parcels if isinstance(p, dict)] if parcels else []
    if len(_rows) < 2:
        return None
    try:
        from app.services.land_intelligence.comprehensive_analysis_service import (
            ComprehensiveAnalysisService,
        )

        return await ComprehensiveAnalysisService()._integrated_context(_rows)
    except Exception:  # noqa: BLE001 — 통합집계 실패는 단일 경로로 폴백(검증 무중단)
        import structlog
        structlog.get_logger(__name__).warning("다필지 통합집계 실패 — 단일 경로 폴백(graceful)")
        return None


async def _pre_design_review(req: "CheckRequest") -> dict[str, Any]:
    """설계 전 인허가 검토 — 부지분석(용도지역·대지면적) 기반.

    설계 산출물이 아직 없을 때, 법정 한도와 가능 규모(건축면적·연면적)를 산정하고
    개발방식별 인허가 가능성을 AI로 요약한다. 설계 정합 검증과 병행되는 첫 단계.
    """
    # ── 다필지 통합면적/통합용도 보정(시장보고서와 동일 공용패턴) ──
    # parcels가 2필지 이상이면 대표 1필지가 아니라 '면적가중 통합면적·우세용도'로
    #   area_sqm·zone_code를 덮어쓴다(요청에 명시값이 있어도 통합값 우선 — 단 우세용도가
    #   mixed_review_required면 기존 zone_code 유지). 1필지 이하/실패면 기존값 그대로(무회귀).
    integrated = await _integrate_parcels(req.parcels)
    zone = (req.zone_code or "").strip()
    area = float(req.area_sqm or 0)
    if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
        area = float(integrated["total_area_sqm"])  # 통합면적으로 가능규모 산정
        _dom = integrated.get("dominant_zone")
        if _dom and _dom != "mixed_review_required":
            zone = str(_dom).strip()  # 통합 우세용도로 한도 매칭

    # ★fail-open 제거: 로컬표 서브스트링 매칭('농림축산…'→'농림', '준주거 검토용지'→'준주거')이
    # 아니라 공용 SSOT resolve_zone_limits(fail-closed 계약)로 한도를 조회한다.
    # 확정 매칭(matched=True)이고 확정 한도(max_*_pct)가 있을 때만 '적합' 판정을 낸다.
    from app.services.zoning.zone_limit_contract import resolve_zone_limits

    resolution = resolve_zone_limits(zone)
    matched = bool(
        resolution.matched
        and resolution.max_bcr_pct is not None
        and resolution.max_far_pct is not None
    )
    # 높이 상한: SSOT는 별도로 두지 않음(기존 로컬표도 전부 0=별도규정). 0=별도규정으로 처리.
    bcr_lim = resolution.max_bcr_pct or 0.0
    far_lim = resolution.max_far_pct or 0.0
    h_lim = 0.0
    checks: list[dict[str, Any]] = []

    if matched:
        # 가능 규모 산정
        max_build_area = area * bcr_lim / 100 if area else 0
        max_gfa = area * far_lim / 100 if area else 0

        def _limit_check(name: str, planned: float | None, limit: float, unit: str) -> dict[str, Any]:
            if planned and planned > 0:
                ok = planned <= limit
                return {
                    "rule_code": name, "rule_name": name,
                    "status": "pass" if ok else "fail",
                    "detail": f"계획 {planned}{unit} / 법정 상한 {limit}{unit}"
                    + ("" if ok else " — 상한 초과"),
                    "regulation_ref": "국토계획법 시행령",
                }
            return {
                "rule_code": name, "rule_name": name, "status": "info",
                "detail": f"법정 상한 {limit}{unit} (설계값 미입력)",
                "regulation_ref": "국토계획법 시행령",
            }

        checks.append(_limit_check("건폐율 상한", req.planned_bcr, bcr_lim, "%"))
        checks.append(_limit_check("용적률 상한", req.planned_far, far_lim, "%"))
        if h_lim > 0:
            checks.append(_limit_check("최고 높이", req.planned_height_m, h_lim, "m"))
        if area:
            checks.append({
                "rule_code": "buildable_scale", "rule_name": "가능 규모(추정)",
                "status": "info",
                "detail": (
                    f"대지 {area:,.0f}㎡ → 최대 건축면적 약 {max_build_area:,.0f}㎡, "
                    f"최대 연면적 약 {max_gfa:,.0f}㎡ (법정 상한 기준, 조례 별도)"
                ),
                "regulation_ref": "국토계획법 시행령",
            })
        zone_name: str | None = resolution.zone_type
    else:
        zone_name = None
        checks.append({
            "rule_code": "zone_unknown", "rule_name": "용도지역 확인 필요",
            "status": "warning",
            "detail": f"용도지역('{zone or '미상'}') 법정 상한 미등록 — 부지분석에서 용도지역 확정 후 재검토 권장.",
            "regulation_ref": "",
        })

    has_fail = any(c["status"] == "fail" for c in checks)
    overall_status = "fail" if has_fail else ("warning" if not matched else "pass")
    summary = (
        f"[설계 전 인허가 검토] 용도지역 {zone_name} 기준 법정 한도 내 가능 규모를 산정했습니다. "
        "설계가 확정되면 설계 정합 검증으로 자동 정밀화됩니다."
        if matched else
        "[설계 전 인허가 검토] 용도지역이 확정되지 않아 부지분석을 먼저 완료해 주세요."
    )

    # ── AI 인허가 가능성 요약(graceful) ──
    if matched and area:
        try:
            from app.services.ai.permit_interpreter import PermitInterpreter

            # 한도값은 위 SSOT resolution에서 이미 확정(bcr_lim/far_lim/h_lim) — 로컬표 재조회 금지.
            evidence = (
                f"- 용도지역 법정 한도({zone_name}, 국토계획법 시행령): "
                f"건폐율 상한 {bcr_lim}%, 용적률 상한 {far_lim}%, 최고높이 {h_lim}m. "
                f"- 대지면적 {area:,.0f}㎡, 건물유형 {req.building_type or '미정'}, "
                f"계획층수 {req.floors or '미정'}. 설계 전 단계이므로 가능성·전략 위주로 판단."
            )
            interp = await PermitInterpreter().generate_interpretation({
                "overall_feasibility": overall_status,
                "violation_count": sum(1 for c in checks if c["status"] == "fail"),
                "warning_count": sum(1 for c in checks if c["status"] == "warning"),
                "total_gfa_sqm": area * far_lim / 100,
                "zone_type": zone_name,
                "violations": [],
                "floor_count": req.floors,
                "building_height_m": req.planned_height_m,
            }, evidence_text=evidence)
            if isinstance(interp, dict) and interp:
                _labels = {
                    "permit_assessment": "인허가 난이도",
                    "exception_analysis": "예외 조항",
                    "relaxation_options": "완화 가능성",
                    "timeline_estimate": "소요 기간",
                    "risk_factors": "리스크 요인",
                    "strategy_recommendation": "전략 제안",
                }
                sections = [f"[{_labels[k]}] {interp[k]}" for k in _labels if interp.get(k)]
                if sections:
                    summary = summary + "\n\n" + "\n\n".join(sections)
        except Exception:
            pass

    # ── WP-P: 법령 근거 칩 가산(additive) — 항목별 + 응답 레벨. 기존 문자열 유지 ──
    for c in checks:
        c.setdefault(
            "legal_refs",
            _legal_refs_for(_PRE_DESIGN_LEGAL_REF_KEYS.get(str(c.get("rule_code", "")), [])),
        )
    _top_keys = _permit_base_keys(req.building_type)
    if matched:
        for k in ("bcr_limit", "far_limit"):
            if k not in _top_keys:
                _top_keys.append(k)

    out: dict[str, Any] = {
        "project_id": req.project_id,
        "phase": "pre_design",
        "violations": [c for c in checks if c["status"] == "fail"],
        "compliant": not has_fail,
        "overall_status": overall_status,
        "checks": checks,
        "summary": summary,
        "legal_refs": _legal_refs_for(_top_keys),
    }
    # 다필지 통합 적용 사실(있으면) — 프론트가 "통합 N필지 기준" 표기에 사용(미전달/1필지면 키 생략).
    if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
        out["integrated"] = {
            "parcel_count": integrated.get("parcel_count"),
            "total_area_sqm": integrated.get("total_area_sqm"),
            "dominant_zone": integrated.get("dominant_zone"),
        }
    return out


@router.post("/check", response_model=ComplianceCheckResult)
async def check_compliance(
    req: CheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """건축 법규 준수 여부를 검증한다.

    설계 기하(design.points/surfaces)가 있으면 설계단계 정합 검증을,
    없으면 부지분석(용도지역·면적) 기반 설계 전 인허가 검토를 수행한다(병행 구조).
    """
    _has_geometry = bool(
        req.design and (req.design.points or req.design.surfaces or req.design.lines)
    )
    if not _has_geometry:
        return await _pre_design_review(req)

    svc = BuildingComplianceService(db=db)
    raw = await svc.check_compliance(
        project_id=req.project_id,
        design_raw=req.design.model_dump(),
    )

    violations = raw.get("violations", []) or []
    compliant = bool(raw.get("compliant", False))

    # 중심엔진 수렴 관측(shadow, 기본 off·best-effort·무중단) — 위반 케이스를 엔진 rules로 대조.
    # ★shadow off면 테넌트 조회조차 안 함(무비용). 라우터에 인증/테넌트 없음 → project.tenant_id로 도출.
    try:
        from apps.api.config import get_settings

        if get_settings().deliberation_shadow_enabled:
            from app.services.deliberation import shadow_integration, shadow_mappers
            mapped = shadow_mappers.building_compliance(raw)
            if mapped:
                from sqlalchemy import select

                from apps.api.database.models.project import Project
                tid = (await db.execute(
                    select(Project.tenant_id).where(Project.id == req.project_id))).scalar_one_or_none()
                # 비차단 observe(엔진 RTT가 검증 응답을 막지 않음). tid 없으면 no-op.
                shadow_integration.observe(
                    "building_compliance",
                    (tid.hex if hasattr(tid, "hex") else str(tid)) if tid is not None else None,
                    mapped)
    except Exception as _e:  # noqa: BLE001 — 관측은 법규검증 흐름 절대 방해 금지(로그만, design_audit와 대칭)
        import structlog
        structlog.get_logger(__name__).warning("shadow 관측 실패(building_compliance)", err=str(_e)[:120])

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
            # WP-P: 위반유형 → 레지스트리 근거 칩(additive·미매핑은 빈 배열).
            "legal_refs": _legal_refs_for(
                _VIOLATION_LEGAL_REF_KEYS.get(str(v.get("type", "")), [])
            ),
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

    # ── WP-P: 응답 레벨 법령 근거(additive) — 공통 인허가 + 위반항목 근거 합산 ──
    _top_keys = _permit_base_keys(req.building_type)
    for v in violations:
        for k in _VIOLATION_LEGAL_REF_KEYS.get(str(v.get("type", "")), []):
            if k not in _top_keys:
                _top_keys.append(k)

    return {
        "project_id": req.project_id,
        "violations": violations,
        "compliant": compliant,
        "overall_status": overall_status,
        "checks": checks,
        "summary": summary,
        "legal_refs": _legal_refs_for(_top_keys),
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


# ── 주소·용도지역 기반 법규 검토(파이프라인 법규 단계 전용) ──
# ★로컬 한도표(_LEGAL_LIMITS_PCT) 제거: 서브스트링 부분일치('농림축산…'→'농림',
# '준주거 검토용지'→'준주거')로 거짓 확정하는 fail-open 버그가 있었다. 용도지역 한도는
# 공용 SSOT resolve_zone_limits(zone_limit_contract, fail-closed 계약)로 일원화한다.


class LegalCheckRequest(BaseModel):
    address: str | None = None
    zone_code: str | None = None          # 용도지역명(부지분석 zoneCode) 또는 코드
    planned_bcr: float = 0                 # 계획 건폐율(%)
    planned_far: float = 0                 # 계획 용적률(%)
    planned_height_m: float = 0            # 계획 높이(m)
    planned_floors: int = 0


class LegalCheckResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    address: str | None = None
    zone_code: str | None = None
    zone_name: str | None = None
    bcr_limit: float = 0
    bcr_planned: float = 0
    bcr_pass: bool = True
    far_limit: float = 0
    far_planned: float = 0
    far_pass: bool = True
    height_limit_m: float = 0
    height_planned_m: float = 0
    height_pass: bool = True
    overall_pass: bool = True
    # 판정 상태(가산 필드): "pass"(적합) / "fail"(부적합) / "needs_verification"(미확인).
    # ★fail-open 제거 핵심: 용도지역 미확인은 적합/부적합이 아니라 'needs_verification'으로 정직 표기.
    overall_status: str = "pass"
    remarks: str | None = None


# ── 항목별 정량 룰검토(BuildingCodeRuleEngine 8개 룰 노출) ──
# legal-check가 건폐율/용적률/높이 3개만 보는 반면, rule-check는 이미 구현된
# BuildingCodeRuleEngine.check_all(8개 룰·조문)을 그대로 직렬화한다. 새 룰 로직 작성 금지.
# 입력 부족 시 엔진이 WARNING/N/A로 정직 반환(가짜 pass 금지).


class RuleCheckRequest(BaseModel):
    """부지분석·설계 컨텍스트(없으면 None/0으로 graceful)."""

    # ── 부지(site_params) ──
    zone_code: str | None = None        # 용도지역명(부지분석 zoneCode). ZONE_DEFAULTS 키와 매칭.
    land_area_sqm: float = 0            # 대지면적(㎡)
    max_bcr: float | None = None        # 허용 건폐율(%). 미입력 시 zone_code로 보완.
    max_far: float | None = None        # 허용 용적률(%). 미입력 시 zone_code로 보완.
    max_height_m: float | None = None   # 높이제한(m). 0/None=제한없음.
    north_boundary_m: float = 0         # 정북방향 인접대지경계선까지 거리(m). 일조권용.

    # ── 설계(design_params) ──
    building_type: str | None = None    # 건물유형(아파트/공동주택/오피스텔/근린생활시설 등)
    building_area_sqm: float = 0        # 건축면적(㎡)
    total_gfa_sqm: float = 0            # 연면적(㎡)
    floor_count_above: int = 0          # 지상 층수
    floor_count_below: int = 0          # 지하 층수
    building_height_m: float = 0        # 건물 높이(m). 0이면 층수×3.3 추정.
    unit_count: int = 0                 # 세대/호수
    setback_m: float | None = None      # 건축선 후퇴거리(m)
    parking_count: int = 0              # 계획 주차대수
    floor_area_per_floor_sqm: float = 0  # 층당 바닥면적(㎡)


class RuleCheckItem(BaseModel):
    rule_id: str
    rule_name: str
    legal_basis: str
    status: str                         # pass / fail / warning / n/a
    required_value: str
    actual_value: str
    message: str
    # WP-P: 룰별 법령 근거 칩(additive·기본 빈 배열 — 구버전 소비자 무영향).
    # legal_basis 자유문자열은 그대로 두고, 레지스트리 검증 근거만 가산한다.
    legal_refs: list[dict[str, Any]] = Field(default_factory=list)


class RuleCheckResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    zone_code: str | None = None
    zone_name: str | None = None
    overall_status: str = "warning"     # pass / fail / warning
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0
    na_count: int = 0
    results: list[RuleCheckItem] = Field(default_factory=list)
    summary: str | None = None
    # WP-P: 응답 레벨 법령 근거(additive) — 공통 인허가 + 8룰 근거 합산(중복 제거).
    legal_refs: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/rule-check", response_model=RuleCheckResponse)
async def rule_check(req: RuleCheckRequest) -> RuleCheckResponse:
    """이미 구현된 BuildingCodeRuleEngine.check_all(8개 룰)을 항목별 정량검토로 노출.

    건폐율·용적률·높이·건축선후퇴·주차·일조·피난방화·장애인편의 8개 항목을 조문과 함께
    반환한다. 부지/설계 입력이 부족하면 엔진이 검토필요(warning)/해당없음(n/a)으로 정직 반환.
    """
    from app.services.permit.building_code_rules import (
        ZONE_DEFAULTS,
        BuildingCodeRuleEngine,
    )

    zone = (req.zone_code or "").strip()
    # ZONE_DEFAULTS 키와 부분일치하는 용도지역명(엔진의 건축선후퇴/일조권 분기에 사용).
    matched_zone = next((name for name in ZONE_DEFAULTS if name in zone), None)

    # 법정 한도 보완: 미입력 시 zone_code 기반 공용 SSOT resolve_zone_limits(fail-closed)로 채움.
    # ★로컬표 서브스트링 매칭 제거 — 확정 매칭(matched=True)일 때만 확정 한도를 채운다.
    #   미매칭이면 None으로 남겨 아래 엔진 기본값(60/200/0)의 graceful 폴백에 맡긴다(거짓 확정 금지).
    max_bcr = req.max_bcr
    max_far = req.max_far
    max_height = req.max_height_m
    if max_bcr is None or max_far is None or max_height is None:
        from app.services.zoning.zone_limit_contract import resolve_zone_limits

        resolution = resolve_zone_limits(zone)
        if resolution.matched:
            if max_bcr is None:
                max_bcr = resolution.max_bcr_pct
            if max_far is None:
                max_far = resolution.max_far_pct
            # SSOT는 높이 상한을 두지 않음(별도규정) → 0.0(기존 로컬표 높이도 전부 0).
            if max_height is None:
                max_height = 0.0

    site_params: dict[str, Any] = {
        "land_area_sqm": req.land_area_sqm,
        "max_bcr": max_bcr if max_bcr is not None else 60,
        "max_far": max_far if max_far is not None else 200,
        "max_height": max_height if max_height is not None else 0,
        "zone_type": matched_zone or zone,
        "north_boundary_m": req.north_boundary_m,
    }
    design_params: dict[str, Any] = {
        "building_area_sqm": req.building_area_sqm,
        "total_gfa_sqm": req.total_gfa_sqm,
        "floor_count_above": req.floor_count_above or 1,
        "floor_count_below": req.floor_count_below,
        "building_height_m": req.building_height_m,
        "unit_count": req.unit_count,
        "building_type": req.building_type or "아파트",
        "parking_count": req.parking_count,
        "floor_area_per_floor_sqm": req.floor_area_per_floor_sqm,
    }
    if req.setback_m is not None:
        design_params["setback_m"] = req.setback_m

    raw_results = BuildingCodeRuleEngine().check_all(design_params, site_params)
    results = [
        RuleCheckItem(
            rule_id=r.rule_id,
            rule_name=r.rule_name,
            legal_basis=r.legal_basis,
            status=str(r.status),
            required_value=r.required_value,
            actual_value=r.actual_value,
            message=r.message,
            # WP-P: 룰 성격별 레지스트리 근거 칩(additive). 미매핑 룰은 빈 배열
            # (legal_basis 텍스트만 — 할루시네이션 링크 금지).
            legal_refs=_legal_refs_for(_RULE_LEGAL_REF_KEYS.get(r.rule_id, [])),
        )
        for r in raw_results
    ]

    fail_count = sum(1 for r in results if r.status == "fail")
    warning_count = sum(1 for r in results if r.status == "warning")
    na_count = sum(1 for r in results if r.status == "n/a")
    pass_count = sum(1 for r in results if r.status == "pass")
    overall = "fail" if fail_count else ("warning" if warning_count else "pass")
    summary = (
        f"법규 8개 항목 검토: 적합 {pass_count} / 부적합 {fail_count} / "
        f"검토필요 {warning_count} / 해당없음 {na_count}."
    )

    # ── WP-P: 응답 레벨 법령 근거(additive) — 공통 인허가 + 8룰 매핑 합산(중복 제거) ──
    _top_keys = _permit_base_keys(req.building_type)
    for r in raw_results:
        for k in _RULE_LEGAL_REF_KEYS.get(r.rule_id, []):
            if k not in _top_keys:
                _top_keys.append(k)

    return RuleCheckResponse(
        zone_code=req.zone_code,
        zone_name=matched_zone,
        overall_status=overall,
        pass_count=pass_count,
        fail_count=fail_count,
        warning_count=warning_count,
        na_count=na_count,
        results=results,
        summary=summary,
        legal_refs=_legal_refs_for(_top_keys),
    )


@router.post("/legal-check", response_model=LegalCheckResponse)
async def legal_check(req: LegalCheckRequest) -> LegalCheckResponse:
    """부지분석 용도지역 기반 건축 법규(건폐율/용적률/높이) 적합성 검토.

    ★fail-open 제거: 용도지역 한도 조회를 (과거의 로컬 서브스트링 한도표가 아닌) 공용 SSOT
    resolve_zone_limits(fail-closed 계약)로 일원화한다. 미등록/미인식 용도지역은
    '적합'(overall_pass=True)으로 절대 반환하지 않고 'needs_verification'(미확인)으로
    정직하게 반환한다. 이 계약은 서브스트링 오매칭('' in k 등)도 구조적으로 차단한다.
    """
    # 공용 fail-closed 계약(SSOT). 로컬 임포트로 라우터 상단 의존성 최소화(rule_check 패턴 동일).
    from app.services.zoning.zone_limit_contract import resolve_zone_limits

    zone = (req.zone_code or "").strip()
    resolution = resolve_zone_limits(req.zone_code)

    # ── 미확인(fail-closed): 용도지역이 확정 매칭되지 않음 → 확정 한도(max_*_pct)가 None ──
    # ★절대 overall_pass=True 금지. 적합/부적합이 아닌 '미확인'으로 정직 표기.
    if not resolution.matched or resolution.max_bcr_pct is None or resolution.max_far_pct is None:
        return LegalCheckResponse(
            address=req.address, zone_code=req.zone_code,
            bcr_planned=req.planned_bcr, far_planned=req.planned_far,
            height_planned_m=req.planned_height_m,
            overall_pass=False,
            overall_status="needs_verification",
            remarks=(
                f"용도지역('{zone or '미상'}') 법정 한도 미확인 — "
                "확정 판정 불가(조례·실제 한도 확인 필요)."
            ),
        )

    # ── 확정 매칭: SSOT 한도값 사용(로컬표 드리프트 제거) ──
    bcr_lim = resolution.max_bcr_pct
    far_lim = resolution.max_far_pct
    # 높이: SSOT는 높이 상한을 두지 않음(기존 로컬표도 전부 0=별도규정). 별도규정으로 통과 처리.
    h_lim = 0.0
    bcr_pass = req.planned_bcr <= bcr_lim if req.planned_bcr > 0 else True
    far_pass = req.planned_far <= far_lim if req.planned_far > 0 else True
    height_pass = True if h_lim == 0 else (req.planned_height_m <= h_lim)
    overall = bcr_pass and far_pass and height_pass
    notes = []
    if not bcr_pass:
        notes.append(f"건폐율 {req.planned_bcr}% > 상한 {bcr_lim}%")
    if not far_pass:
        notes.append(f"용적률 {req.planned_far}% > 상한 {far_lim}%")
    if not height_pass:
        notes.append(f"높이 {req.planned_height_m}m > 상한 {h_lim}m")

    resp = LegalCheckResponse(
        address=req.address, zone_code=req.zone_code, zone_name=resolution.zone_type,
        bcr_limit=bcr_lim, bcr_planned=req.planned_bcr, bcr_pass=bcr_pass,
        far_limit=far_lim, far_planned=req.planned_far, far_pass=far_pass,
        height_limit_m=h_lim, height_planned_m=req.planned_height_m, height_pass=height_pass,
        overall_pass=overall,
        overall_status="pass" if overall else "fail",
        remarks=("적합 — 법정 상한 이내(조례 별도 확인)." if overall else " / ".join(notes)),
    )
    # 법령 근거키(가산·옵셔널) — 확정 매칭 시 근거 조문키 부착(응답은 extra="allow").
    if resolution.legal_ref_keys:
        resp.legal_ref_keys = list(resolution.legal_ref_keys)
    return resp

