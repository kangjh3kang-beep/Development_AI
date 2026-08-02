"""종합 부지분석 API 라우터.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 반환.
LLM 프로바이더를 선택하여 AI 해석에 사용할 모델을 지정할 수 있다.
"""

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.billing_deps import enforce_llm_quota
from app.services.auth.auth_service import get_current_user
from app.services.common.job_store import JobStore
from app.services.land_intelligence.parcel_normalize import ParcelsIn

# P2-2 보안: 종합분석 LLM 호출 라우트 인증 강제(무인증·무쿼터 LLM 호출 → 미과금 비용남용 차단).
# ★전수감사 보강: 사용자별 LLM 쿼터(enforce_llm_quota)를 라우터 레벨로 부착해 한도초과(402)
#   차단을 /comprehensive·/similar-market·/site-layout 전 경로에 일관 적용(경로별 과금정책 불일치 해소).
router = APIRouter(dependencies=[Depends(get_current_user), Depends(enforce_llm_quota)])

logger = structlog.get_logger(__name__)
# ★실행 중 태스크 강참조 — asyncio는 태스크를 약참조로만 들고 있어, 참조를 잃으면 실행 도중
#   GC가 수거해 잡이 영원히 pending으로 남는다(조용한 유실).
_INTERP_TASKS: set[asyncio.Task[None]] = set()


class ComprehensiveAnalysisRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    llm_provider: str | None = Field(
        None, description="LLM 프로바이더 (anthropic/openai/google). 미지정 시 기본값 사용."
    )
    llm_model: str | None = Field(
        None, description="LLM 모델 ID (예: claude-sonnet-4-20250514, gpt-4o-mini). 미지정 시 프로바이더 기본 모델 사용."
    )
    project_id: str | None = Field(
        None, description="프로젝트 ID(원장 성장루프 체인 스코프). 미지정 시 주소/PNU 기반 체인."
    )
    # ★다필지 통합분석: 33필지 등 다필지 업로드 시 필지목록(면적·용도지역 포함)을 전달하면
    #   종합분석이 '통합면적' 기준으로 산출된다(미전달 시 대표주소 단일필지 = N=1). 단일/다필지 일원화.
    # ★parcels 계약 공용 정규화(ParcelsIn): str[](주소배열)/dict[](필지객체) 양 shape 를 검증
    #   단계에서 canonical dict[] 로 수렴(무음 no-op → 단일필지 폴백 은폐 제거). 미지정 시 None.
    parcels: ParcelsIn | None = Field(
        None,
        description="필지목록 [{pnu,address,area_sqm,zone_type}]. 다필지 통합분석용(미지정 시 단일).",
    )
    # ★W2-a(단계분할): AI 해석 2종(부지 해석·시장 내러티브)은 종합분석 소요의 대부분이고,
    #   Cloudflare 엣지 컷오프(~125초)를 넘기는 주범이다. False로 요청하면 결정론 분석만
    #   즉시 받아 화면을 채우고, 해석은 후속 호출로 이어붙일 수 있다(점진 렌더).
    #   ★기본 True — 기존 호출부는 완전 무회귀.
    include_interpretation: bool = Field(
        True,
        description="AI 해석(부지 해석·시장 내러티브) 생성 여부. False면 결정론 분석만 빠르게 반환하고 "
                    "해당 필드는 status='deferred'로 표기된다(생성 실패와 구분됨).",
    )


@router.post("/comprehensive")
async def run_comprehensive_analysis(req: ComprehensiveAnalysisRequest, current_user=Depends(get_current_user)):
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    service = ComprehensiveAnalysisService()
    # Phase 1: 성장루프 체인 스코프(tenant_id+project_id)를 분석에 배선
    return await service.analyze(
        address=req.address,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
        project_id=req.project_id,
        parcels=req.parcels,
        include_interpretation=req.include_interpretation,
    )


class InterpretationRequest(BaseModel):
    """1단계(결정론) 결과를 받아 AI 해석만 생성한다 — 단계분할 2단.

    ★왜 별도 엔드포인트인가: 2단계를 `/comprehensive`에 include_interpretation=True로 다시
    호출하면 데이터 수집·산정을 **처음부터 통째로 재실행**한다(오리진 190초가 그대로 반복되고
    백엔드 부하가 2배). 이 엔드포인트는 이미 산출된 result를 입력으로 받아 LLM 해석만 돌린다.
    """

    result: dict[str, Any] = Field(
        ..., description="1단계 종합분석 응답(그대로 전달). 해석 생성의 입력이 된다."
    )
    llm_provider: str | None = Field(None, description="LLM 프로바이더(미지정 시 기본값).")
    llm_model: str | None = Field(None, description="LLM 모델 ID(미지정 시 프로바이더 기본).")


