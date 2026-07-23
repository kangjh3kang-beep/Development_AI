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
  | "capacity"
  | "terrain"
  | "roadview";

/** VWorld WMTS tiletype 정본(2026-07-17 라이브 채증 — 상류가 유효값을 직접 열거).
 *  유효 범위: [Base, midnight, Hybrid, Satellite, white] — 종전 "gray"는 실존하지 않는
 *  오기였다(InvalidParameterValue/locator=tiletype → 배경지도 전역 미표시). 회색 계열
 *  백지도의 정본명은 "white"다. ★UI 컨트롤 id는 "gray"로 유지하고 전송값(이 타입)만 정본으로
 *  교정했다 — 둘은 별개 네임스페이스다. 컨트롤 id를 함께 바꾸지 않는 이유는 그것이 UI 식별자
 *  (상호배타 해제셋 키·aria 라벨·기본 컨트롤 정의)이기 때문이지 영속 저장 때문이 아니다
 *  (layerControls는 useState 뿐 — localStorage 영속 없음. 근거를 오독하지 말 것). */
export type VWorldBaseLayer = "Base" | "Satellite" | "Hybrid" | "white";

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
  /** 노후도 무자료 사유(백엔드 boundary age_status): no_building(나대지·건물없음) /
   *  no_approval_date(건물 실재·사용승인일 미기재 — 나대지와 구분) /
   *  lookup_failed(키·인증·호출오류) / skipped_bulk(대량생략). 값 있음/ok는 null·미설정.
   *  ★"age 조회 시도됨" 판정에 쓰여 나대지 1필지에 의한 경계 전체 재조회 루프를 끊는다(WP-M3). */
  ageStatus?: string | null;
  /** WS-D 개발여력 — 실효 용적률(%, 7계층 min·서버 산정). 미산정 None(무날조). */
  effectiveFarPct?: number | null;
  /** WS-D 개발여력 — 현황 용적률(%, 전동 연면적합/대지면적·서버 산정). 나대지=0·미상 None. */
  currentFarPct?: number | null;
  /** I7 규제요약 — 실효 건폐율(%, calc_effective_far 동일 계층·서버 산정). 미산정 None. */
  effectiveBcrPct?: number | null;
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
  // 개발여력(WS-D①) — 서버 산정(실효·현황 FAR) 데이터소스+capacityColor 렌더러 실재.
  //   ★R1 BLOCKING 재발 방지: 이 Set 누락 = 레일 클릭 무반응+거짓 "미표시" 배너(위 주석 동일).
  //   active+mapEffect 레이어는 반드시 여기 등록 — 불변식 테스트로 고정.
  "capacity",
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

/* ── WS-D 개발여력 히트맵(선택필지 MVP) ──
   여력비 = (실효FAR − 현황FAR) / 실효FAR. 두 값 모두 서버 산정치가 있을 때만(무날조 —
   한쪽이라도 None이면 null 반환→회색). 음수(현황>실효 — 기존 건물이 현행 한도 초과)는
   0으로 클램프하지 않고 별색(보라)으로 정직 표기: "여력 없음+초과 상태"는 다른 정보다. */
const CAPACITY_RAMP = ["#e2e8f0", "#a7f3d0", "#4ade80", "#16a34a", "#166534"];

export const CAPACITY_LEGEND_ITEMS = [
  { color: "#166534", label: "여력 80%+ (거의 빈 땅)" },
  { color: "#16a34a", label: "60~80%" },
  { color: "#4ade80", label: "40~60%" },
  { color: "#a7f3d0", label: "20~40%" },
  { color: "#e2e8f0", label: "0~20% (거의 소진)" },
  { color: "#a855f7", label: "한도 초과(현황>실효)" },
];

export function capacityRatio(
  effectiveFarPct: number | null | undefined,
  currentFarPct: number | null | undefined,
): number | null {
  if (effectiveFarPct == null || currentFarPct == null || effectiveFarPct <= 0) return null;
  return (effectiveFarPct - currentFarPct) / effectiveFarPct;
}

export function capacityColor(
  effectiveFarPct: number | null | undefined,
  currentFarPct: number | null | undefined,
): string | null {
  const ratio = capacityRatio(effectiveFarPct, currentFarPct);
  if (ratio == null) return null; // 미상 — 색칠하지 않음(무날조)
  if (ratio < 0) return "#a855f7"; // 한도 초과(보라 — 정직 별색)
  const idx = Math.min(CAPACITY_RAMP.length - 1, Math.floor(ratio * CAPACITY_RAMP.length));
  return CAPACITY_RAMP[idx];
}

