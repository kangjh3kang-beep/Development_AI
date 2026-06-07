"""수지분석 v2 Pydantic 스키마 — 요청/응답 모델."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── 요청 ──

class FeasibilityCalculateRequest(BaseModel):
    """수지분석 계산 요청."""
    development_type: str = Field(..., description="M01~M15")
    project_name: str = ""
    total_land_area_sqm: float = Field(gt=0)
    land_category: str = "land"
    official_price_per_sqm: float = 0
    price_multiplier: float = 1.0
    total_gfa_sqm: float = Field(gt=0)
    building_type: str = "apartment"
    total_households: int = 0
    avg_sale_price_per_pyeong: float = 0
    avg_area_pyeong: float = 0
    sale_ratio: float = Field(ge=0, le=1, default=1.0)
    bridge_amount_won: int = 0
    pf_amount_won: int = 0
    midpay_amount_won: int = 0
    sido_name: str = ""
    sigungu_name: str = ""
    project_months: int = 48
    discount_rate: float = 0.08
    equity_won: int = 0
    params: dict[str, Any] = {}
    use_llm: bool = True  # AI 내러티브(수지 해석) 포함 여부(사용자 선택). /calculate는 규칙기반이라 무영향.


class FeasibilityMultiRequest(BaseModel):
    """복수 수지분석 비교 요청."""
    projects: list[FeasibilityCalculateRequest]


class MonteCarloRequest(BaseModel):
    """몬테카를로 시뮬레이션 요청."""
    variables: list[dict[str, Any]] = Field(
        ..., description="[{name, mean, std, distribution?}]"
    )
    n_simulations: int = Field(default=10_000, ge=100, le=100_000)
    seed: Optional[int] = 42


class OptimizationRequest(BaseModel):
    """최적화 요청."""
    variables: dict[str, list[float]] = Field(
        ..., description="{name: [initial, min, max]}"
    )
    objective: str = "max_profit"
    max_iter: int = 200


class TaxCalculateAllRequest(BaseModel):
    """38종 세금 일괄 계산 요청."""
    purchase_won: int = 0
    land_category: str = "land"
    house_count: int = 0
    is_adjusted: bool = False
    area_sqm: float = 0
    official_price_per_sqm: float = 0
    sido_name: str = ""
    sigungu_name: str = ""
    total_households: int = 0
    total_sale_amount_won: int = 0
    total_gfa_sqm: float = 0
    building_type: str = "apartment"
    total_units: int = 0
    avg_area_sqm: float = 85.0


class VCSCommitRequest(BaseModel):
    """버전관리 커밋 요청."""
    message: str
    snapshot: dict[str, Any]


class VCSRollbackRequest(BaseModel):
    """롤백 요청."""
    target_sha: str


# ── 응답 ──

class FeasibilityResultResponse(BaseModel):
    """수지분석 결과 응답."""
    development_type: str
    module_name: str
    total_revenue_won: int
    total_cost_won: int
    net_profit_won: int
    profit_rate_pct: float
    roi_pct: float
    npv_won: int
    grade: str
    cost_breakdown_won: dict[str, int] = {}
    tax_detail: dict[str, Any] = {}
    special_detail: dict[str, Any] = {}


class FeasibilityMultiResponse(BaseModel):
    """복수 비교 응답."""
    results: list[FeasibilityResultResponse]
    comparison: dict[str, Any] = {}


class MonteCarloResponse(BaseModel):
    """몬테카를로 결과 응답."""
    mean: float
    std: float
    p5: float
    p50: float
    p95: float
    probability_positive: float
    convergence_ratio: float
    n_simulations: int
    histogram: list[dict[str, Any]] = []


class TaxResultResponse(BaseModel):
    """세금 결과 응답."""
    grand_total_won: int
    total_items_count: int
    summary_by_stage: dict[str, int]
    acquisition: dict[str, Any] = {}
    construction: dict[str, Any] = {}
    sale: dict[str, Any] = {}
    disposal: dict[str, Any] = {}


class ModuleListResponse(BaseModel):
    """모듈 목록 응답."""
    modules: list[dict[str, str]]


class RecommendationResponse(BaseModel):
    """AI 권고 응답."""
    recommendations: list[dict[str, Any]]
