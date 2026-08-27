"""시장조사보고서 라우터 — 구조화 JSON / PDF / PPTX 생성."""

import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.billing_deps import enforce_llm_quota
from app.services.common.job_store import JobStore
from app.services.land_intelligence.parcel_normalize import ParcelsIn
from app.services.market.market_report_service import MarketReportService, _resolve_trend_months
from app.services.market.migration_region_service import MigrationRegionService
from app.services.market.population_density_service import PopulationDensityService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

_realtx_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market", tags=["시장조사보고서"])

# ── 비동기 시장보고서 작업 저장소(모바일 안정: 긴 동기요청 대신 제출+폴링) ──
#   공용 잡 스토어(Redis 우선·인메모리 폴백) — registry/design_audit과 동일 계약.
_MARKET_JOBS: dict[str, dict[str, Any]] = {}
_MARKET_JOB_TTL = 3600  # 잡 보관 TTL(초)
_MARKET_STORE = JobStore("job:market_report:", memory_backing=_MARKET_JOBS, default_ttl_s=_MARKET_JOB_TTL)


class MarketReportRequest(BaseModel):
    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    use_llm: bool = True  # AI 내러티브 분석 포함 여부(사용자 선택)
    # 선택형 분석 모듈 옵션. 프론트(P1)가 중첩 dict(detail 등)를 보내므로 dict[str, bool]로
    #   제한하면 Pydantic 422가 발생한다 → 값 타입을 풀어 어떤 형태의 옵션도 받도록 완화.
    options: dict | None = None
    # 다필지(통합분석) 필지목록. 프론트(ComprehensiveAnalysisPanel)가 2개 이상 업로드 시 전송.
    #   각 행 = {address, area_sqm, zone_type, farPct(실효), bcrPct(실효), farLegalPct?, bcrLegalPct?}.
    #   2개 이상이면 면적가중 통합면적으로 land_area를 산정한다(대표 1필지 고착 버그 해소).
    #   None/1개면 기존 단일필지 경로 그대로(무회귀).
    #   ★공용 정규화(ParcelsIn): str[]/dict[] 양 shape → canonical dict[](무음 no-op 제거).
    parcels: ParcelsIn | None = None
    # True면 저장본(캐시)을 무시하고 재분석 후 갱신 — regulation.py/permits.py의 `refresh` 계약 미러.
    refresh: bool = False


def _pnu_from_bcode(bcode: str, jibun: str) -> str | None:
    if not bcode or len(bcode) < 10:
        return None
    m = re.search(r"(산)?(\d+)(?:-(\d+))?(?:\s|$)", jibun or "")
    if not m:
        return None
    return f"{bcode}{'2' if m.group(1) else '1'}{m.group(2).zfill(4)}{(m.group(3) or '0').zfill(4)}"


def _resolve(req: MarketReportRequest) -> tuple[str, str | None]:
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    lawd_cd = (pnu or "")[:5] if pnu else (req.bcode or "")[:5]
    if not lawd_cd or len(lawd_cd) < 5:
        raise HTTPException(status_code=400, detail="법정동코드 결정 불가 — bcode 또는 pnu 필요")
    return lawd_cd, pnu


