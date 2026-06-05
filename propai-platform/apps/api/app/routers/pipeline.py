"""프로젝트 파이프라인 API 라우터."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from app.services.ledger import analysis_ledger_service as ledger
from app.services.pipeline.project_pipeline import (
    ProjectPipeline,
    PipelineStage,
    PipelineStatus,
)
from app.services.report.pipeline_report_service import (
    PipelineReport,
    PipelineReportService,
)

router = APIRouter(prefix="/api/v2/pipeline", tags=["pipeline"])


# ── Request / Response 모델 ──────────────────────────────────


class PipelineRunRequest(BaseModel):
    address: str
    project_id: str | None = None
    options: dict | None = None


class StageRerunRequest(BaseModel):
    """특정 단계 재실행 요청."""

    address: str
    project_id: str | None = None
    stage: str  # "site_analysis" | "design" | "cost" | ...
    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="해당 단계에 주입할 사용자 수정값 (예: {\"max_far\": 250})",
    )
    previous_result: dict[str, Any] = Field(
        default_factory=dict,
        description="이전 파이프라인 실행 결과 (stages dict). 미제공 시 전체 재실행.",
    )


class PipelineStageStatusResponse(BaseModel):
    stage: str
    status: str
    duration_ms: int | None = None
    data: dict = {}
    error: str | None = None


class PipelineRunResponse(BaseModel):
    pipeline_id: str
    project_id: str
    status: str
    stages: list[PipelineStageStatusResponse]
    summary: dict = {}


# ── 헬퍼 ──────────────────────────────────────────────────


def _build_stages_response(result) -> list[PipelineStageStatusResponse]:
    """PipelineState → PipelineStageStatusResponse 리스트 변환."""
    stages: list[PipelineStageStatusResponse] = []
    for stage_name, stage_result in result.stages.items():
        stages.append(
            PipelineStageStatusResponse(
                stage=stage_name,
                status=stage_result.status.value,
                duration_ms=stage_result.duration_ms,
                data=stage_result.data,
                error=stage_result.error,
            )
        )
    return stages


# ── 엔드포인트 ────────────────────────────────────────────


@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(req: PipelineRunRequest):
    """주소 입력으로 전체 파이프라인 실행."""
    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=req.options,
    )

    stages = _build_stages_response(result)

    # 서비스 사용료(LLM 별개): 이번 실행에서 실제로 수행된 단계마다 과금(로그인, best-effort).
    # duration_ms가 있는(=이번에 실행된) completed 단계만 → 재사용 단계 중복과금 방지.
    try:
        from app.core.request_context import get_current_user_id

        uid = get_current_user_id()
        if uid:
            ran = [s.stage for s in stages if s.status == "completed" and (s.duration_ms or 0) > 0]
            if ran:
                from app.core.database import async_session_factory
                from app.services.billing import billing_service

                async with async_session_factory() as _db:
                    for stage_name in ran:
                        await billing_service.charge_service(_db, uid, f"stage:{stage_name}")
    except Exception:  # noqa: BLE001
        pass

    # 최종 요약
    summary = {}
    report_data = result.stages.get("report")
    if report_data and report_data.data:
        summary = report_data.data.get("summary", {})

    return PipelineRunResponse(
        pipeline_id=result.pipeline_id,
        project_id=result.project_id,
        status=result.status.value,
        stages=stages,
        summary=summary,
    )


def _normalize_for_interpreter(stage: str, data: dict[str, Any]) -> dict[str, Any]:
    """파이프라인 stage 데이터 키 → 인터프리터 기대 키로 보강(해석 품질↑). 원본 키도 보존."""
    d = dict(data)

    def setdefault_from(target: str, *sources: str) -> None:
        if d.get(target) in (None, "") :
            for s in sources:
                if d.get(s) not in (None, ""):
                    d[target] = d[s]; return

    if stage == "design":
        setdefault_from("total_floor_area_sqm", "total_gfa_sqm")
        setdefault_from("num_floors", "floor_count", "floor_count_above")
        setdefault_from("building_use", "building_type")
        setdefault_from("bcr_pct", "bcr_used_pct", "bcr")
        setdefault_from("far_pct", "far_used_pct", "far")
        setdefault_from("max_bcr_pct", "max_bcr")
        setdefault_from("max_far_pct", "max_far")
        setdefault_from("zone_code", "zone_type")
        setdefault_from("building_footprint_sqm", "building_area_sqm")
    elif stage in ("appraisal", "avm"):
        # 예상시세 추정(desk_appraisal) 결과 → avm_interpreter 입력(estimated_value 등) 매핑.
        if not isinstance(d.get("estimated_value"), dict):
            rng = d.get("range_per_sqm") or {}
            d["estimated_value"] = {
                "value_won": d.get("appraised_total_won"),
                "value_per_sqm_won": d.get("appraised_price_per_sqm"),
                "confidence_score": d.get("confidence"),
                "confidence_interval_low": rng.get("low"),
                "confidence_interval_high": rng.get("high"),
            }
        if not isinstance(d.get("market_statistics"), dict) and isinstance(d.get("market_stats"), dict):
            d["market_statistics"] = d["market_stats"]
    elif stage == "esg":
        # esg_interpreter는 carbon_emissions 중첩을 기대 — 가용 탄소값으로 구성.
        if not isinstance(d.get("carbon_emissions"), dict):
            emb = d.get("embodied_carbon_kg"); op = d.get("operational_carbon_kg")
            per = d.get("total_carbon_per_sqm")
            if any(v is not None for v in (emb, op, per)):
                tot = ((emb or 0) + (op or 0)) / 1000 or None
                d["carbon_emissions"] = {
                    "total_emissions_tco2": round(tot, 2) if tot else None,
                    "emissions_per_sqm": per,
                    "scope1": round((emb or 0) / 1000, 2) if emb else None,
                    "scope3": round((op or 0) / 1000, 2) if op else None,
                }
    return d


async def _interpret_stage(stage: str, data: dict[str, Any]) -> dict[str, Any]:
    """단계 AI 해석(정규화+캐시+인터프리터). interpret 엔드포인트·PDF 생성 공용."""
    data = _normalize_for_interpreter(stage, data)
    from app.services.ai.interpretation_cache import cache_key, get_cached, put_cached
    ckey = cache_key(stage, data)
    cached = await get_cached(ckey)
    if cached:
        return {"ok": True, "stage": stage, "sections": cached, "cached": True}
    try:
        if stage == "site_analysis":
            from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
            sections = await SiteAnalysisInterpreter().generate_interpretation(data)
        elif stage == "design":
            from app.services.ai.design_interpreter import DesignInterpreter
            sections = await DesignInterpreter().generate_interpretation(data)
        elif stage == "cost":
            from app.services.ai.cost_interpreter import CostInterpreter
            sections = await CostInterpreter().generate_interpretation(data)
        elif stage == "feasibility":
            from app.services.ai.feasibility_interpreter import FeasibilityInterpreter
            sections = await FeasibilityInterpreter().generate_interpretation(data)
        elif stage == "tax":
            from app.services.ai.tax_interpreter import TaxInterpreter
            sections = await TaxInterpreter().generate_interpretation(data)
        elif stage == "esg":
            from app.services.ai.esg_interpreter import EsgInterpreter
            sections = await EsgInterpreter().generate_interpretation(data)
        elif stage in ("appraisal", "avm"):
            from app.services.ai.avm_interpreter import AvmInterpreter
            sections = await AvmInterpreter().generate_interpretation(data)
        elif stage == "report":
            from app.services.ai.report_interpreter import ReportInterpreter
            sections = await ReportInterpreter().generate_report_narrative(data)
        else:
            return {"ok": False, "stage": stage, "message": "지원하지 않는 단계입니다.", "sections": {}}
        ok = isinstance(sections, dict) and bool(sections)
        if ok:
            await put_cached(ckey, stage, sections)
        return {"ok": ok, "stage": stage, "sections": sections if isinstance(sections, dict) else {}}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": stage, "message": str(e)[:160], "sections": {}}


async def _gather_report_narratives(result_dict: dict[str, Any], timeout: float = 28.0) -> dict[str, dict[str, str]]:
    """보고서 PDF용 — 단계별 AI 해석을 병렬 수집(캐시 우선, 미스는 생성). 타임아웃 내 완료분만."""
    import asyncio

    stages_map = result_dict.get("stages") or {}
    summary = result_dict.get("summary") or {}
    site = (stages_map.get("site_analysis") or {})
    site_data = site.get("data") if isinstance(site, dict) else {}
    ctx = {
        "address": result_dict.get("address") or (site_data or {}).get("address"),
        "zone_type": (site_data or {}).get("zone_type") or ((site_data or {}).get("basic") or {}).get("zone_type"),
    }
    targets = ["site_analysis", "design", "cost", "feasibility", "tax", "esg"]
    jobs = []
    for stg in targets:
        s = stages_map.get(stg)
        d = s.get("data") if isinstance(s, dict) else None
        if not isinstance(d, dict) or not d:
            # summary 폴백
            d = summary.get(stg) if isinstance(summary.get(stg), dict) else None
        if isinstance(d, dict) and d:
            jobs.append((stg, _interpret_stage(stg, {**ctx, **d})))
    if not jobs:
        return {}
    out: dict[str, dict[str, str]] = {}
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[j for _, j in jobs], return_exceptions=True), timeout=timeout)
        for (stg, _), r in zip(jobs, results):
            if isinstance(r, dict) and r.get("ok") and isinstance(r.get("sections"), dict):
                out[stg] = r["sections"]
    except asyncio.TimeoutError:
        pass
    return out


class InterpretRequest(BaseModel):
    """단계별 AI 해석(온디맨드) 요청 — 보고서 섹션 열람 시 호출."""
    stage: str
    data: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)  # 공통 맥락(주소·용도지역·면적·연면적 등)


@router.post("/interpret", summary="단계 AI 해석 온디맨드 생성(타임아웃 안전)")
async def interpret_stage(req: InterpretRequest) -> dict[str, Any]:
    """한 단계의 인터프리터를 단건 호출해 섹션별 서술 해석을 반환한다.

    파이프라인 동기 실행을 막지 않도록 보고서가 섹션을 볼 때 개별 호출(각 ~10초).
    공통 맥락(주소·용도지역·면적·연면적)을 단계 데이터에 병합해 해석 품질을 높인다.
    """
    stage = (req.stage or "").strip()
    # 맥락(context) → 데이터 병합(단계 data 우선). 인터프리터 공통 키 보강.
    data = {**(req.context or {}), **(req.data or {})}
    out = await _interpret_stage(stage, data)
    return out


@router.post("/report", response_model=PipelineReport)
async def generate_report(req: PipelineRunRequest):
    """파이프라인 실행 + 통합 보고서 생성.

    전체 파이프라인을 실행한 뒤, 결과를 10섹션 은행 PF 심사용
    통합 보고서로 변환하여 반환한다.
    """
    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=req.options,
    )

    # PipelineState → dict 변환 (stages 내부의 StageResult도 직렬화)
    result_dict = result.model_dump()

    report_svc = PipelineReportService()
    report = report_svc.generate(result_dict)
    return report


class ReportPdfRequest(BaseModel):
    """통합 보고서 PDF 요청 — 이미 계산된 결과(result)를 보내면 재실행 없이 즉시 PDF."""
    address: str | None = None
    project_id: str | None = None
    result: dict[str, Any] | None = None   # {summary, stages} (프론트 보유분)


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """프론트 result(stages=list) → PipelineReportService 기대형(stages=dict) 정규화."""
    out = dict(result or {})
    stages = out.get("stages")
    if isinstance(stages, list):
        out["stages"] = {s.get("stage"): s for s in stages if isinstance(s, dict) and s.get("stage")}
    return out


@router.post("/report/pdf", summary="통합 보고서 PDF 다운로드(결과 제공 시 재실행 없음)")
async def generate_report_pdf(req: ReportPdfRequest):
    """통합 분석 보고서를 PDF로 생성. result가 있으면 그것으로(즉시), 없으면 파이프라인 실행."""
    from fastapi.responses import Response
    from app.services.report.pipeline_report_pdf import build_pipeline_report_pdf

    if req.result:
        result_dict = _normalize_result(req.result)
        if req.address and not result_dict.get("address"):
            result_dict["address"] = req.address
    else:
        pipeline = ProjectPipeline()
        state = await pipeline.run(address=req.address or "", project_id=req.project_id, options=None)
        result_dict = state.model_dump()

    report = PipelineReportService().generate(result_dict)
    narratives = await _gather_report_narratives(result_dict)
    pdf = build_pipeline_report_pdf(report.model_dump(), narratives=narratives)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=propai_report.pdf"},
    )


# ── 원장(ledger) 단일출처 직접 렌더 ──────────────────────────

# 원장 analysis_type → 파이프라인 stage 키 매핑.
# PipelineReportService.generate / _gather_report_narratives 가 읽는 stage 키
# (site_analysis, design, cost, feasibility, tax, esg)와 일치시킨다.
# appraisal/avm은 보고서 본문에서 직접 소비하지 않으나 계보 보존용으로 통과시킨다.
_LEDGER_TYPE_TO_STAGE: dict[str, str] = {
    "avm": "appraisal",
    "appraisal": "appraisal",
    "site_analysis": "site_analysis",
    "design": "design",
    "cost": "cost",
    "feasibility": "feasibility",
    "tax": "tax",
    "esg": "esg",
    "permit": "permit",
}


class ReportFromLedgerRequest(BaseModel):
    """원장(ledger) 최신 버전 묶음을 단일출처로 통합 보고서 PDF를 직접 렌더."""
    pnu: str | None = None
    address: str | None = None
    project_id: str | None = None


@router.post("/report/pdf-from-ledger", summary="통합 보고서 PDF(분석 원장 단일출처 직접 렌더)")
async def generate_report_pdf_from_ledger(
    req: ReportFromLedgerRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """분석 원장에 적재된 각 분석타입의 최신 버전 payload를 단일출처로
    PF 심사용 통합 보고서 PDF를 직접 생성한다(프론트 컨텍스트 경유 없이).

    pnu/address/project_id 중 하나로 체인을 식별하며, 원장이 비어 있으면
    빈 PDF 대신 안내 JSON을 반환한다.
    """
    from fastapi.responses import JSONResponse, Response
    from app.services.report.pipeline_report_pdf import build_pipeline_report_pdf

    if not (req.pnu or req.address or req.project_id):
        return JSONResponse(
            status_code=422,
            content={"ok": False, "message": "pnu/address/project_id 중 하나는 필수입니다."},
        )

    tid = str(getattr(current, "tenant_id", "") or "") or None
    bundle = await ledger.get_latest(
        analysis_type=None, tenant_id=tid,
        pnu=req.pnu, address=req.address, project_id=req.project_id,
    )
    if not bundle:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "message": "원장에 분석 데이터가 없습니다. 먼저 분석을 실행/저장하세요."},
        )

    # 원장 묶음 → result_dict 조립(stages=dict). PipelineReportService 기대형.
    stages: dict[str, Any] = {}
    version_parts: list[str] = []
    for atype, entry in bundle.items():
        if not isinstance(entry, dict):
            continue
        stage = _LEDGER_TYPE_TO_STAGE.get(atype, atype)
        payload = entry.get("payload")
        stages[stage] = {
            "stage": stage,
            "data": payload if isinstance(payload, dict) else {},
            "ledger_version": entry.get("version"),
            "content_hash": entry.get("content_hash"),
        }
        version_parts.append(f"{stage}:v{entry.get('version')}")

    site_payload = (stages.get("site_analysis") or {}).get("data") or {}
    address = req.address or (site_payload.get("address") if isinstance(site_payload, dict) else None) or ""

    result_dict: dict[str, Any] = {"address": address, "stages": stages}

    report = PipelineReportService().generate(result_dict)
    narratives = await _gather_report_narratives(result_dict)
    pdf = build_pipeline_report_pdf(
        report.model_dump() if hasattr(report, "model_dump") else report,
        narratives=narratives,
    )
    # 헤더값은 ASCII 안전(콜론/쉼표만, 한글 금지).
    versions_header = ",".join(version_parts)[:300] or "none"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=propai_report_ledger.pdf",
            "X-Ledger-Versions": versions_header,
        },
    )


@router.post("/rerun-stage")
async def rerun_stage(req: StageRerunRequest):
    """특정 단계만 재실행.

    이전 결과를 유지하면서 지정된 단계부터 이후 단계를 연쇄 재계산한다.
    사용자가 입력값(overrides)을 수정한 후 해당 단계만 재분석할 수 있다.

    동작 방식:
    1. ``previous_result`` 가 있으면 해당 단계 이전까지의 결과를 보존한다.
    2. 지정 단계부터 파이프라인 끝까지 재실행한다.
    3. ``overrides`` 는 options 에 ``stage_overrides.{stage}`` 키로 주입되어
       해당 단계 실행 시 참조된다.
    """
    # stage 유효성 검증
    valid_stages = [s.value for s in PipelineStage]
    if req.stage not in valid_stages:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 단계: '{req.stage}'. 가능한 값: {valid_stages}",
        )

    target_idx = valid_stages.index(req.stage)

    # options 구성: overrides를 stage_overrides 하위에 삽입
    options: dict[str, Any] = {}
    if req.overrides:
        options["stage_overrides"] = {req.stage: req.overrides}

    # skip_stages: 재실행 대상 이전 단계를 스킵 (이전 결과 유지)
    skip_before = valid_stages[:target_idx]
    options["skip_stages"] = skip_before

    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=options,
    )

    # 이전 결과가 제공된 경우, 스킵된 단계의 data를 이전 결과로 채움
    if req.previous_result:
        prev_stages = req.previous_result.get("stages", req.previous_result)
        for skipped_stage in skip_before:
            prev_entry = prev_stages.get(skipped_stage)
            if prev_entry and skipped_stage in result.stages:
                prev_data = prev_entry.get("data", prev_entry) if isinstance(prev_entry, dict) else {}
                result.stages[skipped_stage].data = prev_data
                result.stages[skipped_stage].status = PipelineStatus.COMPLETED

    stages = _build_stages_response(result)

    # 보고서도 함께 생성
    result_dict = result.model_dump()
    report_svc = PipelineReportService()
    report = report_svc.generate(result_dict)

    return {
        "pipeline_id": result.pipeline_id,
        "project_id": result.project_id,
        "status": result.status.value,
        "rerun_from": req.stage,
        "stages": [s.model_dump() for s in stages],
        "report": report.model_dump(),
    }
