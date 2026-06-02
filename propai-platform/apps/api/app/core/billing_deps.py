"""과금 한도 강제 의존성 — LLM 소비 엔드포인트에 적용해 한도 초과 시 402 차단.

비로그인/비구독(metered 아님)은 통과(횟수 제한은 프론트/별도 처리).
미들웨어가 주입한 요청 컨텍스트의 user_id를 사용한다.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.request_context import get_current_user_id
from app.services.billing import billing_service


async def enforce_llm_quota(db: AsyncSession = Depends(get_db)) -> None:
    uid = get_current_user_id()
    if not uid:
        return
    try:
        blocked = await billing_service.is_blocked(db, uid)
    except Exception:  # noqa: BLE001 — 과금 조회 실패 시 서비스는 계속
        return
    if blocked:
        raise HTTPException(
            status_code=402,
            detail="LLM 사용 한도를 초과했습니다. 추가결제 후 계속 이용하실 수 있습니다.",
        )