def _parcel_fingerprint(req: MarketReportRequest, pnu: str | None) -> str:
    """필지세트 지문 — 정렬된 필지 식별자(pnu 우선, 없으면 주소) join 후 sha256[:12].

    ★캐시/원장 오적중 봉합: parcel_count만 시그니처에 실으면 "같은 개수, 다른 필지 구성"의
    두 요청이 동일 캐시/변동감지 대상으로 오인된다(예: A+B 2필지 → A+C 2필지로 교체해도
    parcel_count=2로 동일해 캐시가 A+B 결과를 그대로 돌려준다). parcels가 비어있으면(단일
    필지 경로) 대상 pnu/address 자체를 지문 재료로 삼아 항상 결정적이다.
    """
    ids = [
        str(p.get("pnu") or p.get("address") or "")
        for p in (req.parcels or [])
        if isinstance(p, dict) and (p.get("pnu") or p.get("address"))
    ]
    if not ids:
        ids = [pnu or req.address or ""]
    raw = "|".join(sorted(ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _market_report_signature_parts(req: MarketReportRequest, pnu: str | None) -> list[str]:
    """캐시 키 + 원장 input_signature 재료 — build_signature_parts(단일 소유자) 위임.

    6번째 파트(additive)로 필지세트 지문(_parcel_fingerprint)을 싣는다 — 동일 parcel_count라도
    필지 '구성'이 다르면 캐시/원장이 서로 다른 대상으로 정확히 구분된다(필지세트 오적중 봉합).
    ★프론트는 이 지문을 재계산할 수 없으므로 변동감지 비교에서 제외한다(use-analysis-history.ts
    비교 계약 — idx5+는 비교하지 않음. 동수 필지 교체는 히스토리 카드에 "감지 한계"로 정직 표기).
    """
    from app.services.ledger.ledger_adapters import build_signature_parts

    return build_signature_parts(
        address=req.address, pnu=pnu, parcel_count=len(req.parcels or []) or 1,
        use_llm=req.use_llm, options=req.options,
        extra_parts=[_parcel_fingerprint(req, pnu)],
    )


def _aggregate_trade_stats(trade: Any) -> tuple[int | None, float | None]:
    """report['trade']({유형: {count,avg,...}}) → (전체 거래건수, 거래건수가중 평균단가 만원).

    ★기존 코드는 존재하지 않는 result['stats'] 키를 읽어 trade_count가 항상 None이던 결함이
    있었다(build_report의 실제 반환 키는 'trade' — report[.]에 stats라는 최상위 키는 없음).
    trade가 비어있으면 (None, None)(정직 — 미조회와 0건을 구분), 조회했으나 0건이면 (0, None).
    """
    if not isinstance(trade, dict) or not trade:
        return None, None
    total_count = 0
    weighted_sum = 0.0
    for v in trade.values():
        if isinstance(v, dict):
            c = int(v.get("count") or 0)
            a = float(v.get("avg") or 0)
            total_count += c
            weighted_sum += a * c
    if total_count == 0:
        return 0, None
    return total_count, round(weighted_sum / total_count, 1)


async def _generate_and_record_market_report(
    req: MarketReportRequest, lawd_cd: str, pnu: str | None,
    tenant_id: str | None, cache_key: str,
) -> dict[str, Any]:
    """시장보고서 생성 + 원장 기록(ledger_hash) + 캐시 저장 — 동기 /report·비동기 잡 공용 본체."""
    from app.services.common.analysis_cache import cache_put

    result = await MarketReportService().build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options, parcels=req.parcels)
    # ★성장루프 조인키: 시장보고서 요약을 원장에 best-effort 적재(멱등) 후 최상위 `ledger_hash`
    #   노출 — 시장 인사이트 화면의 피드백(👍/👎)이 원장과 조인된다. 실패해도 보고서 무손상.
    #   cache_put 이전에 부착해 캐시 히트 응답에도 조인키가 실린다(같은 내용=같은 해시).
    try:
        from app.services.ledger.analysis_ledger_service import attach_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        if isinstance(result, dict):
            trade_count, avg_price_10k = _aggregate_trade_stats(result.get("trade"))
            wb = await record_user_analysis(
                analysis_type="market_report",
                summary={
                    "address": req.address, "lawd_cd": lawd_cd, "pnu": pnu,
                    "use_llm": req.use_llm,
                    "parcel_count": len(req.parcels or []) or 1,
                    "trade_count": trade_count,
                    "avg_price_10k": avg_price_10k,
                },
                tenant_id=tenant_id,
                pnu=pnu or None, address=req.address, source="market_report",
                # ★변동감지 표준키(input_signature/signature_parts) 재료 — 단일 소유자(ledger_adapters).
                # extra_parts: 필지세트 지문(6번째 파트) — _market_report_signature_parts와 동일 재료.
                parcel_count=len(req.parcels or []) or 1, use_llm=req.use_llm, options=req.options,
                extra_parts=[_parcel_fingerprint(req, pnu)],
            )
            result = attach_ledger_hash(result, wb)
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 보고서 무손상
        pass
    await cache_put("market_report", cache_key, result)
    return result


@router.post("/report", dependencies=[Depends(enforce_llm_quota)])
async def market_report(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 생성(동기) — 저장본이 있고 refresh=False면 즉시 반환(재분석 0).

    첫 호출만 느리고, 이후 같은 입력은 저장본을 즉시 반환한다. req.refresh=True를 보내면
    재분석 후 저장본을 덮어쓴다(regulation.py `/analyze`와 동일 계약).
    """
    lawd_cd, pnu = _resolve(req)
    from app.services.common.analysis_cache import _key, cache_get, llm_fallback_stale

    cache_key = _key(*_market_report_signature_parts(req, pnu))
    # ★LLM 폴백(narrative.generated=False)이 박제된 캐시는 유예(5분) 경과 시 miss로
    #   취급해 재생성 → 성공 시 upsert로 덮어써 자가치유(규제분석과 동일 결함 클래스).
    if not req.refresh:
        cached = await cache_get("market_report", cache_key)
        if cached is not None and not (req.use_llm and llm_fallback_stale(cached)):
            return cached

    tenant_id = str(getattr(current_user, "tenant_id", "") or "") or None
    return await _generate_and_record_market_report(req, lawd_cd, pnu, tenant_id, cache_key)


# ── 비동기 작업 제출/폴링(모바일·탭 종료·리로드 내구성 — registry.py `/analyze/jobs` 경량 패턴 미러) ──

async def _run_market_report_job(
    job_id: str, req: MarketReportRequest, lawd_cd: str, pnu: str | None,
    tenant_id: str | None, cache_key: str,
) -> None:
    cur = dict(await _MARKET_STORE.get(job_id) or {})
    cur["status"] = "running"
    await _MARKET_STORE.put(job_id, cur, _MARKET_JOB_TTL)
    try:
        result = await _generate_and_record_market_report(req, lawd_cd, pnu, tenant_id, cache_key)
        cur = dict(await _MARKET_STORE.get(job_id) or {})
        cur.update(status="done", result=result)
        await _MARKET_STORE.put(job_id, cur, _MARKET_JOB_TTL)
    except Exception as e:  # noqa: BLE001 — 잡 실패는 상태로 표면화(무음 유실 금지)
        cur = dict(await _MARKET_STORE.get(job_id) or {})
        cur.update(status="error", error=str(e)[:200])
        await _MARKET_STORE.put(job_id, cur, _MARKET_JOB_TTL)


@router.post("/report/jobs", dependencies=[Depends(enforce_llm_quota)], summary="시장조사보고서 비동기 작업 제출")
async def market_report_submit(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """긴 동기요청(공공API 다수 호출) 대신 작업을 제출하고 즉시 job_id를 반환한다.

    캐시 적중 시 즉시 결과 반환(작업 생략 — job_id=None, status=done, registry `/analyze/jobs`와
    동일 계약). 미스면 백그라운드로 넘기고, 완료 시 원장 기록 + 캐시 저장까지 잡 안에서 수행한다
    (잡 완료 = 히스토리 엔트리 생성). 진행은 GET /report/jobs/{id}로 폴링.
    """
    lawd_cd, pnu = _resolve(req)
    from app.services.common.analysis_cache import _key, cache_get, llm_fallback_stale

    cache_key = _key(*_market_report_signature_parts(req, pnu))
    # ★동기 /report와 동일 — LLM 폴백 박제 캐시는 유예 경과 시 재생성으로 자가치유.
    if not req.refresh:
        cached = await cache_get("market_report", cache_key)
        if cached is not None and not (req.use_llm and llm_fallback_stale(cached)):
            return {"job_id": None, "status": "done", "result": cached}

    tenant_id = str(getattr(current_user, "tenant_id", "") or "") or None
    job_id = uuid.uuid4().hex
    # ★소유권 기록(IDOR 봉합) — GET이 이 user_id로 스코프한다(불일치=404). 프루닝은 스토어 put lazy.
    await _MARKET_STORE.put(
        job_id, {"status": "pending", "user_id": str(current_user.user_id)}, _MARKET_JOB_TTL
    )
    # ★태스크 강참조 보관(GC 유실 방지 — design_audit·registry와 동일 공용 헬퍼).
    from app.services.common.bg_tasks import create_tracked_task

    create_tracked_task(_run_market_report_job(job_id, req, lawd_cd, pnu, tenant_id, cache_key))
    return {"job_id": job_id, "status": "pending"}


@router.get("/report/jobs/{job_id}", summary="시장조사보고서 작업 상태/결과 조회")
async def market_report_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """작업 상태(pending/running/done/error)와 완료 시 결과를 반환.

    본인 소유만(타인 job_id·미존재·만료 모두 404 동일 취급 — 존재 여부 비노출, IDOR fail-closed).
    """
    j = await _MARKET_STORE.get(job_id)
    if not j or j.get("user_id") != str(current_user.user_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다(만료되었거나 잘못된 ID).")
    return {"status": j["status"], "result": j.get("result"), "error": j.get("error")}


_TREND_CACHE_TTL_HOURS = 6  # 시세추이 경량 캐시 신선도 — 6시간 내 재요청은 MOLIT 재호출 없이 저장본 재사용.


def _trend_cache_is_fresh(cached: dict[str, Any] | None) -> bool:
    """cache_get이 부착한 `_cache.created_at` 메타를 읽어 TTL(6시간) 이내인지 판정.

    파싱 실패·메타 부재는 정직하게 stale 취급(재조회로 진행 — 오래된 값을 신선한 척 반환하지 않음).
    """
    if not cached:
        return False
    created_raw = (cached.get("_cache") or {}).get("created_at")
    if not created_raw:
        return False
    try:
        created = datetime.fromisoformat(str(created_raw))
    except ValueError:
        return False
    now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
    return (now - created) < timedelta(hours=_TREND_CACHE_TTL_HOURS)


@router.get("/trend", summary="시세추이 경량 조회(아파트 평당가 월별)")
async def market_trend(
    address: str = "",
    pnu: str | None = None,
    bcode: str | None = None,
    jibun_address: str | None = None,
    months: int = 12,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """시세추이만 경량 조회 — 보고서 전체(MOLIT 4유형+SGIS+KOSIS+LLM) 재생성 없이 기간만 바꿔 본다.

    아파트 매매 월별 평당가만 산출(MarketReportService.build_trend_only → _apt_trend 공용 재사용,
    신규 산식 0). MOLIT 아파트 매매만 호출 — 전월세·SGIS·KOSIS·LLM·분양 전부 미호출(LLM 과금 게이트
    없음 — enforce_llm_quota 미적용).

    analysis_cache(kind='market_trend', 키=[lawd_cd, months]) 6시간 이내 재사용 — 신선하면
    MOLIT 미호출(source='cache'). lawd_cd 해석은 /report와 동일 헬퍼(_resolve) 재사용.
    """
    from app.services.common.analysis_cache import _key, cache_get, cache_put

    lawd_cd, _pnu = _resolve(MarketReportRequest(
        address=address, pnu=pnu, bcode=bcode, jibun_address=jibun_address, use_llm=False))
    months_n = _resolve_trend_months({"trend_months": months})

    cache_key = _key(lawd_cd, months_n)
    cached = await cache_get("market_trend", cache_key)
    if _trend_cache_is_fresh(cached):
        return {
            "months": cached.get("months", months_n),
            "trend": cached.get("trend", []),
            "source": "cache",
            "cached": True,
        }

    apt_trend = await MarketReportService().build_trend_only(lawd_cd, months_n)
    result = {
        "months": months_n,
        "trend": [{"ym": t.get("ym"), "avg_per_pyeong": t.get("avg_per_pyeong")} for t in apt_trend],
        "source": "molit",
        "cached": False,
    }
    await cache_put("market_trend", cache_key, result)
    return result


class PopulationDensityRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None


def _region_name(address: str | None) -> str | None:
    """주소에서 SGIS 시군구 해석용 시/군/구 토큰 추출(예: '의정부시','강남구')."""
    if not address:
        return None
    m = re.findall(r"([가-힣]+(?:시|군|구))", address)
    # 통합시 자치구(예: '수원시 장안구')는 마지막 구 토큰이 더 구체적.
    return m[-1] if m else None


@router.post("/population-density")
async def population_density(
    req: PopulationDensityRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """P4-B 인구밀도 레이어 데이터 — SGIS 행정동 경계(WGS84)+인구 → 밀도 코로플레스.

    LLM 미사용(데이터 조회) → 과금 게이트 없음. 무자료/키없음은 data_source=unavailable.
    """
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    bcode = ((pnu or "")[:10] if pnu else (req.bcode or "")) or ""
    return await PopulationDensityService().build(bcode=bcode, region_name=_region_name(req.address))


class MigrationRegionRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    year: str | None = None


@router.post("/migration-region")
async def migration_region(
    req: MigrationRegionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """권역 인구이동망 레이어 — 대상 시군구가 속한 시도의 시군구별 순이동 발산 코로플레스.

    SGIS 시군구 경계(WGS84) + KOSIS「시군구별 이동자수」 순이동을 조인해 권역(시도) 지도를
    색으로 시각화한다(전출초과=적·전입초과=청·0=중립). LLM 미사용(데이터 조회) → 과금 게이트 없음.
    KOSIS/SGIS 무키·무자료는 data_source=unavailable(가짜 순이동 금지).
    """
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    bcode = ((pnu or "")[:10] if pnu else (req.bcode or "")) or ""
    return await MigrationRegionService().build_migration_region(
        bcode=bcode, region_name=_region_name(req.address), year=req.year)


@router.post("/report/pdf", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pdf(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 PDF — 통합 보고서 생성엔진 경유(build_report_model_from_market + render_report).

    엔드포인트 경로·요청 계약·응답 헤더(파일명 등)는 프론트 무수정 목표로 이전과 동일 유지."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    pdf, _media_type, _ext = render_report(model, "pdf")
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="market_report.pdf"'},
    )


@router.post("/report/pptx", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pptx(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 PPTX — 통합 보고서 생성엔진 경유(PDF 라우트와 동일 어댑터·모델 재사용)."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    pptx, _media_type, _ext = render_report(model, "pptx")
    return StreamingResponse(
        iter([pptx]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="market_report.pptx"'},
    )


@router.post("/report/docx", dependencies=[Depends(enforce_llm_quota)])
async def market_report_docx(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 DOCX — 통합 보고서 생성엔진 경유(PDF 라우트와 동일 어댑터·모델 재사용)."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    docx, _media_type, _ext = render_report(model, "docx")
    return StreamingResponse(
        iter([docx]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="market_report.docx"'},
    )


# ── 간편 분양성 조사(지번 1개 → 한 화면) ──────────────────────────────────
# ★새 분석엔진을 만들지 않는다 — `QuickSalesSurveyService` 는 기존 셋(시장조사보고서·
#   VWorld 도시계획시설·청약홈 인근분양)을 **조립만** 한다. 계산은 상위 엔진 소유다.
# ★과금·인증은 `/report` 와 **같은 게이트**를 쓴다. 여기만 열어 두면 무료 우회로가 된다.

@router.post(
    "/quick-survey",
    dependencies=[Depends(enforce_llm_quota)],
    summary="간편 분양성 조사(지번 1개 → 주변시세·개발호재·입지·분양사례)",
)
async def quick_sales_survey(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """지번 하나로 공급·가격 축을 한 화면에 모은다.

    ★**이름과 내용의 경계**: 분양성의 수요 축(청약경쟁률·미분양·흡수율)은 이 저장소에
      데이터원이 없다. 응답의 `demand_indicators` 가 그 사실을 **항상** 실어 나른다 —
      블록을 생략하면 "안 본 것"과 "없는 것"이 화면에서 구분되지 않는다.
    """
    lawd_cd, pnu = _resolve(req)
    from app.services.common.analysis_cache import _key, cache_get, cache_put
    from app.services.market.quick_sales_survey_service import QuickSalesSurveyService

    # ★캐시 키는 `/report` 와 **같은 재료**를 쓰되 네임스페이스를 분리한다 —
    #   같은 네임스페이스를 쓰면 표면이 다른 두 산출물이 서로를 덮어쓴다.
    cache_key = _key(*_market_report_signature_parts(req, pnu))
    if not req.refresh:
        cached = await cache_get("quick_sales_survey", cache_key)
        if cached is not None:
            return cached

    result = await QuickSalesSurveyService().build(
        address=req.address, lawd_cd=lawd_cd, pnu=pnu, use_llm=req.use_llm
    )
    await cache_put("quick_sales_survey", cache_key, result)
    return result

class RealtxParcelIn(BaseModel):
    """토지조서 필지 1건 — 프론트(landSchedule)가 보내는 형태.

    ★필지는 **DB `parcels` 테이블에 없다**(2026-08-26 라이브 실측: 총 0행).
      실제 필지는 프론트 `landSchedule.byProject` 에 있으므로 **클라이언트가 보낸다.**
    """

    pnu: str | None = None
    jibun: str | None = None
    address: str | None = None
    area_sqm: float | None = None
    zone_code: str | None = None
    owner_type: str | None = None


class RealtxReportRequest(BaseModel):
    parcels: list[RealtxParcelIn]
    end_ym: str | None = None      # YYYYMM — 미지정 시 당월
    months: int = 6
    prop_type: str = "land"


@router.post(
    "/realtx-report",
    summary="프로젝트 필지 실거래 신고내역 현황분석",
)
async def realtx_report(
    body: RealtxReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """필지 목록의 **실거래 신고내역**을 정리한다 — `#837` 6필드의 첫 소비 통로.

    ★**LLM 미사용**(데이터 조회) → 과금 게이트 없음. 형제(`/quick-survey`·`/trend`)와 같다.

    ★**필지 단위가 아니다.** MOLIT 은 토지 거래의 지번을 마스킹한다(라이브 실측 100%).
      응답의 `groups[].parcel_level_match_absent = "masked_by_source"` 가 그 사실을 말한다.

    ★쿼터: 조회는 **(시군구, 월)** 로 접힌다. 필지 수와 무관하다 —
      응답 `meta.molit_calls` 로 **소비처가 직접 확인**할 수 있다(주장이 아니라 수).
    """
    from app.services.land_intelligence.realtx_report_service import build_realtx_report

    if not body.parcels:
        raise HTTPException(status_code=422, detail="필지 목록이 비어 있습니다.")
    # 상한 — 한 번에 과도한 시군구를 태우지 않는다(쿼터 방어의 두 번째 층).
    if len(body.parcels) > 2000:
        raise HTTPException(status_code=422, detail="필지가 너무 많습니다(최대 2000).")
    months = max(1, min(int(body.months or 6), 24))
    end_ym = (body.end_ym or datetime.now().strftime("%Y%m")).strip()
    return await build_realtx_report(
        [p.model_dump() for p in body.parcels],
        end_ym=end_ym,
        months=months,
        prop_type=body.prop_type or "land",
    )

@router.post(
    "/realtx-report/download",
    summary="실거래 신고내역 현황분석 보고서 다운로드(pdf/pptx/docx)",
)
async def realtx_report_download(
    body: RealtxReportRequest,
    format: str = "pdf",
    current_user: CurrentUser = Depends(get_current_user),
):
    """`/realtx-report` 와 **같은 값**을 정본 통로로 렌더한다.

    ★산식을 여기서 다시 계산하지 않는다 — 같은 서비스를 부르고 어댑터로 옮겨 담는다.
      두 표면(JSON·문서)이 **다른 수를 말하는 것**을 구조적으로 막는다.
    """
    from app.services.land_intelligence.realtx_report_service import build_realtx_report
    from app.services.report.render.engine import render_report
    from app.services.report.render.realtx_adapter import build_report_model_from_realtx

    if not body.parcels:
        raise HTTPException(status_code=422, detail="필지 목록이 비어 있습니다.")
    if len(body.parcels) > 2000:
        raise HTTPException(status_code=422, detail="필지가 너무 많습니다(최대 2000).")
    fmt = (format or "pdf").lower()
    if fmt not in ("pdf", "pptx", "docx"):
        raise HTTPException(status_code=422, detail="format 은 pdf|pptx|docx 만 가능합니다.")
    months = max(1, min(int(body.months or 6), 24))
    end_ym = (body.end_ym or datetime.now().strftime("%Y%m")).strip()
    payload = await build_realtx_report(
        [p.model_dump() for p in body.parcels],
        end_ym=end_ym, months=months, prop_type=body.prop_type or "land",
    )
    model = build_report_model_from_realtx(payload)
    try:
        data, media_type, ext = render_report(model, fmt)
    except Exception as e:  # noqa: BLE001 — 렌더 실패를 500 스택으로 흘리지 않는다
        _realtx_log.warning("실거래 보고서 생성 실패: %s", str(e)[:200])
        raise HTTPException(status_code=500, detail="보고서 생성에 실패했습니다.") from e
    return StreamingResponse(
        iter([data]), media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="realtx_report.{ext}"'},
    )


@router.get(
    "/realtx-layer2/status",
    summary="실거래 2층(저장·정정탐지) 관측 상태 — 관리자 전용",
)
async def realtx_layer2_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """2층이 **살아 있는지**, 무엇을 봤는지 — 저장분을 처음으로 **읽는** 통로.

    ★**LLM 미사용**(읽기 전용 집계) → 과금 게이트 없음.

    ★★**관리자 전용**(2026-08-27 독립 리뷰 M5). 이 응답은 테넌트 데이터가 아니지만
      **플랫폼 전역 규모**(총 저장 행수·전 시군구 수·쿼터 산술·마지막 수집 시각)를
      드러낸다. 종전엔 `get_current_user` 하나뿐이라 **어떤 인증 사용자든** 읽었다.
      ★게이트는 형제(`routers/analysis_ledger.py:_require_admin`)와 **같은 판별**을 쓴다 —
        `role` 로 걸면 **가입 시 모두 `role='admin'`** 이라 누출된다(그 파일이 적어 둔 실측).

    ★왜 필요한가: `#855`·`#860`·`#884` 가 2층을 만들었고 프로덕션에 수천 행이 쌓였는데
      **읽는 코드가 0건**이었다(실측 2026-08-27). 수집이 조용히 멈춰도, 정정이 쏟아져도
      아무도 몰랐다. `#884` 가 스스로 부채로 적어 둔 *"8일 이상 낡음을 판정하는 소비처"* 다.

    ★응답의 `detection.state` 를 먼저 보라 — `corrections.total = 0` 은 **여러 뜻**이 있고
      (`미시험` · `상태소실` · `관측됨_정정없음`) 이 필드가 그것을 가른다. 섞어 읽으면
      **정상을 장애로**, 혹은 **죽은 탐지를 정상으로** 판정하게 된다.
    """
    from app.services.billing.billing_service import is_super_admin
    from app.services.land_intelligence.realtx_layer2_status import build_layer2_status
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if not await is_super_admin(db, current_user.user_id):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        return await build_layer2_status(db)
