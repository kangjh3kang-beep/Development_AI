/**
 * Flagship B — 이미지융합 AVM (PoC) 응답 계약 타입.
 * 백엔드 POST /api/v1/avm-vision/analyze 응답 스키마와 1:1 대응.
 * (계약: 11_flagshipB_contract.md / 백엔드 보고: 12_backend_avm_vision.md)
 */

export type AvmVisionRequest = {
  address?: string | null;
  pnu?: string | null;
  base_value_won?: number | null;
  base_value_per_sqm_won?: number | null;
};

export type AvmVisionImage = {
  available: boolean;
  source: "VWorld-PHOTO" | null;
  /** [lon, lat] — 프론트가 VWorld 이미지 직접 재요청 시 사용 */
  center: [number, number] | null;
  /** VWorld zoom (7~18). null 가능 */
  zoom: number | null;
  bbox: number[] | null;
  /** PoC에서 항상 null */
  thumbnail_url: string | null;
};

export type RoadFrontage = "good" | "normal" | "poor";

export type AvmVisionFeatures = {
  /** image=cv2 영상분석 / proxy=공간컨텍스트 추론 */
  source: "image" | "proxy";
  green_ratio: number | null;
  built_ratio: number | null;
  edge_density: number | null;
  road_frontage: RoadFrontage | null;
  terrain: string | null;
  poi_density: number | null;
  detail: string;
};

export type AvmVisionResult = {
  ok: boolean;
  message?: string;
  address?: string;
  pnu?: string | null;
  coordinates?: { lat: number; lon: number } | null;
  image: AvmVisionImage;
  features: AvmVisionFeatures;
  base_value_won: number | null;
  base_value_per_sqm_won: number | null;
  /** 상한 제한(-8 ~ +8). 근거 없으면 0 */
  adjustment_pct: number;
  adjusted_value_won: number | null;
  /** 0~1 (image>proxy>none) */
  confidence: number;
  rationale: string;
  /** 항상 true(실험적 PoC) */
  experimental: boolean;
  sources: string[];
  /** 이미지 미취득/프록시 폴백 사유 등 */
  note: string;
};
