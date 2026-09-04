"""프로젝트 소유권(tenant) 검증 표준 계약 — IDOR(권한없는 객체참조) 방지 공용 헬퍼.

★전역 전파방지: 요청 body/쿼리의 project_id로 데이터를 조회/변조하는 엔드포인트가 임의 프로젝트를
넘볼 수 없게, "그 프로젝트가 요청자 tenant 소유인가"를 단일 계약으로 검사한다. design_v61의
_assert_project_owned를 표준 헬퍼로 추출해 한 곳(여기)만 고치면 전역이 따라오게 한다.

사용:
    from apps.api.database.session import get_db
    from app.services.auth.auth_service import get_current_user
    from app.services.auth.project_ownership import assert_project_owned

    @router.post("/from-project")
    async def handler(req, db=Depends(get_db), user=Depends(get_current_user)):
        await assert_project_owned(req.project_id, db, user)   # tenant 불일치 → 403
        ...
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def assert_project_owned(project_id: str, db: AsyncSession, user: Any) -> str | None:
    """project_id의 tenant 소유권을 검사한다.

    반환:
    - project_id가 UUID가 아니면(데모/임시 ID) None — 소유권 검사 생략(graceful echo 경로).
    - UUID이고 프로젝트가 존재하면 그 tenant_id(str). user.tenant_id와 불일치면 403.
    - UUID이나 프로젝트 행이 없으면 None — 호출부가 "프로젝트없음" graceful 처리.

    ★가짜 통과 금지: 소유 tenant가 분명히 다르면 403으로 거부한다(무인증/타테넌트 접근 차단).
    """
    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return None  # 비UUID — 소유권 검사 불가(데모 경로)

    row = (await db.execute(
        text("SELECT tenant_id FROM projects WHERE id = :pid"), {"pid": str(pid)}
    )).first()
    if row is None:
        return None  # 프로젝트 없음 — 호출부가 정직 처리
    owner_tenant = str(row[0]) if row[0] is not None else None
    if owner_tenant is not None and str(getattr(user, "tenant_id", "")) != owner_tenant:
        raise HTTPException(status_code=403, detail="해당 프로젝트에 대한 권한이 없습니다")
    return owner_tenant
