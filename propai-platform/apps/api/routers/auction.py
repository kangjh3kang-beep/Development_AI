"""Auction intelligence router for G95.

추가: 경·공매 1단계 — 온비드(공매) 전국연동 3탭(내토지 연동분 / 전국 조건검색 /
전국 최저입찰가 순위) + 저장조건 CRUD + 낙찰가능가 추정 + 관리/cron 동기화.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from packages.schemas.models import AuctionAnalysisRequest, AuctionListingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.auction_service import AuctionService

router = APIRouter()


def _step1_service(db: AsyncSession = Depends(get_db)):
    from app.services.auction.auction_service import AuctionStep1Service

    return AuctionStep1Service(db)


def _onbid_service_key() -> Optional[str]:
    """온비드 서비스 키 해석: ONBID_SERVICE_KEY → settings 폴백(없으면 None=unavailable)."""
    import os

    key = os.getenv("ONBID_SERVICE_KEY")
    if key:
        return key
    try:
        from app.core.config import settings

        return getattr(settings, "ONBID_SERVICE_KEY", "") or None
    except Exception:  # noqa: BLE001
        return None


def _serialize_listing(listing) -> AuctionListingResponse:
    analysis = listing.analysis_json or {}
    return AuctionListingResponse(
        listing_id=listing.id,
        project_id=listing.project_id,
        auction_type=listing.auction_type,
        case_number=listing.case_number,
        court_name=listing.court_name,
        address=listing.address,
        property_type=listing.property_type,
        appraised_value_krw=listing.appraised_value_krw,
        minimum_bid_krw=listing.minimum_bid_krw,
        bid_count=listing.bid_count,
        auction_date=listing.auction_date,
        status=listing.status,
        discount_ratio=float(analysis.get("discount_ratio", 0.0)),
        market_gap_ratio=float(analysis.get("market_gap_ratio", 0.0)),
        investment_score=float(analysis.get("investment_score", 0.0)),
        recommended_max_bid_krw=float(
            analysis.get("recommended_max_bid_krw", listing.minimum_bid_krw)
        ),
        expected_margin_krw=float(analysis.get("expected_margin_krw", 0.0)),
        diligence_flags=list(analysis.get("diligence_flags", [])),
        created_at=listing.created_at,
    )


@router.post("/analyze", response_model=AuctionListingResponse)
async def analyze_auction_listing(
    body: AuctionAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    db: AsyncSession = Depends(get_db),
) -> AuctionListingResponse:
    service = AuctionService(db)
    listing = await service.analyze_and_store(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        auction_type=body.auction_type,
        case_number=body.case_number,
        court_name=body.court_name,
        address=body.address,
        property_type=body.property_type,
        appraised_value_krw=body.appraised_value_krw,
        minimum_bid_krw=body.minimum_bid_krw,
        bid_count=body.bid_count,
        auction_date=body.auction_date,
        occupancy_status=body.occupancy_status,
        senior_lien_exists=body.senior_lien_exists,
        expected_repair_cost_krw=body.expected_repair_cost_krw,
        nearby_market_price_krw=body.nearby_market_price_krw,
    )
    return _serialize_listing(listing)


@router.get("/listings/{listing_id}", response_model=AuctionListingResponse)
async def get_auction_listing(
    listing_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    db: AsyncSession = Depends(get_db),
) -> AuctionListingResponse:
    service = AuctionService(db)
    listing = await service.get_listing(
        tenant_id=current_user.tenant_id,
        listing_id=listing_id,
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="Auction listing not found")
    return _serialize_listing(listing)


@router.get("/opportunities", response_model=list[AuctionListingResponse])
async def list_auction_opportunities(
    project_id: UUID | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[AuctionListingResponse]:
    service = AuctionService(db)
    listings = await service.list_opportunities(
        tenant_id=current_user.tenant_id,
        limit=limit,
        project_id=project_id,
    )
    return [_serialize_listing(listing) for listing in listings]


# ══════════════════════════════════════════════════════════════════════
# 경·공매 1단계 — 온비드(공매) 전국연동 3탭 + 저장조건 + 낙찰가능가 + 동기화
# ══════════════════════════════════════════════════════════════════════


@router.get("/search", summary="② 전국 조건검색(지역·종류·유찰·가격·낙찰가능가)")
async def auction_search(
    region: Optional[str] = Query(None, description="시/도(예: 서울)"),
    kind: Optional[str] = Query(None, description="종류(land/building/apt/officetel/factory/etc)"),
    min_fail: Optional[int] = Query(None, ge=0, description="최소 유찰회수"),
    max_price: Optional[int] = Query(None, ge=0, description="최대 최저입찰가(원)"),
    est_win_max: Optional[int] = Query(None, ge=0, description="예상 낙찰가(중앙) 상한(원)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """전국 공매 물건을 조건검색한다. 캐시 우선, 비면 온비드 동기화 후 재조회.

    각 물건에 est_win(예상 낙찰가 범위·신뢰도·가정)을 포함하며, data_source로
    실연동(onbid_live/court_scrape)/미가용(unavailable) 여부를 정직 표기한다(무목업).
    """
    return await service.search(
        region=region, kind=kind, min_fail=min_fail, max_price=max_price,
        est_win_max=est_win_max, page=page, page_size=page_size,
        service_key=_onbid_service_key(),
    )


@router.get("/ranking", summary="③ 전국 순위(조회수/관심 실데이터, 최저입찰가/할인율 캐시)")
async def auction_ranking(
    region: Optional[str] = Query(None, description="시/도(min_bid/discount_rate 캐시순위 전용)"),
    kind: Optional[str] = Query(None, description="종류(min_bid/discount_rate 캐시순위 전용)"),
    by: str = Query("views", pattern="^(views|interest|min_bid|discount_rate)$",
                    description="views=조회수실데이터 / interest=관심실데이터 / "
                                "min_bid·discount_rate=캐시순위"),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """전국 순위.

    - by=views(기본) → 온비드 조회수 순위(getInqRnkClg 실데이터: 감정가·할인율·순위·주소·상태).
    - by=interest → 온비드 관심 순위(getItrsCltrRnkClg 실데이터).
    - by=min_bid / discount_rate → 캐시(auction_items) 기반 최저입찰가/할인율 순위.
    각 물건엔 est_win(낙찰가능가 범위·신뢰도·가정)을 포함한다(무목업).
    """
    if by in ("views", "interest"):
        return await service.ranking_live(
            service_key=_onbid_service_key(), by=by, limit=limit,
        )
    return await service.ranking(region=region, kind=kind, by=by, limit=limit)


@router.get("/bid-results", summary="④ 물건 입찰결과 조건검색(유찰·낙찰가율·감정가)")
async def auction_bid_results(
    sido: Optional[str] = Query(None, description="소재지 시/도(lctnSdnm)"),
    sigungu: Optional[str] = Query(None, description="소재지 시/군/구(lctnSggnm)"),
    emd: Optional[str] = Query(None, description="소재지 읍/면/동(lctnEmdNm)"),
    prpt_div_cd: Optional[str] = Query(None, description="재산구분코드(prptDivCd)"),
    pbct_stat: Optional[str] = Query(None, pattern="^(win|fail)$",
                                     description="win=낙찰(0010) / fail=유찰(0011)"),
    fail_min: Optional[int] = Query(None, ge=0, description="최소 유찰횟수"),
    fail_max: Optional[int] = Query(None, ge=0, description="최대 유찰횟수"),
    apsl_min: Optional[int] = Query(None, ge=0, description="최소 감정가(원)"),
    apsl_max: Optional[int] = Query(None, ge=0, description="최대 감정가(원)"),
    minbid_min: Optional[int] = Query(None, ge=0, description="최소 최저입찰가(원)"),
    minbid_max: Optional[int] = Query(None, ge=0, description="최대 최저입찰가(원)"),
    land_min: Optional[float] = Query(None, ge=0, description="최소 토지면적(㎡)"),
    land_max: Optional[float] = Query(None, ge=0, description="최대 토지면적(㎡)"),
    bld_min: Optional[float] = Query(None, ge=0, description="최소 건물면적(㎡)"),
    bld_max: Optional[float] = Query(None, ge=0, description="최대 건물면적(㎡)"),
    opbd_start: Optional[str] = Query(None, description="개찰일 시작(yyyyMMdd)"),
    opbd_end: Optional[str] = Query(None, description="개찰일 종료(yyyyMMdd)"),
    cltr_nm: Optional[str] = Query(None, description="물건명 키워드"),
    org_nm: Optional[str] = Query(None, description="처분기관명"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """getCltrBidRsltList2로 물건 입찰결과를 조건검색한다(유찰횟수·낙찰가율·감정가 실데이터).

    무자료 시 전국 조회수 순위(getInqRnkClg)로 폴백하고 정직 표기한다. 각 물건엔
    est_win(낙찰가능가)을 부착한다(무목업).
    """
    pbct_stat_cd = None
    if pbct_stat == "win":
        pbct_stat_cd = "0010"
    elif pbct_stat == "fail":
        pbct_stat_cd = "0011"
    filters = {
        "sido": sido, "sigungu": sigungu, "emd": emd,
        "prpt_div_cd": prpt_div_cd, "pbct_stat_cd": pbct_stat_cd,
        "fail_min": fail_min, "fail_max": fail_max,
        "apsl_min": apsl_min, "apsl_max": apsl_max,
        "minbid_min": minbid_min, "minbid_max": minbid_max,
        "land_min": land_min, "land_max": land_max,
        "bld_min": bld_min, "bld_max": bld_max,
        "opbd_start": opbd_start, "opbd_end": opbd_end,
        "cltr_nm": cltr_nm, "org_nm": org_nm,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    return await service.search_bid_results(
        service_key=_onbid_service_key(), filters=filters,
        page=page, page_size=page_size,
    )


@router.get("/my", summary="① 내 관리토지 중 경공매 연동분(프로젝트별+통합)")
async def auction_my(
    group_by: str = Query("project", pattern="^(project|none)$"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """내 프로젝트/토지조서 PNU와 일치하는 공매 물건을 자동매칭해 반환한다."""
    return await service.my_listings(
        user_id=str(current_user.user_id),
        tenant_id=str(current_user.tenant_id),
        group_by=group_by,
    )


@router.get("/filters", summary="저장조건 목록")
async def auction_list_filters(
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    items = await service.list_filters(user_id=str(current_user.user_id))
    return {"items": items, "total": len(items)}


@router.post("/filters", summary="저장조건 생성")
async def auction_create_filter(
    name: str = Body(..., embed=True),
    conditions: dict[str, Any] = Body(default_factory=dict, embed=True),
    notify: bool = Body(False, embed=True),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    return await service.create_filter(
        user_id=str(current_user.user_id), name=name,
        conditions=conditions, notify=notify,
    )


@router.delete("/filters/{filter_id}", summary="저장조건 삭제")
async def auction_delete_filter(
    filter_id: int,
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    ok = await service.delete_filter(user_id=str(current_user.user_id), filter_id=filter_id)
    if not ok:
        raise HTTPException(status_code=404, detail="저장조건을 찾을 수 없습니다.")
    return {"status": "deleted", "id": filter_id}


@router.post("/sync", summary="경공매 동기화(관리/cron) — 온비드 공매 / 법원경매 스크래핑")
async def auction_sync(
    region: Optional[str] = Query(None, description="시/도(미지정=전국 배치)"),
    kind: Optional[str] = Query(None, description="종류"),
    rows: int = Query(50, ge=1, le=200),
    source: str = Query("onbid", pattern="^(onbid|court)$",
                        description="onbid=공매 실API / court=법원경매 스크래핑"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """공매(온비드 실API) 또는 경매(법원 스크래핑)를 수집해 멱등 upsert한다.

    ★무목업: 키 미설정/호출실패/스크래핑 불가 시 가짜데이터 없이 빈 결과 + reason
    (data_source=unavailable)을 반환한다.
    """
    return await service.sync_region(
        service_key=_onbid_service_key(), region=region, kind=kind, rows=rows,
        source=source,
    )


@router.get("/detail", summary="물건상세 입찰정보(getCltrBidInf2: 유찰누적·면적·이미지·이전입찰)")
async def auction_detail(
    cltr_mng_no: str = Query(..., description="물건관리번호(cltrMngNo)"),
    pbct_cdtn_no: str = Query(..., description="공매조건번호(pbctCdtnNo)"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """순위/목록 아이템의 cltrMngNo+pbctCdtnNo로 온비드 물건상세 입찰정보를 조회한다.

    유찰누적횟수·면적·이미지URL·이전입찰내역·낙찰가율(병합) 등을 정규화해 반환한다.
    무자료/비공개/이미지없음은 null(가짜 금지), 키 미설정/실패는 unavailable+reason.
    """
    try:
        return await service.detail_live(
            service_key=_onbid_service_key(),
            cltr_mng_no=cltr_mng_no, pbct_cdtn_no=pbct_cdtn_no,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "item": None,
            "data_source": "unavailable",
            "reason": f"물건상세 조회 실패: {str(e)[:160]}",
        }


@router.get("/items/{item_id}", summary="공매 물건 상세(+권리/감정 raw +낙찰가능가)")
async def auction_item_detail(
    item_id: int,
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    item = await service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="물건을 찾을 수 없습니다.")
    return item


# ══════════════════════════════════════════════════════════════════════
# 경공매 모니터링 — 관심대상 3입력(토지조서 보유토지 / Excel업로드 / 지도구획)
# ══════════════════════════════════════════════════════════════════════


@router.post("/watchlist/upload", summary="(b) 관심대상 Excel/CSV 업로드(컬럼 자동감지)")
async def auction_watchlist_upload(
    file: UploadFile = File(..., description="xlsx/xls/csv (PNU/주소/소재지 등 헤더 자동감지)"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """업로드 파일을 파싱해 행별 관심대상(source=excel)을 등록한다(무목업).

    PNU/지번/주소/소재지 등 다양한 헤더명을 자동감지한다. 잘못된 파일/빈 컬럼/미인식
    헤더는 400으로 정직하게 거부한다. 반환: 등록건수·파싱건수·인식컬럼·미인식행·예시.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        return await service.upload_watchlist_excel(
            user_id=str(current_user.user_id), raw=raw, filename=file.filename or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/regions", summary="(c) 지도 구획(Polygon) 관심대상 저장")
async def auction_create_region(
    name: str = Body(..., embed=True),
    geojson: dict[str, Any] = Body(..., embed=True),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """지도에서 그린 구획(GeoJSON Polygon/MultiPolygon)을 관심대상으로 저장한다."""
    try:
        return await service.create_region(
            user_id=str(current_user.user_id), name=name, geojson=geojson,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/regions", summary="(c) 내 지도 구획 목록")
async def auction_list_regions(
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    items = await service.list_regions(user_id=str(current_user.user_id))
    return {"items": items, "total": len(items)}


@router.delete("/regions/{region_id}", summary="(c) 지도 구획 삭제")
async def auction_delete_region(
    region_id: int,
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    ok = await service.delete_region(user_id=str(current_user.user_id), region_id=region_id)
    if not ok:
        raise HTTPException(status_code=404, detail="구획을 찾을 수 없습니다.")
    return {"status": "deleted", "id": region_id}


@router.get("/watchlist", summary="관심대상 통합 목록(보유토지/Excel/구획)")
async def auction_watchlist(
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """3입력 통합 관심대상 조회. 보유토지(landschedule)는 호출 시 자동 최신화한다."""
    await service.sync_landschedule_targets(
        user_id=str(current_user.user_id), tenant_id=str(current_user.tenant_id),
    )
    items = await service.list_watch_targets(user_id=str(current_user.user_id))
    return {"items": items, "total": len(items)}


@router.get("/monitor", summary="관심대상별 매칭된 경공매 물건(보유토지/업로드/구획)")
async def auction_monitor(
    group_by: str = Query("source", pattern="^(source)$"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """관심대상 ↔ 캐시 경공매 물건 매칭 결과를 source별(보유토지/Excel/구획)로 반환한다.

    PNU/주소 직접매칭은 즉시, 폴리곤(구획)은 물건 주소 지오코딩(캐시) 후 매칭한다.
    각 물건엔 est_win(낙찰가능가)을 포함하며 data_source를 정직 표기한다(무목업).

    ★관심대상 미등록·온비드 미가용·내부오류 시에도 5xx 대신 200 + 빈결과 + note 로
    graceful 반환한다(가짜데이터 금지).
    """
    try:
        return await service.monitor(
            user_id=str(current_user.user_id),
            tenant_id=str(current_user.tenant_id),
            group_by=group_by,
        )
    except Exception as e:  # noqa: BLE001
        return {
            "group_by": "source",
            "groups": {},
            "total_matched": 0,
            "targets": 0,
            "data_source": "unavailable",
            "note": "관심대상을 등록하면 매칭 결과를 지속 모니터링해 제공합니다."
            f" (일시 조회 실패: {str(e)[:120]})",
        }


@router.post("/monitor/run", summary="(관리/cron) 온비드 동기화+매칭+신규 알림")
async def auction_monitor_run(
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """온비드 실데이터를 적재하고 관심대상과 매칭한 뒤 신규 매칭을 알림 기록한다(무목업).

    ★온비드 미가용·관심대상 미등록·내부오류 시에도 5xx 대신 200 + 빈결과 + note.
    """
    try:
        return await service.monitor_run(
            user_id=str(current_user.user_id),
            tenant_id=str(current_user.tenant_id),
            service_key=_onbid_service_key(),
        )
    except Exception as e:  # noqa: BLE001
        return {
            "status": "ok",
            "synced": 0,
            "data_source": "unavailable",
            "total_matched": 0,
            "new_matches": 0,
            "groups_count": {},
            "note": "관심대상을 등록하면 매칭 결과를 지속 모니터링해 제공합니다."
            f" (일시 동기화 실패: {str(e)[:120]})",
        }
