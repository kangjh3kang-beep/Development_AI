/**
 * D3 — 설계변경 사전예측 응답 타입.
 * 백엔드 POST /api/v1/design-risk/predict 와 1:1 정합.
 * 카테고리/심각도 값은 프론트 배지·필터 키로 그대로 사용.
 */

export type RiskCategory = "법규초과" | "누락" | "간섭정합";
export type RiskSeverity = "high" | "warn" | "info";

export interface DesignRisk {
  category: RiskCategory | string;
  item: string;
  severity: RiskSeverity | string;
  current?: string | null;
  limit?: string | null;
  detail: string;
  remedy: string;
  est_impact?: string | null;
}

export interface DesignRiskSummary {
  high: number;
  warn: number;
  info: number;
  total_predicted_impact_note?: string | null;
}

export interface DesignRiskAiRemedy {
  priority_actions?: string | null;
  savings_opportunity?: string | null;
  expert_review_note?: string | null;
}

export interface DesignRiskBadges {
  note?: string | null;
  data_basis?: string | null;
}

export interface DesignRiskPredictResponse {
  ok: boolean;
  address?: string | null;
  zone_type?: string | null;
  summary?: DesignRiskSummary | null;
  risks?: DesignRisk[] | null;
  ai_remedy?: DesignRiskAiRemedy | null;
  badges?: DesignRiskBadges | null;
  limits_used?: Record<string, unknown> | null;
  data_gaps?: string[] | null;
  sources?: string[] | null;
  // ok:false
  error?: string | null;
}

/** 설계 파라미터(선택) — 요청 design_params 로 전송. */
export interface DesignParamsInput {
  floors?: number;
  gfa?: number;
  bcr?: number;
  far?: number;
  height_m?: number;
  parking?: number;
  units?: number;
}
