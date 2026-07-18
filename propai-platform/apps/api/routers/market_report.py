"""시장조사보고서 라우터 — 구조화 JSON / PDF / PPTX 생성."""

import hashlib
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.billing_deps import enforce_llm_quota
from app.services.common.job_store import JobStore
from app.services.land_intelligence.parcel_normalize import ParcelsIn
from app.services.market.market_report_service import MarketReportService
from app.services.market.migration_region_service import MigrationRegionService
from app.services.market.population_density_service import PopulationDensityService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

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
    from app.services.common.analysis_cache import _key, cache_get

    cache_key = _key(*_market_report_signature_parts(req, pnu))
    if not req.refresh:
        cached = await cache_get("market_report", cache_key)
        if cached is not None:
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
    from app.services.common.analysis_cache import _key, cache_get

    cache_key = _key(*_market_report_signature_parts(req, pnu))
    if not req.refresh:
        cached = await cache_get("market_report", cache_key)
        if cached is not None:
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
