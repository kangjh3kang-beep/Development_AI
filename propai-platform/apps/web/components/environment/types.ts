/**
 * Flagship C-2 — 환경분석(일조·조망·스카이라인) 응답 계약 타입.
 * 백엔드 POST /api/v1/environment/analyze 응답 스키마와 1:1 대응.
 * (계약: 37_backend_environment.md)
 *
 * ⚠ 약식 계산이며 정밀 일조분석/측량이 아니다. 천문 근사식·footprint 추정고 기반.
 *   note·basis(정직성 배지)를 그대로 표기한다(할루시네이션 방지).
 */

export type EnvironmentSeason = "winter" | "summer" | "equinox";

export type SolarGrade = "양호" | "보통" | "불리";
export type SkylinePosition = "돌출" | "조화" | "매몰";

export type EnvironmentRequest = {
  address?: string | null;
  pnu?: string | null;
  design_params?: {
    floors?: number | null;
    height_m?: number | null;
    floor_height_m?: number | null;
  } | null;
  season?: EnvironmentSeason;
};

/** 시각별 태양 위치(고도·방위). sun_positions 항목. */
export type SunPosition = {
  hour: number;
  altitude_deg: number;
  azimuth_deg: number;
};

export type NorthSetback = {
  applies: boolean;
  required_m?: number | null;
  detail: string;
};

export type EnvironmentSolar = {
  sun_positions: SunPosition[];
  sunlight_hours_winter: number;
  north_setback: NorthSetback;
  summary: string;
  grade: SolarGrade;
};

export type EnvironmentView = {
  openness_score: number;
  best_directions: string[];
  blocked_ratio_pct: number;
  summary: string;
};

export type EnvironmentSkyline = {
  subject_height_m: number;
  neighbor_avg_m: number;
  neighbor_max_m: number;
  position: SkylinePosition;
  summary: string;
};

export type EnvironmentBadges = {
  note: string;
  basis: string[];
};

export type EnvironmentSubject = {
  height_m?: number | null;
  floors?: number | null;
  neighbor_count?: number | null;
};

export type EnvironmentResult = {
  ok: boolean;
  /** ok:false 시 사유 */
  message?: string | null;
  address?: string;
  pnu?: string | null;
  zone_type?: string;
  lat?: number;
  lon?: number;
  subject?: EnvironmentSubject;
  solar?: EnvironmentSolar;
  view?: EnvironmentView;
  skyline?: EnvironmentSkyline;
  badges?: EnvironmentBadges;
  sources?: string[];
};
