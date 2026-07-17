/**
 * 선택 필지 GeoJSON 내보내기(I5) — 측량·타 GIS 도구 연계용 순수 직렬화.
 *
 * geometry가 있는 피처만 Feature로 포함(무기하 피처는 제외 건수로 정직 보고).
 * 좌표계는 원본 그대로(WGS84 lon/lat — VWorld 경계 응답 계약).
 */

import type { SatongMapFeature } from "@/lib/satong-map-layers";

export interface SatongGeoJsonExport {
  /** 직렬화 결과 문자열 — GeoJSON(FeatureCollection) 또는 KML 문서(R1 L2: 필드명은 하위호환 유지). */
  json: string;
  /** 포함된 필지 수. */
  included: number;
  /** geometry가 없어 제외된 필지 수. */
  skipped: number;
}

export function buildSelectionGeoJson(features: SatongMapFeature[]): SatongGeoJsonExport {
  const out: object[] = [];
  let skipped = 0;
  for (const f of features) {
    // R1: 얕은 GeoJSON 검증 — type 문자열 + coordinates(또는 GeometryCollection의
    // geometries) 보유만 확인. 비-GeoJSON 임의 객체가 Feature로 새지 않게(skipped 계상).
    const g = f.geometry as { type?: unknown; coordinates?: unknown; geometries?: unknown } | null;
    if (
      !g ||
      typeof g !== "object" ||
      typeof g.type !== "string" ||
      (g.coordinates === undefined && g.geometries === undefined)
    ) {
      skipped += 1;
      continue;
    }
    out.push({
      type: "Feature",
      geometry: f.geometry,
      properties: {
        address: f.address ?? null,
        pnu: f.pnu ?? null,
        areaSqm: f.areaSqm ?? null,
        zoneType: f.zoneType ?? null,
        jimok: f.jimok ?? null,
        officialPricePerSqm: f.officialPricePerSqm ?? null,
        source: f.source ?? null,
      },
    });
  }
  const collection = {
    type: "FeatureCollection",
    name: "satong-selected-parcels",
    features: out,
  };
  return { json: JSON.stringify(collection, null, 2), included: out.length, skipped };
}

/**
 * 카카오맵 로드뷰 딥링크(I3) — 2026-07-17 라이브 검증: /link/roadview/{lat},{lng} →
 * 302로 실제 파노라마(panoid) 리다이렉트 확인(무날조 게이트 통과). 좌표 없으면 null.
 */
export function kakaoRoadviewUrl(lat?: number | null, lon?: number | null): string | null {
  if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return `https://map.kakao.com/link/roadview/${lat},${lon}`;
}

/** XML 텍스트 이스케이프(KML name/description). */
function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** GeoJSON Polygon/MultiPolygon → KML Polygon 문자열들(외곽 링만·lon,lat 순). */
function geometryToKmlPolygons(geometry: { type?: unknown; coordinates?: unknown }): string[] {
  const polys: number[][][][] =
    geometry.type === "Polygon"
      ? [geometry.coordinates as number[][][]]
      : geometry.type === "MultiPolygon"
        ? (geometry.coordinates as number[][][][])
        : [];
  return polys
    .filter((rings) => Array.isArray(rings) && Array.isArray(rings[0]))
    .map((rings) => {
      const ringToCoords = (ring: number[][]) => ring.map((pt) => `${pt[0]},${pt[1]},0`).join(" ");
      const outer = `<outerBoundaryIs><LinearRing><coordinates>${ringToCoords(rings[0])}</coordinates></LinearRing></outerBoundaryIs>`;
      // R1 M3: 내부 링(구멍)도 innerBoundaryIs로 보존 — GeoJSON 내보내기와 기하 동일성 유지.
      const inners = rings
        .slice(1)
        .filter((r) => Array.isArray(r))
        .map((r) => `<innerBoundaryIs><LinearRing><coordinates>${ringToCoords(r)}</coordinates></LinearRing></innerBoundaryIs>`)
        .join("");
      return `<Polygon>${outer}${inners}</Polygon>`;
    });
}

/**
 * 선택 필지 KML 내보내기(V3 — VWorld 활용모델 [23.12] 참고) — 측량·구글어스 호환.
 * GeoJSON 내보내기와 동일한 얕은 검증·정직 제외 계약(included/skipped).
 */
export function buildSelectionKml(features: SatongMapFeature[]): SatongGeoJsonExport {
  const placemarks: string[] = [];
  let skipped = 0;
  for (const f of features) {
    const g = f.geometry as { type?: unknown; coordinates?: unknown } | null;
    const kmlPolys = g && typeof g === "object" ? geometryToKmlPolygons(g) : [];
    if (kmlPolys.length === 0) {
      skipped += 1;
      continue;
    }
    const name = escapeXml(f.address || f.pnu || "필지");
    const desc = escapeXml(
      [f.pnu ? `PNU ${f.pnu}` : null, f.zoneType, f.areaSqm ? `${Math.round(f.areaSqm)}㎡` : null]
        .filter(Boolean)
        .join(" · "),
    );
    const body = kmlPolys.length === 1 ? kmlPolys[0] : `<MultiGeometry>${kmlPolys.join("")}</MultiGeometry>`;
    placemarks.push(`<Placemark><name>${name}</name><description>${desc}</description>${body}</Placemark>`);
  }
  const kml =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>satong-selected-parcels</name>` +
    placemarks.join("") +
    `</Document></kml>`;
  return { json: kml, included: placemarks.length, skipped };
}
