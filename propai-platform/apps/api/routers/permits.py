"""Permit submission and tracking router for v53."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import PermitStatusResponse, PermitSubmissionRequest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from app.services.land_intelligence.parcel_normalize import ParcelsIn
from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.seumter_permit_service import SeumterPermitService

router = APIRouter()


# ── 건축법규 준수 검증 (주소 기반) ──


class ComplianceCheckRequest(BaseModel):
    """주소 기반 건축법규 준수 검증 요청."""
    address: str
    zoning_district: str | None = None
    project_type: str | None = None
    floor_count: int | None = None
    area_sqm: float | None = None  # 대지면적(명시값 있으면 단일필지 면적으로 사용)
    # 다필지 통합 개발 시 필지 목록(2개 이상이면 면적가중 통합면적·우세용도로 보정).
    #   행 계약(프론트 전송 키): {address, area_sqm, zone_type, farPct, bcrPct, farLegalPct, bcrLegalPct}.
    #   미전달/1필지면 기존 단일필지 동작 그대로(무회귀).
    #   ★공용 정규화(ParcelsIn): str[]/dict[] 양 shape → canonical dict[](무음 no-op 제거).
    #   ※ /permits/ai-analysis 의 list[str] parcels(주소배열)는 별개 계약 — 변경 대상 아님.
    parcels: ParcelsIn | None = None


class ComplianceItemResult(BaseModel):
    category: str = ""
    rule: str = ""
    status: str = "pass"
    detail: str = ""


class ComplianceCheckResponse(BaseModel):
    address: str = ""
    zoning_district: str | None = None
    results: list[ComplianceItemResult] = Field(default_factory=list)
    overall_status: str = "pass"
    summary: str = ""
    checked_at: str = ""
    # ── additive(하위호환): 실효/법정/특이부지 정직 반영 필드 ──
    # 기존 프론트는 위 필드만 읽으므로 아래는 옵셔널 가산 — 미상이면 None/빈 배열(가짜값 금지).
    zone_source: str | None = None          # 용도지역 출처(입력값/주소자동조회/미상)
    effective_far_pct: float | None = None  # 실효 용적률(법정·조례 중 낮은 값 + 계획상한)
    effective_bcr_pct: float | None = None  # 실효 건폐율
    legal_far_pct: float | None = None       # 법정상한 용적률(국토계획법, 라벨 전용)
    legal_bcr_pct: float | None = None       # 법정상한 건폐율
    far_basis: str | None = None             # 실효 산정 근거(법정/조례/계획상한 등)
    developability: str | None = None        # 특이부지 게이트(POSSIBLE/CONDITIONAL/...)
    special_parcel: dict[str, Any] | None = None  # 특이부지 감지 결과(경고·해결방안·정직고지)
    # 다필지 통합 적용 사실(2필지 이상일 때만) — 프론트가 "통합 N필지 기준" 표기에 사용.
    integrated: dict[str, Any] | None = None


def _normalize_zone(zone: str | None) -> str | None:
    """입력 용도지역명을 법정 표준키로 정규화. 미매칭이면 None(미상으로 정직 처리)."""
    if not zone or not zone.strip():
        return None
    try:
        from app.services.zoning.legal_zone_limits import normalize_zone_name

        return normalize_zone_name(zone)
    except Exception:  # noqa: BLE001
        return None


@router.post(
    "/compliance-check",
    response_model=ComplianceCheckResponse,
    dependencies=[Depends(enforce_llm_quota)],
)
async def check_building_compliance(
    req: ComplianceCheckRequest,
):
    """주소 기반 건축법규 준수 여부를 검증한다.

    실효 용적률/건폐율(법정범위→조례→계획상한)·특이부지(학교용지·산지·맹지 등) 게이트를
    실제 용도지역 기반으로 산출한다. 하드코딩 한도 테이블·'일반상업지역' 디폴트는 쓰지 않으며,
    용도지역을 확정하지 못하면 한도를 단정하지 않고 '미상'으로 정직 고지한다(할루시네이션 차단).
    """
    # ── 1) 용도지역 확정: 입력값 우선, 미입력 시 주소 자동조회(AutoZoningService) ──
    # 절대 '일반상업지역' 같은 가짜 디폴트로 채우지 않는다. 못 구하면 None(미상).
    zone = _normalize_zone(req.zoning_district)
    zone_source = "입력값" if zone else None
    land_category: str | None = None
    special_districts: list = []
    land_area = 0.0
    zoning_base: dict[str, Any] = {}

    if not zone and req.address:
        try:
            from apps.api.app.services.zoning.auto_zoning_service import AutoZoningService

            zoning_base = await AutoZoningService().analyze_by_address(req.address) or {}
            zone = _normalize_zone(zoning_base.get("zone_type"))
            if zone:
                zone_source = "주소자동조회"
            land_category = zoning_base.get("land_category")
            special_districts = zoning_base.get("special_districts") or []
            land_area = float(zoning_base.get("land_area_sqm") or 0)
        except Exception:  # noqa: BLE001 — 조회 실패는 미상으로 정직 처리(가짜값 금지)
            zoning_base = {}

    # 명시 area_sqm(단일필지)이 오면 zoning_base 미수집 시에도 가능면적 산정에 사용(폴백).
    if (land_area or 0) <= 0 and req.area_sqm and req.area_sqm > 0:
        land_area = req.area_sqm

    # ── 다필지 통합면적/통합용도 보정(시장보고서와 동일 공용패턴) ──
    # parcels가 2필지 이상이면 대표 1필지가 아니라 '면적가중 통합면적·우세용도'로 zoning_district·
    #   가능면적을 보정한다(요청에 명시값이 있어도 통합값 우선 — 단 우세용도가 mixed_review_required면
    #   기존 zone 유지). ★공용 단일경유: /zoning/integrated-analysis와 동일한 ComprehensiveAnalysisService.
    #   _integrated_context(면적가중 _aggregate_integrated_zoning 재사용) — 산식 복제 0. dict 행만 통과.
    #   1필지 이하/실패면 통합 안 함(기존 단일 경로 그대로 = 무회귀).
    integrated: dict[str, Any] | None = None
    _rows = [p for p in (req.parcels or []) if isinstance(p, dict)]
    if len(_rows) >= 2:
        try:
            from app.services.land_intelligence.comprehensive_analysis_service import (
                ComprehensiveAnalysisService,
            )

            integrated = await ComprehensiveAnalysisService()._integrated_context(_rows)
        except Exception:  # noqa: BLE001 — 통합집계 실패는 단일 경로로 폴백(검증 무중단)
            import structlog
            structlog.get_logger(__name__).warning("인허가 다필지 통합집계 실패 — 단일 경로 폴백(graceful)")
            integrated = None
    if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
        land_area = float(integrated["total_area_sqm"])  # 통합면적으로 가능면적 산정
        _dom = integrated.get("dominant_zone")
        if _dom and _dom != "mixed_review_required":
            _z2 = _normalize_zone(str(_dom))
            if _z2:  # 통합 우세용도(정규화 성공 시)로 한도 매칭. 정규화 실패면 기존 zone 유지.
                zone = _z2
                zone_source = "다필지 통합(우세용도)"

    results: list[ComplianceItemResult] = []
    overall = "pass"

    # ── 2) 용도지역 미상 — 한도 단정 불가(정직 처리) ──
    if not zone:
        results.append(ComplianceItemResult(
            category="용도지역",
            rule="용도지역 미상",
            status="info",
            detail=(
                "용도지역을 확정하지 못해 건폐율·용적률·높이 한도를 단정할 수 없습니다. "
                "정확한 용도지역(예: 제2종일반주거지역)을 입력하거나, 토지이용계획확인원으로 "
                "용도지역을 확인한 뒤 다시 검증해 주세요."
            ),
        ))
        return ComplianceCheckResponse(
            address=req.address,
            zoning_district=None,
            results=results,
            overall_status="pass",
            summary="용도지역 미상 — 한도 단정 불가(정직 고지). 용도지역 확정 후 정밀 검증 가능합니다.",
            checked_at=datetime.now().isoformat(),
            zone_source="미상",
        )

    # ── 3) 법정상한(라벨 전용) + 실효 용적률/건폐율(법정→조례→계획상한) 산출 ──
    legal_far = legal_bcr = None
    try:
        from app.services.zoning.legal_zone_limits import legal_limits_for

        legal = legal_limits_for(zone) or {}
        legal_far = legal.get("max_far_pct")
        legal_bcr = legal.get("max_bcr_pct")
    except Exception:  # noqa: BLE001
        legal = {}

    # 조례 SSOT 주입(analyze_zoning과 동일 패턴) — local_ordinance 없으면 OrdinanceService 조회.
    try:
        lo = zoning_base.get("local_ordinance")
        has_ord = isinstance(lo, dict) and lo.get("ordinance_far")
        if not has_ord and req.address:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            _ord = await OrdinanceService().get_ordinance_limits(req.address, zone)
            if isinstance(_ord, dict) and _ord.get("ordinance_far"):
                zoning_base["local_ordinance"] = _ord
    except Exception:  # noqa: BLE001 — 조례 조회 실패 시 법정값 폴백(무손상)
        pass

    # 실효 용적률 계층(far_tier_service 단일출처) — base에 zone_type/zone_limits/조례/구역 포함.
    eff_far = eff_bcr = far_basis = None
    try:
        from app.services.land_intelligence import far_tier_service

        zoning_base.setdefault("zone_type", zone)
        eff = far_tier_service.calc_effective_far(zoning_base, zone, land_area)
        eff_far = eff.get("effective_far_pct")
        eff_bcr = eff.get("effective_bcr_pct")
        far_basis = eff.get("far_basis")
        if legal_far is None:
            legal_far = eff.get("legal_max_far_pct")
    except Exception:  # noqa: BLE001 — 실효 산정 실패 시 법정상한만 표기(미상 아님)
        pass

    # ── 4) 특이부지 게이트(학교용지·산지·맹지·규제구역 등) — 개발가능 단정 차단 ──
    special: dict[str, Any] | None = None
    try:
        from app.services.zoning.special_parcel import detect_special_parcel

        special = detect_special_parcel({
            "zone_type": zone,
            "land_category": land_category,
            "special_districts": special_districts,
            "road_contact": None,
            "road_width_m": None,
        })
    except Exception:  # noqa: BLE001
        special = None

    # ── 5) 결과 항목 구성 ──
    # 건폐율·용적률: 실효값 우선 표기, 법정상한은 별도 라벨로만(조례 실효 미반영 오류 차단).
    if eff_far is not None:
        far_detail = f"실효 용적률 한도는 {eff_far:g}%입니다"
        if far_basis:
            far_detail += f" (근거: {far_basis})"
        if legal_far is not None and float(legal_far) != float(eff_far):
            far_detail += f". 법정상한은 {float(legal_far):g}%입니다(조례·계획에 따라 실효값이 다를 수 있음)"
        far_detail += ". 설계 데이터 입력 시 정밀 검증 가능합니다."
        results.append(ComplianceItemResult(
            category="용적률", rule=f"{zone} 실효 {eff_far:g}%", status="info", detail=far_detail,
        ))
    elif legal_far is not None:
        results.append(ComplianceItemResult(
            category="용적률", rule=f"{zone} 법정상한 {float(legal_far):g}%", status="info",
            detail=(f"법정상한 용적률은 {float(legal_far):g}%입니다(조례 실효값 미확인 — 지자체 도시계획 "
                    "조례 확인 시 더 낮아질 수 있음). 설계 데이터 입력 시 정밀 검증 가능합니다."),
        ))

    if eff_bcr is not None:
        bcr_detail = f"실효 건폐율 한도는 {eff_bcr:g}%입니다"
        if legal_bcr is not None and float(legal_bcr) != float(eff_bcr):
            bcr_detail += f" (법정상한 {float(legal_bcr):g}%)"
        bcr_detail += ". 설계 데이터 입력 시 정밀 검증 가능합니다."
        results.append(ComplianceItemResult(
            category="건폐율", rule=f"{zone} 실효 {eff_bcr:g}%", status="info", detail=bcr_detail,
        ))
    elif legal_bcr is not None:
        results.append(ComplianceItemResult(
            category="건폐율", rule=f"{zone} 법정상한 {float(legal_bcr):g}%", status="info",
            detail=(f"법정상한 건폐율은 {float(legal_bcr):g}%입니다(조례 실효값 미확인). "
                    "설계 데이터 입력 시 정밀 검증 가능합니다."),
        ))

    # 층수 검증: 높이 한도는 용도지역만으로 단정 불가(지구·일조·도로사선 의존) → 단정 표기 금지.
    if req.floor_count:
        results.append(ComplianceItemResult(
            category="높이제한",
            rule=f"{zone} 높이·층수 제한(개별 검토)",
            status="info",
            detail=(f"요청 {req.floor_count}층의 적합 여부는 용도지역만으로 단정할 수 없습니다"
                    "(지구단위계획·일조권·도로사선·고도지구 등 적용). 설계 데이터 입력 시 정밀 검증 가능합니다."),
        ))

    # 특이부지 경고: 개발가능성 게이트가 POSSIBLE이 아니면 '개발가능'으로 단정하지 않고 정직 고지.
    if special and special.get("developability") and special.get("developability") != "POSSIBLE":
        overall = "warn"
        gate = special.get("developability")
        warn_lines = list(special.get("warnings") or [])
        caveat = special.get("development_caveat") or ""
        honest = special.get("honest_disclosure") or ""
        detail = " ".join([x for x in ([caveat, honest] + warn_lines) if x]) or \
            "특이 토지특성이 감지되어 법정/실효 한도가 그대로 실현되지 않을 수 있습니다."
        results.append(ComplianceItemResult(
            category="특이부지",
            rule=f"개발가능성: {special.get('severity_label') or gate}",
            status="warn",
            detail=detail,
        ))

    summary = f"{zone} 기준 법규 검증 완료"
    if overall == "warn":
        summary += " — 특이 토지특성 경고 있음(개발가능성·선행절차 확인 필요)"
    else:
        summary += " (적합)"

    return ComplianceCheckResponse(
        address=req.address,
        zoning_district=zone,
        results=results,
        overall_status=overall,
        summary=summary,
        checked_at=datetime.now().isoformat(),
        zone_source=zone_source,
        effective_far_pct=float(eff_far) if eff_far is not None else None,
        effective_bcr_pct=float(eff_bcr) if eff_bcr is not None else None,
        legal_far_pct=float(legal_far) if legal_far is not None else None,
        legal_bcr_pct=float(legal_bcr) if legal_bcr is not None else None,
        far_basis=far_basis,
        developability=(special.get("developability") if special else "POSSIBLE"),
        special_parcel=special,
        # 다필지 통합 적용 사실(있으면) — 미전달/1필지면 None(단일 경로 무회귀).
        integrated=(
            {
                "parcel_count": integrated.get("parcel_count"),
                "total_area_sqm": integrated.get("total_area_sqm"),
                "dominant_zone": integrated.get("dominant_zone"),
            }
            if integrated and float(integrated.get("total_area_sqm") or 0) > 0
            else None
        ),
    )


class PermitFeasibilityRequest(BaseModel):
    """용도지역 기반 개발방식별 인허가 가능성(허용/불가/복잡도) 조회 요청."""

    zone_type: str


class PermitFeasibilityItem(BaseModel):
    development_type: str = ""
    type_name: str = ""
    zone_type: str = ""
    is_permitted: bool = False
    permit_complexity: int = 3
    complexity_label: str = ""
    reason: str = ""


class PermitFeasibilityResponse(BaseModel):
    zone_type: str = ""
    permitted_count: int = 0
    total_count: int = 0
    items: list[PermitFeasibilityItem] = Field(default_factory=list)
    summary: str = ""


@router.post("/feasibility-matrix", response_model=PermitFeasibilityResponse)
async def get_permit_feasibility_matrix(
    req: PermitFeasibilityRequest,
) -> PermitFeasibilityResponse:
    """용도지역(zone_type) 기준 개발방식별 인허가 가능/불가·복잡도를 산출한다.

    permit_validator(ZONE_PERMIT_MATRIX·PERMIT_COMPLEXITY) 실엔진을 그대로 노출하여,
    해당 용도지역에서 어떤 개발방식이 가능/불가/조건부인지를 프로젝트별로 제공한다.
    """
    from app.services.feasibility.permit_validator import (
        DEVELOPMENT_TYPE_NAMES,
        check_permit_feasibility,
    )

    zone = (req.zone_type or "").strip()
    if not zone:
        raise HTTPException(status_code=400, detail="용도지역(zone_type)이 필요합니다.")

    items = [
        PermitFeasibilityItem(**check_permit_feasibility(code, zone))
        for code in DEVELOPMENT_TYPE_NAMES
    ]
    # 가능한 것 먼저, 그다음 복잡도 낮은 순
    items.sort(key=lambda x: (not x.is_permitted, x.permit_complexity))
    permitted = sum(1 for it in items if it.is_permitted)
    return PermitFeasibilityResponse(
        zone_type=zone,
        permitted_count=permitted,
        total_count=len(items),
        items=items,
        summary=f"{zone}에서 {permitted}/{len(items)}개 개발방식 인허가 가능",
    )


@router.get("/guide")
async def permit_guide(facility_type: str = "단독주택", sigungu: str | None = None):
    """쉬운 규제안내서 — 시설물(건축물 용도)별 인허가 절차(단계별)+관련법령(verified)+제출서류.

    토지이음 '규제안내서 > 쉬운 규제안내서'의 법령엔진 연계판. 주택류(단독·공동·다세대)는
    주택법 절차(사업계획승인·주택공급)를 추가한다. 무날조: 법령 링크는 레지스트리 verified만.
    """
    from app.services.permit.permit_guide_service import get_permit_guide

    return get_permit_guide(facility_type, sigungu=sigungu)


@router.post("/submit", response_model=PermitStatusResponse)
async def submit_permit(
    body: PermitSubmissionRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "write")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.submit(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        permit_type=body.permit_type,
        region=body.region,
        building_area_sqm=body.building_area_sqm,
        is_public=body.is_public,
        is_agricultural=body.is_agricultural,
        applicant_name=body.applicant_name,
        submit_to_seumter=body.submit_to_seumter,
        submitted_document_ids=body.submitted_document_ids,
    )
    return PermitStatusResponse.model_validate(result)


@router.get("/{project_id}/latest", response_model=PermitStatusResponse)
async def get_latest_permit(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)


@router.get("/submissions/{submission_id}/status", response_model=PermitStatusResponse)
async def get_permit_status(
    submission_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_status(
        tenant_id=current_user.tenant_id,
        submission_id=submission_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)


class AIPermitAnalysisRequest(BaseModel):
    """인.허가 AI 분석 요청."""

    address: str
    pnu: str | None = None
    site: dict[str, Any] | None = None  # 부지분석 결과(있으면 재수집 생략)
    parcels: list[str] | None = None  # 다필지 통합 개발 시 추가 필지 주소(2개 이상이면 통합 용적률 산정)
    use_llm: bool = True  # AI 내러티브(개발방식별 LLM 분석) 포함 여부(사용자 선택)
    refresh: bool = False  # True이면 저장본을 무시하고 재분석 후 덮어씀


@router.post("/ai-analysis", dependencies=[Depends(enforce_llm_quota)])
async def ai_permit_analysis(
    req: AIPermitAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
) -> dict[str, Any]:
    """부지분석+조례+상위법령을 종합해 개발방식별 인허가 가능성·문제점·해결방안을 AI 분석.

    parcels에 2개 이상의 필지 주소가 오면 용도지역이 다른 토지를 통합 개발할 때의
    면적가중평균(법정)·최적·최고 용적률을 관련법규와 함께 산정한다.

    첫 호출만 느리고, 이후 같은 입력은 저장본을 즉시 반환한다.
    req.refresh=True 를 보내면 재분석 후 저장본을 덮어쓴다.
    """
    from app.services.common.analysis_cache import _key, cache_get, cache_put
    from app.services.permit.permit_analysis_service import PermitAnalysisService

    if not req.address or not req.address.strip():
        raise HTTPException(status_code=400, detail="주소가 필요합니다.")

    addr = req.address.strip()
    # parcels를 정렬해 순서 무관하게 동일 키가 나오게 한다
    parcels_str = ",".join(sorted(req.parcels or []))
    cache_key = _key(addr, str(req.pnu), str(req.use_llm), parcels_str)

    # 저장본이 있고 재분석 요청이 아니면 즉시 반환
    if not req.refresh:
        cached = await cache_get("permit_ai_analysis", cache_key)
        if cached is not None:
            return cached

    # 실제 분석 실행 → 저장 → 반환
    result = await PermitAnalysisService().analyze(
        addr, req.site or {}, parcels=req.parcels, use_llm=req.use_llm
    )
    # ── 전역정책 Phase0: 인허가 분석 결과에 근거·법령링크 공용블록 가산(additive·graceful·response_model 없음) ──
    #   인허가 가능성 판정의 법적 근거(국토계획법 용도지역·건폐·용적, 건축법 건폐·용적·일조, 지자체 조례)를
    #   클릭 가능한 법령링크로 제공한다(진실원천 배선갭 해소·레지스트리 verified 키 사용). 기존 result 무손상,
    #   evidence/legal_refs/provenance만 setdefault로 가산(이미 있으면 보존). 조례는 시군구로 url 치환.
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        # 조례 url 치환용 시군구 추출 — ★'구'(자치구·가장 구체적)를 우선하고, 없으면 마지막 시/군을
        #   쓴다. '서울특별시 동작구'에서 첫 매칭(서울특별시·광역시)을 잡으면 조례가 엉뚱한 광역시로
        #   가리키므로(구 단위 조례 다수), 구를 우선해 '동작구 도시계획 조례'로 정확히 치환한다.
        _sg_toks = [t for t in addr.split() if len(t) >= 2 and t.endswith(("구", "시", "군"))]
        sg = next((t for t in _sg_toks if t.endswith("구")), None) or (_sg_toks[-1] if _sg_toks else None)
        ev_block = build_evidence_block(
            legal_ref_keys=[
                "zone_use", "bcr_law", "far_law", "bldg_bcr", "bldg_far",
                "daylight_height", "ordinance_bcr", "ordinance_far",
            ],
            sigungu=sg,
            # provenance 출처는 레지스트리 등록명만(미등록명은 registered:false 무의미). VWorld 토지특성=vworld_land_info.
            sources=["vworld_land_info"],
        )
        for _k in ("evidence", "legal_refs", "provenance"):
            if ev_block.get(_k):
                result.setdefault(_k, ev_block[_k])
    except Exception:  # noqa: BLE001 — 근거블록 실패해도 인허가 분석 결과 무손상
        pass
    # ★성장루프 조인키: 분석 요약을 원장에 best-effort 적재(멱등) 후 최상위 `ledger_hash` 노출.
    #   cache_put 이전에 부착해 캐시 히트 응답에도 조인키가 실리게 한다(같은 내용=같은 해시).
    try:
        from app.services.ledger.analysis_ledger_service import attach_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        wb = await record_user_analysis(
            analysis_type="permit_ai",
            summary={
                "address": addr, "pnu": req.pnu,
                "parcel_count": len(req.parcels or []) or 1,
                "use_llm": req.use_llm,
                "verdict": result.get("verdict") or result.get("overall_assessment"),
                "development_methods": [
                    (m.get("method") or m.get("name"))
                    for m in (result.get("methods") or result.get("development_methods") or [])
                    if isinstance(m, dict)
                ] or None,
            },
            tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
            pnu=req.pnu or None, address=addr,
            source="permit_ai",
            # ★변동감지 표준키(input_signature/signature_parts) 재료 — 단일 소유자(ledger_adapters)에서 조합.
            parcel_count=len(req.parcels or []) or 1, use_llm=req.use_llm,
        )
        result = attach_ledger_hash(result, wb)
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 분석 결과 무손상
        pass
    await cache_put("permit_ai_analysis", cache_key, result)
    return result


# ── 인허가 서류 패키지(체크리스트+예상기간+PDF) — permit_package_service 배선 ──
#   그동안 서비스만 있고 라우터·프론트 소비처가 0인 dead code 였다("만들어놓고 배선 안 함" 해소).
#   LLM 미사용(정적 기준표+PDF 렌더) → 과금(enforce_llm_quota) 게이트 불필요.
#   ★track_permit_status 는 배선하지 않는다(무목업): 세움터/DB 등 실제 상태 원천을 조회하지 않고
#     호출자가 보낸 단계명을 진행률로 되돌려주는 계산기일 뿐이라, '상태추적' API 로 노출하면
#     가짜 추적이 된다. 진짜 상태조회는 이 파일의 GET /submissions/{id}/status(DB 기반)가 담당.


@router.get("/package/checklist")
async def get_permit_package_checklist(
    permit_type: str = "건축허가",
    region: str = "default",
    building_area_sqm: float = 0,
    is_public: bool = False,
    is_agricultural: bool = False,
) -> dict[str, Any]:
    """인허가 유형별 필요서류 체크리스트 + 예상 처리기간(병합 JSON).

    정적 기준표 기반 결정론 조회 — /guide(쉬운 규제안내서)와 동형의 참조성 엔드포인트.
    지원 유형: 건축허가/개발행위허가/사용승인. 미지원 유형은 400.
    building_area_sqm(200㎡ 이상 조경계획서)·is_public(BF 인증)·is_agricultural(농지전용)로
    조건부 서류의 적용 여부가 갈린다.
    """
    from apps.api.services.permit_package_service import PermitPackageService

    svc = PermitPackageService()
    try:
        checklist = svc.generate_checklist(
            permit_type,
            building_area_sqm=building_area_sqm,
            is_public=is_public,
            is_agricultural=is_agricultural,
        )
        duration = svc.estimate_permit_duration(permit_type, region)
    except ValueError as e:  # 지원하지 않는 인허가 유형 — 400 으로 정직 반환
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "permit_type": permit_type,
        "region": region,
        "checklist": checklist,
        "duration": duration,
        # 무목업 정직 고지: 기간은 내부 기준표 참고치(지자체·보완요청·심의에 따라 상이).
        "duration_basis": (
            "내부 기준표 기반 참고치 — 실제 처리기간은 지자체·서류보완·심의 여부에 따라"
            " 달라질 수 있습니다."
        ),
    }


class PermitPackagePdfRequest(BaseModel):
    """인허가 서류 패키지 PDF 생성 요청."""

    permit_type: str = "건축허가"
    region: str = "default"
    project_id: str | None = None  # 파일명 표기용(없으면 'package')
    building_area_sqm: float = 0   # 200㎡ 이상이면 조경계획서 등 조건부 서류 적용
    is_public: bool = False        # 공공건축물 여부(BF 인증 등 조건부 서류)
    is_agricultural: bool = False  # 농지 포함 여부(농지전용허가서)


@router.post("/package/pdf")
async def permit_package_pdf(
    req: PermitPackagePdfRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
):
    """인허가 서류 패키지 PDF 다운로드(체크리스트+예상기간 실렌더).

    파일 다운로드 계약: 성공=200 + application/pdf + attachment, 실패=4xx/5xx.
    200 응답에 error JSON 을 담지 않는다(프론트 blob 다운로드가 침묵 오염되는 안티패턴 차단).
    """
    from fastapi.responses import StreamingResponse

    from apps.api.services.permit_package_service import PermitPackageService

    try:
        result = await PermitPackageService().generate_permit_pdf(
            req.project_id or "package",
            {
                "permit_type": req.permit_type,
                "region": req.region,
                "building_area_sqm": req.building_area_sqm,
                "is_public": req.is_public,
                "is_agricultural": req.is_agricultural,
            },
        )
    except ValueError as e:  # 지원하지 않는 인허가 유형 — 400(200+error JSON 금지)
        raise HTTPException(status_code=400, detail=str(e)) from e

    pdf = result.get("pdf_bytes") or b""
    if not pdf.startswith(b"%PDF"):  # 렌더 실패 시 빈/깨진 파일을 200 으로 주지 않는다
        raise HTTPException(status_code=500, detail="PDF 생성에 실패했습니다.")

    # 다운로드 파일명: HTTP 헤더 안전을 위해 ASCII 안전문자만 남긴다(경로조작·인코딩 깨짐 차단).
    safe_id = re.sub(r"[^0-9A-Za-z_-]", "_", req.project_id or "package")[:64] or "package"
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="permit_package_{safe_id}.pdf"'},
    )
