/**
 * 배치도(buildable footprint + 동배치) 응답 계약 — 사통맵 v2 W3.
 * 백엔드 `POST /api/v1/analysis/site-layout`(→ `cad/site_layout_service.build_site_layout`)와 1:1.
 *
 * ⚠ v1 한계(서버가 honest_notes로 명시): 축정렬 직사각형 동·균일 세트백·동지 일조 근사.
 *   **부지 설계 대안이 아니라 볼륨 감**이다. 프론트는 값을 재계산하지 않고 표기만 한다.
 */

/** 서버가 돌려주는 GeoJSON geometry(WGS84) — 지도 오버레이가 그대로 소비한다. */
export type SiteLayoutGeometry = {
  type: string;
  coordinates: unknown;
};

export type SiteLayoutFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties?: { dong?: number; floors?: number } | null;
    geometry: SiteLayoutGeometry;
  }>;
};

/** 일조준수 근사(동 장변 방위 기준) — `_daylight_compliance` 계약. */
export type SiteLayoutDaylight = {
  facade_facing_deg?: number;
  direct_sun_hours?: number;
  /** 일조권 충족(09~15 연속 2h 또는 08~16 총 4h) — 서버 판정을 그대로 표기한다. */
  meets_sunlight?: boolean;
  longest_continuous_0915_h?: number | null;
  south_optimal_hours?: number;
};

export type SiteLayoutOption = {
  /** 판상형/탑상형 등 동 유형(서버 문자열 그대로 표기 — 프론트 재분류 금지). */
  kind: string;
  angle_deg: number;
  /** ★단일동(n≤1)은 인접동이 없어 인동간격 개념이 무의미 → false면 간격을 표시하지 않는다. */
  spacing_meaningful?: boolean;
  buildings: number;
  floors: number;
  height_m: number;
  /** 인동간격(m). 단일동이면 null. */
  spacing_m?: number | null;
  total_units_est?: number;
  daylight?: SiteLayoutDaylight;
  /** 목표 연면적 대비 실현율(%) — 실효 밀도 손실이 여기서 드러난다. */
  yield_pct?: number;
  /** 가용 대지 중 동이 차지하지 않은 비율(%) = 오픈스페이스. */
  openness_pct?: number;
  score?: number;
  buildings_geojson?: SiteLayoutFeatureCollection | null;
  /**
   * ★W3-b: 이 대안의 **높이 기준** 정북 일조 금지 띠. 대안마다 높이가 다르므로 대안별로 온다
   *   (전역 1개면 토글할 때 틀린 밴드가 남는다). 미적용 용도지역·판정 불가면 null.
   */
  north_light_band_geojson?: SiteLayoutGeometry | null;
  north_light_setback_m?: number | null;
};

export type SiteLayoutResult = {
  ok: boolean;
  /** ★서버가 만든 한계·사유 문구. 요약·의역 없이 그대로 표기한다. */
  honest_notes?: string[];
  zone_type?: string;
  building_type?: string;
  land_area_sqm?: number;
  parcel_area_sqm?: number;
  far_pct?: number | null;
  bcr_pct?: number | null;
  target_units_est?: number;
  parcel_geojson?: SiteLayoutGeometry | null;
  /** 세트백 오프셋 후 건축가능 영역 — 대지와의 차이가 곧 세트백 밴드다. */
  buildable_geojson?: SiteLayoutGeometry | null;
  buildable_area_sqm?: number;
  /**
   * ★W3-b: 정북일조 적용 여부와 근사 한계를 **서버가** 말한다. 화면이 용도지역 문자열을
   *   다시 파싱해 판정하면 서버와 갈라진다(이 저장소가 반복해서 겪은 SSOT 이중화).
   */
  north_light?: {
    applies: boolean;
    reason?: string | null;
    boundary_approximation?: string | null;
  } | null;
  setback_m?: number;
  options?: SiteLayoutOption[];
  best?: SiteLayoutOption | null;
  guidance?: string[];
  priority?: string;
};

/** 지도 오버레이가 소비하는 최소 형태 — 선택된 대안 1개만 그린다. */
export type SiteLayoutOverlay = {
  buildable: SiteLayoutGeometry | null;
  buildings: SiteLayoutFeatureCollection | null;
  /** ★W3-b: 정북 일조로 그 높이에 지을 수 없는 북측 띠(미적용이면 null). */
  northLightBand: SiteLayoutGeometry | null;
};

/**
 * 대안 목록에서 안정적인 식별자를 만든다.
 *
 * 서버는 (kind × angle) 조합으로 여러 대안을 내는데 `kind`만으로는 중복이라 토글 키가 될 수
 * 없다. 인덱스만 쓰면 재조회로 순서가 바뀔 때 다른 대안이 선택된 것처럼 보인다 → 둘을 합친다.
 */
export function siteLayoutOptionKey(option: SiteLayoutOption): string {
  return `${option.kind}@${option.angle_deg}`;
}

/** 선택된 대안(키 기준) — 없으면 best, 그것도 없으면 첫 번째. 전부 없으면 null. */
export function resolveSelectedOption(
  result: SiteLayoutResult | null | undefined,
  selectedKey: string | null,
): SiteLayoutOption | null {
  const options = result?.options ?? [];
  if (!options.length) return null;
  if (selectedKey) {
    const hit = options.find((o) => siteLayoutOptionKey(o) === selectedKey);
    if (hit) return hit;
  }
  if (result?.best) {
    const bestKey = siteLayoutOptionKey(result.best);
    const hit = options.find((o) => siteLayoutOptionKey(o) === bestKey);
    if (hit) return hit;
  }
  return options[0];
}

/**
 * 지도 오버레이 payload — 선택 대안의 동 풋프린트 + 건축가능 영역.
 *
 * ★ok=false거나 기하가 없으면 **null을 돌려준다**(가짜 배치 금지). 서버가 폴리곤 미확보 시
 *   honest_notes만 주고 options=[]로 오므로, 여기서 임의 도형을 만들어 채우지 않는다.
 */
export function buildLayoutOverlay(
  result: SiteLayoutResult | null | undefined,
  selectedKey: string | null,
): SiteLayoutOverlay | null {
  if (!result?.ok) return null;
  const option = resolveSelectedOption(result, selectedKey);
  const buildable = result.buildable_geojson ?? null;
  const buildings = option?.buildings_geojson ?? null;
  // ★서버가 `applies:false`면 밴드를 그리지 않는다 — 여기서 용도지역을 다시 판정하지 않는다.
  const northLightBand =
    result.north_light?.applies === true ? option?.north_light_band_geojson ?? null : null;
  if (!buildable && !buildings && !northLightBand) return null;
  return { buildable, buildings, northLightBand };
}
