"""R0.5 — 시트역할 계약(L0.5). 3원 합의(분류기/표제란/내용)로만 role 확정(INV-8).

불합의 시트는 isolated=True로 격리(하류 라우팅 제외). 신호별 판정은 provenance에 보존.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.contracts._types import Probability


class SheetRole(str, Enum):
    """도면 시트 역할(고정 enum)."""

    SITE = "SITE"
    PLAN = "PLAN"
    ELEVATION = "ELEVATION"
    SECTION = "SECTION"
    AREA_TABLE = "AREA_TABLE"
    PARKING = "PARKING"
    SUNLIGHT = "SUNLIGHT"
    DISTRICT_UNIT = "DISTRICT_UNIT"


class SheetRoleAssignment(BaseModel):
    """시트 1장의 역할 확정 결과."""

    sheet_id: str
    role: SheetRole | None = None
    isolated: bool = False
    method: list[str] = Field(default_factory=list)  # 기여 신호(CLASSIFIER/TITLEBLOCK/CONTENT)
    confidence: Probability = 0.0
    flags: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)  # 신호별 원시 판정
