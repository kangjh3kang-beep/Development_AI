"""시니어 전문가 에이전트 자문 라우터 — SeniorOrchestrator 노출(결정론).

오케스트레이션 레이어다(senior_agents 코어 재사용·본문 무변경). 결정론 자문이라 무과금
(미설정=무료 원칙·LLM 미사용). 계정격리: get_current_user 필수. LLM 추론·실서비스 심화
배선은 후속(이 API 위에 얹음). 산출은 SeniorConsultation(근거·면허게이트·정직 maturity).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.senior_agents import senior_orchestrator
from app.services.senior_agents.llm_runner import generate_senior_narrative
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/senior", tags=["시니어 전문가 에이전트"])


async def _enforce_llm_if_needed(db: AsyncSession, use_llm: bool) -> None:
    """use_llm=True일 때만 LLM 한도 게이트(미설정=무료·persona 패턴 동일). 무과금 경로는 통과."""
    if not use_llm:
        return
    from app.core.billing_deps import enforce_llm_quota
    await enforce_llm_quota(db)


def _validate_context(v: dict[str, Any] | None) -> dict[str, Any] | None:
    """context.matched_rule_ids 타입 가드(비-리스트/비-문자열 → 422로 정직 거부)."""
    if v is None:
        return v
    m = v.get("matched_rule_ids")
    if m is not None:
        if not isinstance(m, (list, tuple)):
            raise ValueError("context.matched_rule_ids는 문자열 리스트여야 합니다.")
        if not all(isinstance(x, str) for x in m):
            raise ValueError("context.matched_rule_ids 원소는 문자열이어야 합니다.")
    return v


class SeniorConsultRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=64,
                        description="도메인(한/영: 금융·세무·심의·도시계획·설계·BIM·회계) 또는 에이전트 키")
    context: dict[str, Any] | None = Field(
        None, description="신호(data_completeness/rule_fit/rag_strength/correction_rate[0,1]·matched_rule_ids)")
    high_risk: bool | None = Field(None, description="고위험 강제(미지정=도메인 기본)")
    use_llm: bool = Field(False, description="AI 종합 서술(FinCoT narrative) 생성 — 기본 off·무과금, on 시 한도게이트")

    @field_validator("domain")
    @classmethod
    def _strip_domain(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("domain은 빈 문자열일 수 없습니다.")
        return v

    @field_validator("context")
    @classmethod
    def _check_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_context(v)


class SeniorConsultMultiRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=20,
                               description="다도메인(개발사업=도시+금융+설계 등). 중복·미해당 자동 정리")
    context: dict[str, Any] | None = None

    @field_validator("context")
    @classmethod
    def _check_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_context(v)


@router.get("/agents", summary="시니어 에이전트 목록(고위험·성숙도)")
async def list_agents(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"agents": senior_orchestrator.available()}


@router.post("/consult", summary="시니어 자문(단일 도메인·결정론, use_llm 시 AI 서술)")
async def consult(
    req: SeniorConsultRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # use_llm이면 FinCoT 프롬프트 조립 위해 추론 동반 강제(없으면 narrative 생성 불가).
    ctx = dict(req.context or {})
    if req.use_llm:
        ctx["include_reasoning"] = True
    try:
        result = senior_orchestrator.consult(
            req.domain, context=ctx or None, high_risk=req.high_risk)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    out = result.to_dict()
    # AI 서술(use_llm·추론 동반 시): 단일경유 LLM으로 narrative 생성·주입(graceful — 실패 시 결정론 구조 유지).
    # ★빈 분석(irac_steps 0건)은 LLM 호출·과금 생략(서술할 근거 없음). db는 use_llm 경로에서만 실사용.
    reasoning = out.get("reasoning")
    if req.use_llm and isinstance(reasoning, dict) and reasoning.get("prompt") and reasoning.get("irac_steps"):
        await _enforce_llm_if_needed(db, True)
        narrative = await generate_senior_narrative(reasoning["prompt"], use_llm=True)
        if narrative:
            reasoning["narrative"] = narrative
            reasoning["mode"] = "llm"
    return out


@router.post("/consult-multi", summary="시니어 자문(다도메인·중복제거)")
async def consult_multi(
    req: SeniorConsultMultiRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    results = senior_orchestrator.consult_multi(req.domains, context=req.context)
    return {"consultations": [c.to_dict() for c in results]}
