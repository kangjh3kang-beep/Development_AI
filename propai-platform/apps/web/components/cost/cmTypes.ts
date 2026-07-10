/**
 * CM Phase1 — 원가(Track A) 응답 스키마 타입.
 * 백엔드 /api/v1/cost: BOQ(상세적산)·대안설계 원가비교(D1)·단가 SSOT 3중(D4).
 * 계약 출처: _workspace/24_backend_cm_mvp.md (§6 프론트/QA 정합).
 */

/** BOQ 항목(공종별 물량·단가·금액 + D4 3중·출처 배지). */
export interface BoqItem {
  code: string;
  name: string;
  work_type: string;
  quantity: number;
  unit: string;
  unit_price: number;
  amount: number;
  price_source: string;
  price_basis_year: number | null;
  qto_source: string; // bim(±5%) | derived(±12%)
  standard_unit_price?: number | null;
  market_unit_price?: number | null;
  /** T5 정직화: market_unit_price 출처("simulation" = 결정론 시뮬레이션, 실시세 API 아님). */
  market_unit_price_source?: string | null;
  actual_unit_price?: number | null;
  /** P2 T2: 공종분류 SSOT 대공종(work_breakdown) — 매핑 없으면 null(정직). */
  wb_code?: string | null;
  wb_name?: string | null;
}

/** BOQ 요약(직접·간접·총·신뢰등급). */
export interface BoqSummary {
  direct: number;
  indirect: number;
  total: number;
  confidence_grade: string;
  confidence_band?: string;
  total_project_cost?: number;
}

/** BOQ 배지(정직성 note·출처·신뢰구간). */
export interface BoqBadges {
  note?: string;
  qto_source?: string;
  confidence_band?: string;
  actual_data?: string;
}

/** POST /{pid}/boq 응답. */
export interface BoqResponse {
  ok: boolean;
  estimate_id: string | null;
  items: BoqItem[];
  summary: BoqSummary;
  badges: BoqBadges;
  ai_cost_analysis?: string | null;
}

/** GET /{pid}/estimates 목록 1건(요약) — T5 저장된 적산 목록. */
export interface BoqEstimateListItem {
  estimate_id: string;
  building_type: string;
  structure_type: string;
  total_gfa_sqm: number;
  total_won: number;
  confidence_grade: string;
  created_at: string;
}

/** GET /{pid}/estimates 응답. */
export interface BoqEstimatesListResponse {
  ok: boolean;
  items: BoqEstimateListItem[];
}

/** 단가 SSOT 3중(D4) 항목. */
export interface UnitPriceItem {
  code: string;
  name: string;
  unit: string;
  standard: number;
  market: number | null;
  actual: number | null;
  source: string;
  basis_year: number | null;
  region?: string | null;
  /** T5 정직화: market 값 출처("simulation" = KCCI 결정론 시뮬레이션, 실시세 API 아님). */
  market_source?: string | null;
  /** P1 T4: 단가 4계층 리졸버 tier(T1_public/T2_standard/T3_fallback). */
  tier?: string | null;
  source_url?: string | null;
  /** P2 T4: 재료/노무/경비 3분해(표준단가 프리필용, additive). */
  mat_unit?: number | null;
  labor_unit?: number | null;
  exp_unit?: number | null;
}

/** GET /unit-prices 응답. */
export interface UnitPricesResponse {
  ok: boolean;
  items: UnitPriceItem[];
  note?: string;
}

/** 대안설계 변형 결과(D1). */
export interface AlternativeVariantResult {
  label: string;
  total: number;
  delta: number;
  delta_pct: number;
  affected_work_types: string[];
  rationale: string;
}

/** POST /{pid}/alternatives 응답. */
export interface AlternativesResponse {
  ok: boolean;
  base: { total: number };
  variants: AlternativeVariantResult[];
  note?: string;
}

/* ── D2 — 기성고 EVM + 과다청구 이상탐지 ────────────────────────────────── */

/** 회차별 기성 청구 1건(영속 + 해시체인). */
export interface BillingClaim {
  round: number;
  work_type: string;
  contract_amount: number;
  claimed_amount: number;
  claimed_qty?: number | null;
  unit_price?: number | null;
  contract_unit_price?: number | null;
  progress_pct: number;
  period: string;
  ledger_hash?: string | null;
}

