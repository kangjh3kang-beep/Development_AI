"""표준설계 참조 라이브러리 API(P7 + U3 템플릿 조립).

관리자(총괄관리자)만 도면 사례 업로드/삭제/기하 부착. 목록·유사검색·조립·
플랫폼 설계 저장은 로그인 사용자.
  POST   /design-references               (admin) 도면 파일 + 메타 업로드
  GET    /design-references               목록(용도 필터)
  GET    /design-references/similar       유사 사례 Top-K(결정론 메타 스코어, zone_code 옵션=v2)
  POST   /design-references/from-design   (로그인) 플랫폼 설계를 참조 사례로 저장(source=platform)
  POST   /design-references/{id}/assemble (로그인) 참조 기하를 대상 스펙에 조립(U3)
  POST   /design-references/{id}/geometry (admin) DXF 업로드 → 표준 기하 부착
  DELETE /design-references/{id}          (admin) 삭제
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing.billing_service import is_super_admin
from app.services.cad import design_reference_geometry as geo
from app.services.cad import design_reference_service as svc
from app.services.cad import template_assembly_service as assembly
from app.services.cad.design_spec import DesignSpec
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from apps.api.services.storage_service import (
    ContentRejectedError,
    StorageError,
    upload_design_file,
)

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
            except ContentRejectedError as exc:
                # ★리뷰 필수 #2: 콘텐츠 검증 거부(위장/bomb/실행파일 등)는 클라이언트 귀책 4xx —
                # 인프라 장애(502)와 구분해 자동재시도·오탐 알림을 막는다.
                raise HTTPException(
                    status_code=exc.http_status, detail=f"업로드가 거부되었습니다: {exc.reason}"
                ) from exc
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
    zone_code: str | None = Query(None, description="용도지역 코드 — 지정 시 법규 인지 v2 스코어 정렬"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """유사 사례 Top-K — 설계 생성 시 '사례 참고'로 사용.

    zone_code 미지정 시 기존 v1 동작 그대로(하위호환), 지정 시 similarity_v2
    (용도25+면적20+평형15+지역군10+법규적합20+footprint10) 기준 정렬.
    응답 항목엔 similarity_v2/similarity_breakdown이 additive로 항상 포함된다.
    """
    types = [t.strip() for t in (unit_types or "").split(",") if t.strip()]
    return {"items": await svc.find_similar(db, building_use=building_use, area_sqm=area_sqm,
                                            unit_types=types, k=k, zone_code=zone_code)}


# ── U3: 템플릿 조립 — 요청 스키마 ──

class AssembleRequest(BaseModel):
    """참조 기하 조립 요청 — 대상 설계 스펙(SSOT DesignSpec 그대로)."""

    spec: DesignSpec


class FromDesignRequest(BaseModel):
    """플랫폼 설계 결과를 참조 사례로 저장하는 요청(source=platform)."""

    title: str = Field(min_length=1, max_length=120)
    design_payload: dict[str, Any]
    summary: dict[str, Any] | None = None
    spec: dict[str, Any] | None = None
    building_use: str | None = None
    zone_code: str | None = None
    area_sqm: float | None = None
    total_units: int | None = None
    floors: int | None = None
    unit_types: list[str] = Field(default_factory=list)
    note: str | None = None
    design_version_id: str | None = None


def _opt_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@router.post("/from-design")
async def save_from_design(
    req: FromDesignRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """플랫폼 설계(design_payload)를 표준 기하로 정규화해 참조 사례로 저장(로그인).

    메타 미지정 항목은 동봉된 spec/summary의 실값으로만 보충한다(가짜값 금지).
    """
    try:
        geometry = geo.normalize_geometry(req.design_payload)
    except geo.GeometryError as exc:
        raise HTTPException(status_code=422, detail=f"설계 기하 정규화 실패: {exc}") from exc
    thumb = geo.thumbnail_svg(geometry)

    spec = req.spec or {}
    summary = req.summary or {}
    return await svc.add_reference(
        db, user_id=current.user_id, title=req.title,
        building_use=req.building_use or spec.get("building_use"),
        zone_code=req.zone_code or spec.get("zone_code"),
        area_sqm=req.area_sqm if req.area_sqm is not None else spec.get("site_area_sqm"),
        total_units=(req.total_units if req.total_units is not None
                     else _opt_int(summary.get("total_units"))),
        floors=(req.floors if req.floors is not None
                else _opt_int(summary.get("num_floors"))),
        unit_types=req.unit_types or list(spec.get("target_unit_types") or []),
        file_url=None, file_type=None, source="platform", note=req.note,
        geometry_json=geometry, design_spec_json=req.spec, summary_json=req.summary,
        geometry_source="platform", design_version_id=req.design_version_id,
        thumbnail_svg=thumb,
    )


@router.post("/{ref_id}/assemble")
async def assemble_reference(
    ref_id: str,
    req: AssembleRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """참조 기하를 대상 스펙에 조립(로그인) — 균등 스케일·회전·층수 클램프 + 법규 재검증.

    응답: {design_payload, summary(재계산), violations, passed, adaptations, reference}.
    passed=False면 법규 위반 — 프론트는 적용 차단·사유 표시에 사용한다.
    """
    ref = await svc.get_reference(db, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="설계 사례를 찾을 수 없습니다.")
    try:
        return assembly.assemble_from_reference(ref, req.spec)
    except (geo.GeometryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{ref_id}/geometry")
async def upload_reference_geometry(
    ref_id: str,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DXF 업로드 → 표준 기하 추출·부착(관리자). 파싱 실패는 422(가짜 기하 금지).

    ★정직 한계 표기: 이 경로는 아직 content_inspection(WP-H)에 결선되지 않았다(관리자 전용·
    버킷 영속 없이 DXF 파싱만 수행해 즉시위험이 낮다고 판단해 이번 세션 스코프에서 제외).
    ezdxf 파싱 실패는 422 로 거부되나, zip bomb·MIME 위장 등 별도 검증은 세션2 전역 스윕 대상.
    """
    await _require_admin(current, db)
    ref = await svc.get_reference(db, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="설계 사례를 찾을 수 없습니다.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="빈 파일입니다.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다(최대 25MB).")
    try:
        geometry = geo.dxf_to_geometry(data)
    except geo.GeometryError as exc:
        raise HTTPException(status_code=422, detail=f"DXF 기하 추출 실패: {exc}") from exc
    thumb = geo.thumbnail_svg(geometry)
    await svc.set_geometry(db, ref_id, geometry_json=geometry,
                           geometry_source="dxf", thumbnail_svg=thumb)
    return {"ok": True, "id": ref_id, "geometry_source": "dxf",
            "point_count": len(geometry.get("points", [])),
            "surface_count": len(geometry.get("surfaces", [])),
            "has_thumbnail": thumb is not None}


@router.delete("/{ref_id}")
async def delete_reference(
    ref_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_admin(current, db)
    return await svc.delete_reference(db, ref_id)
