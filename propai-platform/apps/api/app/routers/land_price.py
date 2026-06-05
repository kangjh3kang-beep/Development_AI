"""토지 적정 매입가 추정 라우터 — 토지조서 매입예정가 자동 산정."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.land_intelligence.land_price_estimator import estimate_land_price
from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

router = APIRouter(prefix="/api/v1/land-price", tags=["토지 적정가"])


class LandPriceRequest(BaseModel):
    pnu: str | None = None
    address: str = ""
    area_sqm: float | None = None
    official_price_per_sqm: float | None = None


@router.post("/estimate")
async def land_price_estimate(req: LandPriceRequest):
    """공시지가×지역 시세보정으로 적정 매입가 추정(참고값, 수정가능)."""
    return await estimate_land_price(
        pnu=req.pnu, address=req.address,
        area_sqm=req.area_sqm, official_price_per_sqm=req.official_price_per_sqm,
    )


class DeskAppraisalRequest(BaseModel):
    pnu: str | None = None
    address: str = ""
    area_sqm: float | None = None
    official_price_per_sqm: float | None = None
    comparable_avg_per_sqm: float | None = None   # 주변 토지 실거래 평균단가(선택)
    building_gfa_sqm: float | None = None          # 건물 연면적(주면 토지+건물 복합)
    building_structure: str | None = None
    building_year_built: int | None = None
    monthly_rent_won: float | None = None          # 월 임대료(주면 수익환원법 병행)
    deposit_won: float | None = None
    cap_rate: float | None = None


@router.post("/desk-appraisal")
async def land_desk_appraisal(req: DeskAppraisalRequest):
    """예상 탁상감정 — 공시지가기준법 + 거래사례비교법 결합(정식감정 아님, 참고용)."""
    return await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
        building_gfa_sqm=req.building_gfa_sqm, building_structure=req.building_structure,
        building_year_built=req.building_year_built,
        monthly_rent_won=req.monthly_rent_won, deposit_won=req.deposit_won,
        **({"cap_rate": req.cap_rate} if req.cap_rate is not None else {}),
    )


@router.get("/rone-test")
async def rone_test(statbl_id: str, cycle: str = "MM", region: str = "서울", limit: int = 8):
    """특정 STATBL_ID를 실조회해 파싱·시점수정 계산 검증(env 설정 전 사전검증용)."""
    from app.services.external_api import reb_client as reb

    if not reb.reb_key():
        return {"ok": False, "message": "RONE_API_KEY 미설정"}
    rows = await reb.fetch_statbl_rows(statbl_id, cycle, size=300)
    if not rows:
        return {"ok": False, "statbl_id": statbl_id, "cycle": cycle, "message": "행 없음(통계표ID/주기 확인)"}
    # 변동률 누적계수 + 최신값(레벨형)
    factor = reb.cumulative_factor_from_rows(rows, region)
    latest = reb.latest_value_from_rows(rows, region)
    # 구조 파악용 distinct CLS_NM/ITM_NM 샘플
    cls_set = sorted({str(r.get("CLS_NM") or r.get("CLS_FULLNM") or "") for r in rows if isinstance(r, dict)})[:20]
    itm_set = sorted({str(r.get("ITM_NM") or "") for r in rows if isinstance(r, dict)})[:20]
    return {
        "ok": True, "statbl_id": statbl_id, "cycle": cycle, "region": region,
        "row_count": len(rows),
        "cumulative_factor_(변동률용)": factor,
        "latest_value_(레벨형)": latest,
        "distinct_CLS_NM": cls_set,
        "distinct_ITM_NM": itm_set,
        "sample_rows": rows[:limit],
    }


@router.get("/rone-status")
async def rone_status(keyword: str = "지가변동"):
    """R-ONE 부동산통계정보 API 연동 상태 점검 + 통계표(STATBL_ID) 자동 탐색.

    - 인증키만 입력된 경우: 통계표 목록에서 '지가변동' 통계표 후보를 찾아 STATBL_ID 제시.
    - 둘 다 입력된 경우: 실제 지가변동률을 조회해 누적 시점수정계수를 계산(서울 기준 검증).
    """
    from app.services.external_api import reb_client as reb

    key_set = bool(reb.reb_key())
    statbl_set = bool(reb.reb_statbl_id())
    out: dict = {
        "key_set": key_set,
        "statbl_id_set": statbl_set,
        "ready": reb.reb_ready(),
    }
    if not key_set:
        out["message"] = "RONE_API_KEY가 설정되지 않았습니다. 관리자 화면에서 인증키를 입력하세요."
        return out

    # 통계표 후보 탐색(STATBL_ID 미설정 시 도움) — 4종 통계 키워드별
    import os as _os
    stat_envs = {
        "지가변동률": ("RONE_LANDPRICE_STATBL_ID", "지가변동률"),
        "주택 매매가격지수": ("RONE_HOUSING_STATBL_ID", "매매가격지수"),
        "상업용 투자수익률": ("RONE_COMMYIELD_STATBL_ID", "투자수익률"),
        "전월세전환율": ("RONE_JEONSE_CONV_STATBL_ID", "전월세전환율"),
    }
    discovery: dict = {}
    for label, (env_name, search_kw) in stat_envs.items():
        cands = await reb.discover_statbl_ids(keyword=search_kw)
        discovery[label] = {
            "env": env_name,
            "set": bool((_os.getenv(env_name) or "").strip()),
            "candidates": (cands or [])[:10],
        }
    out["statistics_discovery"] = discovery

    # 단일 키워드 후보(하위호환)
    candidates = await reb.discover_statbl_ids(keyword=keyword)
    if candidates is not None:
        out["statbl_candidates"] = candidates[:30]
        out["candidate_count"] = len(candidates)

    # 둘 다 설정 시 실데이터 검증
    if statbl_set:
        rows = await reb.fetch_land_price_changes(months=24)
        out["rows_fetched"] = len(rows) if rows else 0
        if rows:
            factor = reb.cumulative_factor_from_rows(rows, "서울")
            out["seoul_cumulative_factor_24m"] = factor
            out["sample_row"] = rows[0]
            out["message"] = "R-ONE 실데이터 연동 정상 — 시점수정이 실데이터로 동작합니다."
        else:
            out["message"] = "STATBL_ID로 데이터를 가져오지 못했습니다. 통계표 후보(statbl_candidates)에서 올바른 ID를 확인하세요."
    else:
        out["message"] = "인증키는 정상입니다. 아래 statbl_candidates에서 '지가변동률' STATBL_ID를 RONE_LANDPRICE_STATBL_ID에 입력하세요."
    return out


@router.post("/desk-appraisal/pdf")
async def land_desk_appraisal_pdf(req: DeskAppraisalRequest):
    """예상 탁상감정서 PDF 다운로드."""
    from app.services.land_intelligence.desk_appraisal_pdf import build_desk_appraisal_pdf

    result = await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
    )
    if not result.get("ok"):
        return result  # 공시지가 미확인 등 — JSON 오류 반환
    pdf = build_desk_appraisal_pdf(result, address=req.address)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=propai_desk_appraisal.pdf"},
    )
