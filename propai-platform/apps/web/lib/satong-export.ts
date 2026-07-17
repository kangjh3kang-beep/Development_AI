/**
 * 선택 필지 GeoJSON 내보내기(I5) — 측량·타 GIS 도구 연계용 순수 직렬화.
 *
 * geometry가 있는 피처만 Feature로 포함(무기하 피처는 제외 건수로 정직 보고).
 * 좌표계는 원본 그대로(WGS84 lon/lat — VWorld 경계 응답 계약).
 */

import type { SatongMapFeature } from "@/lib/satong-map-layers";

export interface SatongGeoJsonExport {
  /** FeatureCollection 문자열(pretty 2-space). */
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
