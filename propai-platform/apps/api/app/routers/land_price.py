"""토지 적정 매입가 추정 라우터 — 토지조서 매입예정가 자동 산정."""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.land_intelligence.desk_appraisal_service import desk_appraisal
from app.services.land_intelligence.land_price_estimator import estimate_land_price
from apps.api.rate_limit import limiter

router = APIRouter(prefix="/api/v1/land-price", tags=["토지 적정가"])

# 비회원 무료체험을 허용하되, 무인증 남용을 막기 위한 IP 기반 제한
_LAND_PRICE_LIMIT = "10/minute"


class LandPriceRequest(BaseModel):
    pnu: str | None = None
    address: str = ""
    area_sqm: float | None = None
    official_price_per_sqm: float | None = None


@router.post("/estimate")
@limiter.limit(_LAND_PRICE_LIMIT)
async def land_price_estimate(request: Request, req: LandPriceRequest):
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
    include_ai: bool = True                          # PDF에 AI 상세 해석(avm) 포함 여부
    # ★원장 귀속(additive·옵셔널): 프론트가 UUID 프로젝트일 때만 실어 분석원장에 project_id 로 귀속한다.
    #   무인증 라우터라 tenant 강제는 하지 않으며(기존 소비처 계약 불변), 미전송이면 None(비귀속·정상).
    project_id: str | None = None
    # ★다필지(additive): /desk-appraisal/pdf 에서 2건 이상이면 통합 보고서 모드로 전환.
    #   행 계약: {pnu?, address?, area_sqm?, official_price_per_sqm?, comparable_avg_per_sqm?}
    #   (단건 desk_appraisal 과 동일 인자만). 1회 상한 30필지 — 초과분은 절단·정직 고지.
    parcels: list[dict] = []


@router.post("/desk-appraisal")
@limiter.limit(_LAND_PRICE_LIMIT)
async def land_desk_appraisal(request: Request, req: DeskAppraisalRequest):
    """예상 탁상감정 — 공시지가기준법 + 거래사례비교법 결합(정식감정 아님, 참고용)."""
    result = await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
        building_gfa_sqm=req.building_gfa_sqm, building_structure=req.building_structure,
        building_year_built=req.building_year_built,
        monthly_rent_won=req.monthly_rent_won, deposit_won=req.deposit_won,
        **({"cap_rate": req.cap_rate} if req.cap_rate is not None else {}),
    )
    # ★성장루프 조인키: 탁상감정 요약을 원장에 best-effort 적재(멱등) 후 최상위 `ledger_hash` 노출
    #   — 프론트 피드백(👍/👎)이 이 해시로 원장과 조인된다. 실패해도 감정 결과 무손상.
    try:
        from app.services.ledger.analysis_ledger_service import attach_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        if isinstance(result, dict):
            wb = await record_user_analysis(
                analysis_type="desk_appraisal",
                summary={
                    "address": req.address, "pnu": req.pnu, "area_sqm": req.area_sqm,
                    # ★키 교정: desk_appraisal 반환 dict 은 final_value_won/estimated_total_won/adopted_method/
                    #   (최상위)method 키를 갖지 않아 기존 코드는 항상 None 을 적재했다. 실제 채택 총액=
                    #   appraised_total_won, 채택 근거=weight_note 로 교정(다필지 경로 :258 은 이미 올바름).
                    "final_value_won": result.get("appraised_total_won"),
                    "adopted_method": result.get("weight_note"),
                },
                pnu=req.pnu or None, address=req.address, source="desk_appraisal",
                project_id=req.project_id,
            )
            result = attach_ledger_hash(result, wb)
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 탁상감정 결과 무손상
        pass
    return result


@router.get("/price-trend")
@limiter.limit(_LAND_PRICE_LIMIT)
async def price_trend(request: Request, address: str = ""):
    """지가변동률 월별·연도별 통계분석(시계열) — 차트/추이 표시용. R-ONE 실데이터."""
    from app.services.land_intelligence.reb_statistics_service import _sido_of, land_price_trend
    t = await land_price_trend(address)
    if not t:
        return {"ok": False, "message": "R-ONE 지가변동률 통계표(RONE_LANDPRICE_STATBL_ID) 미설정 또는 데이터 없음"}
    return {"ok": True, "region": _sido_of(address) or "전국", "source": "R-ONE", **t}


