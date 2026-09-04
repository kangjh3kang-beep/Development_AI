"""F-Parcel 배치 계약(Contracts).

배치 잡의 입력(BatchInput), 필지별 결과(BatchItemResult), 집계(BatchAggregate),
잡 상태(ParcelBatchJob), 폴링 응답(BatchResult)을 pydantic v2 모델로 정의한다.

핵심 불변식(INV)을 데이터 모양으로 강제한다:
- 부분성 1급(INV-M2): counts에 not_found/ambiguous/error 칸을 항상 둔다.
- 완결성 신호(INV-M4): completeness + pending 목록을 항상 노출한다.
- 집계 완결성(INV-M5): aggregate.held=True 면 union/면적을 노출하지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ItemStatus(StrEnum):
    """필지 한 건의 해석 상태."""

    CONFIRMED = "confirmed"      # PNU·면적 등 핵심 정보 확정
    AMBIGUOUS = "ambiguous"      # 주소만 있어 지오코딩/보정이 필요(애매)
    NOT_FOUND = "not_found"      # 외부 데이터에서 필지를 찾지 못함
    ERROR = "error"             # 처리 중 예외


class Completeness(StrEnum):
    """배치 전체의 완결성. COMPLETE 이전에는 최종 분석을 하면 안 된다(INV-M4)."""

    PARTIAL = "partial"
    COMPLETE = "complete"


class JobState(StrEnum):
    """배치 잡의 상태기계."""

    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"      # 처리 끝났으나 일부 미확정(부분 성공)
    COMPLETE = "complete"    # 모든 필지 CONFIRMED
    FAILED = "failed"        # 실행 중 예외로 종료(BatchService.run이 저장 — 사유는 BatchResult.error)
    CANCELLED = "cancelled"
    EXPIRED = "expired"      # ★미구현: TTL 스윕 배치가 없어 이 상태로 전이되는 경로가 아직 없다(스코프 제한).


class BatchInput(BaseModel):
    """배치 입력 — 아래 4가지 중 정확히 하나만 지정한다.

    - pnu_list: PNU(19자리) 목록을 직접 지정.
    - polygon: GeoJSON 폴리곤(이 영역에 걸치는 필지를 찾는다).
    - bbox: (min_lon, min_lat, max_lon, max_lat) 사각 영역.
    - admin_code: 행정구역 법정동코드(bcode). ※직접 필지목록 API 없음 → 정직 degrade.
    - district_code: 지구단위계획 구역코드. ※동일하게 degrade.
    - center_address: 중심 주소(지오코딩) + radius_m 반경 → 사각 영역 필지. (실용 구역 선택)
    """

    pnu_list: list[str] | None = None
    polygon: dict[str, Any] | None = None
    bbox: tuple[float, float, float, float] | None = None
    admin_code: str | None = None
    district_code: str | None = None
    center_address: str | None = None
    radius_m: int | None = None  # center_address 보조(기본 500m) — 단독 모드 아님

    @model_validator(mode="after")
    def _exactly_one(self) -> BatchInput:
        """택1 검증 — 입력 모드 중 정확히 하나만 지정(radius_m은 center_address 보조라 제외)."""
        provided = [
            f for f in ("pnu_list", "polygon", "bbox", "admin_code", "district_code", "center_address")
            if getattr(self, f) not in (None, [], (), "")
        ]
        if len(provided) != 1:
            raise ValueError(
                "BatchInput 은 pnu_list/polygon/bbox/admin_code/district_code/center_address 중 "
                f"정확히 하나만 지정해야 합니다(지정됨: {provided})."
            )
        return self

    def normalized(self) -> dict[str, Any]:
        """멱등키 산출용 정규화 딕셔너리(키 순서·표현 고정)."""
        out: dict[str, Any] = {}
        if self.pnu_list is not None:
            # 정렬해 순서에 무관하게 같은 키가 나오도록 한다.
            out["pnu_list"] = sorted(str(p) for p in self.pnu_list)
        if self.polygon is not None:
            out["polygon"] = self.polygon
        if self.bbox is not None:
            out["bbox"] = [round(float(x), 9) for x in self.bbox]
        if self.admin_code is not None:
            out["admin_code"] = str(self.admin_code)
        if self.district_code is not None:
            out["district_code"] = str(self.district_code)
        if self.center_address is not None:
            out["center_address"] = str(self.center_address)
            out["radius_m"] = int(self.radius_m or 500)
        return out


class BatchItemResult(BaseModel):
    """필지 한 건의 처리 결과."""

    pnu: str
    status: ItemStatus
    address: str | None = None
    area_sqm: float | None = None
    record_ref: dict[str, Any] | None = None   # 원천 레코드/메타 참조
    reason: str | None = None                   # 미확정/에러 사유(정직 표기)


class BatchCounts(BaseModel):
    """상태별 집계 카운트(부분성 1급)."""

    total: int = 0
    confirmed: int = 0
    ambiguous: int = 0
    not_found: int = 0
    error: int = 0

    @classmethod
    def from_items(cls, items: list[BatchItemResult]) -> BatchCounts:
        """필지 결과 목록에서 카운트를 계산한다."""
        c = cls(total=len(items))
        for it in items:
            if it.status == ItemStatus.CONFIRMED:
                c.confirmed += 1
            elif it.status == ItemStatus.AMBIGUOUS:
                c.ambiguous += 1
            elif it.status == ItemStatus.NOT_FOUND:
                c.not_found += 1
            elif it.status == ItemStatus.ERROR:
                c.error += 1
        return c


class BatchAggregate(BaseModel):
    """집계 결과 — 모든 필지 CONFIRMED 일 때만 채워진다(INV-M5).

    미확정 필지가 하나라도 있으면 held=True 로 두고 union/면적/관할을 노출하지 않는다
    (부분 집계의 오해를 막기 위한 보류 신호).
    """

    union_boundary: dict[str, Any] | None = None   # GeoJSON
    total_area_sqm: float | None = None
    jurisdiction_flags: dict[str, Any] | None = None
    held: bool = False


class ParcelBatchJob(BaseModel):
    """배치 잡(헤더). 진행 상태와 카운트를 담는다."""

    id: str
    snapshot_id: str
    state: JobState
    region_input: dict[str, Any]
    completeness: Completeness = Completeness.PARTIAL
    counts: BatchCounts = Field(default_factory=BatchCounts)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchResult(BaseModel):
    """폴링 응답 — 페이지네이션된 필지 결과 + 집계 + 미처리 목록."""

    job_id: str
    state: JobState
    completeness: Completeness
    counts: BatchCounts
    items: list[BatchItemResult]
    aggregate: BatchAggregate
    pending: list[str] = Field(default_factory=list)   # 미처리/미확정 pnu 목록(INV-M4)
    error: str | None = None            # state=failed 일 때 실패 사유(정직 보존, 500자 캡)
    outliers: list[dict[str, Any]] = Field(default_factory=list)  # 신뢰루프: 면적 이상치 필지(검토 권고)
    fee_per_unit_krw: float = 0.0       # 필지당 단가(관리자 설정·미설정 0=무료)
    estimated_fee_krw: float = 0.0      # 예상 사용료 = 단가 × 확정 필지수(0=무료)
    region_geo: dict[str, Any] | None = None  # 지도 미리보기용 {center,bbox,radius_m}
    page: int = 1
    size: int = 500
    has_next: bool = False
