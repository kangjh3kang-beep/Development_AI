export type SatongMapLayerId =
  | "cadastre"
  | "zoning"
  | "official-price"
  | "age"
  | "transactions"
  | "presale"
  | "auction"
  | "poi"
  | "development"
  | "terrain"
  | "roadview";

export type VWorldBaseLayer = "Base" | "Satellite" | "Hybrid" | "gray";

export type SatongMapLayerState = {
  enabledLayerIds: SatongMapLayerId[];
  controlsByLayer: Partial<Record<SatongMapLayerId, string[]>>;
};

export type SatongMapFeature = {
  id: string;
  address: string;
  pnu?: string | null;
  lat?: number | null;
  lon?: number | null;
  areaSqm?: number | null;
  zoneType?: string | null;
  zoneType2?: string | null;
  jimok?: string | null;
  officialPricePerSqm?: number | null;
  builtYear?: number | null;
  buildingAgeYears?: number | null;
  geometry?: unknown;
  source?: "search" | "excel" | "map" | "boundary";
};

export const SATONG_RENDERABLE_LAYER_IDS = new Set<SatongMapLayerId>([
  "cadastre",
  "zoning",
  "official-price",
  "age",
  // 실거래(C1)·POI(C2) — 데이터 배선+마커 렌더가 실재하므로 renderable 등록.
  //   미등록 시 레일 클릭이 레이어를 켜지 못하고(early-return) "지도에 표시하지 않습니다"
  //   거짓 배너가 노출된다(정직원칙 역위반 — C2 리뷰 HIGH·C1 도달성 갭 동시 해소).
  "transactions",
  "poi",
  "development",
  "terrain",
]);

export function isRenderableSatongMapLayer(id: string): id is SatongMapLayerId {
  return SATONG_RENDERABLE_LAYER_IDS.has(id as SatongMapLayerId);
}

export function hasSatongLayer(
  state: SatongMapLayerState | undefined,
  id: SatongMapLayerId,
): boolean {
  return !!state?.enabledLayerIds.includes(id);
}

export function hasSatongLayerControl(
  state: SatongMapLayerState | undefined,
  id: SatongMapLayerId,
  controlId: string,
): boolean {
  return !!state?.controlsByLayer[id]?.includes(controlId);
}

export function satongMapFeatureKey(feature: Pick<SatongMapFeature, "id" | "pnu" | "address">): string {
  return feature.pnu || feature.id || feature.address.trim().replace(/\s+/g, " ");
}

export function zoneColor(zone: string | null | undefined, index: number): string {
  const z = zone || "";
  if (z.includes("상업")) return "#ec4899";
  if (z.includes("주거")) return "#14b8a6";
  if (z.includes("공업")) return "#f59e0b";
  if (z.includes("녹지") || z.includes("관리") || z.includes("농림")) return "#65a30d";
  return ["#2563eb", "#7c3aed", "#0891b2", "#ea580c"][index % 4];
}

const PRICE_RAMP = ["#bae6fd", "#7dd3fc", "#38bdf8", "#fb923c", "#ef4444"];

export function priceColor(price: number | null | undefined, min: number, max: number): string {
  if (!price || price <= 0) return "#94a3b8";
  if (max <= min) return PRICE_RAMP[2];
  const normalized = (price - min) / (max - min);
  const index = Math.min(PRICE_RAMP.length - 1, Math.max(0, Math.floor(normalized * PRICE_RAMP.length)));
  return PRICE_RAMP[index];
}

const AGE_RAMP = ["#7dd3fc", "#34d399", "#facc15", "#fb923c", "#ef4444"];

export function ageColor(age: number | null | undefined): string {
  if (age == null || age < 0) return "#94a3b8";
  if (age < 10) return AGE_RAMP[0];
  if (age < 20) return AGE_RAMP[1];
  if (age < 30) return AGE_RAMP[2];
  if (age < 40) return AGE_RAMP[3];
  return AGE_RAMP[4];
}

export function priceManPyeong(perSqm: number | null | undefined): string {
  if (!perSqm || perSqm <= 0) return "-";
  // ㎡·평 병행 표기(1평 = 3.305785㎡) — 공시지가 원천은 원/㎡, 실무 관행은 만원/평.
  const manPerSqm = Math.round(perSqm / 1e4).toLocaleString();
  const manPerPyeong = Math.round((perSqm * 3.305785) / 1e4).toLocaleString();
  return `${manPerSqm}만원/㎡ (${manPerPyeong}만원/평)`;
}

export function resolveVWorldBaseLayer(state: SatongMapLayerState | undefined): VWorldBaseLayer {
  if (!hasSatongLayer(state, "terrain")) return "Base";
  if (hasSatongLayerControl(state, "terrain", "satellite")) return "Satellite";
  if (hasSatongLayerControl(state, "terrain", "hybrid") || hasSatongLayerControl(state, "terrain", "aerial")) {
    return "Hybrid";
  }
  if (hasSatongLayerControl(state, "terrain", "gray")) return "gray";
  return "Base";
}

/** 지도 중심 후보(백엔드 payload.center 또는 프론트 폴백 좌표원) */
export type MapCoord = { lat?: number | null; lon?: number | null; address?: string } | null | undefined;

/**
 * 유효한 지도 focusTarget 을 단일 규칙으로 해석한다.
 *
 * ★서울 폴백(하드코딩 초기 center) 방지의 공용 계약:
 *   백엔드 payload.center 가 null(지오코딩 실패)이어도, 프론트가 이미 보유한
 *   좌표원(선택 필지 좌표·구획도 center 등)을 순서대로 시도해 지도를 선택 위치로 이동시킨다.
 *   후보를 모두 소진하면 null 을 돌려 "위치 확인 불가"로 정직하게 남긴다(가짜 좌표 날조 금지).
 *
 * candidates: 우선순위 순 좌표 후보 배열(앞이 우선). 각 후보는 {lat,lon,address?} 또는 null.
 * 반환: 첫 유효 좌표를 { lat, lon, label } 로. 없으면 null.
 */
export function resolveMapCenter(
  ...candidates: MapCoord[]
): { lat: number; lon: number; label?: string } | null {
  for (const c of candidates) {
    const lat = c?.lat;
    const lon = c?.lon;
    if (typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon)) {
      return { lat, lon, label: c?.address };
    }
  }
  return null;
}

export function mergeSatongMapFeatures(features: SatongMapFeature[]): SatongMapFeature[] {
  const byKey = new Map<string, SatongMapFeature>();
  features.forEach((feature) => {
    const key = satongMapFeatureKey(feature);
    const prev = byKey.get(key);
    byKey.set(key, {
      ...prev,
      ...feature,
      areaSqm: feature.areaSqm ?? prev?.areaSqm ?? null,
      zoneType: feature.zoneType ?? prev?.zoneType ?? null,
      zoneType2: feature.zoneType2 ?? prev?.zoneType2 ?? null,
      jimok: feature.jimok ?? prev?.jimok ?? null,
      officialPricePerSqm: feature.officialPricePerSqm ?? prev?.officialPricePerSqm ?? null,
      builtYear: feature.builtYear ?? prev?.builtYear ?? null,
      buildingAgeYears: feature.buildingAgeYears ?? prev?.buildingAgeYears ?? null,
      geometry: feature.geometry ?? prev?.geometry,
      lat: feature.lat ?? prev?.lat ?? null,
      lon: feature.lon ?? prev?.lon ?? null,
    });
  });
  return Array.from(byKey.values());
}
