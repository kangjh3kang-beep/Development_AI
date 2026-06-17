"""심의분석 파이프라인 API — 원시 입력 → 11계층 전체 분석 → AnalysisResult.

POST /api/v1/analyze: 분석 실행 + 영속화(run_id 반환). GET /api/v1/analyze/{run_id}: 저장 결과 조회.
인증: settings.API_TOKEN 설정 시 베어러 토큰 요구(미설정=개방). 도메인 거부는 422.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_token
from app.contracts.analysis import AnalysisInput, AnalysisResult
from app.core.errors import DomainError
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.pipeline.analysis_store import get_analysis, save_analysis
from app.settings import settings

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResult, dependencies=[Depends(require_token)])
async def analyze(payload: AnalysisInput, session: AsyncSession = Depends(get_session)) -> AnalysisResult:
    # INC-11: 분석 전 캐시 적재(L2→L1, snapshot 결속) · 분석 후 신규 fetch 영속(L1→L2). 모두 best-effort
    # (캐시는 데이터 확보 단계만 — 실패해도 분석 진행, 결정론 영향 0).
    from app.adapters.cache.source_cache import flush_to_db, warm_from_db
    try:
        await warm_from_db(session, payload.snapshot_id)
    except Exception:
        await session.rollback()  # 캐시 적재 실패 → 직접 fetch 경로로 degrade(무음 단정 금지: 분석은 진행)
    # INC-13: 적재된 미러(공급측 DB)를 in-memory로 warm → 소비측 sync get이 DB-backed 미러를 읽음(INV-13 read-only).
    try:
        from app.supply.mirror.mirror_store import warm_mirror_from_db
        await warm_mirror_from_db(session, payload.pnu)
    except Exception:
        await session.rollback()  # 미러 적재 실패 → 미적재 보수 게이팅으로 degrade(분석 진행)
    try:
        result = run_analysis(payload)
    except DomainError as exc:
        # 예외 원문(내부 식별자/경로) 노출 금지 — 안정 코드만 반환(원문은 서버 추적 from exc).
        raise HTTPException(status_code=422, detail=f"domain_error:{type(exc).__name__}") from exc
    try:
        await flush_to_db(session)
    except Exception:
        await session.rollback()  # 캐시 영속 실패 → 다음 분석이 재fetch(분석 결과엔 무영향)
    return await save_analysis(session, result)


@router.get("/analyze/{run_id}", response_model=AnalysisResult, dependencies=[Depends(require_token)])
async def get_analysis_run(run_id: str, session: AsyncSession = Depends(get_session)) -> AnalysisResult:
    result = await get_analysis(session, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return result


@router.post("/analyze/async", dependencies=[Depends(require_token)])
def analyze_async(payload: AnalysisInput) -> dict:
    """비동기 분석 큐잉(P-D). 대량 도면/실 LLM 시 백그라운드. dev eager면 결과 즉시 포함."""
    from app.tasks.analysis_tasks import analyze_task
    ar = analyze_task.delay(payload.model_dump(mode="json"))
    out: dict = {"task_id": ar.id, "status": ar.status, "eager": settings.CELERY_TASK_ALWAYS_EAGER}
    if ar.ready():  # eager(동기 폴백)면 즉시 ready → 결과 포함
        out["result"] = ar.result if ar.successful() else None
    return out


@router.get("/analyze/task/{task_id}", dependencies=[Depends(require_token)])
def analyze_task_status(task_id: str) -> dict:
    """비동기 태스크 상태/결과 조회(운영 worker+backend 시). eager는 backend 없어 POST에 결과 포함."""
    from app.tasks.celery_app import celery_app
    res = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": res.status, "ready": res.ready(),
            "result": res.result if res.ready() and res.successful() else None}
