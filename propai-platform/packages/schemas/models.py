"""PropAI 공유 API 응답 모델.

FastAPI 라우터의 response_model로 사용되며,
OpenAPI JSON → openapi-typescript로 Codex에 공유된다.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from packages.schemas.enums import (
    DesignType,
    EscrowStatus,
    ProjectStatus,
    TaxType,
    UserRole,
)

# ──────────────────────────────────────
# 공통 응답 래퍼
# ──────────────────────────────────────

class ApiResponse(BaseModel):
    """공통 API 응답 래퍼"""
    success: bool = True
    message: str | None = None
    data: dict | list | None = None


class PaginatedResponse(BaseModel):
    """페이지네이션 응답"""
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class ErrorResponse(BaseModel):
    """공통 오류 응답"""
    success: bool = False
    error_code: str
    message: str
    details: dict | None = None


# ──────────────────────────────────────
# 인증 관련
# ──────────────────────────────────────

class TokenResponse(BaseModel):
    """JWT 토큰 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="만료 시간 (초)")


class UserResponse(BaseModel):
    """사용자 정보 응답"""
    id: UUID
    tenant_id: UUID
    email: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    # 회원 시스템(2026-07): 이메일 인증·소셜 전용 여부 — 계정 화면 표시용(additive)
    email_verified: bool = False
    has_password: bool = True


# ──────────────────────────────────────
# 프로젝트
# ──────────────────────────────────────

class ProjectResponse(BaseModel):
    """프로젝트 응답"""
    id: UUID
    tenant_id: UUID
    name: str
    status: ProjectStatus
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    total_area_sqm: float | None = None
    building_type: str | None = None
    created_at: datetime
    updated_at: datetime
    # 분석 스냅샷 — 상세 응답에만 포함(목록은 페이로드 절약 위해 None 유지).
    analysis_snapshot: dict | None = None


class ProjectCreateRequest(BaseModel):
    """프로젝트 생성 요청"""
    name: str = Field(min_length=1, max_length=200)
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    total_area_sqm: float | None = Field(default=None, gt=0)


class ProjectUpdateRequest(BaseModel):
    """프로젝트 수정 요청"""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    total_area_sqm: float | None = Field(default=None, gt=0)
    description: str | None = None
    # 분석 스냅샷(프로젝트별 분석 결과 blob) — 주어지면 그대로 저장(백엔드 단일출처).
    analysis_snapshot: dict | None = None


class ProjectStatusUpdateRequest(BaseModel):
    """프로젝트 상태 전환 요청"""
    status: ProjectStatus


# ──────────────────────────────────────
# 웹훅
# ──────────────────────────────────────

class WebhookCreateRequest(BaseModel):
    """웹훅 생성 요청"""
    url: str = Field(max_length=2000)
    events: list[str] = Field(description="구독 이벤트 목록")
    description: str | None = Field(default=None, max_length=500)


class WebhookUpdateRequest(BaseModel):
    """웹훅 수정 요청"""
    url: str | None = Field(default=None, max_length=2000)
    events: list[str] | None = None
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class WebhookResponse(BaseModel):
    """웹훅 응답"""
    id: UUID
    tenant_id: UUID
    url: str
    events: list[str] | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    """웹훅 전송 이력 응답"""
    id: UUID
    webhook_id: UUID
    event_type: str
    status_code: int | None = None
    success: bool
    attempt: int
    duration_ms: float | None = None
    created_at: datetime


# ──────────────────────────────────────
# API 키
# ──────────────────────────────────────

class APIKeyCreateRequest(BaseModel):
    """API 키 생성 요청"""
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] | None = None
    expires_at: datetime | None = None


class APIKeyCreateResponse(BaseModel):
    """API 키 생성 응답 (평문 키 1회 노출)"""
    id: UUID
    name: str
    key: str = Field(description="평문 API 키 (1회만 노출)")
    key_prefix: str
    scopes: list[str] | None = None
    created_at: datetime


class APIKeyResponse(BaseModel):
    """API 키 목록 조회 응답"""
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str] | None = None
    is_active: bool
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


# ──────────────────────────────────────
# AVM (자동 시세 추정)
# ──────────────────────────────────────

class AlimTalkRequest(BaseModel):
    """Request payload for mock AlimTalk dispatch."""

    project_id: UUID | None = None
    recipient_phone: str = Field(min_length=8, max_length=30)
    template_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    payload: dict | None = None


class NotificationResponse(BaseModel):
    """Stored notification delivery response."""

    id: UUID
    project_id: UUID | None = None
    channel: str
    recipient_phone: str
    template_code: str
    status: str
    external_ref: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class ESignCreateRequest(BaseModel):
    """Request payload for a mock e-sign workflow."""

    project_id: UUID | None = None
    document_name: str = Field(min_length=1, max_length=255)
    document_url: str = Field(min_length=1, max_length=500)
    signer_name: str = Field(min_length=1, max_length=100)
    signer_email: str = Field(min_length=3, max_length=255)
    signer_phone: str | None = Field(default=None, max_length=30)


class ESignResponse(BaseModel):
    """E-sign request status response."""

    id: UUID
    project_id: UUID | None = None
    document_name: str
    document_url: str
    signer_name: str
    signer_email: str
    signer_phone: str | None = None
    provider: str
    status: str
    external_request_id: str | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class AVMValuationResponse(BaseModel):
    """AVM 시세 추정 응답"""
    id: UUID
    project_id: UUID
    estimated_price: float = Field(description="추정 가격 (원)")
    price_per_sqm: float = Field(description="㎡당 단가")
    confidence_score: float = Field(ge=0, le=1, description="신뢰도(실거래 사례 수 기준 — 합성 미계상)")
    comparable_count: int = Field(description="비교 사례 수(실거래+합성 총계 — 모델 입력 기준)")
    # ── W1-6 정직 분리: 콜드스타트 합성 보강이 실거래처럼 보이지 않도록 계수 분리 ──
    real_comparable_count: int = Field(default=0, description="실거래 비교 사례 수(합성 제외)")
    synthetic_count: int = Field(default=0, description="합성 보강 사례 수(콜드스타트 CTGAN, 참고용)")
    # 비교 거래 사례(프론트 표 렌더 계약: address/price(원)/area_sqm/transaction_date/synthetic)
    comparables: list[dict] = Field(default_factory=list, description="비교 거래 사례 상위 3건(synthetic 표기 동반)")
    model_version: str
    created_at: datetime

    # ── LLM(Claude) 자연어 해석 (AvmInterpreter, 키 설정 시 채워짐) ──
    valuation_narrative: str | None = Field(default=None, description="시세 추정 근거·신뢰도 해석")
    comparable_explanation: str | None = Field(default=None, description="비교 사례 분석")
    market_position: str | None = Field(default=None, description="시장 내 가격 포지셔닝")
    appreciation_outlook: str | None = Field(default=None, description="향후 가치 전망")
    investment_recommendation: str | None = Field(default=None, description="투자 관점 종합 의견")

    # ── 표준 근거 블록(#5 evidence 전 라우터 표준화) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")

    # ── 성장루프 조인키: 분석원장 content_hash(sha256) — 프론트 피드백이 이 값으로 원장과 조인 ──
    ledger_hash: str | None = Field(default=None, description="분석원장 조인키(미적재 시 None)")


