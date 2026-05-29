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

// ── 프로젝트 (추가) ──

export interface ProjectStatusUpdateRequest {
  status: ProjectStatus;
}

// ── 웹훅 (추가) ──

export interface WebhookUpdateRequest {
  url?: string | null;
  events?: string[] | null;
  is_active?: boolean | null;
  description?: string | null;
}

export interface WebhookDeliveryResponse {
  id: string;
  webhook_id: string;
  event_type: string;
  status_code?: number | null;
  success: boolean;
  attempt: number;
  duration_ms?: number | null;
  created_at: string;
}

// ── 알림톡/전자서명 ──

export interface AlimTalkRequest {
  project_id?: string | null;
  recipient_phone: string;
  template_code: string;
  message: string;
  payload?: Record<string, unknown> | null;
}

export interface NotificationResponse {
  id: string;
  project_id?: string | null;
  channel: string;
  recipient_phone: string;
  template_code: string;
  status: string;
  external_ref?: string | null;
  sent_at?: string | null;
  created_at: string;
}

export interface ESignCreateRequest {
  project_id?: string | null;
  document_name: string;
  document_url: string;
  signer_name: string;
  signer_email: string;
  signer_phone?: string | null;
}

export interface ESignResponse {
  id: string;
  project_id?: string | null;
  document_name: string;
  document_url: string;
  signer_name: string;
  signer_email: string;
  signer_phone?: string | null;
  provider: string;
  status: string;
  external_request_id?: string | null;
  requested_at: string;
  completed_at?: string | null;
  created_at: string;
}

// ── AVM (추가) ──

export interface AVMRequest {
  project_id: string;
  address: string;
  area_sqm: number;
  building_age_years?: number | null;
  floor?: number | null;
  total_floors?: number | null;
  lawd_cd?: string | null;
  pnu?: string | null;
}

// ── 재무 분석 ──

export interface FinancialAnalysisResponse {
  id: string;
  project_id: string;
  npv: number;
  irr: number;
  payback_period_months: number;
  total_investment: number;
  total_revenue: number;
  risk_score: number;
  created_at: string;
}

// ── 블록체인/에스크로 (추가) ──

export interface DisputeEscrowRequest {
  on_chain_escrow_id: number;
  reason_hash: string;
}

export interface DirectPaymentRequest {
  on_chain_escrow_id: number;
  subcontractor_address: string;
  gross_amount_wei: string;
}

export interface ResolveDisputeRequest {
  on_chain_escrow_id: number;
  release_to_payee: boolean;
}

export interface OnChainEscrowResponse {
  on_chain_escrow_id: number;
  payer: string;
  payee: string;
  subcontractor: string;
  total_amount_wei: string;
  remaining_amount_wei: string;
  expires_at: number;
  condition_hash: string;
  status: string;
}

// ── 기후 리스크 (단순) ──

export interface ClimateRiskRequest {
  project_id: string;
  lat: number;
  lon: number;
  construction_period_months?: number;
}

export interface ClimateRiskResponse {
  flood_risk_score: number;
  heat_risk_score: number;
  overall_risk_level: string;
  risk_factors: Record<string, unknown>[];
  mitigation_tips: string[];
}

// ── 하자 분류 ──

export interface DefectClassificationRequest {
  project_id: string;
  image_url: string;
  location?: string;
}

export interface DefectClassificationResponse {
  defect_type: string;
  severity: string;
  confidence: number;
  description: string;
  repair_recommendation: string;
}

// ── 에너지/ZEB ──

export interface ZEBEnergyRequest {
  project_id: string;
  total_area_sqm: number;
  floors: number;
  window_wall_ratio?: number;
  insulation_grade?: string;
}

export interface ZEBEnergyResponse {
  annual_energy_demand_kwh: number;
  annual_renewable_generation_kwh: number;
  zeb_grade: string;
  energy_independence_rate: number;
  recommendations: string[];
}

export interface EnergyCertificationRequest {
  project_id: string;
  total_area_sqm: number;
  floors: number;
  window_wall_ratio?: number;
  insulation_grade?: string;
  bems_saving_rate?: number;
}

export interface EnergyCertificationResponse {
  energy_grade: string;
  zeb_grade: string;
  annual_energy_demand_kwh: number;
  annual_renewable_generation_kwh: number;
  energy_independence_rate: number;
  bems_saving_rate: number;
  bems_saving_kwh: number;
  recommendations: string[];
}

