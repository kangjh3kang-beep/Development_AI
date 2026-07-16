/**
 * VWORLD API 브라우저 직접 호출 클라이언트.
 *
 * Railway 서버(싱가포르)에서 VWORLD(한국 공공 API) 호출 시 502 에러가 발생하므로,
 * 한국에 위치한 사용자 브라우저에서 직접 VWORLD API를 호출한다.
 *
 * ★키 이원 계약(PR#329 R1 리뷰 HIGH 반영 — 정직 명시): 이 프로젝트는 VWorld 키를
 *   용도별로 두 계약으로 나눈다.
 *   (1) `NEXT_PUBLIC_VWORLD_API_KEY` = 공개(도메인 제한) 키. 브라우저에 값이 노출되는
 *       것을 전제로 발급된 키이며, VWorld 콘솔의 Referer/도메인 화이트리스트가 보호
 *       기제다. 이 파일(브라우저 직접 호출)과 `AvmVisionPanel.tsx`(항공영상 썸네일)가
 *       이 경로를 쓴다 — 두 곳 모두 동일 정책.
 *   (2) `VWORLD_API_KEY` = 서버 전용 키. 사통맵 타일 프록시(`vworld-wmts-proxy.ts`·
 *       `vworld-wms-proxy.ts`)가 Node 런타임에서만 읽고, 브라우저 번들·네트워크
 *       응답 어디에도 값이 노출되지 않는다. 프록시는 이 키가 미설정이면 정직하게
 *       503으로 실패한다(공개 키로 조용히 대체하지 않음).
 *   이 파일이 (1)을 쓰는 것은 '키 노출 버그'가 아니라 의도된 설계다 — 리터럴
 *   하드코딩(소스에 문자열로 박아 넣는 것)과는 다른 문제다.
 */

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? "";

interface VWorldGeocodeResult {
  lat: number;
  lon: number;
  pnu: string | null;
  address: string;
}

interface VWorldLandInfo {
  pnu: string;
  land_category: string;
  area_sqm: number;
  official_price_per_sqm: number;
  zone_type: string | null;
}

interface VWorldComprehensiveResult {
  pnu: string | null;
  coordinates: { lat: number; lon: number } | null;
  zone_type: string | null;
  zone_limits: {
    max_bcr_pct: number;
    max_far_pct: number;
  } | null;
  land_register: {
    land_category: string;
    area_sqm: number;
    official_price_per_sqm: number;
  } | null;
}

// 용도지역별 법적 한도 (국토계획법 제78조)
const ZONE_LIMITS: Record<string, { bcr: number; far: number }> = {
  "제1종전용주거지역": { bcr: 40, far: 100 },
  "제2종전용주거지역": { bcr: 50, far: 150 },
  "제1종일반주거지역": { bcr: 60, far: 200 },
  "제2종일반주거지역": { bcr: 60, far: 250 },
  "제3종일반주거지역": { bcr: 50, far: 300 },
  "준주거지역": { bcr: 70, far: 500 },
  "중심상업지역": { bcr: 90, far: 1500 },
  "일반상업지역": { bcr: 80, far: 1300 },
  "근린상업지역": { bcr: 70, far: 900 },
  "유통상업지역": { bcr: 80, far: 1100 },
  "전용공업지역": { bcr: 70, far: 300 },
  "일반공업지역": { bcr: 70, far: 350 },
  "준공업지역": { bcr: 70, far: 400 },
  "보전녹지지역": { bcr: 20, far: 80 },
  "생산녹지지역": { bcr: 20, far: 100 },
  "자연녹지지역": { bcr: 20, far: 100 },
};

/**
 * WGS84 좌표 배열에서 면적(㎡)을 계산한다 (Shoelace 공식).
 */
function shoelaceAreaWgs84(coords: number[][]): number {
  const n = coords.length;
  if (n < 3) return 0;
  const avgLat = coords.reduce((s, c) => s + c[1], 0) / n;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos((avgLat * Math.PI) / 180);
  let area = 0;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const x1 = coords[i][0] * mPerDegLon;
    const y1 = coords[i][1] * mPerDegLat;
    const x2 = coords[j][0] * mPerDegLon;
    const y2 = coords[j][1] * mPerDegLat;
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2;
}

function calculateAreaFromGeometry(geom: { type: string; coordinates: number[][][][] | number[][][] }): number {
  if (geom.type === "MultiPolygon") {
    return (geom.coordinates as number[][][][]).reduce(
      (total, polygon) => total + shoelaceAreaWgs84(polygon[0]),
      0,
    );
  }
  if (geom.type === "Polygon") {
    return shoelaceAreaWgs84((geom.coordinates as number[][][])[0]);
  }
  return 0;
}

/**
 * 주소 → 좌표+PNU 지오코딩 (PARCEL 우선)
 *
 * VWORLD API가 CORS를 차단하므로 Next.js API Route 프록시를 경유.
 */
