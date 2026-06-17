"""R0 — Preflight 계약(관할/기준일/축척 → PreflightContext).

복수 용도지역은 zones[]로 보존(단일값 가정 금지, INV-2). 미확정 항목은 assumed로 전파.
컨텍스트에는 비결정 필드(타임스탬프 등)를 두지 않아 동일 입력+스냅샷 재현을 보장(INV-7).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.contracts._types import Probability
from app.contracts.enums import JurisdictionSource, ScaleSource


class Zone(BaseModel):
    """용도지역/지구 1건(면적비 보존)."""

    zone_code: str
    area_ratio: Probability | None = None


class JurisdictionContext(BaseModel):
    """관할 해석 결과. 복수 zone 시 stricter_applied=True(더 엄격기준 플래그)."""

    pnu: str
    sido_code: str | None = None
    sigungu_code: str | None = None
    zones: list[Zone] = Field(default_factory=list)
    stricter_applied: bool = False
    source: JurisdictionSource
    assumed: bool = False
    blocked: bool = False


class BaseDateResult(BaseModel):
    """기준일(effective_date) 확정 결과."""

    effective_date: date | None = None
    assumed: bool = False


class ScaleResult(BaseModel):
    """축척/단위 확정 결과(분모 = 1:N의 N)."""

    scale_denominator: float | None = None
    source: ScaleSource | None = None
    assumed: bool = False


class PreflightContext(BaseModel):
    """Preflight 게이트가 잠근 통합 컨텍스트. 후속 계층에 그대로 전파."""

    pnu: str
    snapshot_id: str
    input_hash: str
    jurisdiction: JurisdictionContext
    base_date: BaseDateResult
    scale: ScaleResult
    blocked: bool = False
    assumed_fields: list[str] = Field(default_factory=list)
