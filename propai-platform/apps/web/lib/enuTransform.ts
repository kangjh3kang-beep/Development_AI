/**
 * SP1 위성 3D — ENU 로컬평면 좌표변환 순수코어 (프론트 결정론 검산용).
 *
 * 백엔드 `app/services/digital_twin/scene_service.py:_enu_xz`와 1:1 동일식이다:
 *   x = (lon - lon0) * 111320 * cos(lat0)   // 동(+x)
 *   z = -(lat - lat0) * 111320              // 남(+z) — Three.js 우수좌표(북=−z)
 * 원점=(lon0,lat0)=필지중심. 백엔드 ENU payload가 단일 진실원천이며, 본 모듈은 클라이언트
 * 측 재계산·검산·footprint 스케일링을 부작용/네트워크 0으로 결정론 제공한다.
 */

export type LonLat = readonly [number, number]; // [lon, lat] (WGS84, deg)
export type Enu2 = [number, number]; // [x(동), z(남)] (m)

const M_PER_DEG = 111_320.0;
const toRad = (deg: number): number => (deg * Math.PI) / 180;
const round3 = (v: number): number => Math.round(v * 1000) / 1000;
// -0을 0으로 정규화(===는 -0==0이 true라 분기로 깔끔히 통일).
const norm = (v: number): number => (v === 0 ? 0 : v);

/** WGS84 (lon,lat) → ENU [x(동), z(남)]. 원점=(lon0,lat0). 백엔드 _enu_xz 동일식. */
export function enuXZ(lon: number, lat: number, lon0: number, lat0: number): Enu2 {
  const x = (lon - lon0) * M_PER_DEG * Math.cos(toRad(lat0));
  const z = -(lat - lat0) * M_PER_DEG;
  return [norm(x), norm(z)];
}

/**
 * ring [[lon,lat],...] → ENU [[x,z],...] (소수 3자리 — 백엔드 _ring_to_enu 정합).
 * 무효(빈/유한하지 않은 좌표)는 건너뛴다(가짜 점 금지). 비배열·빈 입력은 빈 배열.
 */
export function ringToEnu(ring: ReadonlyArray<LonLat>, lon0: number, lat0: number): Enu2[] {
  if (!Array.isArray(ring) || ring.length === 0) return [];
  const out: Enu2[] = [];
  for (const p of ring) {
    if (!p || p.length < 2) continue;
    const lon = p[0];
    const lat = p[1];
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const [x, z] = enuXZ(lon, lat, lon0, lat0);
    out.push([round3(x), round3(z)]);
  }
  return out;
}

/** ENU 점들의 축정렬 bbox(footprint 스케일·카메라 프레이밍용). 빈 입력은 null(가짜 bbox 금지). */
export function boundsEnu(
  pts: ReadonlyArray<Enu2>,
): { minX: number; minZ: number; maxX: number; maxZ: number } | null {
  if (!Array.isArray(pts) || pts.length === 0) return null;
  let minX = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxZ = -Infinity;
  for (const [x, z] of pts) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (z < minZ) minZ = z;
    if (z > maxZ) maxZ = z;
  }
  return { minX, minZ, maxX, maxZ };
}