async function geocodeAddress(address: string): Promise<VWorldGeocodeResult | null> {
  if (!VWORLD_API_KEY) return null;

  for (const addrType of ["PARCEL", "ROAD"]) {
    try {
      const params = new URLSearchParams({
        service: "address",
        request: "getcoord",
        key: VWORLD_API_KEY,
        address,
        type: addrType,
        format: "json",
      });

      // CORS 우회: Next.js API Route 프록시 경유
      const resp = await fetch(`/api/vworld/data?${params}`);
      if (!resp.ok) continue;

      const data = await resp.json();
      const response = data?.response;
      if (response?.status !== "OK") continue;

      const point = response?.result?.point;
      const lat = parseFloat(point?.y ?? "0");
      const lon = parseFloat(point?.x ?? "0");
      if (lat === 0 && lon === 0) continue;

      const structure = response?.refined?.structure ?? {};
      const pnu = structure.level4LC || null;

      return { lat, lon, pnu, address };
    } catch {
      continue;
    }
  }
  return null;
}

/**
 * PNU → 토지정보 (지목, 면적, 공시지가)
 *
 * VWORLD /req/data API는 CORS 미지원이므로 Next.js API Route를 통해 프록시.
 */
async function getLandInfo(pnu: string): Promise<VWorldLandInfo | null> {
  if (!VWORLD_API_KEY || !pnu) return null;

  try {
    // geometry=true로 필지 형상도 가져와서 면적을 직접 계산
    const params = new URLSearchParams({
      service: "data",
      request: "GetFeature",
      data: "LP_PA_CBND_BUBUN",
      key: VWORLD_API_KEY,
      format: "json",
      crs: "EPSG:4326",
      attrFilter: `pnu:=:${pnu}`,
      geometry: "true",
      attribute: "true",
    });

    const proxyUrl = `/api/vworld/data?${params}`;
    const resp = await fetch(proxyUrl);
    if (!resp.ok) return null;

    const data = await resp.json();
    const features = data?.response?.result?.featureCollection?.features;
    if (!features || features.length === 0) return null;

    const feature = features[0];
    const props = feature.properties ?? {};
    const geom = feature.geometry;

    // 면적 계산: 필지 형상(Polygon/MultiPolygon)의 좌표로 Shoelace 공식 적용
    let areaSqm = 0;
    if (geom) {
      areaSqm = calculateAreaFromGeometry(geom);
    }

    // 용도지역 추출
    const landUse = props.lnbpLndcgrNm ?? props.prposAreaDstrcCodeNm ?? "";
    let zoneType: string | null = null;
    for (const zone of Object.keys(ZONE_LIMITS)) {
      if (landUse.includes(zone)) {
        zoneType = zone;
        break;
      }
    }

    // 지목 추출: "226-2 대" → "대"
    const jibunStr = String(props.jibun ?? "");
    const landCat = jibunStr.split(" ").pop() ?? props.jimok ?? "";

    return {
      pnu,
      land_category: landCat,
      area_sqm: areaSqm > 0 ? areaSqm : parseFloat(props.lndpclAr ?? props.area ?? "0"),
      official_price_per_sqm: parseFloat(props.jiga ?? props.pblntfPclnd ?? "0"),
      zone_type: zoneType,
    };
  } catch {
    return null;
  }
}

/**
 * 주소 → 종합 토지분석 (브라우저에서 직접 VWORLD 호출)
 *
 * 백엔드의 /zoning/comprehensive를 대체한다.
 * Railway 서버가 해외 IP라서 VWORLD 502 에러가 발생하는 문제를 우회.
 */
export async function fetchVWorldComprehensive(
  address: string,
): Promise<VWorldComprehensiveResult | null> {
  // 1. 지오코딩 (주소 → 좌표 + PNU)
  const geo = await geocodeAddress(address);
  if (!geo) return null;

  // 2. PNU로 토지정보 조회
  let landInfo: VWorldLandInfo | null = null;
  if (geo.pnu) {
    landInfo = await getLandInfo(geo.pnu);
  }

  // 3. 용도지역 → 법적 한도 매핑
  const zoneType = landInfo?.zone_type ?? null;
  const limits = zoneType ? ZONE_LIMITS[zoneType] ?? null : null;

  return {
    pnu: geo.pnu,
    coordinates: { lat: geo.lat, lon: geo.lon },
    zone_type: zoneType,
    zone_limits: limits ? { max_bcr_pct: limits.bcr, max_far_pct: limits.far } : null,
    land_register: landInfo
      ? {
          land_category: landInfo.land_category,
          area_sqm: landInfo.area_sqm,
          official_price_per_sqm: landInfo.official_price_per_sqm,
        }
      : null,
  };
}