class AVMRequest(BaseModel):
    """AVM 시세 추정 요청"""
    project_id: UUID
    address: str
    area_sqm: float = Field(gt=0)
    building_age_years: int | None = Field(default=None, ge=0)
    floor: int | None = None
    total_floors: int | None = None
    lawd_cd: str | None = Field(default=None, description="법정동코드 (5자리)")
    pnu: str | None = Field(default=None, description="필지고유번호 (19자리)")


# ──────────────────────────────────────
# 법규 검토
# ──────────────────────────────────────

class RegulationCheckResponse(BaseModel):
    """법규 검토 응답"""
    id: UUID
    project_id: UUID
    regulation_type: str
    is_compliant: bool
    violations: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0, le=1)
    source_documents: list[str] = Field(default_factory=list, description="참조 법령 문서")
    created_at: datetime


# ──────────────────────────────────────
# 세금 계산
# ──────────────────────────────────────

class TaxCalculationResponse(BaseModel):
    """세금 계산 응답"""
    id: UUID
    project_id: UUID
    tax_type: TaxType
    amount: float = Field(description="세액 (원)")
    taxable_value: float = Field(description="과세표준")
    tax_rate: float = Field(description="세율")
    deductions: list[dict] = Field(default_factory=list, description="공제 항목")
    optimization_tips: list[str] = Field(default_factory=list, description="절세 팁")
    created_at: datetime

    # LLM(Claude) 세무 전략 해석 (TaxInterpreter, 키 설정 시 채워짐)
    ai_tax_summary: str | None = Field(default=None, description="세금 부담 종합")
    ai_optimization_strategy: str | None = Field(default=None, description="절세 전략")
    ai_entity_comparison: str | None = Field(default=None, description="사업주체별 비교")
    ai_timing_strategy: str | None = Field(default=None, description="시점 전략")
    ai_deduction_opportunities: str | None = Field(default=None, description="공제·감면 기회")
    ai_risk_factors: str | None = Field(default=None, description="세무 리스크")


# ──────────────────────────────────────
# 설계/BIM
# ──────────────────────────────────────

class DesignResponse(BaseModel):
    """설계 응답"""
    id: UUID
    project_id: UUID
    design_type: DesignType
    file_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class BIMQuantityResponse(BaseModel):
    """BIM 물량산출 응답"""
    id: UUID
    project_id: UUID
    total_volume_m3: float
    total_area_sqm: float
    material_breakdown: list[dict] = Field(default_factory=list)
    element_count: int
    ifc_version: str
    created_at: datetime


# ──────────────────────────────────────
# 드론/IoT
# ──────────────────────────────────────

class DroneInspectionResponse(BaseModel):
    """드론 점검 응답"""
    id: UUID
    project_id: UUID
    inspection_date: datetime
    defects_found: int
    defects: list[dict] = Field(default_factory=list)
    severity_summary: dict = Field(default_factory=dict, description="심각도별 건수")
    images_processed: int
    created_at: datetime


# ──────────────────────────────────────
# 블록체인/에스크로
# ──────────────────────────────────────

class CreateEscrowRequest(BaseModel):
    """에스크로 생성 요청 — Solidity createEscrow() 매핑"""
    project_id: UUID
    payee_address: str = Field(description="수취인(매도자) 지갑 주소")
    payer_address: str = Field(description="지불인(매수자) 지갑 주소")
    subcontractor_address: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="하도급자 주소 (없으면 zero address)",
    )
    expires_at: int = Field(description="만료 Unix timestamp (uint64)")
    condition_hash: str = Field(description="조건 해시 (bytes32 hex)")


class FundEscrowRequest(BaseModel):
    """에스크로 자금 입금 요청 — Solidity fundEscrow() 매핑"""
    on_chain_escrow_id: int = Field(description="온체인 에스크로 ID (uint256)")
    amount_wei: str = Field(description="입금할 금액 (wei 문자열)")


class ReleaseEscrowRequest(BaseModel):
    """에스크로 자금 해제 요청 — Solidity releaseEscrow() 매핑"""
    on_chain_escrow_id: int = Field(description="온체인 에스크로 ID (uint256)")


class DisputeEscrowRequest(BaseModel):
    """에스크로 분쟁 요청 — Solidity initiateDispute() 매핑"""
    on_chain_escrow_id: int = Field(description="온체인 에스크로 ID (uint256)")
    reason_hash: str = Field(description="분쟁 사유 해시 (bytes32 hex)")


class EscrowTransactionResponse(BaseModel):
    """에스크로 트랜잭션 응답"""
    id: UUID
    project_id: UUID
    status: EscrowStatus
    amount_wei: str = Field(description="금액 (wei 단위 문자열)")
    on_chain_escrow_id: int | None = Field(
        default=None, description="온체인 에스크로 ID",
    )
    tx_hash: str | None = None
    contract_address: str | None = None
    buyer_address: str
    seller_address: str
    created_at: datetime


class DirectPaymentRequest(BaseModel):
    """하도급 대금 직불 요청 — Solidity directPaymentToSubcontractor() 매핑.

    건설산업기본법 제35조 준거: 원수급자 계좌 경유 없이 하수급자 직접 지급.
    """

    on_chain_escrow_id: int = Field(description="온체인 에스크로 ID (uint256)")
    subcontractor_address: str = Field(description="하수급자 지갑 주소")
    gross_amount_wei: str = Field(description="지급 금액 (wei 문자열)")


class ResolveDisputeRequest(BaseModel):
    """분쟁 해결 요청 — Solidity resolveDispute() 매핑 (owner 전용)."""

    on_chain_escrow_id: int = Field(description="온체인 에스크로 ID (uint256)")
    release_to_payee: bool = Field(
        description="True=수취인 지급, False=지불인 환불",
    )


class OnChainEscrowResponse(BaseModel):
    """온체인 에스크로 상태 조회 응답"""
    on_chain_escrow_id: int
    payer: str
    payee: str
    subcontractor: str
    total_amount_wei: str
    remaining_amount_wei: str
    expires_at: int
    condition_hash: str
    status: str = Field(description="온체인 상태 (PendingFunding/Funded/...)")


# ──────────────────────────────────────
# 재무 분석
# ──────────────────────────────────────

class FinancialAnalysisResponse(BaseModel):
    """재무 분석 응답"""
    id: UUID
    project_id: UUID
    npv: float = Field(description="순현재가치 (원)")
    irr: float = Field(description="내부수익률")
    payback_period_months: int = Field(description="회수 기간 (월)")
    total_investment: float = Field(description="총 투자비")
    total_revenue: float = Field(description="총 수입")
    risk_score: float = Field(ge=0, le=1, description="리스크 점수")
    created_at: datetime


