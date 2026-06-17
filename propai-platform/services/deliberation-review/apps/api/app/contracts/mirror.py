"""R2 — versioned 미러 계약. 소비측은 이 미러만 읽는다(INV-13). MirrorSnapshot은 불변.

미수집 관할은 RulesetLoad.degraded로 비차단 표면화(INV-15). HarvestJob은 공급측 비동기 수집 요청.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MirrorSnapshot(BaseModel):
    """승인(ACTIVE) 룰만 적재된 불변 미러. snapshot_id로 R1.5/R3과 정합.

    frozen — 소비측이 속성 재할당으로 미러를 변경할 수 없다(INV-13 immutability).
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    jurisdiction: str
    version: str = "v1"
    rules: list[dict] = Field(default_factory=list)
    active_candidate_ids: list[str] = Field(default_factory=list)


class RulesetLoad(BaseModel):
    """소비측 미러 로드 결과. 미수집 시 degraded+eta(비차단)."""

    jurisdiction: str
    degraded: bool = False
    blocked: bool = False
    eta: int | None = None  # 영업일
    standard_level: str | None = None  # degraded 시 상위표준(national 등)
    snapshot: MirrorSnapshot | None = None


class HarvestJob(BaseModel):
    """공급측 수집 요청(비동기). 소비 경로를 차단하지 않음."""

    jurisdiction: str
    status: str = "ENQUEUED"
