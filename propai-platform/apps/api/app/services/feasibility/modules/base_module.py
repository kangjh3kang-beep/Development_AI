"""BaseModule ABC — 모든 개발유형 모듈의 추상 기반 클래스.

각 모듈은 calculate() 메서드로 ModuleInput → ModuleOutput 변환.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModuleInput:
    """모듈 공통 입력."""
    development_type: str  # M01~M15
    project_name: str = ""

    # 토지
    total_land_area_sqm: float = 0
    land_category: str = "land"
    official_price_per_sqm: float = 0
    price_multiplier: float = 1.0

    # 건축
    total_gfa_sqm: float = 0
    building_type: str = "apartment"
    floors: int = 0
    total_households: int = 0

    # 분양
    avg_sale_price_per_pyeong: float = 0
    avg_area_pyeong: float = 0
    sale_ratio: float = 1.0

    # 금융
    bridge_amount_won: int = 0
    bridge_rate: float = 0.06
    bridge_months: int = 12
    pf_amount_won: int = 0
    pf_rate: float = 0.045
    pf_months: int = 30
    midpay_amount_won: int = 0
    midpay_rate: float = 0.04
    midpay_months: int = 18

    # 지역
    sido_name: str = ""
    sigungu_name: str = ""
    house_count: int = 0
    is_adjusted_area: bool = False
    region_type: str = "capital_area"

    # 기타
    project_months: int = 48
    discount_rate: float = 0.08
    equity_won: int = 0
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleOutput:
    """모듈 공통 출력."""
    development_type: str
    module_name: str

    # 수입
    total_revenue_won: int = 0
    revenue_detail: dict[str, Any] = field(default_factory=dict)

    # 비용
    total_land_cost_won: int = 0
    total_construction_cost_won: int = 0
    total_finance_cost_won: int = 0
    total_other_cost_won: int = 0
    total_tax_cost_won: int = 0
    total_cost_won: int = 0

    # KPI
    net_profit_won: int = 0
    profit_rate_pct: float = 0.0
    roi_pct: float = 0.0            # 사업수익률 = 순이익/총사업비 (경로 간 비교 표준)
    roe_pct: float | None = None   # 자기자본수익률 = 순이익/자기자본 (레버리지, 자기자본 제공 시만)
    npv_won: int = 0
    grade: str = "F"

    # 상세
    cost_detail: dict[str, Any] = field(default_factory=dict)
    tax_detail: dict[str, Any] = field(default_factory=dict)
    special_detail: dict[str, Any] = field(default_factory=dict)


class BaseModule(ABC):
    """개발유형 모듈 추상 기반 클래스."""

    @property
    @abstractmethod
    def code(self) -> str:
        """모듈 코드 (M01~M15)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """모듈 이름 (한국어)."""
        ...

    @abstractmethod
    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        """수지분석 계산 실행."""
        ...

    def validate_input(self, inp: ModuleInput) -> list[str]:
        """입력 검증. 오류 메시지 리스트 반환 (빈 리스트 = OK)."""
        errors = []
        if inp.total_land_area_sqm <= 0:
            errors.append("total_land_area_sqm must be > 0")
        if inp.total_gfa_sqm <= 0:
            errors.append("total_gfa_sqm must be > 0")
        return errors
