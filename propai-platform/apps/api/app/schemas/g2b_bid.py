"""나라장터(G2B) 입찰/낙찰 Pydantic 스키마."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── 입찰 공고 응답 ──

class G2BBidResponse(BaseModel):
    """입찰 공고 상세 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bid_notice_no: str
    bid_notice_nm: str
    bid_type: str
    category_tags: list[str] = []

    org_name: str
    org_type: Optional[str] = None
    demand_org_name: Optional[str] = None

    estimated_price: Optional[int] = None
    budget_amount: Optional[int] = None

    bid_begin_dt: Optional[datetime] = None
    bid_close_dt: Optional[datetime] = None
    open_dt: Optional[datetime] = None
    notice_dt: Optional[datetime] = None

    region_sido: Optional[str] = None
    region_sigungu: Optional[str] = None
    delivery_place: Optional[str] = None

    bid_method: Optional[str] = None
    contract_method: Optional[str] = None
    qualification: Optional[str] = None

    status: str = "active"

    award_price: Optional[int] = None
    award_rate: Optional[float] = None
    award_company: Optional[str] = None
    award_dt: Optional[datetime] = None
    bid_count: Optional[int] = None

    g2b_url: Optional[str] = None

    ai_risk_score: Optional[float] = None
    ai_recommended_bid_rate: Optional[float] = None
    ai_analysis_summary: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class G2BBidListResponse(BaseModel):
    """입찰 공고 목록 응답."""

    items: list[G2BBidResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── 목록 조회 필터 ──

class G2BBidFilter(BaseModel):
    """입찰 공고 검색 필터."""

    keyword: Optional[str] = Field(None, description="공고명 검색 키워드")
    bid_type: Optional[str] = Field(None, description="업무구분(공사/용역/물품)")
    region_sido: Optional[str] = Field(None, description="시/도")
    region_sigungu: Optional[str] = Field(None, description="시/군/구")
    status: Optional[str] = Field(None, description="상태(active/closed/awarded/failed)")
    category_tag: Optional[str] = Field(None, description="AI 분류 태그")
    min_price: Optional[int] = Field(None, description="최소 추정가격")
    max_price: Optional[int] = Field(None, description="최대 추정가격")
    org_type: Optional[str] = Field(None, description="기관유형")
    date_from: Optional[datetime] = Field(None, description="공고일 시작")
    date_to: Optional[datetime] = Field(None, description="공고일 종료")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ── 낙찰 통계 ──

class G2BAwardStatResponse(BaseModel):
    """낙찰가율 통계 응답."""

    model_config = ConfigDict(from_attributes=True)

    stat_period: str
    bid_type: str
    region_sido: Optional[str] = None
    avg_award_rate: Optional[float] = None
    min_award_rate: Optional[float] = None
    max_award_rate: Optional[float] = None
    bid_count: int = 0
    avg_competition_ratio: Optional[float] = None


class G2BAwardStatsResponse(BaseModel):
    """낙찰가율 통계 목록."""

    items: list[G2BAwardStatResponse]
    total: int


# ── AI 분석 요청/응답 ──

class G2BBidAnalyzeRequest(BaseModel):
    """입찰 AI 분석 요청."""

    simulation_iterations: int = Field(10000, ge=1000, le=100000, description="몬테카를로 반복 횟수")
    cost_volatility_pct: float = Field(10.0, ge=0.0, le=50.0, description="공사비 변동성(%)")

    # ── 수동 보정 (정밀 분석 시 자동 추정값을 사용자가 덮어쓰기) ──
    total_gfa_sqm: Optional[float] = Field(None, ge=0, description="연면적(㎡) 수동 보정")
    floor_count_above: Optional[int] = Field(None, ge=1, description="지상 층수 수동 보정")
    floor_count_below: Optional[int] = Field(None, ge=0, description="지하 층수 수동 보정")
    structure_type: Optional[str] = Field(None, description="구조(RC/SRC/SC/PC/목구조)")
    building_type_override: Optional[str] = Field(None, description="건물유형 수동 지정")
    target_margin_pct: float = Field(5.0, ge=0.0, le=30.0, description="목표 마진율(%)")

    # AI(LLM) 해석 (선택)
    include_ai_interpretation: bool = Field(
        True, description="LLM 자연어 해석 포함 여부(정밀분석 기본 활성)"
    )
    model_tier: str = Field(
        "standard", description="LLM 등급(standard=Sonnet/premium=Opus)"
    )


# ── 정밀 분석 섹션 서브모델 (6엔진 연동 결과) ──

class BidSpecEstimate(BaseModel):
    """추정가격 역산으로 산출한 건축 개요(자동/수동/공고명)."""

    building_type: str
    total_gfa_sqm: float
    floor_count_above: int
    floor_count_below: int
    structure_type: str
    source: str = Field(description="auto/notice/manual")
    confidence: float = Field(description="추정 신뢰도(0~1)")


class BidCostBreakdown(BaseModel):
    """QTO 기반 원가 산출 + 원가 몬테카를로."""

    direct_cost: Optional[int] = None
    total_project_cost: Optional[int] = None
    category_totals: dict = Field(default_factory=dict)
    cost_p10: Optional[int] = None
    cost_p50: Optional[int] = None
    cost_p80: Optional[int] = None
    cost_p90: Optional[int] = None
    cv: Optional[float] = None
    risk_contributions: dict = Field(default_factory=dict)


class BidQtoItem(BaseModel):
    """공종별 물량 항목."""

    work_code: str = ""
    item_name: str = ""
    unit: str = ""
    quantity: float = 0.0


class BidZoning(BaseModel):
    """입찰 지역 용도지역/법규 한도(근사)."""

    zone_type: Optional[str] = None
    max_bcr_pct: Optional[float] = None
    max_far_pct: Optional[float] = None
    max_height_m: Optional[float] = None
    pnu: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class BidPermitCheck(BaseModel):
    """인허가 가능성 + 건축법규 PQ 체크(참고용)."""

    is_permitted: Optional[bool] = None
    permit_complexity: Optional[int] = None
    reason: Optional[str] = None
    rule_results: list[dict] = Field(default_factory=list)


class BidEsg(BaseModel):
    """GRESB ESG 점수(녹색건축 가산 전략)."""

    total_score: Optional[int] = None
    grade: Optional[str] = None
    components: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class BidCashflow(BaseModel):
    """낙찰 후 월별 현금흐름 요약."""

    irr_annual_pct: Optional[float] = None
    peak_negative_cashflow: Optional[int] = None
    net_profit: Optional[int] = None
    phases: dict = Field(default_factory=dict)


class BidSensitivity(BaseModel):
    """민감도 토네이도 분석."""

    tornado: list[dict] = Field(default_factory=list)
    scenarios: list[dict] = Field(default_factory=list)


class BidMarketFeed(BaseModel):
    """지역·공종 낙찰가율 시장동향 피드."""

    items: list[G2BAwardStatResponse] = Field(default_factory=list)
    region_avg: Optional[float] = None
    region_std: Optional[float] = None


class BidInterpretation(BaseModel):
    """입찰 분석 결과에 대한 LLM(Claude) 자연어 해석.

    규칙기반 6엔진 수치를 입력으로, 입찰 의사결정에 필요한 5개 관점을
    전문가 내러티브로 생성한다. LLM 호출 실패 시 None으로 폴백한다.
    """

    bid_strategy: str = Field(description="투찰 전략 — 적정 투찰가율 근거, 시장 대비 포지셔닝")
    feasibility_view: str = Field(description="사업성 진단 — NPV/ROI/수익확률 해석, 수주 매력도")
    risk_assessment: str = Field(description="리스크 평가 — 원가/경쟁/발주처 리스크 종합 진단")
    cost_competitiveness: str = Field(description="원가 경쟁력 — 손익분기 대비 여유, 실행원가 관점")
    recommendation: str = Field(description="종합 권고 — 입찰 참여/조건부/회피 의견과 핵심 근거")

    model_used: Optional[str] = Field(None, description="해석에 사용된 LLM 모델 ID")
    generated: bool = Field(True, description="LLM 생성 성공 여부(폴백 시 False)")


class G2BBidAnalyzeResponse(BaseModel):
    """입찰 AI 분석 결과."""

    bid_notice_no: str
    bid_notice_nm: str
    estimated_price: Optional[int] = None

    # 적정 투찰가 예측
    recommended_bid_rate_low: float = Field(description="추천 투찰가율 하한(%)")
    recommended_bid_rate_mid: float = Field(description="추천 투찰가율 중앙값(%)")
    recommended_bid_rate_high: float = Field(description="추천 투찰가율 상한(%)")

    # 사업성 분석
    expected_npv: Optional[int] = Field(None, description="예상 NPV(KRW)")
    expected_roi: Optional[float] = Field(None, description="예상 ROI(%)")
    profit_probability: Optional[float] = Field(None, description="수익 확률(%)")

    # 리스크 스코어
    risk_score_cost: float = Field(description="공사비 변동 리스크(0~100)")
    risk_score_trust: float = Field(description="발주기관 신뢰도(0~100)")
    risk_score_competition: float = Field(description="경쟁 강도(0~100)")
    risk_score_total: float = Field(description="종합 리스크(0~100)")

    # 시장 컨텍스트
    region_avg_award_rate: Optional[float] = Field(None, description="해당 지역 평균 낙찰가율")
    similar_bids_count: int = Field(0, description="유사 공종 최근 입찰 건수")

    ai_summary: str = Field(description="AI 분석 요약 텍스트")
    g2b_url: Optional[str] = None

    # ── 정밀 분석 섹션 (6엔진 연동, /feasibility 응답에서만 채워짐) ──
    spec: Optional[BidSpecEstimate] = None
    cost_breakdown: Optional[BidCostBreakdown] = None
    qto: Optional[list[BidQtoItem]] = None
    zoning: Optional[BidZoning] = None
    permit_check: Optional[BidPermitCheck] = None
    esg: Optional[BidEsg] = None
    cashflow: Optional[BidCashflow] = None
    sensitivity: Optional[BidSensitivity] = None
    market_feed: Optional[BidMarketFeed] = None
    break_even_bid_rate: Optional[float] = Field(None, description="손익분기 낙찰가율(%)")
    recommended_bid_price: Optional[int] = Field(None, description="적정 투찰가(KRW)")
    analysis_warnings: list[str] = Field(default_factory=list)

    # ── LLM 자연어 해석 (정밀분석 + include_ai_interpretation=True 시 채워짐) ──
    ai_interpretation: Optional["BidInterpretation"] = None


# ── 대시보드 통계 ──

class G2BDashboardStats(BaseModel):
    """대시보드 요약 통계."""

    total_active: int = Field(description="현재 진행 중 공고 수")
    closing_soon: int = Field(description="마감 임박(48시간 내) 공고 수")
    avg_award_rate: Optional[float] = Field(None, description="최근 30일 평균 낙찰가율")
    ai_recommended_count: int = Field(description="AI 추천 입찰 건수")
    total_estimated_value: Optional[int] = Field(None, description="진행 중 공고 총 추정가격")
