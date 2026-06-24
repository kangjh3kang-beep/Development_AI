"""설계 생성(design-gen) 라우터 — 인제스트·검색·생성·법규 노출.

design_ingest 파이프라인(파싱→임베딩→Qdrant→검색→조합→인허가/법규검증→근거)을
HTTP로 노출한다. 모든 산출물은 근거(evidence·법령링크)를 동반한다([[feedback_evidence_and_links]]).

★보안 불변(교차테넌트 누출 방지):
- tenant_id는 **절대 클라이언트 입력에서 받지 않는다**. 요청 스키마에 tenant_id 필드를 두지 않고,
  서비스 호출 시 무조건 인증 컨텍스트(current_user.tenant_id)로 강제 주입한다.
- 검색은 SiteQuery.tenant_id를 인증값으로 강제 → Qdrant tenant 필터가 항상 걸린다(전역검색 금지).
- project_id가 주어지면 해당 테넌트 소유(Project.organization_id == user.tenant_id)인지 검증한다.
- 업로드는 라우터가 크기·빈파일·형식을 검증한다(parsers에는 크기 가드가 없음).
- 과금은 미설정 시 무료가 기본. LLM/임베딩을 쓰는 인제스트·생성에만 구독자 한도 게이트
  (enforce_llm_quota, 설정 0이면 무과금·구독자 초과 시에만 402)를 부착한다.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from app.models.project import Project
from app.services.design_ingest import object_store
from app.services.design_ingest.design_spec import drawing_types_by_discipline
from app.services.design_ingest.ingest_service import ingest_design_file
from app.services.design_ingest.law_coverage import (
    DESIGN_LAW_MAP,
    all_referenced_laws,
    laws_for,
    verify_coverage,
)
from app.services.design_ingest.orchestrator import (
    DesignRequest,
    generate_design_proposals,
)
from app.services.design_ingest.parsers import detect_format
from app.services.design_ingest.search_service import (
    SiteQuery,
    corpus_stats,
    get_drawing_object_key,
    search_drawings,
)
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/design-gen", tags=["설계 생성"])

# 업로드 도면 크기 상한(도면 PDF/DXF 여유) — parsers엔 가드 없으므로 라우터가 강제.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB
# 입력 검증 상한(비상식 값 차단 — 할루시네이션/오남용 방지).
_MAX_AREA_SQM = 5_000_000.0
_MAX_TOP_K = 50
_MAX_TOP_N = 10
# 다필지 통합 입력 상한 — 한 개발구역 통합 설계 규모(대량배치는 별도 parcel_batch 경로).
_MAX_PARCELS = 200
# 콜드스타트 배치 인제스트(표준설계 일괄적재) — 한 요청 파일 수 상한(DoS·과금 폭주 방지).
_MAX_BATCH_FILES = 50
# 배치 누적 용량 상한 — 거대 배치의 처리시간/외부 임베딩 호출 폭주 방어(파일당 25MB와 별개).
_MAX_BATCH_TOTAL_BYTES = 200 * 1024 * 1024  # 200MB


# ── 요청 스키마(★tenant_id 필드 없음 — 인증 컨텍스트에서만 강제) ──
class SearchRequest(BaseModel):
    """설계도면 검색 요청. 부지 조건으로 유사 도면을 찾는다."""

    drawing_type: str | None = None          # site_plan/floor_plan/section/elevation/parking 등
    zone_type: str | None = None             # 용도지역 힌트
    area_sqm: float | None = None            # 대상 면적(㎡) — 근사 매칭
    area_tolerance_pct: float = 30.0         # 면적 허용 오차(%)
    keywords: str = ""                       # 자유 키워드
    top_k: int = 5                           # 반환 개수(1~50)


class GenerateRequest(BaseModel):
    """부지 조건 → 인허가 부합 설계안 Top-N 생성 요청."""

    area_sqm: float                          # 대지면적(㎡) — 필수
    zone_code: str = "2R"                    # 용도지역 코드
    zone_name: str | None = None             # 용도지역명(한글)
    sigungu: str | None = None               # 시군구(조례·링크 verified용)
    dev_type: str = "M06"                    # 개발방식 코드
    building_use: str | None = None          # 건축 용도(미지정 시 엔진 기본)
    ordinance_far_pct: float | None = None   # 조례 용적률(실효, 있으면 우선)
    ordinance_bcr_pct: float | None = None   # 조례 건폐율(실효, 있으면 우선)
    ordinance_height_m: float | None = None  # 조례 절대 높이한도(m) — 매스 층수캡(선택·없으면 법정/코드)
    ordinance_setback_m: float | None = None # 조례 이격거리(m) — 배치·일조 base(선택·없으면 법정/코드)
    width_m: float | None = None             # 부지 폭(m) — 건물 배치 폴리곤 정확화(선택)
    depth_m: float | None = None             # 부지 깊이(m) — 선택
    land_category: str | None = None         # 지목/토지유형 — 특이부지 게이트(학교용지·농지·산지 등)
    special_districts: list[str] | None = None  # 특별구역(GB·문화재·군사·상수원 등) — 특이부지 게이트
    parcels: list[dict] | None = None        # 다필지(≥2) 통합 — 각 {area_sqm,zone_code,zone_name,
    #   ordinance_far_pct,ordinance_bcr_pct,land_category,special_districts}. 주어지면 면적가중 통합
    avg_unit_area_sqm: float = 84.0          # 평균 평형(㎡)
    unit_types: list[str] | None = None      # 평형 믹스(예: ["59A","84A"]) — cad UNIT_TYPES 화이트리스트 검증
    top_n: int = 3                           # 설계안 개수(1~10)
    project_id: str | None = None            # 연결 프로젝트(소유 검증됨)
    verify: bool = False                     # True면 추천안 독립검증(선택형·LLM)
    interpret: bool = False                  # True면 추천안 LLM 해석 6섹션(선택형·LLM)


# ── 내부 헬퍼 ──
async def _verify_project_ownership(
    db: AsyncSession, project_id: str | None, tenant_id: uuid.UUID
) -> None:
    """project_id가 주어지면 해당 테넌트 소유인지 검증(org.id==tenant.id 1:1).

    소유 아님/미존재 → 403. 형식 오류 → 400. 미지정(None) → 통과.
    컬럼 드리프트 회피를 위해 organization_id 단일 컬럼만 조회한다(전체 ORM 로드 금지).
    """
    if not project_id:
        return
    try:
        pid = uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=400, detail="프로젝트 ID 형식이 올바르지 않습니다.") from e

    proj_org = (
        await db.execute(select(Project.organization_id).where(Project.id == pid))
    ).scalar_one_or_none()
    if proj_org is None or proj_org != tenant_id:
        # 소유 불일치/미존재는 동일 응답(존재 은닉) — 권한 없음.
        raise HTTPException(status_code=403, detail="이 프로젝트에 대한 권한이 없습니다.")


async def _read_upload(file: UploadFile) -> bytes:
    """업로드 바이트 취득 + 빈파일/크기/형식 검증(parsers엔 가드 없음 → 라우터 책임)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다(최대 25MB).")
    if detect_format(file.filename or "") == "unknown":
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 형식입니다(xlsx/dxf/ifc/pdf/png/jpg/webp).",
        )
    return data


