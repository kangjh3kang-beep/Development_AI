"""인허가 사례(건축HUB) 라우터.

GET /api/v1/permit-cases?pnu=&kind=&page=&page_size=
PNU 기준 동일 법정동의 주택(hs)·건축(arch) 인허가 사례를 정규화·요약해 반환한다.
산정 로직은 app/services/permit/permit_case_service.py에 있으며 본 라우터는 얇게 위임한다.

원칙: PNU 미해석·키없음·호출실패·무자료 전부 빈 결과 200 + note (가짜 데이터 금지).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.permit_case import PermitCaseResponse
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter()


@router.get(
    "",
    response_model=PermitCaseResponse,
    summary="인허가 사례 조회 — 건축HUB 기본개요(법정동 단위)",
)
async def list_permit_cases(
    pnu: str = Query(..., min_length=10, description="필지고유번호(PNU, 최소 앞 10자리 숫자)"),
    kind: str = Query("arch", pattern="^(arch|hs)$", description="arch=건축인허가, hs=주택인허가"),
    page: int = Query(1, ge=1, description="페이지 번호(1부터)"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기(1~100)"),
    current_user: CurrentUser = Depends(get_current_user),
) -> PermitCaseResponse:
    """PNU의 법정동 기준 인허가 사례 + 분위수 요약을 조회한다.

    - cases: 페이지네이션 적용된 정규화 사례 목록
    - summary/total: 전체 조회분 기준(페이지와 무관)
    - 빈 결과도 200으로 정직 반환(note에 사유 표기)
    """
    from app.services.permit.permit_case_service import PermitCaseService

    result = await PermitCaseService().get_nearby_cases(pnu=pnu.strip(), kind=kind)

    # 페이지네이션은 라우터에서 적용 — summary·total은 전체 조회분 기준 유지
    start = (page - 1) * page_size
    paged = result.cases[start : start + page_size]
    return result.model_copy(update={"cases": paged})