/** EVM 누적 곡선 1포인트. */
export interface EvmCurvePoint {
  round: number;
  pv: number;
  ev: number;
  ac: number;
}

/** EVM 요약(spi/cpi는 PV/AC=0 시 null). */
export interface EvmSummary {
  pv: number;
  ev: number;
  ac: number;
  spi: number | null;
  cpi: number | null;
  curve: EvmCurvePoint[];
}

/** 과다청구 이상탐지 경고. */
export interface BillingAnomaly {
  level: string; // high | warn
  type: string;
  detail: string;
  evidence?: Record<string, unknown> | string | number | null;
}

/** 정직성 배지(검토 권장·확정 아님 + 출처·임계치). */
export interface BillingBadges {
  note?: string;
  unit_price_source?: string;
  thresholds?: Record<string, unknown>;
  data?: string; // no_data 등
}

/** GET /{pid}/billing 응답. */
export interface BillingSummaryResponse {
  ok: boolean;
  status?: string;
  contract_total: number;
  claims: BillingClaim[];
  evm: EvmSummary;
  anomalies: BillingAnomaly[];
  badges: BillingBadges;
}

/** POST /{pid}/billing 응답. */
export interface BillingRegisterResponse {
  ok: boolean;
  claim_id?: string;
  ledger_hash?: string | null;
  anomalies_triggered: BillingAnomaly[];
}

/** POST /{pid}/billing 요청. */
export interface BillingRegisterRequest {
  round: number;
  work_type: string;
  contract_amount: number;
  claimed_amount: number;
  claimed_qty?: number;
  unit_price?: number;
  contract_unit_price?: number;
  progress_pct: number;
  period: string;
}

/** 대안설계 요청 변형 입력. */
export interface AlternativeVariantInput {
  label: string;
  overrides: {
    structure_type?: string;
    floor_count_above?: number;
    floor_count_below?: number;
    total_gfa_sqm?: number;
  };
}

/* ── P4 T1 — 절감 시나리오 Top-N ──────────────────────────────────────────── */

/** 절감 후보의 영향 공종 1건(WB 브리지 병기). */
export interface SavingAffectedItem {
  name: string;
  wb_code?: string | null;
  wb_name?: string | null;
  delta_amount: number;
}

/** 절감 시나리오 후보 1건(랭킹된 결과). */
export interface SavingCandidate {
  label: string;
  rationale: string;
  overrides: Record<string, string | number>;
  total: number;
  delta: number;
  delta_pct: number;
  savings: number;
  affected_work_types: string[];
  affected: SavingAffectedItem[];
  tradeoff: string;
}

/** POST /{pid}/saving-scenarios 응답. */
export interface SavingScenariosResponse {
  ok: boolean;
  project_id: string;
  base_total: number;
  top_n: number;
  evaluated_count: number;
  saving_count: number;
  candidates: SavingCandidate[];
  note?: string;
}

/* ── P4 T2 — 설계변경 예측공사비 ──────────────────────────────────────────── */

/** 몬테카를로 추가공사비 밴드(base 대비 총액 분포). */
export interface ChangeForecastMcBand {
  base_total: number;
  p10: number;
  p50: number;
  p90: number;
  mean: number;
  std: number;
}

/** 리스크 1건 → 공종(WB) delta 시나리오. */
export interface ChangeForecastScenario {
  risk_item: string;
  risk_category?: string | null;
  severity?: string | null;
  wb_targets: string[];
  wb_names: (string | null)[];
  wb_base_amount: number;
  delta_pct_low: number;
  delta_pct_high: number;
  delta_low: number;
  delta_high: number;
  basis: string;
}

/** POST /{pid}/change-forecast 응답. */
export interface ChangeForecastResponse {
  ok: boolean;
  project_id: string;
  base_total: number;
  mc_band: ChangeForecastMcBand;
  scenarios: ChangeForecastScenario[];
  data_gaps: string[];
  note?: string;
}

/** POST /{pid}/change-forecast 요청 risks[] 항목(design_change_predictor risks[]와 동일 계약). */
export interface ChangeForecastRiskInput {
  category?: string;
  item: string;
  severity?: string;
  current?: string | null;
  limit?: string | null;
  detail?: string;
  remedy?: string;
  est_impact?: string | null;
}
