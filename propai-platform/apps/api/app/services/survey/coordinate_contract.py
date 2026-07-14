"""좌표 계약(CoordinateContract) 최소 모델 — 측량·CAD 좌표 정합의 계약서.

무엇을 담나(쉬운 말):
- 어떤 좌표계(SRID)에서 어떤 좌표계로 바꿨는지(source→target),
- 그 변환을 믿을 수 있게 해주는 '기준점(control point)'이 최소 3점 이상 있는지,
- 기준점을 변환했을 때 실제 측정값과 얼마나 어긋나는지(RMSE, mm 단위),
- 변환이 거쳐 간 단계(transform_trace),
- 그리고 이 좌표가 '검증됨(VERIFIED)'인지 '현장 확인 필요(FIELD_VERIFICATION_REQUIRED)'인지.

DB 테이블이 아니라 계산·리포트용 순수 모델이다(마이그레이션 없음).

※ 명세 A6 공차표는 '참조 규범'으로만 채택한다. 파이프라인은 그대로 m(미터) 단위로 돌고,
  공차 검증만 mm(밀리미터)로 환산해서 따진다(전면 mm 전환 아님).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# ── 1mm 내부단위(A6 참조 규범) — 공차는 전부 mm 로 표기·검증한다 ──
INTERNAL_UNIT_MM: float = 1.0


class VerificationStatus(str, Enum):
    """좌표 정합 상태 — 오차가 공차 안이면 VERIFIED, 넘으면 현장 확인 필요, 못 따지면 불가."""

    VERIFIED = "VERIFIED"                                # 공차 이내 — 신뢰 가능
    FIELD_VERIFICATION_REQUIRED = "FIELD_VERIFICATION_REQUIRED"  # 공차 초과 — 현장 실측 필요(정직)
    UNAVAILABLE = "UNAVAILABLE"                          # 변환기 미설치·기준점 부족 등으로 판정 불가


class ToleranceTable(BaseModel):
    """명세 A6 공차표(참조 규범) — 초과하면 FIELD_VERIFICATION_REQUIRED 로 정직 강등.

    기본값은 한국 지적측량 관행에 근거한 합리적 규범값이며 호출측이 덮어쓸 수 있다.
    좌표(위치) 공차는 mm, 면적차·중첩률은 비율(%)·0~1 로 표기한다.
    """

    # 왕복(GIS→DXF→GIS) 재투영 오차 — 좌표계·정밀도가 맞으면 사실상 0 에 수렴해야 한다.
    roundtrip_rmse_mm: float = Field(1.0, gt=0, description="왕복 재투영 RMSE 상한(mm)")
    roundtrip_max_mm: float = Field(5.0, gt=0, description="왕복 재투영 최대 점오차 상한(mm)")
    # 기준점 정합 잔차 — 측량 성과와 도면 좌표의 어긋남 허용치.
    control_point_rmse_mm: float = Field(50.0, gt=0, description="기준점 정합 RMSE 상한(mm)")
    # 지적경계 대조 — 면적 차이와 겹침 비율.
    area_diff_pct: float = Field(3.0, gt=0, description="면적차 허용 상한(%)")
    overlap_ratio_min: float = Field(
        0.98, ge=0, le=1, description="중첩률(IoU) 하한 — 이보다 낮으면 어긋남"
    )


class ControlPoint(BaseModel):
    """기준점 1점 — 같은 지점을 두 좌표계에서 각각 잰 (x,y) 쌍.

    source=원본 좌표계 좌표, target=목표 좌표계 좌표. 변환이 정확하면
    source 를 변환한 값이 target 과 거의 일치해야 한다(그 차이가 잔차).
    """

    name: str = Field(..., description="기준점 이름/번호")
    source: tuple[float, float] = Field(..., description="원본 좌표계 (x,y)")
    target: tuple[float, float] = Field(..., description="목표 좌표계 (x,y)")


class TransformTraceEntry(BaseModel):
    """변환이 거쳐 간 한 단계 — 어디서 어디로, 어떤 방법으로 바꿨는지 남긴다(감사 추적)."""

    step: str = Field(..., description="단계 설명")
    source_srid: int = Field(..., description="입력 SRID")
    target_srid: int = Field(..., description="출력 SRID")
    method: str = Field("pyproj", description="변환 방법(기본 pyproj)")


class CoordinateContract(BaseModel):
    """좌표 계약 — 변환의 신뢰도를 한 장에 요약한 계약서(최소형).

    control_points 는 3점 이상이어야 신뢰(부족하면 status=UNAVAILABLE, rmse_mm=None).
    """

    source_srid: int
    target_srid: int
    control_points: list[ControlPoint] = Field(default_factory=list)
    rmse_mm: float | None = Field(None, description="기준점 정합 RMSE(mm) — 판정 불가 시 None")
    transform_trace: list[TransformTraceEntry] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.UNAVAILABLE
    notes: list[str] = Field(default_factory=list)


class RoundtripResult(BaseModel):
    """왕복(GIS→DXF→GIS) 오차 리포트 — 좌표계·정밀도가 맞는지 되짚어 확인한 결과."""

    point_count: int = 0
    rmse_mm: float | None = None
    max_error_mm: float | None = None
    within_tolerance: bool = False
    dxf_precision_mm: float = Field(
        0.0, description="DXF 저장 격자(mm) — 0=무손실. 실측 도면의 좌표 절단 오차 모사"
    )
    notes: list[str] = Field(default_factory=list)


class BoundaryReconcile(BaseModel):
    """지적경계 대조 — 기준(GIS) 경계와 DXF 경계의 면적차·중첩률(IoU)을 잰 결과."""

    reference_area_sqm: float | None = None
    dxf_area_sqm: float | None = None
    area_diff_pct: float | None = None
    overlap_ratio: float | None = Field(None, description="교집합/합집합(IoU) — 1.0 이면 완전일치")
    computed_in_srid: int | None = Field(None, description="면적·중첩을 계산한 평면 좌표계")
    within_tolerance: bool = False
    notes: list[str] = Field(default_factory=list)


class ReconcileReport(BaseModel):
    """DXF 업로드 → 지적경계 대조 종합 리포트.

    contract(기준점 RMSE)·roundtrip(왕복 오차)·boundary(면적차·중첩률) 세 검증을 묶고,
    하나라도 공차를 넘거나 판정 불가면 status=FIELD_VERIFICATION_REQUIRED(정직 강등).
    field_verification_reasons 에 '왜 현장 확인이 필요한지' 사유를 남긴다(가짜 통과 금지).
    """

    status: VerificationStatus = VerificationStatus.UNAVAILABLE
    tolerances: ToleranceTable = Field(default_factory=ToleranceTable)
    contract: CoordinateContract | None = None
    roundtrip: RoundtripResult | None = None
    boundary: BoundaryReconcile | None = None
    field_verification_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
