/**
 * Flagship C-1 — 지형분석(경사도·토공량·지형단면) 응답 계약 타입.
 * 백엔드 POST /api/v1/terrain/analyze 응답 스키마와 1:1 대응.
 * (계약: 15_flagshipC1_contract.md)
 *
 * ⚠ EXPERIMENTAL: 광역 DEM 근사이며 검증된 정밀측량이 아니다.
 *   해상도·표고소스·신뢰도를 응답에 명시하고 그대로 표기한다(할루시네이션 방지).
 */

export type TerrainRequest = {
  address?: string | null;
  pnu?: string | null;
  /** 토공 기준고(계획고). 미제공 시 필지 평균표고 사용 */
  target_level_m?: number | null;
  /** 지형단면 방위(도, 0~360). 미제공 시 최대경사방향 */
  section_bearing_deg?: number | null;
};

export type SlopeClass = "평지" | "완경사" | "경사" | "급경사";
export type EarthworkBalance = "절토우세" | "성토우세" | "균형";

export type TerrainSlope = {
  mean_pct: number;
  max_pct: number;
  aspect_deg: number | null;
  class: SlopeClass;
  detail: string;
};

export type TerrainEarthwork = {
  base_level_m: number;
  cut_volume_m3: number;
  fill_volume_m3: number;
  net_m3: number;
  balance: EarthworkBalance;
  detail: string;
};

export type CrossSectionPoint = {
  dist_m: number;
  elev_m: number;
};

export type TerrainCrossSection = {
  bearing_deg: number;
  length_m: number;
  points: CrossSectionPoint[];
  min_elev_m: number;
  max_elev_m: number;
  relief_m: number;
};

export type TerrainCoordinates = {
  lat: number;
  lon: number;
};

export type TerrainResult = {
  ok: boolean;
  /** ok:false 시 사유 */
  message?: string | null;
  address?: string;
  pnu?: string | null;
  coordinates?: TerrainCoordinates;
  elevation_source?: string;
  resolution_m?: number;
  sample_count?: number;
  area_sqm?: number | null;
  slope?: TerrainSlope;
  earthwork?: TerrainEarthwork;
  cross_section?: TerrainCrossSection;
  confidence?: number;
  note?: string;
  sources?: string[];
};
