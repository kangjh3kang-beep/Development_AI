/**
 * 실거래 마커의 **화면 내/밖** 집계 — 「무음 절단 금지」를 뷰포트 축으로 확장한다.
 *
 * ★왜 필요한가(2026-09-04 라이브 실측): 범례는 `실거래 N곳`이라 적는데 그 N은 **생성한**
 *   마커 수이고 **화면에 보이는** 수가 아니다. 실거래 fitBounds 는 maxZoom 15 인데
 *   지적도는 CADASTRE_MIN_ZOOM(17) 이상에서만 보이므로, 사용자가 지적을 보려고 확대하면
 *   먼 마커부터 뷰포트를 벗어난다. 그때 범례는 여전히 6곳이라 말한다 →
 *   사용자는 「아파트가 없다」로 읽는다. 실제 신고가 정확히 그것이었다.
 *
 *   실측(지도 컨테이너 962x600): z15 에서 6/6 화면 안 → z17 에서 5/6 이탈.
 *   이탈한 것이 전부 원거리였고 그 원거리가 전부 아파트라 **유형 결함처럼 보였다.**
 *   유형 분기는 코드 어디에도 없다 — 그래서 이 함수는 **유형을 차별하지 않는다.**
 *
 * ★Leaflet 의존이 없다. 이 파일의 관례대로(resolveMarketRenderPlan·planSatongLabels와 동형)
 *   "무엇을 고지할지" 결정 로직만 순수함수로 분리해 window.L 목업 없이 회귀 테스트한다.
 */

/** 지도 뷰포트(위경도 경계). Leaflet LatLngBounds 에서 파생해 넘긴다. */
export interface MarketViewportBounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface MarketViewportSummary {
  /** 그린 마커(그룹) 총수 — 범례의 "N곳"과 같은 모집단. */
  total: number;
  /**
   * 화면 안/밖 마커 수. ★`null` = **판정하지 않았다**(경계 미확보·비정상 경계).
   *
   * ★0 으로 쓰지 않는다 — `0`(재 봤고 전부 보인다)과 `null`(못 쟀다)이 화면에서
   *   구별되지 않으면 «모름»이 «이상 없음»으로 읽힌다. 이 저장소가 이미 데인 형태다.
   */
  inView: number | null;
  outside: number | null;
  /** 좌표가 유한수가 아니라 어느 쪽으로도 판정할 수 없는 수(정직 고지용). */
  indeterminate: number;
  /** 유형별 **화면 밖** 수 — 어느 유형이 사라졌는지 말해 준다. */
  outsideByType: Record<string, number>;
}

/** 경계가 판정에 쓸 수 있는 값인가. */
function usableBounds(b: MarketViewportBounds | null | undefined): b is MarketViewportBounds {
  if (!b) return false;
  const { south, west, north, east } = b;
  if (![south, west, north, east].every((v) => typeof v === "number" && Number.isFinite(v))) return false;
  // ★양방향으로 건다 — 한쪽만 검사하면 뒤집힌 경계가 조용히 "전부 화면 밖"을 만든다.
  if (south > north) return false;
  // 경도 래핑(동경<서경)은 국내 좌표에 없어야 한다. 나오면 **판정을 거부**한다(추측 금지).
  if (west > east) return false;
  return true;
}

/**
 * 렌더 계획과 현재 뷰포트로 화면 내/밖을 집계한다.
 *
 * @param entries 유형별 렌더 계획(resolveMarketRenderPlan 결과와 구조 호환)
 * @param bounds  현재 지도 경계. 없거나 비정상이면 **판정하지 않는다**(null 반환).
 */
export function summarizeMarketViewport(
  entries: ReadonlyArray<{ type: string; groups: ReadonlyArray<{ lat?: number | null; lon?: number | null }> }> | null | undefined,
  bounds: MarketViewportBounds | null | undefined,
): MarketViewportSummary {
  const list = entries ?? [];
  let total = 0;
  let indeterminate = 0;
  let inView = 0;
  let outside = 0;
  const outsideByType: Record<string, number> = {};

  const judged = usableBounds(bounds);

  for (const entry of list) {
    for (const g of entry.groups ?? []) {
      total += 1;
      const lat = g?.lat;
      const lon = g?.lon;
      const finite =
        typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon);
      if (!finite) {
        indeterminate += 1;
        continue;
      }
      if (!judged) continue;
      // ★경계 위(=)는 화면 **안**으로 센다. 경계를 한쪽만 열면 반대쪽이 무제한이 된다.
      const within =
        lat >= bounds!.south && lat <= bounds!.north && lon >= bounds!.west && lon <= bounds!.east;
      if (within) {
        inView += 1;
      } else {
        outside += 1;
        outsideByType[entry.type] = (outsideByType[entry.type] ?? 0) + 1;
      }
    }
  }

  if (!judged) {
    return { total, inView: null, outside: null, indeterminate, outsideByType: {} };
  }
  return { total, inView, outside, indeterminate, outsideByType };
}

/**
 * 고지 문구. 화면 밖이 없거나 **판정하지 않았으면 빈 문자열**(고지 자체를 생략).
 *
 * ★"화면 밖 0곳"을 찍지 않는다 — 아무 일도 없을 때 말하면 노트가 소음이 되고,
 *   진짜 절단 고지(사전컷·좌표미확보·반경밖)가 그 소음에 묻힌다.
 */
export function marketOffscreenNote(summary: MarketViewportSummary): string {
  if (summary.outside == null || summary.outside <= 0) return "";
  return `화면 밖 ${summary.outside}곳(축소하면 보입니다)`;
}
