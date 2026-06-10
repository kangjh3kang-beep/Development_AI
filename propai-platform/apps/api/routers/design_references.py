"""표준설계 참조 라이브러리 API(P7).

관리자(총괄관리자)만 도면 사례 업로드/삭제. 목록·유사검색은 로그인 사용자 열람.
  POST   /design-references          (admin) 도면 파일 + 메타 업로드
  GET    /design-references          목록(용도 필터)
  GET    /design-references/similar  유사 사례 Top-K(결정론 메타 스코어)
  DELETE /design-references/{id}     (admin) 삭제
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from apps.api.services.storage_service import StorageError, upload_design_file
from app.services.cad import design_reference_service as svc
from app.services.billing.billing_service import is_super_admin

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/design-references", tags=["설계 참조 라이브러리"])

_MAX_BYTES = 25 * 1024 * 1024  # 25MB(도면 PDF/DXF 여유)


async def _require_admin(current: CurrentUser, db: AsyncSession) -> None:
    if not await is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자만 설계 사례를 관리할 수 있습니다.")


@router.post("")
async def upload_reference(
    file: UploadFile | None = File(None),
    title: str = Form(...),
    building_use: str = Form(""),
    zone_code: str = Form(""),
    area_sqm: float | None = Form(None),
    total_units: int | None = Form(None),
    floors: int | None = Form(None),
    unit_types: str = Form(""),  # 콤마구분 또는 JSON 배열
    source: str = Form(""),
    note: str = Form(""),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """도면 사례 업로드(관리자). 파일은 선택(메타만 등록도 허용)."""
    await _require_admin(current, db)

    # unit_types 파싱(JSON 배열 또는 콤마)
    types: list[str] = []
    s = (unit_types or "").strip()
    if s:
        try:
            parsed = json.loads(s)
            types = [str(x).strip() for x in parsed] if isinstance(parsed, list) else []
        except Exception:  # noqa: BLE001
            types = [t.strip() for t in s.split(",") if t.strip()]

    file_url, file_type = None, None
    if file is not None:
        data = await file.read()
        if data:
            if len(data) > _MAX_BYTES:
                raise HTTPException(status_code=413, detail="파일이 너무 큽니다(최대 25MB).")
            try:
                up = await upload_design_file(data, file.content_type or "", file.filename or "")
                file_url, file_type = up["url"], up["file_type"]
            except StorageError as exc:
                raise HTTPException(status_code=502, detail=f"스토리지 업로드 실패: {exc}") from exc

    return await svc.add_reference(
        db, user_id=current.user_id, title=title, building_use=building_use or None,
        zone_code=zone_code or None, area_sqm=area_sqm, total_units=total_units, floors=floors,
        unit_types=types, file_url=file_url, file_type=file_type, source=source or None,
        note=note or None,
    )


@router.get("")
async def list_references(
    building_use: str | None = Query(None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await svc.list_references(db, building_use=building_use)}


@router.get("/similar")
async def similar_references(
    building_use: str | None = Query(None),
    area_sqm: float | None = Query(None),
    unit_types: str = Query(""),
    k: int = Query(5, ge=1, le=20),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """유사 사례 Top-K — 설계 생성 시 '사례 참고'로 사용."""
    types = [t.strip() for t in (unit_types or "").split(",") if t.strip()]
    return {"items": await svc.find_similar(db, building_use=building_use, area_sqm=area_sqm,
                                            unit_types=types, k=k)}


@router.delete("/{ref_id}")
async def delete_reference(
    ref_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_admin(current, db)
    return await svc.delete_reference(db, ref_id)
