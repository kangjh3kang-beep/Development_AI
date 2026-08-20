/**
 * 좌표 앵커로 **지번을 자가치유**한다 — PNU 를 확보하지 못한 필지를
 * `/zoning/parcel-at-point` 로 해석해 진짜 PNU·주소를 받아온다.
 *
 * ## 앵커 우선순위(무날조 경계가 여기 있다)
 *
 *   ① 진짜 PNU 보유            → 치유 불필요(`parcelDisplayAddress` 가 지번을 파생한다)
 *   ② 주소에 지번 보유         → 치유 불필요(이미 필지를 특정한다)
 *   ③ 좌표(lat/lon) 보유       → 좌표로 해석한다
 *   ④ 경계(geometry)만 보유    → 대표점을 **일시 계산**해 해석한다.
 *                                ★그 대표점을 **영속하지 않는다** — 근사좌표가 "좌표미상"
 *                                  분기를 전역에서 우회한다(SatongMultiMap.tsx 의
 *                                  boundaryFeatureToMapFeature 주석과 같은 규약).
 *                                ★★그리고 그 대표점이 **자기 폴리곤 안에 있을 때만** 쓴다 —
 *                                  `geometryRepresentativePoint` 는 **경계상자 중심**이라
 *                                  오목·부정형 필지(서버가 `terrain:"부정형"` 으로 표기하는
 *                                  그 필지들)에서는 **폴리곤 밖**에 떨어진다. 밖의 점으로
 *                                  parcel-at-point 를 때리면 **이웃 필지의 PNU·주소**가 오고,
 *                                  치유가 그걸 채택해 영속한다 — 이 모듈이 없애겠다고 선언한
 *                                  "조용한 오답" 그 자체다. 밖이면 **해석하지 않는다**.
 *   ⑤ 앵커가 **주소뿐이고 동 단위** → ★해석하지 않는다.
 *                                라이브 실측(2026-08-20): 동 단위 주소는 서버가 임의의 한
 *                                필지(`114-1`)로 수렴시킨다. 같은 동 77필지에 그걸 쓰면
 *                                77행이 전부 같은 오답이 된다 — 지오코딩으로 채우지 않는다.
 *
 * ## 면적 대조를 **일부러 안 넣은 이유**(위양성도 결함이다)
 *
 * "응답 면적을 보유분과 대조해 불일치면 미채택" 도 검토했으나 **기각**했다. 보유 면적은 엑셀
 * 입력값인 경우가 많고 그건 비권위다 — 라이브 실측에서 입력 330㎡ 가 공부상 53㎡ 로 정상
 * 보정되며 `area_warning` 이 붙었다. 면적이 크게 다른 것은 **정상 동작**이므로, 그걸 오답
 * 신호로 쓰면 **맞는 치유를 막는다**. 정확한 판정자는 위 ④의 "대표점이 자기 폴리곤 안인가" 다.
 *
 * ## 왜 동시성 상한이 필요한가
 *
 * 실제 신고 프로젝트가 **77필지**다. 상한 없이 돌리면 재진입할 때마다 77개 요청이
 * 한꺼번에 나간다. `#694` 가 쓴 상한 4를 그대로 따른다.
 */

import { addressHasJibun, normalizePnu } from "@/lib/pnu";
import { geometryRepresentativePoint } from "@/lib/satong-map-layers";
import { pointInLeafletRings } from "@/lib/satong-click-menu";

export type HealableParcel = {
  pnu?: string | null;
  address?: string | null;
  lat?: number | null;
  lon?: number | null;
  geometry?: unknown;
};

export type HealedJibun = {
  /** 입력 배열에서의 위치 — 주소가 전부 같아도 행을 틀리지 않게 인덱스로 되돌린다. */
  index: number;
  pnu: string;
  address: string | null;
};

/** 좌표로 해석해야 하는 필지인가 — 그렇다면 쓸 좌표를 돌려준다(아니면 null). */
export function jibunHealAnchor(
  parcel: HealableParcel,
): { lat: number; lon: number } | null {
  // ①② 이미 필지를 특정할 수 있으면 건드리지 않는다.
  if (normalizePnu(parcel.pnu)) return null;
  if (addressHasJibun(parcel.address)) return null;
  // ③ 필지 좌표
  if (
    typeof parcel.lat === "number" && Number.isFinite(parcel.lat) &&
    typeof parcel.lon === "number" && Number.isFinite(parcel.lon)
  ) {
    return { lat: parcel.lat, lon: parcel.lon };
  }
  // ④ 경계 대표점(일시 계산 — 영속 금지). **자기 폴리곤 안일 때만** 쓴다.
  const point = geometryRepresentativePoint(parcel.geometry);
  if (!point) return null;
  const rings = geometryToLatLonRings(parcel.geometry);
  // 링을 못 읽으면(형식 밖) 판정할 수 없다 → 쓰지 않는다(모르면 안 쓴다).
  if (rings.length === 0) return null;
  return pointInLeafletRings(point.lat, point.lon, rings) ? point : null;
}

