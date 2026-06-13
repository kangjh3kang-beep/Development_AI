/**
 * 시장·인구·소득 분석(MarketInsights) 전용 TypeScript 타입.
 *
 * 백엔드 /market/report 응답(`market_report_service.py` + `market_models.py`)의
 * 실제 구조에 맞춰 정의한다. 신규 필드(연령분포·가구유형·인구이동·소득·data_source 등)는
 * 백엔드가 항상 채워주지 않으므로 **전부 옵셔널**로 두고, 화면에서는 방어적으로 접근한다.
 *
 * 원칙: report:any 제거 · 하위호환(기존 키 무변경) · 신규는 옵셔널 가산.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

/** 데이터 출처 상태 — 'live'(실데이터) / 'fallback'(합성·추정) / 'unavailable'(데이터 없음). */
export type DataSource = "live" | "fallback" | "unavailable";

/** 인구 이동망(SGIS/행안부 기반). top_inflow_regions 항목은 좌표가 없을 수 있다(옵셔널). */
export interface MigrationRegion {
  name?: string;
  ratio?: number; // %
  count?: number; // 명
  /** 좌표는 백엔드가 제공할 때만 채워진다(현재 미제공 가능). 지도 렌더는 좌표가 있을 때만. */
  lat?: number;
  lon?: number;
}

export interface MigrationData {
  target_adm_cd?: string;
  year?: string;
  total_inflow?: number;
  total_outflow?: number;
  net_migration?: number;
  top_inflow_regions?: MigrationRegion[];
}

/** 거주 인구·가구 특성(SGIS 센서스). age_distribution/household_types는 키-값 맵. */
export interface PopulationData {
  target_adm_cd?: string;
  year?: string;
  total_population?: number;
  /** 연령대별 인구 분포. 예: { "20대": 1200, "30대": 1500 } 또는 성별 분해 맵일 수 있음. */
  age_distribution?: Record<string, number | Record<string, number>>;
  /** 가구원수별 분포. 예: { "1인가구": 800, "2인가구": 600 }. */
  household_types?: Record<string, number>;
}

/** 거시 소득 지표(KOSIS). 단위는 만원. */
export interface MacroIncomeData {
  sigungu_cd?: string;
  year?: string;
  avg_income_10k?: number;
  median_income_10k?: number;
  income_bracket_ratio?: Record<string, number>;
}

/** 2단계 민간(K-Atlas) 초정밀 지표. 연동 전에는 null/undefined. */
export interface MicroFinancialData {
  gisId?: string;
  cntCust?: number;
  avgAge?: number;
  avgInc?: number;
  medianInc?: number;
  cntCustEmp?: number;
  avrCreditscore?: number;
  cntCustHOwn?: number;
  sumLoanAmt?: number;
  sumCardAvgAmt3m?: number;
  [key: string]: number | string | null | undefined;
}

/** 통합 인구/소득 프로파일(백엔드 DemographicProfile.model_dump()). */
export interface DemographicProfile {
  source_phase?: number;
  migration?: MigrationData;
  population?: PopulationData;
  macro_income?: MacroIncomeData;
  micro_finance?: MicroFinancialData | null;
  /** 신규(옵셔널): 인구·소득 데이터 출처 상태. 없으면 화면에서 추론. */
  data_source?: DataSource;
}

/** 사업 타당성(Feasibility) 분석. FeasibilityDashboard가 사용하는 구조와 일치. */
export interface FeasibilityAnalysis {
  massing?: {
    land_area_sqm: number;
    gfa_sqm: number;
    gfa_pyeong: number;
    estimated_far: number;
    estimated_bca: number;
  };
  financials?: {
    total_revenue_10k: number;
    land_cost_10k: number;
    construction_cost_10k: number;
    soft_cost_10k: number;
    total_cost_10k: number;
    net_profit_10k: number;
    roi_percent: number;
  };
  assumptions?: {
    avg_pyeong_price_10k: number;
    construction_cost_per_pyeong_10k: number;
  };
}

/** AI 내러티브(LLM 생성). 결정론 영역 외 — 텍스트 한정. */
export interface MarketNarrative {
  summary?: string;
  opportunities?: string[];
  risks?: string[];
  price_trend?: string;
  target_persona?: string;
}

/** /market/report 응답 전체. 기존 키는 그대로, 신규는 옵셔널. */
export interface MarketReport {
  generated_at?: string;
  address?: string;
  lawd_cd?: string;
  coordinates?: { lat?: number; lon?: number } | null;
  months?: string[];
  zone_type?: string | null;
  official_price_per_sqm?: number | null;
  trade?: Record<string, any>;
  rent?: Record<string, any>;
  apt_trend?: any[];
  infrastructure?: Record<string, any>;
  demographics?: DemographicProfile | null;
  narrative?: MarketNarrative | null;
  feasibility_analysis?: FeasibilityAnalysis | null;
  /** 신규(옵셔널): 보고서 전체 데이터 출처 상태. */
  data_source?: DataSource;
}