# ── 엔드포인트 ──
@router.post("/ingest", dependencies=[Depends(enforce_llm_quota)])
async def ingest(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """설계파일(엑셀/DXF/IFC/PDF/이미지) 1건 인제스트. tenant_id는 인증 컨텍스트 강제."""
    await _verify_project_ownership(db, project_id, current.tenant_id)
    data = await _read_upload(file)
    return await ingest_design_file(
        filename=file.filename or "",
        content=data,
        project_id=project_id,
        tenant_id=str(current.tenant_id),  # ★클라이언트 입력 무시 — 인증값만
    )


@router.post("/ingest-batch", dependencies=[Depends(enforce_llm_quota)])
async def ingest_batch(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """표준설계 도면 다중 일괄 인제스트 — 콜드스타트 코퍼스 부트스트랩.

    파일별 독립 처리: 일부 파일 실패가 전체 배치를 막지 않는다(정직 — 파일별 결과 보고).
    tenant_id는 인증 컨텍스트 강제(클라이언트 입력 무시), project_id는 소유 검증.
    중복(동일 content_hash)은 point_id 멱등 업서트로 안전 — 별도 중복카운트는 신뢰 신호가
    없어 표기하지 않고, 색인 여부(indexed/not_indexed)만 정직 집계한다.
    """
    if not files:
        raise HTTPException(status_code=400, detail="업로드 파일이 없습니다.")
    if len(files) > _MAX_BATCH_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"한 번에 최대 {_MAX_BATCH_FILES}개까지 업로드할 수 있습니다.",
        )
    await _verify_project_ownership(db, project_id, current.tenant_id)

    results: list[dict[str, Any]] = []
    counts = {"total": len(files), "indexed": 0, "not_indexed": 0, "failed": 0}
    total_bytes = 0
    for idx, f in enumerate(files):
        name = f.filename or ""
        try:
            data = await _read_upload(f)  # 파일별 빈/크기/형식 검증(실패는 이 파일만 fail)
            total_bytes += len(data)
            if total_bytes > _MAX_BATCH_TOTAL_BYTES:
                # 누적 용량 초과 — 이 파일부터 나머지는 처리하지 않고 정직 보고(부분 처리·중단).
                cap_mb = _MAX_BATCH_TOTAL_BYTES // (1024 * 1024)
                for rf in files[idx:]:
                    counts["failed"] += 1
                    results.append({
                        "filename": rf.filename or "",
                        "ok": False,
                        "error": f"배치 누적 용량 상한({cap_mb}MB) 초과 — 미처리(나눠서 업로드)",
                    })
                break
            res = await ingest_design_file(
                filename=name,
                content=data,
                project_id=project_id,
                tenant_id=str(current.tenant_id),  # ★인증값 강제
            )
            if res.get("indexed"):
                counts["indexed"] += 1
            else:
                counts["not_indexed"] += 1
            results.append({
                "filename": name,
                "ok": True,
                "drawing_type": res.get("drawing_type"),
                "content_hash": res.get("content_hash"),
                "indexed": res.get("indexed"),
                "index_skip_reason": res.get("index_skip_reason"),
                "stored": res.get("stored"),
                "store_skip_reason": res.get("store_skip_reason"),
            })
        except HTTPException as he:  # _read_upload 검증 실패(빈/크기/형식) — 이 파일만 fail
            counts["failed"] += 1
            results.append({"filename": name, "ok": False, "error": str(he.detail)})
        except Exception as e:  # noqa: BLE001 — 한 파일 예외가 배치 전체를 깨면 안 됨
            counts["failed"] += 1
            logger.info("배치 인제스트 파일 실패(%s): %s", name, str(e)[:140])
            results.append({"filename": name, "ok": False, "error": str(e)[:160]})

    return {"ok": True, **counts, "results": results}


@router.post("/search")
async def search(
    req: SearchRequest,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """부지 조건으로 유사 설계도면 검색. tenant 필터는 인증 컨텍스트로 강제(전역검색 금지)."""
    top_k = max(1, min(req.top_k, _MAX_TOP_K))
    if req.area_sqm is not None and (
        not math.isfinite(req.area_sqm) or req.area_sqm <= 0 or req.area_sqm > _MAX_AREA_SQM
    ):
        raise HTTPException(status_code=422, detail="면적 값이 올바르지 않습니다.")
    query = SiteQuery(
        drawing_type=req.drawing_type,
        zone_type=req.zone_type,
        area_sqm=req.area_sqm,
        area_tolerance_pct=max(0.0, min(req.area_tolerance_pct, 100.0)),  # [0,100] 클램프
        keywords=req.keywords,
        tenant_id=str(current.tenant_id),  # ★항상 인증값 — 클라이언트 tenant 주입 불가
    )
    result = await search_drawings(query, top_k=top_k)
    # 썸네일 보관 결과에 인라인 미리보기용 presigned URL 첨부(서버측·테넌트 스코프·단기).
    if object_store.is_configured():
        tid = str(current.tenant_id)
        for r in result.get("results", []):
            if r.get("has_thumbnail") and r.get("content_hash"):
                try:
                    # content_hash 비정상(비-hex) 시 thumb_key가 ValueError → None 강등(검색 비차단).
                    r["thumb_url"] = object_store.presigned_get_url(
                        object_store.thumb_key(tid, r["content_hash"]), tid, expires=600
                    )
                except Exception:  # noqa: BLE001 — 미리보기 URL 실패는 검색 결과를 깨지 않음
                    r["thumb_url"] = None
    return result


async def _validated_design_request(
    req: GenerateRequest, db: AsyncSession, current: CurrentUser
) -> DesignRequest:
    """GenerateRequest 검증 + 소유검증 + DesignRequest 구성(generate·generate/pdf 공용).

    tenant_id는 인증 컨텍스트 강제(클라이언트 입력 무시). 값 오류는 422.
    """
    if not math.isfinite(req.area_sqm) or req.area_sqm <= 0 or req.area_sqm > _MAX_AREA_SQM:
        raise HTTPException(status_code=422, detail="대지면적 값이 올바르지 않습니다.")
    if req.ordinance_bcr_pct is not None and not (0 < req.ordinance_bcr_pct <= 100):
        raise HTTPException(status_code=422, detail="건폐율(%) 값이 올바르지 않습니다(0~100).")
    if req.ordinance_far_pct is not None and (
        not math.isfinite(req.ordinance_far_pct) or req.ordinance_far_pct <= 0
    ):
        raise HTTPException(status_code=422, detail="용적률(%) 값이 올바르지 않습니다.")
    if not math.isfinite(req.avg_unit_area_sqm) or req.avg_unit_area_sqm <= 0:
        raise HTTPException(status_code=422, detail="평균 평형(㎡) 값이 올바르지 않습니다.")
    for _label, _v in (
        ("부지 폭", req.width_m), ("부지 깊이", req.depth_m),
        ("조례 높이한도", req.ordinance_height_m), ("조례 이격거리", req.ordinance_setback_m),
    ):
        if _v is not None and (not math.isfinite(_v) or _v <= 0 or _v > 100_000):
            raise HTTPException(status_code=422, detail=f"{_label}(m) 값이 올바르지 않습니다.")
    # 평형 믹스는 cad UNIT_TYPES(39A~114A) 화이트리스트만 허용 — 미허용 값은 정직 거부(임의 평형 차단).
    unit_types: list[str] | None = None
    if req.unit_types is not None:
        if not isinstance(req.unit_types, list):
            raise HTTPException(status_code=422, detail="평형 믹스(unit_types) 형식이 올바르지 않습니다.")
        from app.services.cad.auto_design_engine import UNIT_TYPES

        invalid = [t for t in req.unit_types if t not in UNIT_TYPES]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"허용되지 않은 평형: {', '.join(map(str, invalid))} "
                f"(허용: {', '.join(sorted(UNIT_TYPES))}).",
            )
        # 입력순 중복제거(컴포지션의 unique 처리와 일관).
        unit_types = list(dict.fromkeys(req.unit_types)) or None
    if req.parcels is not None:  # 다필지 통합 입력 검증(각 필지 면적 양수·개수 상한)
        if not isinstance(req.parcels, list) or len(req.parcels) > _MAX_PARCELS:
            raise HTTPException(status_code=422, detail=f"필지 목록이 올바르지 않습니다(최대 {_MAX_PARCELS}개).")
        for _p in req.parcels:
            _a = _p.get("area_sqm") if isinstance(_p, dict) else None
            if not isinstance(_a, (int, float)) or not math.isfinite(_a) or _a <= 0:
                raise HTTPException(status_code=422, detail="각 필지의 대지면적(area_sqm)이 올바르지 않습니다.")
    await _verify_project_ownership(db, req.project_id, current.tenant_id)

    kwargs: dict[str, Any] = {
        "area_sqm": req.area_sqm,
        "zone_code": req.zone_code,
        "zone_name": req.zone_name,
        "sigungu": req.sigungu,
        "dev_type": req.dev_type,
        "ordinance_far_pct": req.ordinance_far_pct,
        "ordinance_bcr_pct": req.ordinance_bcr_pct,
        "ordinance_height_m": req.ordinance_height_m,   # 조례 높이한도(m) — 매스 층수캡
        "ordinance_setback_m": req.ordinance_setback_m,  # 조례 이격거리(m) — 배치·일조 base
        "width_m": req.width_m,
        "depth_m": req.depth_m,
        "land_category": req.land_category,
        "special_districts": req.special_districts,
        "parcels": req.parcels,
        "avg_unit_area_sqm": req.avg_unit_area_sqm,
        "unit_types": unit_types,                        # 검증된 평형 믹스(화이트리스트·중복제거)
        "top_n": max(1, min(req.top_n, _MAX_TOP_N)),
        "tenant_id": str(current.tenant_id),  # ★인증값 강제
        "project_id": req.project_id,
        "verify": req.verify,
        "interpret": req.interpret,
    }
    if req.building_use:
        kwargs["building_use"] = req.building_use
    return DesignRequest(**kwargs)


@router.post("/generate", dependencies=[Depends(enforce_llm_quota)])
async def generate(
    req: GenerateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """부지 조건 → 인허가 부합 설계안 Top-N(근거·법령링크 동반). tenant_id 인증 강제."""
    return await generate_design_proposals(await _validated_design_request(req, db, current))


@router.post("/generate/pdf", dependencies=[Depends(enforce_llm_quota)])
async def generate_pdf(
    req: GenerateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """부지 조건 → 설계제안 타당성 보고서 PDF(다운로드). generate와 동일 산출을 PDF로."""
    result = await generate_design_proposals(await _validated_design_request(req, db, current))
    from app.services.design_ingest.design_proposal_pdf import build_design_proposal_pdf
    try:
        pdf = build_design_proposal_pdf(result)
    except Exception as e:  # noqa: BLE001 — PDF 생성 실패가 500 폭주로 새지 않게 정직 503
        logger.warning("설계제안 PDF 생성 실패: %s", str(e)[:160])
        raise HTTPException(status_code=503, detail="PDF 생성에 실패했습니다(라이브러리/폰트 확인).") from e
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="design_proposal.pdf"'},
    )


@router.get("/laws/coverage")
async def laws_coverage(
    sigungu: str | None = Query(None),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """설계 단계별 참조 법규의 연결성(coverage)과 전체 참조 법규 목록(근거).

    부동산개발·건축 관련 법규가 레지스트리에 전수 연결돼 있는지 검증 결과를 노출한다.
    """
    return {
        "coverage": verify_coverage(),
        "laws": all_referenced_laws(sigungu=sigungu),
    }


@router.get("/laws/{domain}")
async def laws_for_domain(
    domain: str,
    sigungu: str | None = Query(None),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """특정 설계 도메인(zoning/permit/design/parking/environment 등)의 참조 법규."""
    if domain not in DESIGN_LAW_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"알 수 없는 도메인입니다. 가능: {', '.join(sorted(DESIGN_LAW_MAP))}",
        )
    return {"domain": domain, "laws": laws_for(domain, sigungu=sigungu)}


@router.get("/drawing-types")
async def drawing_types(
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """도면 분류 택소노미(분야별) — 프론트 검색 필터·라벨의 단일 출처(실무 전수조사 반영)."""
    return {"by_discipline": drawing_types_by_discipline()}


@router.get("/corpus-stats")
async def corpus_stats_endpoint(
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """테넌트의 누적 설계도면 코퍼스 현황(분야별 건수) — 축적 가시화·코퍼스 갭. tenant 인증 강제."""
    return await corpus_stats(str(current.tenant_id))


@router.get("/drawings/{content_hash}/url")
async def drawing_original_url(
    content_hash: str,
    variant: str = Query("original"),  # original | thumb(저해상 프록시)
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """업로드한 도면의 단기 조회 URL(presigned). ★서버 권위적·테넌트 스코프(IDOR-proof).

    content_hash만 받고 키는 인증 테넌트로 서버가 조회·재구성한다(클라이언트 키 미신뢰).
    variant=thumb는 썸네일(프록시·deterministic 키), original은 원본(Qdrant object_key 조회).
    미보관/미설정/타테넌트 → 404(존재 은닉). 비공개 — 단기 서명 URL로만 노출.
    """
    if not object_store.is_configured():
        raise HTTPException(status_code=404, detail="원본 저장소가 구성되지 않았습니다.")
    tid = str(current.tenant_id)
    if variant == "thumb":
        try:
            key: str | None = object_store.thumb_key(tid, content_hash)
        except ValueError as e:  # content_hash 형식 오류
            raise HTTPException(status_code=404, detail="원본을 찾을 수 없습니다.") from e
    else:
        key = await get_drawing_object_key(content_hash, tid)
    if not key:
        raise HTTPException(status_code=404, detail="원본을 찾을 수 없습니다.")
    url = object_store.presigned_get_url(key, tid, expires=600)
    if not url:
        raise HTTPException(status_code=404, detail="원본 조회 URL을 생성할 수 없습니다.")
    return {"url": url, "expires_in": 600}


# ── AI Hub 데이터 자동 다운로드(aihubshell) → 설계생성 시드 인제스트(총괄관리자 전용) ──
class AihubSeedRequest(BaseModel):
    dataset_key: str                 # AI Hub datasetkey(목록조회로 확인)
    file_key: str | None = None      # ★특정 filekey(권장·콤마 다중). 미지정=전체(TB 위험)
    max_files: int = 100             # 압축해제 도면 인제스트 상한


@router.get("/seed/aihub/list")
async def seed_aihub_list(
    dataset_key: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """AI Hub 데이터셋/파일트리 목록(aihubshell -mode l). datasetkey 주면 filekey 확인. 총괄관리자."""
    from app.services.billing.billing_service import is_super_admin
    if not await is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="총괄관리자 전용입니다.")
    from app.services.design_ingest.aihub_seed_service import AihubSeedService
    return await AihubSeedService().list_datasets(dataset_key)


@router.post("/seed/aihub")
async def seed_aihub(
    req: AihubSeedRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """AI Hub 특정 filekey 다운로드(aihubshell) → 압축해제 도면 → design_drawings 시드(콜드스타트).

    전제(일회성·관리자): AIHUB_API_KEY 시크릿 + 데이터셋 '활용신청 승인'. 무목업: 미설정·실패는 정직 상태.
    디스크 안전: file_key 지정 권장(미지정=전체 TB). 총괄관리자 전용.
    """
    from app.services.billing.billing_service import is_super_admin
    if not await is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="AI Hub 시드 인제스트는 총괄관리자 전용입니다.")
    from app.services.design_ingest.aihub_seed_service import AihubSeedService
    return await AihubSeedService().ingest_dataset(
        req.dataset_key, req.file_key,
        max_files=max(1, min(req.max_files, 2000)),
        tenant_id=str(current.tenant_id),
    )
