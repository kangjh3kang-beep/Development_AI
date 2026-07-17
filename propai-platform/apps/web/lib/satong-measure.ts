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

/**
 * 폴리곤 면적(㎡) — 위도 기준 등장방형(equirectangular) 투영 후 신발끈 공식.
 * 필지 스케일(수 km 이내)에서 오차 무시 가능. 점 3개 미만이면 0.
 */
export function polygonAreaSqm(points: MeasurePoint[]): number {
  if (points.length < 3) return 0;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const latRef = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const cosLat = Math.cos(toRad(latRef));
  // 위경도 → 로컬 미터 좌표
  const xy = points.map((p) => ({
    x: toRad(p.lon) * EARTH_RADIUS_M * cosLat,
    y: toRad(p.lat) * EARTH_RADIUS_M,
  }));
  let sum = 0;
  for (let i = 0, j = xy.length - 1; i < xy.length; j = i, i += 1) {
    sum += xy[j].x * xy[i].y - xy[i].x * xy[j].y;
  }
  return Math.abs(sum) / 2;
}

/** 면적 표시 포맷 — "1,234㎡ (373.3평)". 3점 미만/비정상은 "0㎡". */
export function formatAreaSqm(sqm: number): string {
  if (!Number.isFinite(sqm) || sqm <= 0) return "0㎡";
  const pyeong = sqm / 3.305785;
  return `${Math.round(sqm).toLocaleString()}㎡ (${pyeong.toFixed(1)}평)`;
}
