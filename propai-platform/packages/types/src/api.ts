// PropAI v30.0 - API 응답/요청 타입 (packages/schemas/models.py 미러)

import type {
  ProjectStatus,
  EscrowStatus,
  UserRole,
  DesignType,
  TaskStatus,
  DefectSeverity,
  TaxType,
} from './enums';

// ── 공통 응답 래퍼 ──

export interface ApiResponse<T = unknown> {
  success: boolean;
  message?: string | null;
  data?: T | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface ErrorResponse {
  success: false;
  error_code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

// ── 인증 ──

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface UserResponse {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

// ── 프로젝트 ──

export interface ProjectResponse {
  id: string;
  tenant_id: string;
  name: string;
  status: ProjectStatus;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
}

export interface ProjectUpdateRequest {
  name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  total_area_sqm?: number | null;
  description?: string | null;
}

// ── 부지 분석 ──

export interface SiteAnalysisResponse {
  id: string;
  project_id: string;
  pnu: string;
  land_use_zone?: string | null;
  building_coverage_ratio?: number | null;
  floor_area_ratio?: number | null;
  land_area_sqm?: number | null;
  official_land_price?: number | null;
  created_at: string;
}

// ── AVM 감정 평가 ──

export interface AVMValuationResponse {
  id: string;
  project_id: string;
  estimated_price: number;
  price_per_sqm: number;
  confidence_score: number;
  comparable_count: number;
  model_version: string;
  created_at: string;
}

// ── 수익성 분석 ──

export interface FeasibilityResponse {
  id: string;
  project_id: string;
  total_project_cost: number;
  total_revenue: number;
  net_profit: number;
  irr?: number | null;
  npv?: number | null;
  payback_period_months?: number | null;
  created_at: string;
}

// ── 설계 ──

export interface DesignResponse {
  id: string;
  project_id: string;
  design_type: DesignType;
  file_url?: string | null;
  thumbnail_url?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// ── 인허가 ──

export interface PermitResponse {
  id: string;
  project_id: string;
  permit_type: string;
  status: string;
  submitted_at?: string | null;
  approved_at?: string | null;
  tracking_number?: string | null;
}

// ── 에스크로 ──

export interface EscrowTransactionResponse {
  id: string;
  project_id: string;
  status: EscrowStatus;
  amount_wei: string;
  on_chain_escrow_id?: number | null;
  tx_hash?: string | null;
  contract_address?: string | null;
  buyer_address: string;
  seller_address: string;
  created_at: string;
}

// ── 드론 ──

export interface DroneInspectionResponse {
  id: string;
  project_id: string;
  inspection_date: string;
  defects_found: number;
  defects: Record<string, unknown>[];
  severity_summary: Record<string, number>;
  images_processed: number;
  created_at: string;
}

export interface DefectResponse {
  id: string;
  inspection_id: string;
  severity: DefectSeverity;
  description: string;
  location_x: number;
  location_y: number;
  image_url: string;
  confidence: number;
}

// ── 비동기 태스크 ──

export interface TaskResponse {
  task_id: string;
  status: TaskStatus;
  result?: unknown;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
}

// ── 법규 검토 ──

export interface RegulationCheckResponse {
  id: string;
  project_id: string;
  regulation_type: string;
  is_compliant: boolean;
  violations: Record<string, unknown>[];
  recommendations: string[];
  confidence_score: number;
  source_documents: string[];
  created_at: string;
}

// ── 세금 계산 ──

export interface TaxCalculationResponse {
  id: string;
  project_id: string;
  tax_type: TaxType;
  amount: number;
  taxable_value: number;
  tax_rate: number;
  deductions: Record<string, unknown>[];
  optimization_tips: string[];
  created_at: string;
}

// ── 수지분석 v2 ──

export interface FeasibilityAnalysisRequest {
  project_id: string;
  scenario_name?: string;
  total_investment_krw: number;
  annual_revenue_krw: number;
  annual_operating_cost_krw: number;
  discount_rate?: number;
  annual_growth_rate?: number;
  analysis_years?: number;
  exit_value_krw?: number | null;
}

export interface FeasibilityCashflowRow {
  year: number;
  revenue_krw: number;
  operating_cost_krw: number;
  net_cashflow_krw: number;
  discounted_cashflow_krw: number;
}

export interface FeasibilityAnalysisResponse {
  id: string;
  project_id: string;
  scenario_name?: string | null;
  npv: number;
  irr: number;
  payback_period_months: number;
  total_investment_krw: number;
  total_revenue_krw: number;
  risk_score: number;
  discount_rate: number;
  annual_growth_rate: number;
  analysis_years: number;
  exit_value_krw: number;
  cashflows: FeasibilityCashflowRow[];
  assumptions: Record<string, unknown>;
  created_at: string;
}

// ── 몬테카를로 시뮬레이션 ──

export interface MonteCarloRequest {
  project_id: string;
  base_npv: number;
  base_irr: number;
  simulations?: number;
  revenue_std_ratio?: number;
  cost_std_ratio?: number;
}

export interface MonteCarloResponse {
  project_id: string;
  simulations: number;
  npv_mean: number;
  npv_std: number;
  npv_p5: number;
  npv_p95: number;
  irr_mean: number;
  irr_std: number;
  probability_positive_npv: number;
}

// ── BIM 물량산출 ──

export interface BIMQuantityResponse {
  id: string;
  project_id: string;
  total_volume_m3: number;
  total_area_sqm: number;
  material_breakdown: Record<string, unknown>[];
  element_count: number;
  ifc_version: string;
  created_at: string;
}

// ── 시공 일정 ──

export interface ConstructionScheduleRequest {
  project_id: string;
  total_area_sqm: number;
  floors_above: number;
  floors_below?: number;
  structure_type?: string;
}

export interface ConstructionScheduleResponse {
  total_duration_days: number;
  schedule: Record<string, unknown>[];
  critical_path: string[];
  milestones: Record<string, unknown>[];
}

// ── 탄소 배출량 ──

export interface CarbonCalculationRequest {
  project_id: string;
  material_breakdown: Record<string, unknown>[];
  total_area_sqm: number;
}

export interface CarbonCalculationResponse {
  total_embodied_carbon: number;
  total_operational_carbon: number;
  total_carbon: number;
  breakdown: Record<string, unknown>[];
  reduction_tips: string[];
}

// ── 전세 리스크 ──

export interface JeonseRiskRequest {
  project_id: string;
  address: string;
  jeonse_price: number;
  sale_price: number;
}

export interface JeonseRiskResponse {
  jeonse_ratio: number;
  risk_level: string;
  risk_score: number;
  analysis: string;
  factors: Record<string, unknown>[];
}

// ── 조합원 분담금 ──

export interface UnionContributionRequest {
  project_id: string;
  total_project_cost: number;
  total_appraised_value: number;
  individual_appraised_value: number;
  target_area_sqm: number;
  avg_sale_price_per_sqm: number;
}

export interface UnionContributionResponse {
  proportional_rate: number;
  individual_contribution: number;
  total_project_cost: number;
  breakdown: Record<string, unknown>;
  scenarios: Record<string, unknown>[];
}

// ── 기후 리스크 (통합) ──

export interface ClimateRiskAssessmentRequest {
  project_id: string;
  lat: number;
  lon: number;
  asset_value_krw: number;
  construction_period_months?: number;
}

export interface ClimateRiskAssessmentResponse {
  assessment_id: string;
  project_id: string;
  flood_risk_score: number;
  heat_risk_score: number;
  overall_risk_level: string;
  annual_expected_loss_krw: number;
  risk_factors: Record<string, unknown>[];
  mitigation_tips: string[];
  insurance_recommendations: Record<string, unknown>[];
  created_at: string;
}

// ── 에스크로 요청 ──

export interface CreateEscrowRequest {
  project_id: string;
  payee_address: string;
  payer_address: string;
  subcontractor_address?: string;
  expires_at: number;
  condition_hash: string;
}

export interface FundEscrowRequest {
  on_chain_escrow_id: number;
  amount_wei: string;
}

export interface ReleaseEscrowRequest {
  on_chain_escrow_id: number;
}

// ── 도메인 에이전트 ──

export interface DomainAgentRunRequest {
  project_id: string;
  domain: string;
  question: string;
  context?: Record<string, unknown>;
  approval_role?: string;
}

export interface DomainAgentRunResponse {
  task_id: string;
  project_id: string;
  domain: string;
  status: string;
  confidence_score: number;
  recommendation: string;
  findings: Record<string, unknown>[];
  approval_required: boolean;
  approval_status: string;
}

export interface DomainMultiAnalysisResponse {
  items: DomainAgentRunResponse[];
  portfolio_summary: string;
}

// ── 계약서 생성 ──

export interface ContractDraftResponse {
  draft_id: string;
  project_id: string;
  project_name: string;
  contract_type: string;
  target_language: string;
  title: string;
  counterparty_name: string;
  effective_date: string;
  contract_amount_krw?: number | null;
  document_url: string;
  status: string;
  sign_status: string;
  key_terms: Record<string, unknown>[];
  clauses: Record<string, unknown>[];
  summary: string;
  rendered_markdown: string;
  esign_request_id?: string | null;
  created_at: string;
}

// ── 디지털 트윈 ──

export interface DigitalTwinStatusResponse {
  snapshot_id: string;
  project_id: string;
  project_name: string;
  building_type: string;
  status: string;
  operational_readiness_score: number;
  eui: number;
  eui_grade: string;
  benchmark_eui: number;
  sensor_health_ratio: number;
  occupancy_rate: number;
  recent_anomaly_count: number;
  highest_anomaly_severity: string;
  critical_alarm_count: number;
  predicted_next_day_energy_kwh?: number | null;
  recommendations: string[];
  created_at: string;
}

// ── 통합 리스크 ──

export interface UnifiedRiskAssessmentResponse {
  assessment_id: string;
  project_id: string;
  composite_risk_score: number;
  grade: string;
  var_95_ratio: number;
  p90_adjusted_cost_krw: number;
  expected_downside_krw: number;
  dimension_scores: Record<string, unknown>[];
  summary: string;
  created_at: string;
}

// ── 인허가 상태 ──

export interface PermitStatusResponse {
  submission_id: string;
  project_id: string;
  permit_type: string;
  region: string;
  submission_reference: string;
  status: string;
  current_stage: string;
  progress_pct: number;
  readiness_score: number;
  estimated_business_days: number;
  estimated_calendar_days: number;
  missing_required_documents: string[];
  checklist: Record<string, unknown>[];
  summary: string;
  submitted_at?: string | null;
  created_at: string;
}

// ── 대시보드 ──

export interface DashboardStatsResponse {
  total_projects: number;
  projects_by_status: Record<string, number>;
  active_webhooks: number;
  active_api_keys: number;
  ai_cost_month_usd: number;
  ai_tokens_month: number;
}

// ── 웹훅 ──

export interface WebhookCreateRequest {
  url: string;
  events: string[];
  description?: string | null;
}

export interface WebhookResponse {
  id: string;
  tenant_id: string;
  url: string;
  events?: string[] | null;
  is_active: boolean;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

// ── API 키 ──

export interface APIKeyCreateRequest {
  name: string;
  scopes?: string[] | null;
  expires_at?: string | null;
}

export interface APIKeyCreateResponse {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
  scopes?: string[] | null;
  created_at: string;
}

export interface APIKeyResponse {
  id: string;
  name: string;
  key_prefix: string;
  scopes?: string[] | null;
  is_active: boolean;
  last_used_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}
