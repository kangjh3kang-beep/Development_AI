"""사용자별 프로젝트/분석 영속 저장소 (기기 무관 동기화).

프론트의 localStorage(zustand) 상태(프로젝트 목록 + 프로젝트별 분석 스냅샷)를
사용자 계정에 JSON으로 보관해 다른 기기/브라우저에서도 불러올 수 있게 한다.

ORM 이원 레지스트리 문제를 피하기 위해 raw SQL(text())로 단순 KV 업서트.
테이블: user_project_store(user_id uuid pk, data jsonb, updated_at timestamptz)
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/store", tags=["사용자 저장소"])


class StorePutRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict, description="프로젝트/스냅샷 JSON")


@router.get("/projects", summary="내 프로젝트/분석 동기화 데이터 조회")
async def get_store(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = (await db.execute(
        text("SELECT data FROM user_project_store WHERE user_id = :uid"),
        {"uid": str(current_user.user_id)},
    )).first()
    if not row or row[0] is None:
        return {"data": {}}
    data = row[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:  # noqa: BLE001
            data = {}
    return {"data": data}


@router.put("/projects", summary="내 프로젝트/분석 동기화 데이터 저장")
async def put_store(
    body: StorePutRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await db.execute(
        text(
            "INSERT INTO user_project_store (user_id, data, updated_at) "
            "VALUES (:uid, CAST(:data AS jsonb), now()) "
            "ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()"
        ),
        {"uid": str(current_user.user_id), "data": json.dumps(body.data, ensure_ascii=False)},
    )
    await db.commit()
    return {"status": "ok"}
