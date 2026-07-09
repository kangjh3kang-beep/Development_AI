"""수지분석 v2 Pydantic 스키마 — 요청/응답 모델."""

from __future__ import annotations

from typing import Any

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
    seed: int | None = 42
    # base 제공 시 변수 합산(simple_npv) 대신 실수지(FeasibilityServiceV2.calculate)
    # 섭동으로 net_profit_won 분포를 산출한다. 미제공 시 기존 동작 그대로(하위호환).
    base: FeasibilityCalculateRequest | None = None


class OptimizationRequest(BaseModel):
    """최적화 요청."""
    variables: dict[str, list[float]] = Field(
        ..., description="{name: [initial, min, max]}"
    )
    objective: str = "max_profit"
    max_iter: int = 200


class SensitivityScenarioSpec(BaseModel):
    """민감도 사용자 정의 시나리오(미지정 시 엔진 프리셋 5종 사용)."""
    name: str
    # 지원 변수: sale_price | construction_cost | land_cost | interest_rate | project_months
    variable: str
    deltas_pct: list[float] = Field(..., description="변동폭 목록(예: [-20,-10,0,10,20])")


class SensitivityRequest(BaseModel):
    """민감도 분석(토네이도) 요청 — 실수지 base 입력 기반."""
    base: FeasibilityCalculateRequest
    scenarios: list[SensitivityScenarioSpec] | None = None


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


class FeasibilityBaselineRequest(BaseModel):
    """부지직후 시장표준 baseline 수지분석 요청 — 부지 데이터만 입력."""
    address: str = ""
    zone_type: str = ""           # 용도지역명(예: 자연녹지지역). 미입력 시 주소로 자동감지.
    zone_code: str = ""           # 용도지역 코드(있으면 라벨용).
    land_area_sqm: float = 0      # 부지면적(㎡). 미입력 시 자동감지.
    pnu: str = ""                 # 필지고유번호(있으면 자동감지 보조).
    region: str = ""              # 시도명(분양가 시드 폴백용). 빈값=주소 시도 추론에 양보 —
    #                               맹목 "서울"은 비서울 부지 baseline을 서울가로 과대(W1-4 동일 클래스).
    official_price_per_sqm: float = 0  # 공시지가(원/㎡). 미입력 시 자동감지/표준.
    development_type: str = ""    # 강제 개발유형(미입력 시 용도지역 대표유형 자동선택).
    equity_won: int = 0           # 자기자본(미입력 시 토지비 기반 가정).


class FeasibilityBaselineResponse(FeasibilityResultResponse):
    """baseline 응답 — /calculate 결과 구조 동일 + baseline 메타필드.

    프론트가 /calculate 렌더를 그대로 재사용하되, is_baseline/confidence/sources/
    assumptions 로 추정 여부·시장표준 출처·역산 가정을 정직하게 표기(무목업).
    """
    is_baseline: bool = True
    confidence: str = "보통"      # 낮음/보통 — 추정 데이터 비중에 따라.
    sources: dict[str, Any] = {}   # 각 입력값의 출처 라벨(실데이터/시장표준/추정).
    assumptions: dict[str, Any] = {}  # 역산 GFA·표준단가 등 가정 명시.


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
    # ── 실수지 모드 메타(additive — 기본값은 기존 변수합 동작 의미 유지) ──
    target_metric: str = "variable_sum"   # base 제공 시 "net_profit_won"
    calc_source: str = "simple_npv"       # base 제공 시 "feasibility_v2"
    note: str | None = None            # 횟수 상한 등 적용 제약 정직 고지


class SensitivityResponse(BaseModel):
    """민감도 분석(토네이도) 응답 — 시나리오별 실수지 재계산 결과."""
    base_result: dict[str, Any]
    scenarios: list[dict[str, Any]] = []
    tornado: list[dict[str, Any]] = []
    # 섭동 원점(실수지 산출 기준값) — 어떤 값을 중심으로 변동했는지 출처 표기
    base_values: dict[str, float] = {}
    calc_source: str = "feasibility_v2"


class TaxResultResponse(BaseModel):
    """세금 결과 응답."""
    grand_total_won: int
    total_items_count: int
    summary_by_stage: dict[str, int]
    acquisition: dict[str, Any] = {}
    construction: dict[str, Any] = {}
    sale: dict[str, Any] = {}
    disposal: dict[str, Any] = {}
    # 법령 원문링크(레지스트리 출력 — 세목별 근거. additive, 구버전 빈 배열)
    legal_refs: list[dict[str, Any]] = []
    # 표준 근거 블록(#5): {evidence, legal_refs, provenance, trust}. 가산(graceful·구버전 None).
    evidence: dict[str, Any] | None = None


class ModuleListResponse(BaseModel):
    """모듈 목록 응답."""
    modules: list[dict[str, str]]


class RecommendationResponse(BaseModel):
    """AI 권고 응답."""
    recommendations: list[dict[str, Any]]