# ──────────────────────────────────────
# 전세 리스크
# ──────────────────────────────────────

class JeonseRiskRequest(BaseModel):
    """전세 리스크 분석 요청"""
    project_id: UUID
    address: str = Field(description="분석 대상 주소")
    jeonse_price: float = Field(gt=0, description="전세가 (원)")
    sale_price: float = Field(gt=0, description="매매가 (원)")


class JeonseRiskResponse(BaseModel):
    """전세 리스크 분석 응답"""
    jeonse_ratio: float = Field(description="전세가율")
    risk_level: str = Field(description="위험 등급 (SAFE/LOW/MEDIUM/HIGH/CRITICAL)")
    risk_score: float = Field(ge=0, le=1, description="위험 점수")
    analysis: str = Field(description="종합 분석")
    factors: list[dict] = Field(default_factory=list, description="위험 요인")
    # 표준 근거 블록(#5): {evidence, legal_refs, provenance, trust}. 가산(graceful·구버전 None).
    evidence: dict | None = Field(default=None, description="근거·산식·출처 블록")


# ──────────────────────────────────────
# 탄소 배출량
# ──────────────────────────────────────

class CarbonCalculationRequest(BaseModel):
    """탄소 배출량 산출 요청"""
    project_id: UUID
    material_breakdown: list[dict] = Field(description="자재별 물량 (BIM 산출 결과)")
    total_area_sqm: float = Field(gt=0, description="총 면적 (㎡)")


class CarbonCalculationResponse(BaseModel):
    """탄소 배출량 산출 응답"""
    total_embodied_carbon: float = Field(description="내재 탄소 (kgCO2e)")
    total_operational_carbon: float = Field(description="운영 탄소 (kgCO2e)")
    total_carbon: float = Field(description="총 탄소 (kgCO2e)")
    breakdown: list[dict] = Field(default_factory=list, description="자재별 배출량")
    reduction_tips: list[str] = Field(default_factory=list, description="저감 방안")


# ──────────────────────────────────────
# 시공/ESG AI
# ──────────────────────────────────────

class ConstructionScheduleRequest(BaseModel):
    """시공 일정 생성 요청"""
    project_id: UUID
    total_area_sqm: float = Field(gt=0, description="총 시공 면적 (㎡)")
    floors_above: int = Field(ge=1, description="지상 층수")
    floors_below: int = Field(default=1, ge=0, description="지하 층수")
    structure_type: str = Field(default="RC", description="구조형식 (RC/SRC/SC)")


class ConstructionScheduleResponse(BaseModel):
    """시공 일정 생성 응답"""
    total_duration_days: int = Field(description="총 공사기간 (일)")
    schedule: list[dict] = Field(description="공정별 일정")
    critical_path: list[str] = Field(description="주공정선 (Critical Path)")
    milestones: list[dict] = Field(default_factory=list, description="주요 마일스톤")
    # ── 표준 근거 블록(#5 evidence) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")


class ClimateRiskRequest(BaseModel):
    """기후 리스크 분석 요청"""
    project_id: UUID
    lat: float = Field(description="위도")
    lon: float = Field(description="경도")
    construction_period_months: int = Field(default=24, description="시공 기간 (월)")


class ClimateRiskResponse(BaseModel):
    """기후 리스크 분석 응답"""
    flood_risk_score: float = Field(ge=0, le=1, description="홍수 리스크")
    heat_risk_score: float = Field(ge=0, le=1, description="폭염 리스크")
    overall_risk_level: str = Field(description="종합 등급 (LOW/MEDIUM/HIGH/CRITICAL)")
    risk_factors: list[dict] = Field(default_factory=list, description="위험 요인")
    mitigation_tips: list[str] = Field(default_factory=list, description="리스크 대응 방안")
    # ── 표준 근거 블록(#5 evidence) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")


class DefectClassificationRequest(BaseModel):
    """하자 사진 AI 분류 요청"""
    project_id: UUID
    image_url: str = Field(description="하자 사진 URL")
    location: str = Field(default="", description="하자 위치 설명")


class DefectClassificationResponse(BaseModel):
    """하자 사진 AI 분류 응답"""
    defect_type: str = Field(description="하자 유형")
    severity: str = Field(description="심각도 (MINOR/MODERATE/MAJOR/CRITICAL)")
    confidence: float = Field(ge=0, le=1, description="AI 판정 신뢰도")
    description: str = Field(description="하자 상세 설명")
    repair_recommendation: str = Field(description="보수 권장 사항")
    # ── 표준 근거 블록(#5 evidence) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")


class ZEBEnergyRequest(BaseModel):
    """ZEB 에너지 시뮬레이션 요청"""
    project_id: UUID
    total_area_sqm: float = Field(gt=0, description="총 면적 (㎡)")
    floors: int = Field(ge=1, description="층수")
    window_wall_ratio: float = Field(default=0.35, ge=0.1, le=0.9, description="창면적비")
    insulation_grade: str = Field(default="1등급", description="단열 등급")


class ZEBEnergyResponse(BaseModel):
    """ZEB 에너지 시뮬레이션 응답"""
    annual_energy_demand_kwh: float = Field(description="연간 에너지 요구량 (kWh)")
    annual_renewable_generation_kwh: float = Field(description="연간 재생에너지 생산량 (kWh)")
    zeb_grade: str = Field(description="ZEB 등급 (1~5등급 또는 미달)")
    energy_independence_rate: float = Field(description="에너지 자립률 (%)")
    recommendations: list[str] = Field(default_factory=list, description="에너지 개선 권장 사항")
    # ── 표준 근거 블록(#5 evidence) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")


# ──────────────────────────────────────
# 헬스체크
# ──────────────────────────────────────

class SystemVersionResponse(BaseModel):
    """System version and environment response."""

    app_name: str
    version: str
    environment: str
    api_prefixes: list[str] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    """Extended health response for the system module."""

    status: str
    version: str
    environment: str
    services: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime


class DashboardStatsResponse(BaseModel):
    """Top-level dashboard counters for the current tenant."""

    total_projects: int = 0
    projects_by_status: dict[str, int] = Field(default_factory=dict)
    active_webhooks: int = 0
    active_api_keys: int = 0
    ai_cost_month_usd: float = 0.0
    ai_tokens_month: int = 0


class DashboardTimelinePoint(BaseModel):
    """Monthly portfolio activity point."""

    period: str
    project_count: int = 0


class DashboardTimelineResponse(BaseModel):
    """Portfolio timeline response."""

    items: list[DashboardTimelinePoint] = Field(default_factory=list)


class DashboardActivityItem(BaseModel):
    """Recent dashboard activity item."""

    category: str
    action: str
    resource_id: str
    resource_name: str
    occurred_at: datetime


class DashboardRecentActivityResponse(BaseModel):
    """Recent activity feed response."""

    items: list[DashboardActivityItem] = Field(default_factory=list)


