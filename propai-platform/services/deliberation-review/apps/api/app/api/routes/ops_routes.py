"""운영 라우트 — GET /api/v1/doctor: 통합 상태(어댑터 live/mock, 키 보유 여부). 키 값 비노출.

★보안: doctor는 어떤 외부 키를 보유했는지(핑거프린트)를 드러내므로 analyze와 동일한 베어러 토큰을
요구한다(require_token). API_TOKEN 미설정(dev)이면 개방, 설정 시 'Bearer <token>' 일치 필요.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_token
from app.services.ops.integration_status import integration_status

router = APIRouter(prefix="/api/v1", tags=["ops"])


@router.get("/doctor", dependencies=[Depends(require_token)])
def doctor() -> dict:
    return {"status": "ok", "integrations": integration_status()}
