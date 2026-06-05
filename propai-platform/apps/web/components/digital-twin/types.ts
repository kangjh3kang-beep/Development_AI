/**
 * 가상준공 3D 디지털트윈 — 백엔드 응답 계약(POST /api/v1/digital-twin/scene).
 *
 * ⚠ 정직성 가드: 표고=SRTM 등 광역 DEM(실측 측량 아님), 주변건물=footprint 압출 추정,
 *   건물 매스=AI 절차생성(인허가 도면 아님), 항공=촬영 시점 상이 가능.
 *   추정/실측은 시각(점선·반투명 vs 실선·채움)으로 구분한다.
 */

/** ENU 로컬 평면 좌표(미터). x=동, z=북(−위도방향), y=표고. */
export type Enu2 = [number, number]; // [x, z]
export type Enu3 = [number, number, number]; // [x, y, z]

/** 필지 폴리곤(ENU 미터). */
export interface DigitalTwinParcel {
  ring_enu: Enu2[];
  center_enu: Enu2;
}

/** 지형 메시(verts/indices). */
export interface DigitalTwinTerrain {
  verts: Enu3[];
  indices: number[];
  elev0: number;
  nx: number;
  nz: number;
  bbox_m: Record<string, number>;
}

/** 지면 항공 텍스처(VWorld PHOTO 프록시). */
export interface DigitalTwinAerial {
  image_proxy_url: string;
  center: [number, number]; // [lon, lat]
  zoom: number;
  cover_m: number;
}

/** 주변 건물(footprint 압출 추정). */
export interface DigitalTwinNeighbor {
  footprint_enu: Enu2[];
  height_m: number;
  estimated: boolean;
}

/** 우리 건물(AI 절차생성 glb). */
export interface DigitalTwinBuilding {
  glb_url: string | null;
  place_at_enu: Enu3;
}

/** 정직성 배지. */
export interface DigitalTwinBadges {
  terrain_source: string;
  terrain_resolution_m: number;
  confidence: number;
  neighbors_estimated: boolean;
  note: string;
}

/** POST /api/v1/digital-twin/scene 응답. */
export interface DigitalTwinScenePayload {
  ok: boolean;
  message?: string;
  address?: string;
  pnu?: string | null;
  lat0?: number;
  lon0?: number;
  parcel?: DigitalTwinParcel;
  terrain?: DigitalTwinTerrain;
  aerial?: DigitalTwinAerial;
  neighbors?: DigitalTwinNeighbor[];
  building?: DigitalTwinBuilding;
  badges?: DigitalTwinBadges;
  sources?: string[];
}

/** 레이어 토글 상태. */
export interface DigitalTwinLayers {
  terrain: boolean;
  aerial: boolean;
  parcel: boolean;
  building: boolean;
  neighbors: boolean;
}
