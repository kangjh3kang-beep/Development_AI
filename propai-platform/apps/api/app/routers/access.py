"""접도·도로 기반(access_basis) 라우터 — 명세 P4 'Statutory Road·Access'.

엔드포인트:
 - POST /api/v1/access/assess : 도로 접근을 legal/physical/emergency 3상태로 분리 판정.

게이트: 인증(get_current_user)만. 규칙기반(LLM 무의존)·법규 판정이라 무과금(enforce_llm_quota 미부착).
정직: 법정 접도 근거 미확보 시 REQUIRES_AUTHORITY_CONFIRMATION로 확정 PASS를 만들지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.access import AccessAssessment, AccessAssessmentRequest
from app.services.auth.auth_service import get_current_user

router = APIRouter(prefix="/access", tags=["접도·도로 기반(P4)"])


@router.post("/assess", response_model=AccessAssessment)
async def assess_access_endpoint(
    req: AccessAssessmentRequest, current_user=Depends(get_current_user)
) -> AccessAssessment:
    """도로 접근(접도) 종합 판정 — 3상태 분리 + 종합 게이트 + 근거계약.

    부지분석 result와 동형 필드(road_side·road_width_m·road_contact·dead_end_road·flag_lot·
    fire_truck_access_width_m 등)를 받아, special_parcel 판정 룰군(§44·도로법·소방)과 토지이음
    접도요건을 재사용·합성한다. 값이 미상인 항목은 정직하게 강등(날조·낙관 폴백 금지).
    """
    from app.services.access.access_basis_service import assess_access

    # extra='allow'로 부지분석 result의 추가 필드까지 통과 소비.
    return assess_access(req.model_dump(exclude_none=False))