export interface KepcoCalculationRequest {
  usage_kwh: number;
  contract_type?: string;
  demand_kw?: number;
}

export interface KepcoCalculationResponse {
  contract_type: string;
  usage_kwh: number;
  demand_kw: number;
  base_charge_krw: number;
  energy_charge_krw: number;
  climate_fund_krw: number;
  fuel_adjustment_krw: number;
  vat_krw: number;
  total_bill_krw: number;
}

// ── 전세 리스크 (이미 존재) ──

// ── 조합원 분담금 (이미 존재) ──

// ── 시스템/대시보드 ──

export interface SystemVersionResponse {
  app_name: string;
  version: string;
  environment: string;
  api_prefixes: string[];
}

export interface SystemHealthResponse {
  status: string;
  version: string;
  environment: string;
  services: Record<string, string>;
  checked_at: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  services: Record<string, unknown>;
}

export interface DashboardTimelinePoint {
  period: string;
  project_count: number;
}

export interface DashboardTimelineResponse {
  items: DashboardTimelinePoint[];
}

export interface DashboardActivityItem {
  category: string;
  action: string;
  resource_id: string;
  resource_name: string;
  occurred_at: string;
}

export interface DashboardRecentActivityResponse {
  items: DashboardActivityItem[];
}

// ── AI 비용 ──

