"""전문가 패널 분석 라우터 — 다관점 분석·토론·검증."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.billing_deps import enforce_llm_quota
from app.services.expert_panel.expert_panel_service import ExpertPanelService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter(prefix="/expert-panel", tags=["전문가 패널"])


class ExpertPanelRequest(BaseModel):
    analysis_type: str = Field(description="permit|regulation|market|feasibility|site")
    context: dict[str, Any] | str = Field(default_factory=dict, description="분석 결과/맥락")
    address: str = ""
    mode: str = "single"  # single | deep(정밀 다중 에이전트)


@router.post("/analyze", summary="전문가 패널 다관점 분석·검증", dependencies=[Depends(enforce_llm_quota)])
async def analyze_panel(
    req: ExpertPanelRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """분석유형별 관련 전문가 관점에서 분석·토론하고 통합 결론·검증을 제시한다."""
    if not req.context:
        raise HTTPException(status_code=400, detail="분석 맥락(context)이 필요합니다.")
    mode = "deep" if req.mode == "deep" else "single"
    result = await ExpertPanelService().analyze(
        analysis_type=req.analysis_type, context=req.context, address=req.address, mode=mode
    )

    # 표준 근거 블록(#5): 패널이 실제 산출한 검증 신뢰도·참여 전문가 수 등 집계값만
    # items로 가산(graceful·무목업). 폴백(generated=False)이거나 신뢰도 미산출이면 부착 안 함.
    if isinstance(result, dict) and result.get("generated"):
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            verification = result.get("verification") or {}
            experts = result.get("experts") or []
            roster = result.get("roster") or []
            ev_items: list[dict] = []

            # 검증 신뢰도(패널이 산출한 0~100 정수) — 실제 값이 있을 때만
            if verification.get("confidence") is not None:
                ev_items.append({
                    "label": "패널 검증 신뢰도",
                    "value": verification.get("confidence"),
                    "basis": "다관점 전문가 검토·통합 후 산출(0~100, LLM 패널)",
                })
            # 참여 전문가 수(실제 의견을 낸 전문가)
            if experts:
                ev_items.append({
                    "label": "참여 전문가",
                    "value": f"{len(experts)}명 ({', '.join(roster) if roster else ''})",
                    "basis": f"분석유형 '{result.get('analysis_type', '')}' 전문가 로스터 다관점 분석",
                })
            # 식별 리스크 수(검증 단계 산출)
            risks = verification.get("risks") or []
            if risks:
                ev_items.append({
                    "label": "식별 핵심 리스크",
                    "value": f"{len(risks)}건",
                    "basis": "전문가 패널 검증(반론·맹점 포함) 단계 도출",
                })

            if ev_items:
                result["evidence"] = build_evidence_block(
                    items=ev_items,
                    legal_ref_keys=None,  # 분석유형 무관 — 패널 자체는 특정 법령에 종속 안 됨(정직표기)
                )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음.
            pass

    return result
