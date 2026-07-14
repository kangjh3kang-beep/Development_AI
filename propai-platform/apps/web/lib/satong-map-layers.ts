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
  // 분양(청약홈 /presale/nearby)·공경매(온비드 /auction/search+geocode) — 실데이터 배선 완료.
  "presale",
  "auction",
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

const AGE_RAMP = ["#38bdf8", "#34d399", "#facc15", "#fb923c", "#ef4444"];

export const AGE_LEGEND_ITEMS = [
  { color: "#38bdf8", label: "10년 미만 (신축)" },
  { color: "#34d399", label: "10~20년 (준신축)" },
  { color: "#facc15", label: "20~30년 (보통)" },
  { color: "#fb923c", label: "30~40년 (노후)" },
  { color: "#ef4444", label: "40년 이상 (극노후)" },
];

export function ageColor(age: number | null | undefined): string {
  if (age == null || age < 0) return "#94a3b8";
  if (age < 10) return AGE_RAMP[0];
  if (age < 20) return AGE_RAMP[1];
  if (age < 30) return AGE_RAMP[2];
  if (age < 40) return AGE_RAMP[3];
  return AGE_RAMP[4];
}

export function ageLabel(age: number | null | undefined): string {
  if (age == null || age < 0) return "정보없음";
  if (age < 10) return "10년 미만 (신축)";
  if (age < 20) return "10~20년 (준신축)";
  if (age < 30) return "20~30년 (보통)";
  if (age < 40) return "30~40년 (노후)";
  return "40년 이상 (극노후)";
}

export function priceManPyeong(perSqm: number | null | undefined): string {
  if (!perSqm || perSqm <= 0) return "-";
  // ㎡·평 병행 표기(1평 = 3.305785㎡) — 공시지가 원천은 원/㎡, 실무 관행은 만원/평.
  const manPerSqm = Math.round(perSqm / 1e4).toLocaleString();
  const manPerPyeong = Math.round((perSqm * 3.305785) / 1e4).toLocaleString();
  return `${manPerSqm}만원/㎡ (${manPerPyeong}만원/평)`;
}

export function pricePyeongOnly(perSqm: number | null | undefined): string {
  if (!perSqm || perSqm <= 0) return "-";
  const manPerPyeong = Math.round((perSqm * 3.305785) / 1e4).toLocaleString();
  return `${manPerPyeong}만원/평`;
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

/**
 * GeoJSON Polygon/MultiPolygon의 대표점(경계상자 중심)을 [lat, lon]으로 돌려준다.
 *
 * 실측 필지 경계의 기하 중심이므로 날조 좌표가 아니다 — 좌표 필드가 없는 필지
 * (엑셀 PNU행 등: /zoning/parse-parcels가 lat/lon을 채우지 않음)의 앵커 폴백으로 쓴다.
 * 좌표계 주의: GeoJSON은 [lng, lat] 순서.
 */
export function geometryRepresentativePoint(
  geometry: unknown,
): { lat: number; lon: number } | null {
  const geo = geometry as { type?: string; coordinates?: unknown } | null | undefined;
  if (!geo?.type || !Array.isArray(geo.coordinates)) return null;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let minLon = Infinity;
  let maxLon = -Infinity;
  const eatRing = (ring: unknown) => {
    if (!Array.isArray(ring)) return;
    for (const pt of ring) {
      if (!Array.isArray(pt) || pt.length < 2) continue;
      const [lng, lat] = pt as [number, number];
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLon) minLon = lng;
      if (lng > maxLon) maxLon = lng;
    }
  };
  if (geo.type === "Polygon") {
    (geo.coordinates as unknown[]).forEach(eatRing);
  } else if (geo.type === "MultiPolygon") {
    (geo.coordinates as unknown[]).forEach((poly) => {
      if (Array.isArray(poly)) poly.forEach(eatRing);
    });
  } else {
    return null;
  }
  if (!Number.isFinite(minLat) || !Number.isFinite(minLon)) return null;
  return { lat: (minLat + maxLat) / 2, lon: (minLon + maxLon) / 2 };
}

/** resolveSelectionAnchor 결과 — source로 좌표 출처를 구분한다(정직 노트·디버깅용). */
export type SelectionAnchor = {
  lat: number;
  lon: number;
  source: "parcel" | "boundary" | "map-center";
  /** 앵커 필지의 주소·PNU — 좌표와 같은 필지 기준으로 주소 파생(경매 region 등)을 묶는다.
   *  map-center 앵커(무선택)는 필지가 없으므로 null. */
  address: string | null;
  pnu: string | null;
} | null;

/**
 * 좌표 기반 지도 레이어(분양·경매·개발계획·POI)의 공용 앵커 해석 규칙.
 *
 * ★앵커 단선 방지의 단일 계약(버그수정 정책 — 공용화):
 *   종전엔 '첫 선택 필지의 lat/lon'만 봐서, 좌표 없는 필지(엑셀 PNU행·프로젝트 시드)가
 *   첫 자리에 오면 레이어를 켜도 조회 자체가 생략돼 침묵 빈지도가 됐다.
 *   ① 좌표를 가진 첫 필지 → source "parcel"
 *   ② 없으면 경계(geometry)를 가진 첫 필지의 대표점 → source "boundary"
 *      (경계보강(/zoning/parcel-boundaries)이 도착하면 자동으로 앵커가 살아난다)
 *   ③ 선택이 아예 없을 때만 지도중심 폴백 → source "map-center"
 *      (선택이 있는데 좌표가 전무하면 null — 엉뚱한 지도중심 조회 역전 차단, 기존 계약 유지)
 */
export function resolveSelectionAnchor(
  parcels: Array<Pick<SatongMapFeature, "lat" | "lon" | "geometry" | "address" | "pnu">>,
  mapCenter: { lat: number; lon: number } | null | undefined,
): SelectionAnchor {
  for (const parcel of parcels) {
    if (
      typeof parcel.lat === "number" && Number.isFinite(parcel.lat) &&
      typeof parcel.lon === "number" && Number.isFinite(parcel.lon)
    ) {
      return {
        lat: parcel.lat,
        lon: parcel.lon,
        source: "parcel",
        address: parcel.address || null,
        pnu: parcel.pnu ?? null,
      };
    }
  }
  for (const parcel of parcels) {
    const point = geometryRepresentativePoint(parcel.geometry);
    if (point) {
      return { ...point, source: "boundary", address: parcel.address || null, pnu: parcel.pnu ?? null };
    }
  }
  if (parcels.length === 0 && mapCenter &&
    Number.isFinite(mapCenter.lat) && Number.isFinite(mapCenter.lon)) {
    return { lat: mapCenter.lat, lon: mapCenter.lon, source: "map-center", address: null, pnu: null };
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