class AICostBreakdownItem(BaseModel):
    """Per-service AI cost breakdown."""

    service_name: str
    model_name: str
    request_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class AICostDashboardResponse(BaseModel):
    """Monthly AI usage summary."""

    month: str
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    by_service: list[AICostBreakdownItem] = Field(default_factory=list)


class AIBudgetGateResponse(BaseModel):
    """Budget gate evaluation response."""

    endpoint: str
    monthly_budget_usd: float
    current_cost_usd: float
    remaining_budget_usd: float
    allowed: bool


class KepcoCalculationRequest(BaseModel):
    """Request model for KEPCO tariff estimation."""

    usage_kwh: float = Field(gt=0)
    contract_type: str = Field(default="general", description="general | industrial | education")
    demand_kw: float = Field(default=0.0, ge=0)


class KepcoCalculationResponse(BaseModel):
    """Response model for KEPCO tariff estimation."""

    contract_type: str
    usage_kwh: float
    demand_kw: float
    base_charge_krw: float
    energy_charge_krw: float
    climate_fund_krw: float
    fuel_adjustment_krw: float
    vat_krw: float
    total_bill_krw: float
    # 표준 근거 블록(#5): 요금 산식·구성·출처를 가산(graceful·선택). 미부착 시 None.
    evidence: dict | None = Field(default=None)


class DataRoomDocumentInput(BaseModel):
    """Uploaded data room document metadata."""

    file_name: str
    storage_url: str
    size_bytes: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    parsed_summary: str | None = None


class UnderwritingRequest(BaseModel):
    """Request model for investment underwriting."""

    project_id: UUID
    project_name: str
    total_cost_krw: float = Field(gt=0)
    projected_revenue_krw: float = Field(gt=0)
    acquisition_price_krw: float = Field(gt=0)
    equity_krw: float = Field(gt=0)
    debt_krw: float = Field(ge=0)
    jeonse_ratio: float | None = Field(default=None, ge=0, le=1)
    assumptions_json: dict = Field(default_factory=dict)
    data_room_documents: list[DataRoomDocumentInput] = Field(default_factory=list)


class UnderwritingResponse(BaseModel):
    """Response model for investment underwriting."""

    underwriting_id: UUID
    project_id: UUID
    project_name: str
    risk_level: str
    risk_score: float
    recommendation: str
    projected_profit_krw: float
    profit_margin_ratio: float
    debt_ratio: float
    equity_multiple: float
    jeonse_ratio: float | None = None
    key_risks: list[dict] = Field(default_factory=list)
    narrative: str
    created_at: datetime


class ComplianceCheckResponse(BaseModel):
    """Contract model for Phase E compliance checks."""

    check_id: UUID
    project_id: UUID
    check_type: str
    status: str
    score: float | None = None
    findings: list[dict] = Field(default_factory=list)
    remediation_plan: str | None = None


class KYCDocumentInput(BaseModel):
    """KYC document metadata submitted for screening."""

    document_kind: str
    file_name: str
    storage_url: str
    identifier_masked: str | None = None


class KYCDocumentResponse(BaseModel):
    """Stored KYC document metadata."""

    document_id: UUID
    subject_name: str
    document_kind: str
    verified: bool
    storage_url: str


class AMLScreeningResponse(BaseModel):
    """AML screening details."""

    screening_id: UUID
    subject_name: str
    match_status: str
    risk_level: str
    matched_lists: list[str] = Field(default_factory=list)
    notes: str | None = None


class ComplianceScreeningRequest(BaseModel):
    """Request model for KYC and AML screening."""

    project_id: UUID
    subject_name: str
    check_type: str = Field(default="aml-kyc")
    transaction_amount_krw: float = Field(gt=0)
    politically_exposed: bool = False
    residency_countries: list[str] = Field(default_factory=list)
    documents: list[KYCDocumentInput] = Field(default_factory=list)


class ComplianceScreeningResponse(BaseModel):
    """Response model for KYC and AML screening."""

    compliance_check: ComplianceCheckResponse
    aml_screening: AMLScreeningResponse
    kyc_documents: list[KYCDocumentResponse] = Field(default_factory=list)


class LeaseAbstractionResponse(BaseModel):
    """Contract model for lease abstraction outputs."""

    abstraction_id: UUID
    project_id: UUID
    tenant_name: str
    lease_type: str
    area_sqm: float
    deposit_krw: float
    monthly_rent_krw: float
    critical_terms: list[dict] = Field(default_factory=list)


class LeaseAnalysisRequest(BaseModel):
    """Request model for lease abstraction and IFRS16 schedule generation."""

    project_id: UUID
    source_document_name: str
    tenant_name: str
    lease_type: str
    area_sqm: float = Field(gt=0)
    deposit_krw: float = Field(default=0.0, ge=0)
    monthly_rent_krw: float = Field(default=0.0, ge=0)
    start_date: datetime
    end_date: datetime
    discount_rate: float = Field(default=0.055, ge=0, le=0.2)
    critical_terms: list[dict] = Field(default_factory=list)
    abstraction_text: str | None = None


class LeaseIFRS16ScheduleResponse(BaseModel):
    """Contract model for IFRS16 schedules."""

    schedule_id: UUID
    project_id: UUID
    lease_term_months: int
    discount_rate: float
    rou_asset_krw: float
    lease_liability_krw: float
    payment_schedule: list[dict] = Field(default_factory=list)


class LeaseAnalysisResponse(BaseModel):
    """Response model for lease abstraction and IFRS16 schedule generation."""

    abstraction: LeaseAbstractionResponse
    ifrs16_schedule: LeaseIFRS16ScheduleResponse


class ESGAssessmentRequest(BaseModel):
    """Request model for ESG and GRESB scoring."""

    project_id: UUID
    reporting_period: str
    gross_floor_area_sqm: float = Field(gt=0)
    scope1_tco2e: float = Field(default=0.0, ge=0)
    scope2_tco2e: float = Field(default=0.0, ge=0)
    scope3_tco2e: float = Field(default=0.0, ge=0)
    energy_independence_rate: float = Field(default=0.0, ge=0, le=100)
    climate_risk_score: float = Field(default=0.0, ge=0, le=1)
    lost_time_incident_rate: float = Field(default=0.0, ge=0)
    community_programs_count: int = Field(default=0, ge=0)
    board_independence_ratio: float = Field(default=0.0, ge=0, le=1)
    disclosures: list[dict] = Field(default_factory=list)
    use_llm: bool = True  # AI 내러티브(ESG 해석) 포함 여부(사용자 선택)


class ESGAssessmentResponse(BaseModel):
    """Contract model for ESG and GRESB results."""

    assessment_id: UUID
    project_id: UUID
    reporting_period: str
    status: str
    environmental_score: float | None = None
    social_score: float | None = None
    governance_score: float | None = None
    overall_score: float | None = None
    gresb_rating: str | None = None
    carbon_total_tco2e: float | None = None
    disclosures: list[dict] = Field(default_factory=list)
    action_plan: str | None = None
    # 표준 근거 블록(#5) — 산출 점수·탄소·산식·법령링크·신선도. 미부착 시 None(스키마 무손상).
    evidence: dict | None = Field(default=None)


