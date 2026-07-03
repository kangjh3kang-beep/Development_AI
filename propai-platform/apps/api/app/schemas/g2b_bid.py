"""나라장터(G2B) 입찰/낙찰 Pydantic 스키마."""

from __future__ import annotations

from datetime import datetime
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
    org_type: str | None = None
    demand_org_name: str | None = None

    estimated_price: int | None = None
    budget_amount: int | None = None

    bid_begin_dt: datetime | None = None
    bid_close_dt: datetime | None = None
    open_dt: datetime | None = None
    notice_dt: datetime | None = None

    region_sido: str | None = None
    region_sigungu: str | None = None
    delivery_place: str | None = None

    bid_method: str | None = None
    contract_method: str | None = None
    qualification: str | None = None

    status: str = "active"

    award_price: int | None = None
    award_rate: float | None = None
    award_company: str | None = None
    award_dt: datetime | None = None
    bid_count: int | None = None

    g2b_url: str | None = None

    ai_risk_score: float | None = None
    ai_recommended_bid_rate: float | None = None
    ai_analysis_summary: str | None = None

    created_at: datetime
    updated_at: datetime


class G2BBidListResponse(BaseModel):
    """입찰 공고 목록 응답."""

    items: list[G2BBidResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── 입찰 공고 상세(raw_data 한글 라벨 매핑) ──
# 우리는 입찰공고 원본 API 응답 전체(144필드)를 raw_data에 저장하지만,
# 기본 응답 스키마는 ~20필드뿐이다. 아래 구조는 raw_data를 코드→한글라벨로
# 매핑해 "라벨+값" 형태로 구조적으로 노출한다(원본 통째 노출 금지).

class LabeledItem(BaseModel):
    """한글 라벨 + 표시값 한 쌍(예: 라벨="입찰방식", 값="일반경쟁")."""

    label: str
    value: str


class G2BAttachment(BaseModel):
    """공고 첨부문서(파일명 + 다운로드 URL)."""

    name: str
    url: str


class G2BContact(BaseModel):
    """발주/수요기관 담당자 연락처."""

    org: str | None = None  # 공고기관명
    demand_org: str | None = None  # 수요기관명
    name: str | None = None  # 담당자명
    tel: str | None = None  # 전화
    email: str | None = None  # 이메일
    exec_name: str | None = None  # 집행관명
    opening_place: str | None = None  # 개찰장소


class G2BDetailSections(BaseModel):
    """상세 화면용 섹션 묶음(일반/제한/일정/금액/첨부/연락처/링크)."""

    general: list[LabeledItem] = []  # 일반 정보
    restriction: list[LabeledItem] = []  # 참가 제한
    schedule: list[LabeledItem] = []  # 일정
    price: list[LabeledItem] = []  # 금액
    attachments: list[G2BAttachment] = []  # 첨부문서
    contact: G2BContact = G2BContact()  # 담당자 연락처
    links: dict[str, str] = {}  # 외부 링크


class G2BBidDetailResponse(G2BBidResponse):
    """입찰 공고 상세 응답(기본 응답 + 한글 라벨 매핑 detail)."""

    detail: G2BDetailSections


# ── 목록 조회 필터 ──

class G2BBidFilter(BaseModel):
    """입찰 공고 검색 필터."""

    keyword: str | None = Field(None, description="공고명 검색 키워드")
    bid_type: str | None = Field(None, description="업무구분(공사/용역/물품)")
    region_sido: str | None = Field(None, description="시/도")
    region_sigungu: str | None = Field(None, description="시/군/구")
    status: str | None = Field(None, description="상태(active/closed/awarded/failed)")
    category_tag: str | None = Field(None, description="AI 분류 태그")
    min_price: int | None = Field(None, description="최소 추정가격")
    max_price: int | None = Field(None, description="최대 추정가격")
    org_type: str | None = Field(None, description="기관유형")
    closing_days: int | None = Field(None, description="마감 N일 이내(예: 7=마감임박)")
    date_from: datetime | None = Field(None, description="공고일 시작")
    date_to: datetime | None = Field(None, description="공고일 종료")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ── 낙찰 통계 ──

class G2BAwardStatResponse(BaseModel):
    """낙찰가율 통계 응답."""

    model_config = ConfigDict(from_attributes=True)

    stat_period: str
    bid_type: str
    region_sido: str | None = None
    avg_award_rate: float | None = None
    min_award_rate: float | None = None
    max_award_rate: float | None = None
    bid_count: int = 0
    avg_competition_ratio: float | None = None


class G2BAwardStatsResponse(BaseModel):
    """낙찰가율 통계 목록."""

    items: list[G2BAwardStatResponse]
    total: int


# ── AI 분석 요청/응답 ──

class G2BBidAnalyzeRequest(BaseModel):
    """입찰 AI 분석 요청."""

    model_config = ConfigDict(protected_namespaces=())

    simulation_iterations: int = Field(10000, ge=1000, le=100000, description="몬테카를로 반복 횟수")
    cost_volatility_pct: float = Field(10.0, ge=0.0, le=50.0, description="공사비 변동성(%)")

    # ── 수동 보정 (정밀 분석 시 자동 추정값을 사용자가 덮어쓰기) ──
    total_gfa_sqm: float | None = Field(None, ge=0, description="연면적(㎡) 수동 보정")
    floor_count_above: int | None = Field(None, ge=1, description="지상 층수 수동 보정")
    floor_count_below: int | None = Field(None, ge=0, description="지하 층수 수동 보정")
    structure_type: str | None = Field(None, description="구조(RC/SRC/SC/PC/목구조)")
    building_type_override: str | None = Field(None, description="건물유형 수동 지정")
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

    direct_cost: int | None = None
    total_project_cost: int | None = None
    category_totals: dict = Field(default_factory=dict)
    cost_p10: int | None = None
    cost_p50: int | None = None
    cost_p80: int | None = None
    cost_p90: int | None = None
    cv: float | None = None
    risk_contributions: dict = Field(default_factory=dict)


class BidQtoItem(BaseModel):
    """공종별 물량 항목."""

    work_code: str = ""
    item_name: str = ""
    unit: str = ""
    quantity: float = 0.0


class BidZoning(BaseModel):
    """입찰 지역 용도지역/법규 한도(근사)."""

    zone_type: str | None = None
    max_bcr_pct: float | None = None
    max_far_pct: float | None = None
    max_height_m: float | None = None
    pnu: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BidPermitCheck(BaseModel):
    """인허가 가능성 + 건축법규 PQ 체크(참고용)."""

    is_permitted: bool | None = None
    permit_complexity: int | None = None
    reason: str | None = None
    rule_results: list[dict] = Field(default_factory=list)


class BidEsg(BaseModel):
    """GRESB ESG 점수(녹색건축 가산 전략)."""

    total_score: int | None = None
    grade: str | None = None
    components: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class BidCashflow(BaseModel):
    """낙찰 후 월별 현금흐름 요약."""

    irr_annual_pct: float | None = None
    peak_negative_cashflow: int | None = None
    net_profit: int | None = None
    phases: dict = Field(default_factory=dict)


class BidSensitivity(BaseModel):
    """민감도 토네이도 분석."""

    tornado: list[dict] = Field(default_factory=list)
    scenarios: list[dict] = Field(default_factory=list)


class BidMarketFeed(BaseModel):
    """지역·공종 낙찰가율 시장동향 피드."""

    items: list[G2BAwardStatResponse] = Field(default_factory=list)
    region_avg: float | None = None
    region_std: float | None = None


class BidInterpretation(BaseModel):
    """입찰 분석 결과에 대한 LLM(Claude) 자연어 해석.

    규칙기반 6엔진 수치를 입력으로, 입찰 의사결정에 필요한 5개 관점을
    전문가 내러티브로 생성한다. LLM 호출 실패 시 None으로 폴백한다.
    """

    model_config = ConfigDict(protected_namespaces=())

    bid_strategy: str = Field(description="투찰 전략 — 적정 투찰가율 근거, 시장 대비 포지셔닝")
    feasibility_view: str = Field(description="사업성 진단 — NPV/ROI/수익확률 해석, 수주 매력도")
    risk_assessment: str = Field(description="리스크 평가 — 원가/경쟁/발주처 리스크 종합 진단")
    cost_competitiveness: str = Field(description="원가 경쟁력 — 손익분기 대비 여유, 실행원가 관점")
    recommendation: str = Field(description="종합 권고 — 입찰 참여/조건부/회피 의견과 핵심 근거")

    model_used: str | None = Field(None, description="해석에 사용된 LLM 모델 ID")
    generated: bool = Field(True, description="LLM 생성 성공 여부(폴백 시 False)")


class G2BBidAnalyzeResponse(BaseModel):
    """입찰 AI 분석 결과."""

    bid_notice_no: str
    bid_notice_nm: str
    estimated_price: int | None = None

    # 적정 투찰가 예측
    recommended_bid_rate_low: float = Field(description="추천 투찰가율 하한(%)")
    recommended_bid_rate_mid: float = Field(description="추천 투찰가율 중앙값(%)")
    recommended_bid_rate_high: float = Field(description="추천 투찰가율 상한(%)")

    # 사업성 분석
    expected_npv: int | None = Field(None, description="예상 NPV(KRW)")
    expected_roi: float | None = Field(None, description="예상 ROI(%)")
    profit_probability: float | None = Field(None, description="수익 확률(%)")

    # 리스크 스코어
    risk_score_cost: float = Field(description="공사비 변동 리스크(0~100)")
    risk_score_trust: float = Field(description="발주기관 신뢰도(0~100)")
    risk_score_competition: float = Field(description="경쟁 강도(0~100)")
    risk_score_total: float = Field(description="종합 리스크(0~100)")

    # 시장 컨텍스트
    region_avg_award_rate: float | None = Field(None, description="해당 지역 평균 낙찰가율")
    similar_bids_count: int = Field(0, description="유사 공종 최근 입찰 건수")

    ai_summary: str = Field(description="AI 분석 요약 텍스트")
    g2b_url: str | None = None

    # ── 정밀 분석 섹션 (6엔진 연동, /feasibility 응답에서만 채워짐) ──
    spec: BidSpecEstimate | None = None
    cost_breakdown: BidCostBreakdown | None = None
    qto: list[BidQtoItem] | None = None
    zoning: BidZoning | None = None
    permit_check: BidPermitCheck | None = None
    esg: BidEsg | None = None
    cashflow: BidCashflow | None = None
    sensitivity: BidSensitivity | None = None
    market_feed: BidMarketFeed | None = None
    break_even_bid_rate: float | None = Field(None, description="손익분기 낙찰가율(%)")
    recommended_bid_price: int | None = Field(None, description="적정 투찰가(KRW)")
    analysis_warnings: list[str] = Field(default_factory=list)

    # ── LLM 자연어 해석 (정밀분석 + include_ai_interpretation=True 시 채워짐) ──
    ai_interpretation: BidInterpretation | None = None


# ── 대시보드 통계 ──

class G2BAnalysisHistoryItem(BaseModel):
    """입찰 분석 히스토리 목록 항목."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bid_id: UUID
    bid_notice_no: str | None = None
    bid_notice_nm: str | None = None
    params: dict = Field(default_factory=dict)
    recommended_bid_rate: float | None = None
    risk_score: float | None = None
    expected_roi: float | None = None
    summary: str | None = None
    created_at: datetime | None = None


class G2BAnalysisHistoryDetail(G2BAnalysisHistoryItem):
    """분석 히스토리 상세(전체 결과 포함)."""

    result: dict = Field(default_factory=dict)


class G2BAnalysisHistoryResponse(BaseModel):
    """분석 히스토리 목록 응답."""

    items: list[G2BAnalysisHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class G2BDashboardStats(BaseModel):
    """대시보드 요약 통계."""

    total_active: int = Field(description="현재 진행 중 공고 수")
    closing_soon: int = Field(description="마감 임박(7일 내) 공고 수")
    avg_award_rate: float | None = Field(None, description="최근 30일 평균 낙찰가율")
    ai_recommended_count: int = Field(description="AI 추천 입찰 건수")
    total_estimated_value: int | None = Field(None, description="진행 중 공고 총 추정가격")
