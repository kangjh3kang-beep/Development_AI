"""측량·좌표 계약(CoordinateContract) 라우터 — DXF↔GIS 좌표 정합 검증.

엔드포인트:
 - POST /api/v1/survey/coordinate/contract   : 기준점(≥3)으로 좌표 계약 산출(RMSE·상태).
 - POST /api/v1/survey/coordinate/reconcile  : DXF 경계(직접 링 or base64 DXF) ↔ 지적경계 종합 대조.

게이트: 왕복·기준점·면적차/중첩률 중 하나라도 공차를 넘거나 못 재면 상태를
FIELD_VERIFICATION_REQUIRED(현장 확인 필요)로 정직하게 강등한다(가짜 통과 금지).
DB 변경 없음 — 계산·리포트 전용. 인증(get_current_user) 필요.
"""
from __future__ import annotations

import base64

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth.auth_service import get_current_user
from app.services.survey.coordinate_contract import (
    ControlPoint,
    CoordinateContract,
    ReconcileReport,
    ToleranceTable,
)
from app.services.survey.coordinate_service import (
    build_coordinate_contract,
    extract_dxf_boundary_ring,
    reconcile_report,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/survey/coordinate", tags=["측량·좌표 계약"])

Point = tuple[float, float]

# base64 DXF 입력 길이 상한(약 20MB) — 디코드·파싱 전 조기 거부용(대형 입력 DoS 방어).
_MAX_DXF_B64_LEN = 20 * 1024 * 1024


class ContractRequest(BaseModel):
    """좌표 계약 요청 — 같은 지점을 두 좌표계에서 잰 기준점 3점 이상."""

    control_points: list[ControlPoint] = Field(..., description="기준점(≥3)")
    source_srid: int = Field(..., description="원본 SRID(예: 4326)")
    target_srid: int = Field(..., description="목표 SRID(예: 5186 지적 중부원점)")
    tolerances: ToleranceTable | None = Field(None, description="공차표 덮어쓰기(미지정 시 A6 기본)")


class ReconcileRequest(BaseModel):
    """지적경계 종합 대조 요청.

    dxf_ring 을 직접 주거나 dxf_base64(업로드 DXF)를 주면 경계 링을 자동 추출한다.
    """

    control_points: list[ControlPoint] = Field(default_factory=list, description="기준점(≥3 권장)")
    reference_ring: list[Point] = Field(..., description="기준(지적) 경계 좌표 링")
    reference_srid: int = Field(..., description="기준 경계 SRID(예: 4326)")
    dxf_ring: list[Point] | None = Field(None, description="DXF 경계 좌표 링(지적계 미터)")
    dxf_base64: str | None = Field(None, description="업로드 DXF(base64) — dxf_ring 미지정 시 자동 추출")
    dxf_srid: int = Field(..., description="DXF 경계 SRID(예: 5186)")
    source_srid: int | None = Field(None, description="계약·왕복 검증 원본 SRID(기본=reference_srid)")
    target_srid: int | None = Field(None, description="계약·왕복 검증 목표 SRID(기본=dxf_srid)")
    tolerances: ToleranceTable | None = Field(None, description="공차표 덮어쓰기(미지정 시 A6 기본)")
    dxf_precision_mm: float = Field(0.0, ge=0, description="DXF 저장 격자(mm) — 왕복 절단오차 모사")


@router.post("/contract", response_model=CoordinateContract)
async def create_contract(
    req: ContractRequest,
    user: dict = Depends(get_current_user),
) -> CoordinateContract:
    """기준점으로 좌표 계약을 산출한다(RMSE·transform_trace·상태)."""
    return build_coordinate_contract(
        req.control_points, req.source_srid, req.target_srid, req.tolerances
    )


@router.post("/reconcile", response_model=ReconcileReport)
async def reconcile(
    req: ReconcileRequest,
    user: dict = Depends(get_current_user),
) -> ReconcileReport:
    """DXF 경계 ↔ 지적경계 종합 대조 리포트를 산출한다.

    dxf_ring 이 없고 dxf_base64 가 있으면 업로드 DXF 에서 경계 링을 뽑는다(미검출 시 빈 링).
    """
    dxf_ring = req.dxf_ring
    if dxf_ring is None and req.dxf_base64:
        # 대형 base64 입력 DoS 방어 스톱갭 — 디코드/임시파일/파싱 전에 길이로 조기 거부.
        # (매직바이트·아카이브 한도 등 완전한 콘텐츠 보안은 WP-H 전담)
        if len(req.dxf_base64) > _MAX_DXF_B64_LEN:
            raise HTTPException(
                status_code=413,
                detail="DXF가 너무 큽니다(base64 20MB 초과) — 파일을 줄여 다시 시도하세요.",
            )
        try:
            dxf_bytes = base64.b64decode(req.dxf_base64)
        except Exception:  # noqa: BLE001
            dxf_bytes = b""
        dxf_ring = extract_dxf_boundary_ring(dxf_bytes) or []
    if dxf_ring is None:
        dxf_ring = []

    return reconcile_report(
        control_points=req.control_points,
        reference_ring=[(float(x), float(y)) for x, y in req.reference_ring],
        reference_srid=req.reference_srid,
        dxf_ring=[(float(x), float(y)) for x, y in dxf_ring],
        dxf_srid=req.dxf_srid,
        source_srid=req.source_srid,
        target_srid=req.target_srid,
        tolerances=req.tolerances,
        dxf_precision_mm=req.dxf_precision_mm,
    )