class InsuranceRecommendationResponse(BaseModel):
    """Insurance recommendation item."""

    recommendation_id: UUID
    coverage_type: str
    priority: str
    annual_premium_estimate_krw: float
    coverage_limit_krw: float
    rationale: str


class ClimateRiskAssessmentRequest(BaseModel):
    """Request model for climate risk packaging."""

    project_id: UUID
    lat: float
    lon: float
    asset_value_krw: float = Field(gt=0)
    construction_period_months: int = Field(default=24, ge=1)


class ClimateRiskAssessmentResponse(BaseModel):
    """Response model for climate risk packaging."""

    assessment_id: UUID
    project_id: UUID
    flood_risk_score: float
    heat_risk_score: float
    overall_risk_level: str
    annual_expected_loss_krw: float
    risk_factors: list[dict] = Field(default_factory=list)
    mitigation_tips: list[str] = Field(default_factory=list)
    insurance_recommendations: list[InsuranceRecommendationResponse] = Field(default_factory=list)
    created_at: datetime
    # 표준 근거 블록(#5): 위험점수·연간기대손실 산식·출처를 가산(graceful·선택). 미부착 시 None.
    evidence: dict | None = Field(default=None)


class MarketingContentRequest(BaseModel):
    """Request model for marketing content generation."""

    project_id: UUID
    project_name: str
    channel: str
    asset_type: str
    target_audience: str
    tone: str = "professional"
    highlights: list[str] = Field(default_factory=list)


class MarketingContentResponse(BaseModel):
    """Response model for marketing content generation."""

    content_id: UUID
    project_id: UUID
    channel: str
    headline: str
    body: str
    call_to_action: str
    created_at: datetime


class OMReportRequest(BaseModel):
    """Request model for offering memorandum generation."""

    project_id: UUID
    project_name: str
    asset_type: str
    investment_highlights: list[str] = Field(default_factory=list)
    target_audience: str = "institutional"
    risk_factors: list[str] = Field(default_factory=list)
    output_format: str = "markdown"


class OMReportResponse(BaseModel):
    """Response model for offering memorandum generation."""

    memorandum_id: UUID
    project_id: UUID
    title: str
    executive_summary: str
    sections: list[dict] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    output_format: str
    created_at: datetime


class DomainAgentRunRequest(BaseModel):
    """Request model for a single domain agent execution."""

    project_id: UUID
    domain: str
    question: str
    context: dict = Field(default_factory=dict)
    approval_role: str = "manager"


class DomainAgentRunResponse(BaseModel):
    """Response model for a single domain agent execution."""

    task_id: UUID
    project_id: UUID
    domain: str
    status: str
    confidence_score: float
    recommendation: str
    findings: list[dict] = Field(default_factory=list)
    approval_required: bool = False
    approval_status: str = "not-required"


class DomainMultiAnalysisRequest(BaseModel):
    """Request model for multi-domain analysis."""

    project_id: UUID
    domains: list[str] = Field(default_factory=list)
    question: str
    context: dict = Field(default_factory=dict)
    approval_role: str = "manager"


class DomainMultiAnalysisResponse(BaseModel):
    """Response model for multi-domain analysis."""

    items: list[DomainAgentRunResponse] = Field(default_factory=list)
    portfolio_summary: str


class DomainAgentHistoryItemResponse(BaseModel):
    """Persisted domain-agent execution history item."""

    task_id: UUID
    project_id: UUID
    domain: str
    status: str
    confidence_score: float
    recommendation: str
    findings: list[dict] = Field(default_factory=list)
    approval_required: bool
    approval_status: str = "not-required"
    approver_role: str | None = None
    narrative: str | None = None
    created_at: datetime


class DomainAgentHistoryResponse(BaseModel):
    """Persisted domain-agent execution history response."""

    items: list[DomainAgentHistoryItemResponse] = Field(default_factory=list)


class DomainAgentApprovalQueueItemResponse(BaseModel):
    """Pending or persisted approval queue item for domain-agent tasks."""

    approval_id: UUID
    task_id: UUID
    project_id: UUID
    domain: str
    approver_role: str
    status: str
    rationale: str | None = None
    recommendation: str
    confidence_score: float
    created_at: datetime
    decided_at: datetime | None = None


class DomainAgentApprovalQueueResponse(BaseModel):
    """Domain-agent approval queue response."""

    items: list[DomainAgentApprovalQueueItemResponse] = Field(default_factory=list)


class DomainAgentApprovalDecisionRequest(BaseModel):
    """Approval decision request for a persisted domain-agent task."""

    decision: str = Field(pattern="^(approved|rejected)$")
    rationale: str | None = Field(default=None, max_length=1000)


class DomainAgentApprovalBatchDecisionRequest(BaseModel):
    """Batch approval decision request for persisted domain-agent tasks."""

    project_id: UUID
    approval_ids: list[UUID] = Field(default_factory=list, min_length=1)
    decision: str = Field(pattern="^(approved|rejected)$")
    rationale: str | None = Field(default=None, max_length=1000)


class DomainAgentApprovalBatchDecisionResponse(BaseModel):
    """Batch approval decision response for persisted domain-agent tasks."""

    items: list[DomainAgentApprovalQueueItemResponse] = Field(default_factory=list)
    updated_count: int = 0


class MaintenanceAnomalyRequest(BaseModel):
    """Contract-first request model for maintenance anomaly detection."""

    project_id: UUID
    equipment_name: str
    equipment_type: str
    location: str | None = None
    vibration_mm_s: float = Field(default=0.0, ge=0)
    temperature_c: float = Field(default=0.0, ge=-30)
    energy_efficiency_ratio: float = Field(default=1.0, ge=0)


class MaintenanceAnomalyResponse(BaseModel):
    """Contract-first response model for maintenance anomaly detection."""

    alert_id: UUID
    project_id: UUID
    anomaly_score: float
    remaining_useful_life_days: int | None = None
    hvac_efficiency_score: float | None = None
    severity: str
    recommendation: str
    work_order_id: UUID | None = None


class TenantFeedbackRequest(BaseModel):
    """Contract-first request model for tenant feedback analysis."""

    project_id: UUID
    unit_label: str | None = None
    category: str
    feedback_text: str
    satisfaction_rating: int = Field(default=3, ge=1, le=5)


class TenantFeedbackResponse(BaseModel):
    """Contract-first response model for tenant feedback analysis."""

    ticket_id: UUID
    project_id: UUID
    sentiment_score: float
    sentiment_label: str
    ai_reply: str
    created_at: datetime


class TenantSatisfactionRequest(BaseModel):
    """Contract-first request model for tenant satisfaction aggregation."""

    project_id: UUID
    promoter_count: int = Field(default=0, ge=0)
    passive_count: int = Field(default=0, ge=0)
    detractor_count: int = Field(default=0, ge=0)
    occupancy_rate: float = Field(default=0.0, ge=0, le=1)
    arrears_ratio: float = Field(default=0.0, ge=0, le=1)