@router.get("/rone-test")
async def rone_test(statbl_id: str, cycle: str = "MM", region: str = "서울", limit: int = 8):
    """특정 STATBL_ID를 실조회해 파싱·시점수정 계산 검증(env 설정 전 사전검증용)."""
    from app.services.external_api import reb_client as reb

    if not reb.reb_key():
        return {"ok": False, "message": "RONE_API_KEY 미설정"}
    # 월 변동률 대용량 표는 최근월 직접조회(실시간 최신), 그 외는 일반 조회
    if cycle == "MM":
        rows = await reb.fetch_recent_monthly_rows(statbl_id, months=24)
    else:
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


# ★다필지 1회 상한 — land-report 의 120(auto_zoning.py:1389) 선례보다 보수적. desk-appraisal 은
#   필지당 외부조회(지오코딩·공시지가·실거래·R-ONE)가 무거워 30필지로 절단(초과분 정직 고지).
_DESK_APPRAISAL_MAX_PARCELS = 30


async def _desk_appraisal_pdf_multi(req: "DeskAppraisalRequest", parcels: list[dict], format: str):
    """다필지 탁상감정서 — 필지별 desk_appraisal 순차 호출 → 통합 보고서.

    - 상한 30필지: 초과분은 절단하고 보고서 caption 에 정직 고지(N배 외부조회 방지).
    - AI 해석(include_ai)·원장 적재는 대표(첫 성공) 필지 1건만(N배 LLM 과금·원장 중복 방지).
    - 성공 필지가 0건이면 단건과 동일하게 JSON 오류 반환(정직).
    """
    from app.services.report.render import build_report_model_from_appraisal_multi, render_report

    omitted = max(0, len(parcels) - _DESK_APPRAISAL_MAX_PARCELS)
    capped = parcels[:_DESK_APPRAISAL_MAX_PARCELS]

    # ★필지별 호출 = '제한 동시성(4) + 필지당 타임아웃(20s)' — R1 리뷰 적발 반영.
    #   순차 × 무타임아웃이면 30필지 × 수 초(실거래 조회)가 게이트웨이/클라이언트 타임아웃을
    #   넘길 수 있다. 동시 4는 외부 공공API 부하 예의(과도 병렬 금지)와 지연의 절충.
    #   타임아웃/실패 필지는 행 단위 격리 → '보완필요' 표기(전체 500 전멸 금지).
    import asyncio as _asyncio

    _sem = _asyncio.Semaphore(4)

    async def _one(p: dict) -> tuple[str, dict]:
        addr = (p.get("address") or "").strip()
        try:
            async with _sem:
                # 단건과 동일 인자만 전달(대표필지 수동입력 전파 금지 — 필지별 자체 자동조회).
                r = await _asyncio.wait_for(
                    desk_appraisal(
                        pnu=p.get("pnu"), address=addr, area_sqm=p.get("area_sqm"),
                        official_price_per_sqm=p.get("official_price_per_sqm"),
                        comparable_avg_per_sqm=p.get("comparable_avg_per_sqm"),
                    ),
                    timeout=20.0,
                )
        except Exception:  # noqa: BLE001 — 개별 필지 실패/타임아웃은 통합 보고서를 막지 않음
            r = {"ok": False, "message": "추정 실패", "address": addr}
        return addr, (r if isinstance(r, dict) else {"ok": False, "address": addr})

    # gather 는 입력 순서를 보존하므로 필지 순번(#)이 요청 순서와 일치한다.
    pairs = await _asyncio.gather(*(_one(p) for p in capped))
    addresses: list[str] = [a for a, _ in pairs]
    results: list[dict] = [r for _, r in pairs]

    ok_idx = [i for i, r in enumerate(results) if r.get("ok")]
    if not ok_idx:
        return {
            "ok": False,
            "message": "다필지 탁상감정: 공시지가를 확인할 수 있는 필지가 없습니다. "
                       "PNU 또는 공시지가를 확인 후 다시 시도하세요.",
            "parcels_count": len(results),
        }
    rep_i = ok_idx[0]
    rep = results[rep_i]
    rep_addr = addresses[rep_i]

    # ★원장 적재는 다필지에서도 1회만(N중 과금 방지) — 통합 총액 합계·필지수 summary(additive).
    try:
        from app.services.ledger.ledger_adapters import record_user_analysis
        total_final = sum(int(r.get("appraised_total_won") or 0)
                          for r in results if r.get("ok") and r.get("appraised_total_won") is not None)
        await record_user_analysis(
            analysis_type="desk_appraisal",
            summary={
                "address": req.address or rep_addr, "pnu": rep.get("pnu"),
                "parcels_count": len(results),
                "final_value_won": total_final,   # 통합(성공 필지 합계) — 다필지 additive
            },
            pnu=rep.get("pnu") or None, address=req.address or rep_addr, source="desk_appraisal",
        )
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 보고서 생성 무손상
        pass

    # ★AI 해석은 대표(첫 성공) 필지 1건만(N배 LLM 과금 방지 — 단건과 동일 패턴).
    ai_sections: dict | None = None
    if req.include_ai:
        import asyncio

        from app.routers.pipeline import _interpret_stage

        try:
            interp = await asyncio.wait_for(
                _interpret_stage("avm", {"address": rep_addr, **rep}), timeout=30.0)
            if isinstance(interp, dict) and interp.get("ok") and isinstance(interp.get("sections"), dict):
                ai_sections = interp["sections"]
        except Exception:  # noqa: BLE001 — 타임아웃/해석 실패해도 PDF는 생성
            ai_sections = None

    model = build_report_model_from_appraisal_multi(
        results, addresses=addresses, ai_sections=ai_sections, omitted_count=omitted)
    data, media_type, ext = render_report(model, format)
    return Response(
        content=data, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=propai_desk_appraisal_multi.{ext}"},
    )