# ── AI 해석 비동기 잡 ────────────────────────────────────────────────────────
# ★실측 근거(2026-08-01 프로덕션): 1단계(결정론)는 신규 주소 3.4초·초회 27초로 CF 엣지(~125초)에
#   한참 못 미치는데, **해석 2종만으로 125초를 넘어 524**가 재현됐다(2/2). 동기 응답으로는
#   해석을 사용자에게 전달할 방법이 없다 → 제출·폴링 잡으로 전환한다.
# ★신규 인프라 0: design_audit·registry가 쓰는 공용 JobStore(Redis 우선·인메모리 폴백,
#   블루그린 컷오버 안전)를 그대로 재사용한다.
_INTERP_JOBS: dict[str, dict[str, Any]] = {}
_INTERP_JOB_TTL = 1800  # 30분 — 해석 1회 소요(>125초) 대비 충분하고 결과 재열람 여유
_INTERP_STORE = JobStore(
    "job:interpretation:", memory_backing=_INTERP_JOBS, default_ttl_s=_INTERP_JOB_TTL
)


async def _interp_job_set(job_id: str, **fields: Any) -> None:
    """잡 항목 병합 갱신(소유자 등 기존 필드 보존) — put이 교체 계약이라 get→merge→put."""
    cur = dict(await _INTERP_STORE.get(job_id) or {})
    cur.update(fields)
    await _INTERP_STORE.put(job_id, cur, _INTERP_JOB_TTL)


async def _run_interpretation_job(
    job_id: str, result: dict[str, Any], llm_provider: str | None, llm_model: str | None,
) -> None:
    """백그라운드 실행 — 완료/실패를 잡에 기록한다. **절대 raise하지 않는다**(태스크 유실 방지)."""
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    custom_llm = None
    if llm_provider:
        try:
            from app.services.ai.llm_provider import get_llm
            custom_llm = get_llm(provider=llm_provider, model=llm_model)
        except Exception:  # noqa: BLE001 — 커스텀 LLM 실패는 기본 프로바이더로 폴백(analyze와 동일)
            custom_llm = None

    try:
        service = ComprehensiveAnalysisService()
        # ★analyze()와 **같은 generate_interpretations()** 를 탄다(경로별 품질 분기 구조적 차단).
        parts = await service.generate_interpretations(result, custom_llm=custom_llm)
        await _interp_job_set(job_id, status="done", result=parts)
    except Exception as e:  # noqa: BLE001 — 잡 실패는 상태로 남긴다(조용한 영구 pending 금지)
        logger.warning("AI 해석 잡 실패", job_id=job_id, error=str(e)[:160])
        await _interp_job_set(
            job_id, status="error", error=f"{type(e).__name__}: {str(e)[:160]}",
        )


@router.post("/interpretation")
async def submit_interpretation(req: InterpretationRequest, current_user=Depends(get_current_user)):
    """AI 해석 생성을 **제출**하고 즉시 job_id를 반환한다(폴링형).

    ★동기 반환하지 않는 이유: 해석 2종은 실측 125초 초과로 CF 엣지에서 잘린다. 제출은 즉시
    끝나므로 엣지 타임아웃과 무관해지고, 프론트는 폴링으로 결과를 받는다.
    """
    job_id = f"interp_{uuid.uuid4().hex[:16]}"
    await _interp_job_set(
        job_id,
        status="pending",
        user_id=str(getattr(current_user, "id", "") or "") or None,
    )
    # ★fire-and-forget 태스크 참조를 보관한다 — 참조가 없으면 GC가 실행 중 태스크를 수거할 수 있다.
    task = asyncio.create_task(
        _run_interpretation_job(job_id, req.result, req.llm_provider, req.llm_model)
    )
    _INTERP_TASKS.add(task)
    task.add_done_callback(_INTERP_TASKS.discard)
    return {"job_id": job_id, "status": "pending"}


@router.get("/interpretation/{job_id}")
async def get_interpretation(job_id: str, current_user=Depends(get_current_user)):
    """해석 잡 상태 조회 — pending / done(result) / error(error).

    ★소유자 검증: 잡은 제출한 사용자만 조회할 수 있다(job_id 추측으로 남의 해석을 읽는 IDOR 차단).
    """
    job = await _INTERP_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="해석 작업을 찾을 수 없습니다(만료되었거나 존재하지 않음).")
    owner = job.get("user_id")
    me = str(getattr(current_user, "id", "") or "") or None
    if owner and owner != me:
        raise HTTPException(status_code=404, detail="해석 작업을 찾을 수 없습니다.")
    out: dict[str, Any] = {"job_id": job_id, "status": job.get("status")}
    if job.get("status") == "done":
        out["result"] = job.get("result")
    elif job.get("status") == "error":
        out["error"] = job.get("error")
    return out


class SimilarMarketRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    land_area_sqm: float | None = Field(None, description="대지면적(㎡). 미지정 시 자동감지.")
    region: str = Field("서울", description="지역(공사비 권역).")
    equity_won: int = Field(10_000_000_000, description="자기자본(원). ROE 산정용.")
    use_llm: bool = Field(False, description="AI 해석 포함 여부.")
    with_senior: bool = Field(True, description="시니어 금융전문가 자문(DSCR 등) 포함 여부.")
    top_n: int = Field(3, ge=1, le=5, description="유사건축물 시장조사 가산 상위 추천 수.")


@router.post("/similar-market")
async def run_similar_market_feasibility(
    req: SimilarMarketRequest, current_user=Depends(get_current_user)
):
    """Stage 3 — 유사건축물 시장조사·사업성.

    검증된 사업성 엔진(auto_recommend_top3: 인허가 게이트·특이부지·senior 금융)의 사업유형별
    추천에, 설계 참조 라이브러리(시드 코퍼스)에서 검색한 유사 설계 도면을 가산해 반환한다.
    호출자 귀속(향후 사용량 쿼터)을 위해 current_user를 받는다(현재 설계 참조는 시드 tenant 스코프).
    """
    from app.services.land_intelligence.similar_market_service import (
        similar_market_feasibility,
    )

    return await similar_market_feasibility(
        address=req.address,
        land_area_sqm=req.land_area_sqm,
        region=req.region,
        equity_won=req.equity_won,
        use_llm=req.use_llm,
        with_senior=req.with_senior,
        top_n=req.top_n,
    )


class SiteLayoutRequest(BaseModel):
    parcel_geojson: dict | None = Field(
        None, description="대지 경계 GeoJSON geometry(WGS84). 미지정 시 pnu로 조회."
    )
    pnu: str | None = Field(None, description="필지 PNU(parcel_geojson 미지정 시 VWorld 조회).")
    zone_type: str = Field("", description="용도지역.")
    building_type: str = Field("", description="건축유형(빌라류면 판상 전용).")
    far_pct: float | None = Field(None, description="가용 용적률(%). 미지정 시 통념 폴백.")
    bcr_pct: float | None = Field(None, description="건폐율 상한(%). 동수 캡에 사용.")
    land_area_sqm: float | None = Field(None, description="대지면적(㎡). 미지정 시 폴리곤 면적.")
    priority: str = Field("balanced", description="배치 우선순위: balanced|daylight|density.")
    use_llm: bool = Field(False, description="LLM 부지맞춤 조언 포함 여부(기하는 결정론 불변).")


@router.post("/site-layout")
async def run_site_layout(req: SiteLayoutRequest, current_user=Depends(get_current_user)):
    """Stage 4 — 토지모양·향·접도 기반 배치도(buildable footprint + 동배치) on 구역도.

    대지 폴리곤을 세트백 오프셋해 buildable footprint를 만들고, 동을 그리드 샘플링으로 배치해
    일조준수·yield·조망 멀티오브젝티브로 최적안을 산출한다. 폴리곤 미확보 시 정직 고지.
    """
    from app.services.cad.site_layout_service import (
        attach_layout_llm_advice,
        build_site_layout,
    )

    geojson = req.parcel_geojson
    # parcel_geojson 미지정 + pnu 있으면 VWorld로 경계 조회(graceful).
    if not geojson and req.pnu:
        try:
            from app.services.external_api.vworld_service import VWorldService

            parcel = await VWorldService().get_parcel_by_pnu(req.pnu)
            geojson = (parcel or {}).get("geometry")
        except Exception:  # noqa: BLE001 — 조회 실패는 honest 빈 배치로 진행
            geojson = None

    layout = build_site_layout(
        parcel_geojson=geojson,
        zone_type=req.zone_type,
        building_type=req.building_type,
        far_pct=req.far_pct,
        bcr_pct=req.bcr_pct,
        land_area_sqm=req.land_area_sqm,
        priority=req.priority,
    )
    return await attach_layout_llm_advice(layout, use_llm=req.use_llm)


@router.get("/llm-providers")
async def list_llm_providers():
    """사용 가능한 LLM 프로바이더 목록 반환.

    API 키가 환경변수에 설정된 프로바이더만 반환한다.
    """
    from app.services.ai.llm_provider import get_available_providers

    return {"providers": get_available_providers()}