class TenantSatisfactionResponse(BaseModel):
    """Contract-first response model for tenant satisfaction aggregation."""

    financial_health_id: UUID
    project_id: UUID
    nps: float
    churn_risk_score: float
    health_grade: str
    created_at: datetime


class AssetIntelligenceRequest(BaseModel):
    """Contract-first request model for asset intelligence."""

    project_id: UUID
    base_value_krw: float = Field(gt=0)
    maintenance_score: float | None = Field(default=None, ge=0, le=100)
    tenant_score: float | None = Field(default=None, ge=0, le=100)
    market_score: float | None = Field(default=None, ge=0, le=100)
    climate_score: float | None = Field(default=None, ge=0, le=100)


class AssetIntelligenceResponse(BaseModel):
    """Contract-first response model for asset intelligence."""

    snapshot_id: UUID
    project_id: UUID
    composite_score: float
    grade: str
    adjusted_value_krw: float
    component_scores: dict = Field(default_factory=dict)
    capex_recommendations: list[dict] = Field(default_factory=list)
    created_at: datetime


class PortalPostRequest(BaseModel):
    """Request model for posting a listing to a portal."""

    project_id: UUID
    project_name: str
    region_code: str
    property_type: str
    price_krw: float = Field(gt=0)
    area_sqm: float = Field(gt=0)
    title: str
    description: str
    images: list[str] = Field(default_factory=list)


class PortalPostResponse(BaseModel):
    """Response model for a portal listing post."""

    listing_id: UUID
    project_id: UUID
    portal_name: str
    listing_external_id: str
    listing_url: str | None = None
    status: str
    view_count: int = 0
    inquiry_count: int = 0
    created_at: datetime


class PortalBatchPostRequest(BaseModel):
    """Request model for posting to multiple portals."""

    project_id: UUID
    project_name: str
    region_code: str
    property_type: str
    price_krw: float = Field(gt=0)
    area_sqm: float = Field(gt=0)
    title: str
    description: str
    portals: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)


class PortalBatchPostResponse(BaseModel):
    """Response model for posting to multiple portals."""

    items: list[PortalPostResponse] = Field(default_factory=list)
    success_count: int = 0


class PortalMarketDataResponse(BaseModel):
    """Response model for aggregated portal market data."""

    region_code: str
    active_listing_count: int = 0
    average_price_krw: float = 0.0
    average_area_sqm: float = 0.0
    average_inquiry_count: float = 0.0
    top_portals: list[dict] = Field(default_factory=list)


class InvestorReportRequest(BaseModel):
    """Request model for multilingual investor report generation."""

    project_id: UUID
    project_name: str
    target_languages: list[str] = Field(default_factory=lambda: ["ko", "en"])
    asset_type: str
    investment_highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    include_sections: list[str] = Field(
        default_factory=lambda: [
            "executive-summary",
            "market",
            "financials",
            "esg",
            "risks",
        ]
    )


class InvestorReportVariantResponse(BaseModel):
    """Single language investor report variant."""

    report_id: UUID
    target_language: str
    title: str
    quality_score: float | None = None
    translated_text: str


class InvestorReportResponse(BaseModel):
    """Response model for multilingual investor reports."""

    project_id: UUID
    report_type: str
    variants: list[InvestorReportVariantResponse] = Field(default_factory=list)
    generated_sections: list[str] = Field(default_factory=list)
    # 성장루프 조인키: 분석원장 content_hash(sha256) — 프론트 피드백이 원장과 조인(미적재 시 None)
    ledger_hash: str | None = None


class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str = "healthy"
    version: str
    services: dict = Field(default_factory=dict, description="의존 서비스 상태")


# ──────────────────────────────────────
# G92 포털 연동
# ──────────────────────────────────────

class PortalListingCreateRequest(BaseModel):
    """포털 매물 게재 요청."""
    project_id: UUID
    portal_name: str = Field(min_length=1, max_length=60)
    listing_external_id: str = Field(min_length=1)
    property_type: str
    price_krw: float = Field(gt=0)
    area_sqm: float = Field(gt=0)
    description: str | None = None
    listing_url: str | None = None


class PortalListingResponse(BaseModel):
    """포털 매물 게재 응답."""
    id: UUID
    project_id: UUID
    portal_name: str
    listing_external_id: str
    status: str
    property_type: str
    price_krw: float
    area_sqm: float
    view_count: int = 0
    inquiry_count: int = 0
    published_at: datetime
    created_at: datetime


class PortalPerformanceResponse(BaseModel):
    """포털 성과 메트릭 응답."""
    listing_id: UUID
    view_count: int
    inquiry_count: int
    click_through_rate: float
    bookmark_count: int
    ranking_position: int | None = None
    snapshot_date: datetime


# ──────────────────────────────────────
# G93 다국어 보고서
# ──────────────────────────────────────

class TranslationRequest(BaseModel):
    """번역 요청."""
    project_id: UUID
    report_type: str = Field(default="feasibility")
    source_language: str = Field(default="ko", max_length=10)
    target_language: str = Field(max_length=10)
    source_text: str = Field(min_length=1)
    translation_engine: str = Field(default="claude-sonnet")


class KDXMetricSnapshot(BaseModel):
    """KDX 최신 지표 스냅샷."""

    region_code: str
    metric_type: str
    value: float
    currency: str
    recorded_at: datetime


class KDXTelemetryLogResponse(BaseModel):
    """KDX 최근 텔레메트리 로그."""

    id: UUID
    source: str
    event_type: str
    status: str
    created_at: datetime


class KDXOverviewResponse(BaseModel):
    """KDX 모니터링 대시보드 응답."""

    connection_status: str
    throughput_tps: int
    data_sync_latency_ms: int
    latest_metric: KDXMetricSnapshot | None = None
    recent_logs: list[KDXTelemetryLogResponse] = Field(default_factory=list)


class TranslationResponse(BaseModel):
    """번역 결과 응답."""
    id: UUID
    project_id: UUID
    source_language: str
    target_language: str
    translated_text: str
    translation_engine: str
    quality_score: float | None = None
    word_count: int
    created_at: datetime


# ──────────────────────────────────────
# G91 AI 비용 예산
# ──────────────────────────────────────

class AICostBudgetRequest(BaseModel):
    """Request model for AI cost budget configuration."""

    endpoint: str
    monthly_budget_usd: float = Field(gt=0)
    month: str | None = None
    alert_threshold_ratio: float = Field(default=0.8, ge=0.1, le=1.0)


class AICostBudgetResponse(BaseModel):
    """Response model for AI cost budget configuration."""

    budget_id: UUID
    endpoint: str
    month: str
    monthly_budget_usd: float
    alert_threshold_ratio: float
    created_at: datetime


class EnergyCertificationRequest(BaseModel):
    """Request model for energy certification estimation."""

    project_id: UUID
    total_area_sqm: float = Field(gt=0)
    floors: int = Field(ge=1)
    window_wall_ratio: float = Field(default=0.35, ge=0.1, le=0.9)
    insulation_grade: str = Field(default="1?깃툒")
    bems_saving_rate: float = Field(default=0.0, ge=0, le=0.5)