export interface AICostBreakdownItem {
  service_name: string;
  model_name: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface AICostDashboardResponse {
  month: string;
  total_cost_usd: number;
  total_tokens: number;
  by_service: AICostBreakdownItem[];
}

export interface AIBudgetGateResponse {
  endpoint: string;
  monthly_budget_usd: number;
  current_cost_usd: number;
  remaining_budget_usd: number;
  allowed: boolean;
}

export interface AICostBudgetRequest {
  endpoint: string;
  monthly_budget_usd: number;
  month?: string | null;
  alert_threshold_ratio?: number;
}

export interface AICostBudgetResponse {
  budget_id: string;
  endpoint: string;
  month: string;
  monthly_budget_usd: number;
  alert_threshold_ratio: number;
  created_at: string;
}

// ── 투자 심사/언더라이팅 ──

export interface DataRoomDocumentInput {
  file_name: string;
  storage_url: string;
  size_bytes?: number;
  tags: string[];
  parsed_summary?: string | null;
}

export interface UnderwritingRequest {
  project_id: string;
  project_name: string;
  total_cost_krw: number;
  projected_revenue_krw: number;
  acquisition_price_krw: number;
  equity_krw: number;
  debt_krw: number;
  jeonse_ratio?: number | null;
  assumptions_json: Record<string, unknown>;
  data_room_documents: DataRoomDocumentInput[];
}

export interface UnderwritingResponse {
  underwriting_id: string;
  project_id: string;
  project_name: string;
  risk_level: string;
  risk_score: number;
  recommendation: string;
  projected_profit_krw: number;
  profit_margin_ratio: number;
  debt_ratio: number;
  equity_multiple: number;
  jeonse_ratio?: number | null;
  key_risks: Record<string, unknown>[];
  narrative: string;
  created_at: string;
}

// ── 컴플라이언스/KYC/AML ──

export interface ComplianceCheckResponse {
  check_id: string;
  project_id: string;
  check_type: string;
  status: string;
  score?: number | null;
  findings: Record<string, unknown>[];
  remediation_plan?: string | null;
}

export interface KYCDocumentInput {
  document_kind: string;
  file_name: string;
  storage_url: string;
  identifier_masked?: string | null;
}

export interface KYCDocumentResponse {
  document_id: string;
  subject_name: string;
  document_kind: string;
  verified: boolean;
  storage_url: string;
}

export interface AMLScreeningResponse {
  screening_id: string;
  subject_name: string;
  match_status: string;
  risk_level: string;
  matched_lists: string[];
  notes?: string | null;
}

export interface ComplianceScreeningRequest {
  project_id: string;
  subject_name: string;
  check_type?: string;
  transaction_amount_krw: number;
  politically_exposed?: boolean;
  residency_countries: string[];
  documents: KYCDocumentInput[];
}

export interface ComplianceScreeningResponse {
  compliance_check: ComplianceCheckResponse;
  aml_screening: AMLScreeningResponse;
  kyc_documents: KYCDocumentResponse[];
}

// ── 계약/전자서명 ──

export interface ContractGenerationRequest {
  project_id: string;
  contract_type?: string;
  target_language?: string;
  counterparty_name: string;
  effective_date: string;
  contract_amount_krw?: number | null;
  special_clauses: string[];
}

export interface ContractESignRequest {
  signer_name: string;
  signer_email: string;
  signer_phone?: string | null;
}

export interface ContractKeyTermResponse {
  label: string;
  value: string;
}

export interface ContractClauseResponse {
  title: string;
  body: string;
}

// ── 리스/IFRS16 ──

export interface LeaseAbstractionResponse {
  abstraction_id: string;
  project_id: string;
  tenant_name: string;
  lease_type: string;
  area_sqm: number;
  deposit_krw: number;
  monthly_rent_krw: number;
  critical_terms: Record<string, unknown>[];
}

export interface LeaseAnalysisRequest {
  project_id: string;
  source_document_name: string;
  tenant_name: string;
  lease_type: string;
  area_sqm: number;
  deposit_krw?: number;
  monthly_rent_krw?: number;
  start_date: string;
  end_date: string;
  discount_rate?: number;
  critical_terms: Record<string, unknown>[];
  abstraction_text?: string | null;
}

export interface LeaseIFRS16ScheduleResponse {
  schedule_id: string;
  project_id: string;
  lease_term_months: number;
  discount_rate: number;
  rou_asset_krw: number;
  lease_liability_krw: number;
  payment_schedule: Record<string, unknown>[];
}

export interface LeaseAnalysisResponse {
  abstraction: LeaseAbstractionResponse;
  ifrs16_schedule: LeaseIFRS16ScheduleResponse;
}

// ── ESG/GRESB ──

export interface ESGAssessmentRequest {
  project_id: string;
  reporting_period: string;
  gross_floor_area_sqm: number;
  scope1_tco2e?: number;
  scope2_tco2e?: number;
  scope3_tco2e?: number;
  energy_independence_rate?: number;
  climate_risk_score?: number;
  lost_time_incident_rate?: number;
  community_programs_count?: number;
  board_independence_ratio?: number;
  disclosures: Record<string, unknown>[];
}

export interface ESGAssessmentResponse {
  assessment_id: string;
  project_id: string;
  reporting_period: string;
  status: string;
  environmental_score?: number | null;
  social_score?: number | null;
  governance_score?: number | null;
  overall_score?: number | null;
  gresb_rating?: string | null;
  carbon_total_tco2e?: number | null;
  disclosures: Record<string, unknown>[];
  action_plan?: string | null;
}

export interface InsuranceRecommendationResponse {
  recommendation_id: string;
  coverage_type: string;
  priority: string;
  annual_premium_estimate_krw: number;
  coverage_limit_krw: number;
  rationale: string;
}

// ── 포털 연동 ──

export interface PortalPostRequest {
  project_id: string;
  project_name: string;
  region_code: string;
  property_type: string;
  price_krw: number;
  area_sqm: number;
  title: string;
  description: string;
  images: string[];
}

export interface PortalPostResponse {
  listing_id: string;
  project_id: string;
  portal_name: string;
  listing_external_id: string;
  listing_url?: string | null;
  status: string;
  view_count: number;
  inquiry_count: number;
  created_at: string;
}

export interface PortalBatchPostRequest {
  project_id: string;
  project_name: string;
  region_code: string;
  property_type: string;
  price_krw: number;
  area_sqm: number;
  title: string;
  description: string;
  portals: string[];
  images: string[];
}

export interface PortalBatchPostResponse {
  items: PortalPostResponse[];
  success_count: number;
}

export interface PortalMarketDataResponse {
  region_code: string;
  active_listing_count: number;
  average_price_krw: number;
  average_area_sqm: number;
  average_inquiry_count: number;
  top_portals: Record<string, unknown>[];
}

export interface PortalListingCreateRequest {
  project_id: string;
  portal_name: string;
  listing_external_id: string;
  property_type: string;
  price_krw: number;
  area_sqm: number;
  description?: string | null;
  listing_url?: string | null;
}

export interface PortalListingResponse {
  id: string;
  project_id: string;
  portal_name: string;
  listing_external_id: string;
  status: string;
  property_type: string;
  price_krw: number;
  area_sqm: number;
  view_count: number;
  inquiry_count: number;
  published_at: string;
  created_at: string;
}

export interface PortalPerformanceResponse {
  listing_id: string;
  view_count: number;
  inquiry_count: number;
  click_through_rate: number;
  bookmark_count: number;
  ranking_position?: number | null;
  snapshot_date: string;
}

// ── 마케팅 ──

export interface MarketingContentRequest {
  project_id: string;
  project_name: string;
  channel: string;
  asset_type: string;
  target_audience: string;
  tone?: string;
  highlights: string[];
}

export interface MarketingContentResponse {
  content_id: string;
  project_id: string;
  channel: string;
  headline: string;
  body: string;
  call_to_action: string;
  created_at: string;
}

export interface OMReportRequest {
  project_id: string;
  project_name: string;
  asset_type: string;
  investment_highlights: string[];
  target_audience?: string;
  risk_factors: string[];
  output_format?: string;
}

export interface OMReportResponse {
  memorandum_id: string;
  project_id: string;
  title: string;
  executive_summary: string;
  sections: Record<string, unknown>[];
  risk_factors: string[];
  output_format: string;
  created_at: string;
}

// ── 투자자 보고 ──

export interface InvestorReportRequest {
  project_id: string;
  project_name: string;
  target_languages: string[];
  asset_type: string;
  investment_highlights: string[];
  risks: string[];
  include_sections: string[];
}

export interface InvestorReportVariantResponse {
  report_id: string;
  target_language: string;
  title: string;
  quality_score?: number | null;
  translated_text: string;
}

export interface InvestorReportResponse {
  project_id: string;
  report_type: string;
  variants: InvestorReportVariantResponse[];
  generated_sections: string[];
}

// ── 번역 ──

export interface TranslationRequest {
  project_id: string;
  report_type?: string;
  source_language?: string;
  target_language: string;
  source_text: string;
  translation_engine?: string;
}

export interface TranslationResponse {
  id: string;
  project_id: string;
  source_language: string;
  target_language: string;
  translated_text: string;
  translation_engine: string;
  quality_score?: number | null;
  word_count: number;
  created_at: string;
}

// ── KDX 데이터 연동 ──

export interface KDXMetricSnapshot {
  region_code: string;
  metric_type: string;
  value: number;
  currency: string;
  recorded_at: string;
}

export interface KDXTelemetryLogResponse {
  id: string;
  source: string;
  event_type: string;
  status: string;
  created_at: string;
}

export interface KDXOverviewResponse {
  connection_status: string;
  throughput_tps: number;
  data_sync_latency_ms: number;
  latest_metric?: KDXMetricSnapshot | null;
  recent_logs: KDXTelemetryLogResponse[];
}

// ── 챗봇 ──

export interface ChatbotSessionCreateRequest {
  project_id?: string | null;
  domain?: string;
  title?: string | null;
  model_name?: string;
}

export interface ChatbotMessageRequest {
  session_id: string;
  content: string;
}

export interface ChatbotSessionResponse {
  session_id: string;
  project_id?: string | null;
  domain: string;
  title: string;
  message_count: number;
  total_tokens: number;
  model_name: string;
  last_activity_at: string;
  created_at: string;
}

export interface ChatbotMessageResponse {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  token_count: number;
  sequence_number: number;
  created_at: string;
}

export interface ChatbotConversationResponse {
  session: ChatbotSessionResponse;
  messages: ChatbotMessageResponse[];
}

export interface ChatbotReplyResponse {
  session: ChatbotSessionResponse;
  user_message: ChatbotMessageResponse;
  assistant_message: ChatbotMessageResponse;
}

// ── 경매 분석 ──

export interface AuctionAnalysisRequest {
  project_id?: string | null;
  auction_type?: string;
  case_number: string;
  court_name: string;
  address: string;
  property_type?: string;
  appraised_value_krw: number;
  minimum_bid_krw: number;
  bid_count?: number;
  auction_date?: string | null;
  occupancy_status?: string;
  senior_lien_exists?: boolean;
  expected_repair_cost_krw?: number;
  nearby_market_price_krw?: number | null;
}

export interface AuctionListingResponse {
  listing_id: string;
  project_id?: string | null;
  auction_type: string;
  case_number: string;
  court_name: string;
  address: string;
  property_type: string;
  appraised_value_krw: number;
  minimum_bid_krw: number;
  bid_count: number;
  auction_date?: string | null;
  status: string;
  discount_ratio: number;
  market_gap_ratio: number;
  investment_score: number;
  recommended_max_bid_krw: number;
  expected_margin_krw: number;
  diligence_flags: string[];
  created_at: string;
}

// ── 시공/공사 ──

export interface ContractorCreateRequest {
  company_name: string;
  business_number: string;
  category?: string;
  specialties: string[];
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  address?: string | null;
  rating?: number | null;
  notes?: string | null;
}

export interface ContractorResponse {
  contractor_id: string;
  company_name: string;
  business_number: string;
  category: string;
  specialties: string[];
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  address?: string | null;
  rating?: number | null;
  is_active: boolean;
  created_at: string;
}

export interface ContractorRecommendationRequest {
  project_id?: string | null;
  category?: string;
  required_specialties: string[];
  region_hint?: string | null;
  max_results?: number;
}

export interface ContractorRecommendationItem {
  contractor_id: string;
  company_name: string;
  category: string;
  specialties: string[];
  rating?: number | null;
  match_score: number;
  reasons: string[];
}

export interface ContractorRecommendationResponse {
  category: string;
  recommendations: ContractorRecommendationItem[];
}

export interface MaterialPriceRefreshRequest {
  project_id?: string | null;
  region_code?: string;
  material_codes: string[];
}

export interface MaterialPriceHistoryPointResponse {
  snapshot_at: string;
  unit_price_krw: number;
  price_index: number;
  mom_change_ratio: number;
  source_name: string;
}

export interface MaterialPriceItemResponse {
  material_code: string;
  material_name: string;
  category: string;
  unit: string;
  current_unit_price_krw: number;
  latest_price_index: number;
  mom_change_ratio: number;
  yoy_change_ratio: number;
  estimated_project_cost_krw?: number | null;
  alert_level: string;
  history: MaterialPriceHistoryPointResponse[];
}

export interface MaterialPriceAlertResponse {
  material_code: string;
  severity: string;
  title: string;
  detail: string;
}

export interface MaterialPriceSnapshotResponse {
  as_of: string;
  project_id?: string | null;
  region_code: string;
  items: MaterialPriceItemResponse[];
  alerts: MaterialPriceAlertResponse[];
}

export interface CostEscalationRequest {
  project_id: string;
  base_construction_cost_krw: number;
  baseline_year: number;
  target_year: number;
  construction_duration_months?: number;
  material_share_ratio?: number;
  labor_share_ratio?: number;
  overhead_share_ratio?: number;
  contingency_ratio?: number;
  region_code?: string;
  material_codes: string[];
}

export interface CostEscalationYearResponse {
  year: number;
  ppi_index: number;
  escalation_ratio: number;
  projected_cost_krw: number;
}

export interface CostEscalationMaterialImpactResponse {
  material_code: string;
  material_name: string;
  weight_ratio: number;
  baseline_unit_price_krw: number;
  latest_unit_price_krw: number;
  delta_ratio: number;
  cost_impact_krw: number;
}

export interface CostEscalationAlertResponse {
  severity: string;
  title: string;
  detail: string;
}

export interface CostEscalationResponse {
  id: string;
  project_id: string;
  baseline_year: number;
  target_year: number;
  construction_duration_months: number;
  base_construction_cost_krw: number;
  adjusted_cost_krw: number;
  escalation_amount_krw: number;
  overall_escalation_ratio: number;
  contingency_ratio: number;
  contingency_amount_krw: number;
  ppi_source: string;
  material_impacts: CostEscalationMaterialImpactResponse[];
  yearly_projection: CostEscalationYearResponse[];
  alerts: CostEscalationAlertResponse[];
  summary: string;
  created_at: string;
}

// ── 설비/테넌트/자산 ──

export interface MaintenanceAnomalyRequest {
  project_id: string;
  equipment_name: string;
  equipment_type: string;
  location?: string | null;
  vibration_mm_s?: number;
  temperature_c?: number;
  energy_efficiency_ratio?: number;
}

export interface MaintenanceAnomalyResponse {
  alert_id: string;
  project_id: string;
  anomaly_score: number;
  remaining_useful_life_days?: number | null;
  hvac_efficiency_score?: number | null;
  severity: string;
  recommendation: string;
  work_order_id?: string | null;
}

export interface TenantFeedbackRequest {
  project_id: string;
  unit_label?: string | null;
  category: string;
  feedback_text: string;
  satisfaction_rating?: number;
}

export interface TenantFeedbackResponse {
  ticket_id: string;
  project_id: string;
  sentiment_score: number;
  sentiment_label: string;
  ai_reply: string;
  created_at: string;
}

export interface TenantSatisfactionRequest {
  project_id: string;
  promoter_count?: number;
  passive_count?: number;
  detractor_count?: number;
  occupancy_rate?: number;
  arrears_ratio?: number;
}

export interface TenantSatisfactionResponse {
  financial_health_id: string;
  project_id: string;
  nps: number;
  churn_risk_score: number;
  health_grade: string;
  created_at: string;
}

export interface AssetIntelligenceRequest {
  project_id: string;
  base_value_krw: number;
  maintenance_score?: number | null;
  tenant_score?: number | null;
  market_score?: number | null;
  climate_score?: number | null;
}

export interface AssetIntelligenceResponse {
  snapshot_id: string;
  project_id: string;
  composite_score: number;
  grade: string;
  adjusted_value_krw: number;
  component_scores: Record<string, unknown>;
  capex_recommendations: Record<string, unknown>[];
  created_at: string;
}

// ── 디지털 트윈 (추가) ──

export interface DigitalTwinStatusRequest {
  project_id: string;
  building_type?: string;
  gross_floor_area_sqm: number;
  annual_energy_kwh: number;
  occupancy_rate?: number;
  sensor_count?: number;
  online_sensor_count?: number;
  critical_alarm_count?: number;
  recent_outdoor_temps_c: number[];
  recent_energy_readings_kwh: number[];
  target_outdoor_temp_c?: number | null;
}

// ── 리스크 분석 (추가) ──

export interface UnifiedRiskAssessmentRequest {
  project_id: string;
  base_project_cost_krw: number;
  market_risk_score: number;
  ltv_ratio: number;
  dscr: number;
  permit_readiness_ratio?: number;
  occupancy_rate: number;
  presale_ratio?: number;
  climate_risk_score: number;
  cost_volatility_ratio: number;
}

export interface RiskDimensionScoreResponse {
  dimension: string;
  score: number;
  weight: number;
  rationale: string;
}

// ── 인허가 (추가) ──

export interface PermitSubmissionRequest {
  project_id: string;
  permit_type?: string;
  region?: string;
  building_area_sqm: number;
  is_public?: boolean;
  is_agricultural?: boolean;
  applicant_name?: string | null;
  submit_to_seumter?: boolean;
  submitted_document_ids: string[];
}

export interface PermitChecklistItemResponse {
  id: string;
  name: string;
  required: boolean;
  applicable: boolean;
  submitted: boolean;
}

// ── 도메인 에이전트 (추가) ──

export interface DomainMultiAnalysisRequest {
  project_id: string;
  domains: string[];
  question: string;
  context?: Record<string, unknown>;
  approval_role?: string;
}

export interface DomainAgentHistoryItemResponse {
  task_id: string;
  project_id: string;
  domain: string;
  status: string;
  confidence_score: number;
  recommendation: string;
  findings: Record<string, unknown>[];
  approval_required: boolean;
  approval_status: string;
  approver_role?: string | null;
  narrative?: string | null;
  created_at: string;
}

export interface DomainAgentHistoryResponse {
  items: DomainAgentHistoryItemResponse[];
}

export interface DomainAgentApprovalQueueItemResponse {
  approval_id: string;
  task_id: string;
  project_id: string;
  domain: string;
  approver_role: string;
  status: string;
  rationale?: string | null;
  recommendation: string;
  confidence_score: number;
  created_at: string;
  decided_at?: string | null;
}

export interface DomainAgentApprovalQueueResponse {
  items: DomainAgentApprovalQueueItemResponse[];
}

export interface DomainAgentApprovalDecisionRequest {
  decision: string;
  rationale?: string | null;
}

export interface DomainAgentApprovalBatchDecisionRequest {
  project_id: string;
  approval_ids: string[];
  decision: string;
  rationale?: string | null;
}

export interface DomainAgentApprovalBatchDecisionResponse {
  items: DomainAgentApprovalQueueItemResponse[];
  updated_count: number;
}
