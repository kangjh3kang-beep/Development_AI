/**
 * 사통맵 거리재기 순수 계산 — 하버사인 누적거리 + 표시 포맷.
 *
 * 지도 클릭 팝오버(단일 팝오버 계약)의 "거리재기" 도구가 사용한다. Leaflet 의존 없이
 * 순수 함수로 두어 vitest 로 수치 검증한다(플러그인 미도입 — 폴리라인+라벨은 지도측 렌더).
 */

export interface MeasurePoint {
  lat: number;
  lon: number;
}

const EARTH_RADIUS_M = 6_371_000;

/** 두 좌표 간 하버사인 거리(m). */
export function haversineMeters(a: MeasurePoint, b: MeasurePoint): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** 경로(점 목록)의 누적 거리(m). 점이 2개 미만이면 0. */
export function totalDistanceMeters(points: MeasurePoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += haversineMeters(points[i - 1], points[i]);
  }
  return total;
}

/** 거리 표시 포맷 — 1km 미만 "532m", 이상 "1.24km"(소수 2자리). */
export function formatDistance(meters: number): string {
  if (!Number.isFinite(meters) || meters < 0) return "0m";
  if (meters < 1000) return `${Math.round(meters)}m`;
  return `${(meters / 1000).toFixed(2)}km`;
}
