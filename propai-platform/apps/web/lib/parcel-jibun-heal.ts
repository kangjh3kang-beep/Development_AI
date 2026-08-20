/**
 * 좌표 앵커로 **지번을 자가치유**한다 — PNU 를 확보하지 못한 필지를
 * `/zoning/parcel-at-point` 로 해석해 진짜 PNU·주소를 받아온다.
 *
 * ## 앵커 우선순위(무날조 경계가 여기 있다)
 *
 *   ① 진짜 PNU 보유            → 치유 불필요(`parcelDisplayAddress` 가 지번을 파생한다)
 *   ② 주소에 지번 보유         → 치유 불필요(이미 필지를 특정한다)
 *   ③ 좌표(lat/lon) 보유       → 좌표로 해석한다
 *   ④ 경계(geometry)만 보유    → 대표점을 **일시 계산**해 해석한다
 *                                ★그 대표점을 **영속하지 않는다** — 근사좌표가 "좌표미상"
 *                                  분기를 전역에서 우회한다(SatongMultiMap.tsx 의
 *                                  boundaryFeatureToMapFeature 주석과 같은 규약).
 *   ⑤ 앵커가 **주소뿐이고 동 단위** → ★해석하지 않는다.
 *                                라이브 실측(2026-08-20): 동 단위 주소는 서버가 임의의 한
 *                                필지(`114-1`)로 수렴시킨다. 같은 동 77필지에 그걸 쓰면
 *                                77행이 전부 같은 오답이 된다 — 지오코딩으로 채우지 않는다.
 *
 * ## 왜 동시성 상한이 필요한가
 *
 * 실제 신고 프로젝트가 **77필지**다. 상한 없이 돌리면 재진입할 때마다 77개 요청이
 * 한꺼번에 나간다. `#694` 가 쓴 상한 4를 그대로 따른다.
 */

import { addressHasJibun, normalizePnu } from "@/lib/pnu";
import { geometryRepresentativePoint } from "@/lib/satong-map-layers";

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
  // ④ 경계 대표점(일시 계산 — 영속 금지)
  return geometryRepresentativePoint(parcel.geometry);
}

/**
 * 치유 대상 **건수**. 이펙트 의존성은 rows 전체가 아니라 이 수를 써야 한다 —
 * 배열 identity 를 의존성으로 두면 치유 결과가 배열을 갱신하고 그게 다시 이펙트를 깨우는
 * 무한 루프가 된다(치유가 성공하면 이 수는 줄어들어 루프가 자연히 멈춘다).
 */
export function countJibunHealTargets(parcels: HealableParcel[]): number {
  return parcels.reduce((n, parcel) => (jibunHealAnchor(parcel) ? n + 1 : n), 0);
}

/** 좌표 → 필지 해석기(호출부가 `/zoning/parcel-at-point` 를 주입한다 — 이 모듈은 순수). */
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
  const targets: Array<{ index: number; point: { lat: number; lon: number } }> = [];
  parcels.forEach((parcel, index) => {
    const point = jibunHealAnchor(parcel);
    if (point) targets.push({ index, point });
  });
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