class EnergyCertificationResponse(BaseModel):
    """Energy grade and certification response."""

    energy_grade: str
    zeb_grade: str
    annual_energy_demand_kwh: float
    annual_renewable_generation_kwh: float
    energy_independence_rate: float
    bems_saving_rate: float
    bems_saving_kwh: float
    recommendations: list[str] = Field(default_factory=list)
    # 표준 근거 블록(#5): 에너지등급·ZEB·수요량 산식·출처를 가산(graceful·선택). 미부착 시 None.
    evidence: dict | None = Field(default=None)


class ChatbotSessionCreateRequest(BaseModel):
    """Request model for creating a chatbot session."""

    project_id: UUID | None = None
    domain: str = Field(default="general", max_length=40)
    title: str | None = Field(default=None, max_length=200)
    model_name: str = Field(default="claude-sonnet-4-5")


class ChatbotMessageRequest(BaseModel):
    """Request model for sending a chatbot message."""

    session_id: UUID
    content: str = Field(min_length=1, max_length=4000)


class ChatbotSessionResponse(BaseModel):
    """Response model for a chatbot session."""

    session_id: UUID
    project_id: UUID | None = None
    domain: str
    title: str
    message_count: int
    total_tokens: int
    model_name: str
    last_activity_at: datetime
    created_at: datetime


class ChatbotMessageResponse(BaseModel):
    """Response model for a chatbot message."""

    message_id: UUID
    session_id: UUID
    role: str
    content: str
    token_count: int
    sequence_number: int
    created_at: datetime


class ChatbotConversationResponse(BaseModel):
    """Chatbot conversation detail response."""

    session: ChatbotSessionResponse
    messages: list[ChatbotMessageResponse] = Field(default_factory=list)


class ChatbotReplyResponse(BaseModel):
    """Chatbot reply response including user and assistant messages."""

    session: ChatbotSessionResponse
    user_message: ChatbotMessageResponse
    assistant_message: ChatbotMessageResponse


class AuctionAnalysisRequest(BaseModel):
    """Request model for auction analysis."""

    project_id: UUID | None = None
    auction_type: str = Field(default="court_auction", max_length=30)
    case_number: str = Field(min_length=1, max_length=100)
    court_name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=300)
    property_type: str = Field(default="residential", max_length=40)
    appraised_value_krw: float = Field(gt=0)
    minimum_bid_krw: float = Field(gt=0)
    bid_count: int = Field(default=0, ge=0)
    auction_date: datetime | None = None
    occupancy_status: str = Field(default="unknown", max_length=30)
    senior_lien_exists: bool = False
    expected_repair_cost_krw: float = Field(default=0.0, ge=0)
    nearby_market_price_krw: float | None = Field(default=None, gt=0)


class AuctionListingResponse(BaseModel):
    """Response model for an analyzed auction listing."""

    listing_id: UUID
    project_id: UUID | None = None
    auction_type: str
    case_number: str
    court_name: str
    address: str
    property_type: str
    appraised_value_krw: float
    minimum_bid_krw: float
    bid_count: int
    auction_date: datetime | None = None
    status: str
    discount_ratio: float
    market_gap_ratio: float
    investment_score: float
    recommended_max_bid_krw: float
    expected_margin_krw: float
    diligence_flags: list[str] = Field(default_factory=list)
    created_at: datetime


class ContractorCreateRequest(BaseModel):
    """Request model for creating or updating a contractor."""

    company_name: str = Field(min_length=1, max_length=200)
    business_number: str = Field(min_length=10, max_length=20)
    category: str = Field(default="general_contractor", max_length=60)
    specialties: list[str] = Field(default_factory=list)
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    notes: str | None = None


class ContractorResponse(BaseModel):
    """Response model for a contractor."""

    contractor_id: UUID
    company_name: str
    business_number: str
    category: str
    specialties: list[str] = Field(default_factory=list)
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None
    rating: float | None = None
    is_active: bool
    created_at: datetime


class ContractorRecommendationRequest(BaseModel):
    """Request model for contractor recommendations."""

    project_id: UUID | None = None
    category: str = Field(default="general_contractor", max_length=60)
    required_specialties: list[str] = Field(default_factory=list)
    region_hint: str | None = None
    max_results: int = Field(default=5, ge=1, le=20)


class ContractorRecommendationItem(BaseModel):
    """Ranked contractor recommendation item."""

    contractor_id: UUID
    company_name: str
    category: str
    specialties: list[str] = Field(default_factory=list)
    rating: float | None = None
    match_score: float
    reasons: list[str] = Field(default_factory=list)


class ContractorRecommendationResponse(BaseModel):
    """Response model for contractor recommendations."""

    category: str
    recommendations: list[ContractorRecommendationItem] = Field(default_factory=list)


class MaterialPriceRefreshRequest(BaseModel):
    """Request model for refreshing material price snapshots."""

    project_id: UUID | None = None
    region_code: str = Field(default="KR", min_length=2, max_length=20)
    material_codes: list[str] = Field(default_factory=list)


class MaterialPriceHistoryPointResponse(BaseModel):
    """Single historical material price point."""

    snapshot_at: datetime
    unit_price_krw: float
    price_index: float
    mom_change_ratio: float
    source_name: str


class MaterialPriceItemResponse(BaseModel):
    """Material price trend response item."""

    material_code: str
    material_name: str
    category: str
    unit: str
    current_unit_price_krw: float
    latest_price_index: float
    mom_change_ratio: float
    yoy_change_ratio: float
    estimated_project_cost_krw: float | None = None
    alert_level: str
    history: list[MaterialPriceHistoryPointResponse] = Field(default_factory=list)


class MaterialPriceAlertResponse(BaseModel):
    """Material price alert summary."""

    material_code: str
    severity: str
    title: str
    detail: str


class MaterialPriceSnapshotResponse(BaseModel):
    """Latest material price response including trend and alert summary."""

    as_of: datetime
    project_id: UUID | None = None
    region_code: str
    items: list[MaterialPriceItemResponse] = Field(default_factory=list)
    alerts: list[MaterialPriceAlertResponse] = Field(default_factory=list)


class CostEscalationRequest(BaseModel):
    """Request model for project-level cost escalation analysis."""

    project_id: UUID
    base_construction_cost_krw: float = Field(gt=0)
    baseline_year: int = Field(ge=2020, le=2100)
    target_year: int = Field(ge=2020, le=2105)
    construction_duration_months: int = Field(default=18, ge=1, le=120)
    material_share_ratio: float = Field(default=0.62, ge=0, le=1)
    labor_share_ratio: float = Field(default=0.28, ge=0, le=1)
    overhead_share_ratio: float = Field(default=0.10, ge=0, le=1)
    contingency_ratio: float = Field(default=0.07, ge=0, le=0.5)
    region_code: str = Field(default="KR", min_length=2, max_length=20)
    material_codes: list[str] = Field(default_factory=list)


