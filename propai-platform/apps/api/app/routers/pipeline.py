"""프로젝트 파이프라인 API 라우터."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
