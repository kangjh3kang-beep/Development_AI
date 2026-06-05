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
  actual_unit_price?: number | null;
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