/** GeoJSON Polygon/MultiPolygon → Leaflet 링([lat, lon] 쌍 배열들). GeoJSON 은 [lon, lat] 순서. */
function geometryToLatLonRings(geometry: unknown): Array<Array<[number, number]>> {
  const geo = geometry as { type?: string; coordinates?: unknown } | null | undefined;
  if (!geo?.type || !Array.isArray(geo.coordinates)) return [];
  const rings: Array<Array<[number, number]>> = [];
  const eatRing = (ring: unknown) => {
    if (!Array.isArray(ring)) return;
    const pts: Array<[number, number]> = [];
    for (const pt of ring) {
      if (!Array.isArray(pt) || pt.length < 2) continue;
      const [lon, lat] = pt as [number, number];
      if (Number.isFinite(lon) && Number.isFinite(lat)) pts.push([lat, lon]);
    }
    if (pts.length >= 3) rings.push(pts);
  };
  if (geo.type === "Polygon") {
    (geo.coordinates as unknown[]).forEach(eatRing);
  } else if (geo.type === "MultiPolygon") {
    (geo.coordinates as unknown[]).forEach((poly) => {
      if (Array.isArray(poly)) poly.forEach(eatRing);
    });
  }
  return rings;
}

/**
 * 치유 대상 목록 — **좌표를 공유하는 필지는 전부 제외한다.**
 *
 * ## 왜 (2026-08-20 백엔드 실측)
 *
 * `parcel_excel_service` 의 지오코딩은 동 단위 주소 행에 대해
 * **`lat`/`lon` 을 먼저 박고 그 뒤에** "번지 없이 동·읍·면 단위만 입력" 가드로 `pnu` 를
 * 보류한다(`p["lat"]=…` → C2-2 `status="ambiguous"; return` → `p["pnu"]=gp` 미도달).
 * 즉 **PNU 는 정직하게 비었는데 좌표는 77행이 전부 동 대표지점**일 수 있다.
 *
 * 그 좌표로 `parcel-at-point` 를 때리면 77행이 **전부 같은 필지(114-1)** 를 받는다 —
 * 이 모듈이 없애겠다고 선언한 바로 그 "조용한 오답" 이다. 지금은 엑셀 유입부가 좌표를
 * 싣지 않아 도달하지 않지만, 그건 **우연한 보호**다(한 줄만 추가되면 뚫린다).
 *
 * 판정은 단순하고 확실하다: **서로 다른 필지가 같은 좌표를 가질 수 없다.**
 * 좌표가 겹치면 그건 필지 좌표가 아니라 **파생·대표 좌표**이므로 정체성 해석에 쓰지 않는다.
 */
export function collectJibunHealTargets(
  parcels: HealableParcel[],
): Array<{ index: number; point: { lat: number; lon: number } }> {
  const found: Array<{ index: number; point: { lat: number; lon: number } }> = [];
  const seen = new Map<string, number>();
  parcels.forEach((parcel, index) => {
    const point = jibunHealAnchor(parcel);
    if (!point) return;
    const key = `${point.lat},${point.lon}`;
    seen.set(key, (seen.get(key) ?? 0) + 1);
    found.push({ index, point });
  });
  return found.filter((t) => (seen.get(`${t.point.lat},${t.point.lon}`) ?? 0) === 1);
}

/**
 * 치유 대상 **건수**. 이펙트 의존성은 rows 전체가 아니라 이 수를 써야 한다 —
 * 배열 identity 를 의존성으로 두면 치유 결과가 배열을 갱신하고 그게 다시 이펙트를 깨우는
 * 무한 루프가 된다(치유가 성공하면 이 수는 줄어들어 루프가 자연히 멈춘다).
 */
export function countJibunHealTargets(parcels: HealableParcel[]): number {
  return collectJibunHealTargets(parcels).length;
}

/** 좌표 → 필지 해석기(호출부가 `/zoning/parcel-at-point` 를 주입한다 — 이 모듈은 순수).
 *  ※ 이 별칭의 **타입 시그니처 줄**을 지우는 변이는 런타임 동작이 없어 테스트로 잡히지 않는다
 *    (컴파일 단계에서만 의미가 있다 — type-check 가 그 층의 게이트다). */
export type ParcelPointResolver = (
  point: { lat: number; lon: number },
) => Promise<{ pnu?: string | null; address?: string | null } | null>;

/**
 * 미해석 필지를 좌표로 해석한다. **진짜 PNU 를 받은 것만** 결과에 넣는다(무날조).
 * @param limit 동시 요청 상한(기본 4).
 */
export async function healParcelJibunByPoint(
  parcels: HealableParcel[],
  resolve: ParcelPointResolver,
  options?: { limit?: number; isCancelled?: () => boolean },
): Promise<HealedJibun[]> {
  const limit = Math.max(1, options?.limit ?? 4);
  // ★대상 선별은 countJibunHealTargets 와 **같은 함수**를 쓴다 — 두 벌이면 이펙트가 세는 수와
  //   실제로 쏘는 수가 갈려, 줄지 않는 카운트로 무한 재실행이 된다.
  const targets = collectJibunHealTargets(parcels);
  if (targets.length === 0) return [];

  const healed: HealedJibun[] = [];
  let cursor = 0;
  const worker = async () => {
    for (;;) {
      if (options?.isCancelled?.()) return;
      const task = targets[cursor];
      cursor += 1;
      if (!task) return;
      let result: Awaited<ReturnType<ParcelPointResolver>> = null;
      try {
        result = await resolve(task.point);
      } catch {
        // 한 필지의 실패가 나머지를 막지 않는다 — 그 필지는 정직하게 미해석으로 남는다.
        continue;
      }
      const pnu = normalizePnu(result?.pnu);
      if (!pnu) continue; // 서버가 필지를 특정하지 못했다 → 지어내지 않는다.
      healed.push({ index: task.index, pnu, address: result?.address ?? null });
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, targets.length) }, worker));
  return healed;
}
