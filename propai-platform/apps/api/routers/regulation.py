"""법규 검토 라우터."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from packages.schemas.models import RegulationCheckResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from app.services.land_intelligence.parcel_normalize import ParcelsIn
from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.rate_limit import ai_limiter, limiter
from apps.api.services.regulation_service import RegulationService

router = APIRouter()


class RegulationCheckRequest(BaseModel):
    project_id: UUID
    regulation_type: str
    project_info: dict


class RegulationAnalyzeRequest(BaseModel):
    """규제 종합 분석(계층) 요청 — 인증 불필요(부지 공개데이터 기반)."""

    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    use_llm: bool = True
    refresh: bool = False  # True이면 저장본을 무시하고 재분석 후 덮어씀
    # 다필지 통합 개발 시 필지 목록(2개 이상이면 면적가중 통합면적·우세용도로 보정).
    #   행 계약(프론트 전송 키): {address, area_sqm, zone_type, farPct, bcrPct, farLegalPct, bcrLegalPct}.
    #   미전달/1필지면 기존 단일필지 동작 그대로(무회귀).
    #   ★공용 정규화(ParcelsIn): str[]/dict[] 양 shape → canonical dict[](무음 no-op 제거).
    parcels: ParcelsIn | None = None


@router.post(
    "/analyze",
    summary="부지 규제 종합 분석(계층 대시보드)",
    dependencies=[Depends(enforce_llm_quota)],
)
async def analyze_regulation(body: RegulationAnalyzeRequest) -> dict:
    """부지에 적용되는 상위법령·도시계획·조례·개별규제를 계층으로 정리하고
    정량 한도(건폐/용적/높이/주차)와 AI 통합 해석을 반환한다.

    첫 호출만 느리고, 이후 같은 입력은 저장본을 즉시 반환한다.
    body.refresh=True 를 보내면 재분석 후 저장본을 덮어쓴다.
    """
    import re as _re

    from app.services.common.analysis_cache import _key, cache_get, cache_put
    from app.services.regulation.regulation_analysis_service import (
        RegulationAnalysisService,
    )

    pnu = body.pnu
    if not pnu and body.bcode and body.jibun_address:
        m = _re.search(r"(산)?(\d+)(?:-(\d+))?", body.jibun_address or "")
        if m and len(body.bcode) >= 10:
            pnu = (f"{body.bcode}{'2' if m.group(1) else '1'}"
                   f"{m.group(2).zfill(4)}{(m.group(3) or '0').zfill(4)}")
    if not body.address or not body.address.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="주소가 필요합니다.")

    addr = body.address.strip()
    # 다필지 통합은 별도 캐시 키로 분리(단일/통합 결과가 섞이지 않게) — dict 행만.
    # ★개수만이 아니라 필지 '구성'(주소·면적·용도)을 시그니처에 반영한다. 같은 대표주소·같은
    #   개수라도 면적/용도 구성이 다르면 통합결과가 다르므로, 개수만 쓰면 영속 캐시가 충돌한다.
    #   정렬해 순서 무관하게 만든다(같은 필지 집합이면 입력 순서가 달라도 동일 키).
    _rows = [p for p in (body.parcels or []) if isinstance(p, dict)]
    _parcels_sig = (
        "|".join(sorted(
            f"{(p.get('address') or '')}:{p.get('area_sqm')}:{p.get('zone_type')}"
            for p in _rows
        ))
        if len(_rows) >= 2 else ""
    )
    cache_key = _key(addr, str(pnu), str(body.use_llm), _parcels_sig)

    # 저장본이 있고 재분석 요청이 아니면 즉시 반환
    if not body.refresh:
        cached = await cache_get("regulation_analyze", cache_key)
        if cached is not None:
            return cached

    # 실제 분석 실행 → 저장 → 반환. parcels>=2면 서비스가 통합면적·우세용도로 보정.
    result = await RegulationAnalysisService().analyze(
        addr, pnu=pnu, use_llm=body.use_llm, parcels=body.parcels)
    # ★성장루프 조인키: 규제분석 요약을 원장에 best-effort 적재(멱등) 후 최상위 `ledger_hash` 노출.
    #   cache_put 이전에 부착해 캐시 히트 응답에도 조인키가 실린다(같은 내용=같은 해시).
    try:
        from app.services.ledger.analysis_ledger_service import attach_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        _limits = result.get("limits") if isinstance(result, dict) else None
        wb = await record_user_analysis(
            analysis_type="regulation",
            summary={
                "address": addr, "pnu": pnu,
                "parcel_count": len(_rows) or 1,
                "use_llm": body.use_llm,
                "zone_type": (result.get("zone_type") if isinstance(result, dict) else None),
                "limits": _limits if isinstance(_limits, dict) else None,
            },
            pnu=pnu, address=addr, source="regulation",
            # ★변동감지 표준키(input_signature/signature_parts) 재료 — 단일 소유자(ledger_adapters)에서 조합.
            parcel_count=len(_rows) or 1, use_llm=body.use_llm,
        )
        if isinstance(result, dict):
            result = attach_ledger_hash(result, wb)
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 규제분석 결과 무손상
        pass
    await cache_put("regulation_analyze", cache_key, result)
    return result


class RegulationReportRequest(BaseModel):
    """법규 검토서 다운로드 요청 — 프론트가 방금 받은 /analyze 결과를 그대로 실어 재분석·LLM 재호출 0.

    ``result``: /regulation/analyze 응답 dict(부지 요약·정량 한도·계층·영향도·AI 해석·근거) 그대로.
    ``address``: 표지 소재지 표기용(없으면 result.address 폴백).
    """

    result: dict
    address: str | None = None


@router.post("/report", summary="법규 검토서 다운로드(PDF/PPTX/DOCX)")
async def regulation_report(body: RegulationReportRequest, format: str = "pdf"):
    """법규 검토서 다운로드(PDF/PPTX/DOCX) — 통합 보고서 생성엔진 경유.

    ★재분석 0: 프론트가 화면에 이미 받은 /analyze 결과(body.result)를 그대로 '조립'만 한다
      (LLM 재호출·네트워크 0 → 과금·지연 없음). 산식은 어댑터에서 만들지 않는다(값 배치만).
    파일 다운로드 계약: 성공=200 + 바이너리(attachment), 실패=4xx(200+error JSON 금지).
    기존 /land-price/desk-appraisal/pdf 패턴 미러.
    """
    # ★무인증 렌더 엔드포인트 자기 DoS 방어(R1 P3) — 정상 /analyze 결과는 수십 KB 급이므로
    #   2MB 상한이면 실사용 무영향. 초과는 413(조립 거부·서버 자원 보호).
    import json as _json

    from fastapi import HTTPException

    if len(_json.dumps(body.result, ensure_ascii=False)) > 2_000_000:
        raise HTTPException(status_code=413, detail="result payload too large (2MB 상한)")
    from fastapi import HTTPException
    from fastapi.responses import Response

    from app.services.report.render import (
        build_report_model_from_regulation,
        render_report,
    )

    result = body.result if isinstance(body.result, dict) else {}
    if not result:
        raise HTTPException(status_code=400, detail="법규 분석 결과가 필요합니다.")
    fmt = (format or "pdf").lower()
    if fmt not in {"pdf", "pptx", "docx"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 포맷입니다(pdf/pptx/docx).")

    address = (body.address or result.get("address") or "").strip()
    model = build_report_model_from_regulation(result, address=address)
    data, media_type, ext = render_report(model, fmt)
    return Response(
        content=data, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=propai_regulation_report.{ext}"},
    )


@router.post("/check", response_model=RegulationCheckResponse)
@limiter.limit(ai_limiter)
async def check_regulation(
    request: Request,
    body: RegulationCheckRequest,
    current_user: CurrentUser = Depends(RequirePermission("regulation", "write")),
    db: AsyncSession = Depends(get_db),
) -> RegulationCheckResponse:
    """법규 적합성을 검토한다."""
    svc = RegulationService(db)
    return await svc.check_regulation(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        regulation_type=body.regulation_type,
        project_info=body.project_info,
    )


# ── 고시 원문 검색(전수 다운로드 없이 타깃 검색) ──
@router.get("/gosi/search", summary="고시 원문 내용 검색(법제처 행정규칙 본문·무다운로드)")
async def gosi_search(
    q: str,
    max_results: int = 3,
    current_user: CurrentUser = Depends(RequirePermission("regulation", "read")),
) -> dict:
    """국가 고시(행정규칙) 본문을 법제처 DRF로 검색·발췌(파일 다운로드 없이). 지역 결정고시는 토지이음."""
    from app.services.legal.gosi_search_service import GosiSearchService
    return await GosiSearchService().search_content(q, max_results=max(1, min(max_results, 5)))


# ── LLM 관련법령 탐색 + 정본 교차검증 ──
class LegalDiscoverRequest(BaseModel):
    """부지/개발 맥락(용도지역·지목·개발방식·시설유형·특이사항·시군구 등)."""

    context: dict


@router.post(
    "/legal-discovery",
    summary="LLM 관련법령·고시 탐색 + 정본(LegalHub) 교차검증",
    dependencies=[Depends(enforce_llm_quota)],
)
@limiter.limit(ai_limiter)
async def legal_discovery(
    request: Request,
    body: LegalDiscoverRequest,
    current_user: CurrentUser = Depends(RequirePermission("regulation", "read")),
) -> dict:
    """LLM이 맥락에 맞는 핵심·관련 법령/조례/고시를 식별 → 정본 교차검증(verified_ssot/llm_unverified).

    무날조: 정본 미등재는 검증권고로 정직 표기, 해석 불가 인용은 제외. 지역 고시 토지이음 deep-link 동반.
    """
    from app.services.legal.legal_discovery_service import LegalDiscoveryService
    return await LegalDiscoveryService().discover(body.context or {})
