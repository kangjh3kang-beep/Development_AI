"""L3-B — 공학 시뮬 지표 계약. 모든 지표는 method_trace(모델/가정/입력) 동반(INV-19).

필수 입력 결손 → status=UNAVAILABLE(무음 추정 금지, INV-21). emit가 근거 없는 값 출력 차단.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.core.errors import MethodTraceMissing


class MetricStatus(str, Enum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"  # 필수 입력 결손 — 확인 불가
    HELD = "HELD"


class MethodTrace(BaseModel):
    """시뮬 지표의 근거 — 사용 모델 + 가정 + 입력."""

    model: str
    assumptions: list[str] = Field(default_factory=list)
    inputs: dict = Field(default_factory=dict)
    basis_article: str | None = None


class SimMetric(BaseModel):
    metric_id: str
    value: float | None = None
    unit: str = ""
    status: MetricStatus = MetricStatus.OK
    confidence: float = 1.0
    method_trace: MethodTrace | None = None
    flags: list[str] = Field(default_factory=list)
    required: float | None = None  # 기준값(회전반경/기준시간 등)


def emit(metric: SimMetric) -> SimMetric:
    """출력 게이트 — 값 보유 지표에 method_trace 부재 시 거부(INV-19)."""
    if metric.value is not None and metric.method_trace is None:
        raise MethodTraceMissing(f"sim metric '{metric.metric_id}' has value without method_trace")
    return metric