@router.post("/desk-appraisal/pdf")
@limiter.limit(_LAND_PRICE_LIMIT)
async def land_desk_appraisal_pdf(request: Request, req: DeskAppraisalRequest, format: str = "pdf"):
    """예상 탁상감정서 다운로드(PDF/PPTX/DOCX) — 통합 보고서 생성엔진 경유.

    ★다필지: req.parcels 가 2건 이상이면 필지별로 desk_appraisal 을 순차 호출해 '다필지 통합'
      보고서를 만든다(상한 30필지·초과분 절단·정직 고지). 그 외(0~1건)는 기존 단건 경로를
      바이트 동일하게 유지(무회귀). AI 해석·원장 적재는 다필지에서도 1회만(N배 과금 방지).
    """
    # ★다필지 모드 분기 — 단건 경로(아래)는 그대로 두어 무회귀.
    _parcels = [p for p in (req.parcels or []) if isinstance(p, dict)]
    if len(_parcels) >= 2:
        return await _desk_appraisal_pdf_multi(req, _parcels, format)

    from app.services.report.render import build_report_model_from_appraisal, render_report

    result = await desk_appraisal(
        pnu=req.pnu, address=req.address, area_sqm=req.area_sqm,
        official_price_per_sqm=req.official_price_per_sqm,
        comparable_avg_per_sqm=req.comparable_avg_per_sqm,
    )
    if not result.get("ok"):
        return result  # 공시지가 미확인 등 — JSON 오류 반환

    # ★원장 적재(형제 /desk-appraisal :64-79와 동일 인자): PDF 다운로드 경로도 탁상감정 요약을
    #   분석원장에 best-effort로 적재해 성장루프·SSOT에서 누락되지 않게 한다. PDF는 Response로
    #   반환하므로 ledger_hash attach는 생략. 원장 적재 실패해도 PDF 생성 무손상.
    try:
        from app.services.ledger.ledger_adapters import record_user_analysis
        if isinstance(result, dict):
            await record_user_analysis(
                analysis_type="desk_appraisal",
                summary={
                    "address": req.address, "pnu": req.pnu, "area_sqm": req.area_sqm,
                    # ★키 교정(형제 /desk-appraisal :76-77 과 동일): 채택 총액=appraised_total_won,
                    #   채택 근거=weight_note. 기존엔 없는 키를 읽어 항상 None 이 적재됐다.
                    "final_value_won": result.get("appraised_total_won"),
                    "adopted_method": result.get("weight_note"),
                },
                pnu=req.pnu or None, address=req.address, source="desk_appraisal",
                project_id=req.project_id,
            )
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 PDF 생성 무손상
        pass

    ai_sections: dict | None = None
    if req.include_ai:
        # 통합보고서와 동일 패턴: avm 인터프리터(정규화+캐시) 산출을 PDF에 결합.
        import asyncio

        from app.routers.pipeline import _interpret_stage

        try:
            interp = await asyncio.wait_for(
                _interpret_stage("avm", {"address": req.address, **result}), timeout=30.0)
            if isinstance(interp, dict) and interp.get("ok") and isinstance(interp.get("sections"), dict):
                ai_sections = interp["sections"]
        except Exception:  # noqa: BLE001 — 타임아웃/해석 실패해도 PDF는 생성
            ai_sections = None

    model = build_report_model_from_appraisal(result, address=req.address or "", ai_sections=ai_sections)
    data, media_type, ext = render_report(model, format)
    return Response(
        content=data, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=propai_desk_appraisal.{ext}"},
    )
