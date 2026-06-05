/**
 * Flagship A — 90초 AI PreCheck 응답 타입.
 * 백엔드 계약(06_flagshipA_contract.md)을 그대로 반영한다.
 * - A: POST /api/v1/precheck/instant
 * - B: POST /api/v1/precheck/zoning-signals
 */

export type PreCheckSignal = "pass" | "warn" | "fail";

export type PreCheckRuleName =
  | "용도지역 허용"
  | "건폐율"
  | "용적률"
  | "높이"
  | "주차"
  | "일조";

export interface PreCheckRuleResult {
  rule: PreCheckRuleName | string;
  status: PreCheckSignal;
  detail: string;
}

export interface PreCheckMethod {
  code: string; // "M01" ~ "M15"
  name: string;
  signal: PreCheckSignal;
  permitted: boolean;
  complexity: number; // 1~5
  complexity_label: string;
  checks: PreCheckRuleResult[];
  reason: string;
}

export interface PreCheckLegalLimits {
  bcr_pct: number | null;
  far_pct: number | null;
  height_m: number | null;
  source: string;
}

export interface PreCheckSummary {
  pass: number;
  warn: number;
  fail: number;
  best: string | null; // "Mxx"
  llm_note: string | null;
}

/** A. 즉시 룰체크 응답 */
export interface InstantPreCheckResponse {
  ok: boolean;
  address: string;
  pnu: string | null;
  zone_type: string;
  area_sqm: number | null;
  legal_limits: PreCheckLegalLimits;
  methods: PreCheckMethod[];
  summary: PreCheckSummary;
  elapsed_ms: number;
  sources: string[];
  // 빈/오류 경로(ok:false)에서 백엔드가 사유 전달
  message?: string | null;
}

/** A. 즉시 룰체크 요청 */
export interface InstantPreCheckRequest {
  address: string;
  pnu?: string | null;
  area_sqm?: number | null;
  use_llm?: boolean;
}

export type ZoningSignalType =
  | "통합개발후보"
  | "용도상향기회"
  | "역세권개발"
  | "저밀재건축";

export type ZoningSignalLevel = "high" | "mid" | "low";

export interface ZoningSignalParcel {
  pnu: string;
  zone_type: string;
  adjacent: boolean;
}

export interface ZoningSignal {
  type: ZoningSignalType | string;
  score: number; // 0~100
  level: ZoningSignalLevel;
  parcels: ZoningSignalParcel[];
  rationale: string;
}

export interface ZoningSignalTarget {
  pnu: string;
  zone_type: string;
  address: string;
}

/** B. 조닝 시그널 응답 */
export interface ZoningSignalsResponse {
  ok: boolean;
  target: ZoningSignalTarget;
  signals: ZoningSignal[];
  // parcel-boundaries 재사용 가능 시 GeoJSON FeatureCollection 등
  geojson: unknown | null;
  sources: string[];
  message?: string | null;
  note?: string | null;
}

/** B. 조닝 시그널 요청 */
export interface ZoningSignalsRequest {
  address?: string | null;
  pnu?: string | null;
  radius_m?: number;
}