/** 실거래 유형(매매 6종 — 전월세는 앞 4종만 지원, 백엔드 _TRADE_TYPES/_RENT_TYPES 미러) SSOT.
 *  ★색상 SSOT 통합(분석품질 레인G): 종전 SatongMultiMap.MARKET_TYPE_COLORS와
 *  NearbyTransactionsMap.TRADE_TYPES가 같은 6색을 각자 하드코딩해 한쪽만 고치면 다른 쪽이
 *  침묵 발산했다 — AGE_LEGEND_ITEMS/CAPACITY_LEGEND_ITEMS와 동일 계층(이 파일)으로 승격. */
export const MARKET_TRADE_TYPES: { key: string; label: string; color: string }[] = [
  { key: "apt", label: "아파트", color: "#14b8a6" },
  { key: "villa", label: "연립다세대", color: "#3b82f6" },
  { key: "house", label: "단독다가구", color: "#f59e0b" },
  { key: "officetel", label: "오피스텔", color: "#8b5cf6" },
  { key: "land", label: "토지", color: "#65a30d" },
  { key: "commercial", label: "상업업무용", color: "#ec4899" },
];

export const MARKET_TYPE_COLORS: Record<string, string> = Object.fromEntries(
  MARKET_TRADE_TYPES.map((t) => [t.key, t.color]),
);

export const MARKET_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  MARKET_TRADE_TYPES.map((t) => [t.key, t.label]),
);

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

/** 규제 오버레이 — zoning 컨트롤 id → VWorld WMS 레이어 정본명.
 *  ★2026-07-17 라이브 채증: 5종 전부 WMS GetCapabilities 355개 목록 실존 + GetMap 매트릭스
 *   (서울 광역 bbox) 실PNG 반환 확인(무날조 게이트 — lp_pa_cbnd·tiletype 함정 재발 방지).
 *  ★"지구단위"·"개발행위 제한"은 LAYERS의 기존 플레이스홀더("원천 연결 후 활성화")를
 *   설계 의도대로 잠금 해제한 것 — 신규 발명 아님. 이름은 소문자 정본(WMS는 대소문자 구분,
 *   데이터 API의 대문자 계약과 별개 — #366 교훈). */
export const REGULATION_WMS_BY_CONTROL: Record<string, string> = {
  "development-limit": "lt_c_upisuq171", // 개발행위허가제한지역
  "district-unit": "lt_c_upisuq161", // 지구단위계획
  "water-protect": "lt_c_um710", // 상수원보호구역
  "edu-protect": "lt_c_uo101", // 교육환경보호구역(숙박·위락 업종 인허가 직결)
  "height-district": "lt_c_uq123", // 고도지구(높이 제한)
};

/** 활성 규제 컨트롤 → WMS LAYERS 파라미터(콤마 조인, 사전 정의 순서 고정).
 *  빈 문자열 = 규제 오버레이 없음(타일 레이어 미부설). */
export function resolveRegulationWmsLayers(state: SatongMapLayerState | undefined): string {
  if (!hasSatongLayer(state, "zoning")) return "";
  return Object.keys(REGULATION_WMS_BY_CONTROL)
    .filter((controlId) => hasSatongLayerControl(state, "zoning", controlId))
    .map((controlId) => REGULATION_WMS_BY_CONTROL[controlId])
    .join(",");
}

export function resolveVWorldBaseLayer(state: SatongMapLayerState | undefined): VWorldBaseLayer {
  if (!hasSatongLayer(state, "terrain")) return "Base";
  if (hasSatongLayerControl(state, "terrain", "satellite")) return "Satellite";
  if (hasSatongLayerControl(state, "terrain", "hybrid") || hasSatongLayerControl(state, "terrain", "aerial")) {
    return "Hybrid";
  }
  // 컨트롤 id "gray"(UI 식별자·라벨 "회색") → 전송값은 VWorld tiletype 정본 "white".
  if (hasSatongLayerControl(state, "terrain", "gray")) return "white";
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
        // 빈 문자열은 '미보유'로 강등해 null로 통일한다(address·pnu 동일 규약 — 리뷰 LOW).
        address: parcel.address || null,
        pnu: parcel.pnu || null,
      };
    }
  }
  for (const parcel of parcels) {
    const point = geometryRepresentativePoint(parcel.geometry);
    if (point) {
      return { ...point, source: "boundary", address: parcel.address || null, pnu: parcel.pnu || null };
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
      ageStatus: feature.ageStatus ?? prev?.ageStatus ?? null,
    effectiveFarPct: feature.effectiveFarPct ?? prev?.effectiveFarPct ?? null,
    currentFarPct: feature.currentFarPct ?? prev?.currentFarPct ?? null,
    effectiveBcrPct: feature.effectiveBcrPct ?? prev?.effectiveBcrPct ?? null,
      geometry: feature.geometry ?? prev?.geometry,
      lat: feature.lat ?? prev?.lat ?? null,
      lon: feature.lon ?? prev?.lon ?? null,
    });
  });
  return Array.from(byKey.values());
}