class CostEscalationYearResponse(BaseModel):
    """Yearly PPI escalation projection."""

    year: int
    ppi_index: float
    escalation_ratio: float
    projected_cost_krw: float


class CostEscalationMaterialImpactResponse(BaseModel):
    """Material-specific contribution to escalation."""

    material_code: str
    material_name: str
    weight_ratio: float
    baseline_unit_price_krw: float
    latest_unit_price_krw: float
    delta_ratio: float
    cost_impact_krw: float


class CostEscalationAlertResponse(BaseModel):
    """Escalation alert summary."""

    severity: str
    title: str
    detail: str


class CostEscalationResponse(BaseModel):
    """Project-level cost escalation response."""

    id: UUID
    project_id: UUID
    baseline_year: int
    target_year: int
    construction_duration_months: int
    base_construction_cost_krw: float
    adjusted_cost_krw: float
    escalation_amount_krw: float
    overall_escalation_ratio: float
    contingency_ratio: float
    contingency_amount_krw: float
    ppi_source: str
    material_impacts: list[CostEscalationMaterialImpactResponse] = Field(default_factory=list)
    yearly_projection: list[CostEscalationYearResponse] = Field(default_factory=list)
    alerts: list[CostEscalationAlertResponse] = Field(default_factory=list)
    summary: str
    created_at: datetime
    # ── 표준 근거 블록(#5 evidence) ──
    evidence: dict | None = Field(default=None, description="표준 근거 블록(evidence·legal_refs·provenance·trust)")


class DigitalTwinStatusRequest(BaseModel):
    """Request model for persisted digital twin status snapshots."""

    project_id: UUID
    building_type: str = Field(default="office", max_length=40)
    gross_floor_area_sqm: float = Field(gt=0)
    annual_energy_kwh: float = Field(gt=0)
    occupancy_rate: float = Field(default=0.92, ge=0, le=1)
    sensor_count: int = Field(default=24, ge=1, le=5000)
    online_sensor_count: int = Field(default=24, ge=0, le=5000)
    critical_alarm_count: int = Field(default=0, ge=0, le=500)
    recent_outdoor_temps_c: list[float] = Field(default_factory=list)
    recent_energy_readings_kwh: list[float] = Field(default_factory=list)
    target_outdoor_temp_c: float | None = None


class DigitalTwinStatusResponse(BaseModel):
    """Response model for the latest digital twin status snapshot."""

    snapshot_id: UUID
    project_id: UUID
    project_name: str
    building_type: str
    status: str
    operational_readiness_score: float
    eui: float
    eui_grade: str
    benchmark_eui: float
    sensor_health_ratio: float
    occupancy_rate: float
    recent_anomaly_count: int
    highest_anomaly_severity: str
    critical_alarm_count: int
    predicted_next_day_energy_kwh: float | None = None
    recommendations: list[str] = Field(default_factory=list)
    created_at: datetime


class UnifiedRiskAssessmentRequest(BaseModel):
    """Request model for unified v53 risk analysis."""

    project_id: UUID
    base_project_cost_krw: float = Field(gt=0)
    market_risk_score: float = Field(ge=0, le=100)
    ltv_ratio: float = Field(ge=0, le=1)
    dscr: float = Field(gt=0, le=5)
    permit_readiness_ratio: float = Field(default=0.0, ge=0, le=1)
    occupancy_rate: float = Field(ge=0, le=1)
    presale_ratio: float = Field(default=0.0, ge=0, le=1)
    climate_risk_score: float = Field(ge=0, le=100)
    cost_volatility_ratio: float = Field(ge=0, le=1)


class RiskDimensionScoreResponse(BaseModel):
    """Single risk dimension score item."""

    dimension: str
    score: float
    weight: float
    rationale: str


class UnifiedRiskAssessmentResponse(BaseModel):
    """Response model for unified v53 risk scoring."""

    assessment_id: UUID
    project_id: UUID
    composite_risk_score: float
    grade: str
    var_95_ratio: float
    p90_adjusted_cost_krw: float
    expected_downside_krw: float
    dimension_scores: list[RiskDimensionScoreResponse] = Field(default_factory=list)
    summary: str
    created_at: datetime


class PermitSubmissionRequest(BaseModel):
    """Request model for permit submission and readiness tracking."""

    project_id: UUID
    permit_type: str = Field(default="building_permit", max_length=50)
    region: str = Field(default="seoul", max_length=50)
    building_area_sqm: float = Field(gt=0)
    is_public: bool = False
    is_agricultural: bool = False
    applicant_name: str | None = Field(default=None, max_length=120)
    submit_to_seumter: bool = True
    submitted_document_ids: list[str] = Field(default_factory=list)


class PermitChecklistItemResponse(BaseModel):
    """Single permit checklist item."""

    id: str
    name: str
    required: bool
    applicable: bool
    submitted: bool


class PermitStatusResponse(BaseModel):
    """Response model for permit status and tracking."""

    submission_id: UUID
    project_id: UUID
    permit_type: str
    region: str
    submission_reference: str
    status: str
    current_stage: str
    progress_pct: float
    readiness_score: float
    estimated_business_days: int
    estimated_calendar_days: int
    missing_required_documents: list[str] = Field(default_factory=list)
    checklist: list[PermitChecklistItemResponse] = Field(default_factory=list)
    summary: str
    submitted_at: datetime | None = None
    created_at: datetime


class ContractGenerationRequest(BaseModel):
    """Request model for project-scoped contract draft generation."""

    project_id: UUID
    contract_type: str = Field(default="construction", max_length=50)
    target_language: str = Field(default="ko", max_length=10)
    counterparty_name: str = Field(min_length=1, max_length=120)
    effective_date: datetime
    contract_amount_krw: float | None = Field(default=None, ge=0)
    special_clauses: list[str] = Field(default_factory=list)


class ContractESignRequest(BaseModel):
    """Request model for handing a generated draft into e-sign."""

    signer_name: str = Field(min_length=1, max_length=100)
    signer_email: str = Field(min_length=3, max_length=255)
    signer_phone: str | None = Field(default=None, max_length=30)


class ContractKeyTermResponse(BaseModel):
    """Single key-term item for generated contracts."""

    label: str
    value: str


class ContractClauseResponse(BaseModel):
    """Single clause item for generated contracts."""

    title: str
    body: str


class ContractDraftResponse(BaseModel):
    """Response model for generated contract drafts."""

    draft_id: UUID
    project_id: UUID
    project_name: str
    contract_type: str
    target_language: str
    title: str
    counterparty_name: str
    effective_date: datetime
    contract_amount_krw: float | None = None
    document_url: str
    status: str
    sign_status: str
    key_terms: list[ContractKeyTermResponse] = Field(default_factory=list)
    clauses: list[ContractClauseResponse] = Field(default_factory=list)
    summary: str
    rendered_markdown: str
    esign_request_id: UUID | None = None
    created_at: datetime
