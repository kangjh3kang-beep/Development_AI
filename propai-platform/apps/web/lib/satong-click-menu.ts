/**
 * 사통맵 지도 클릭 팝오버(단일 팝오버 계약 — 디자인컴프) 순수 로직.
 *
 * 지도 클릭 시 그 지점에 액션 메뉴(필지 선택·정보 / 거리재기 / 닫기)를 1개만 띄운다.
 * 여기는 Leaflet/DOM 비의존 순수 계산만 둔다 — 팝오버 위치 클램프·지점 오버레이 판정 —
 * 렌더는 SatongMultiMap 이 담당한다.
 * ★지번 축약은 여기 없다 — `parcelShortLabel`(lib/pnu) 로 옮겼다. PNU 로 지번을 파생한 뒤
 *   줄여야 하는데 이 모듈은 PNU 를 모른다(축약 구현이 두 벌이면 한쪽만 고쳐진다).
 */

export interface ClickMenuPosition {
  left: number;
  top: number;
}

/**
 * 팝오버 좌표를 지도 컨테이너 안으로 클램프한다.
 * 메뉴는 클릭점 아래(+12px)에 앵커하되, 하단 공간이 부족하면 클릭점 위로 뒤집는다.
 */
export function clampClickMenuPosition(
  point: { x: number; y: number },
  container: { width: number; height: number },
  menu: { width: number; height: number },
): ClickMenuPosition {
  const margin = 8;
  const half = menu.width / 2;
  const left = Math.min(Math.max(point.x, half + margin), Math.max(half + margin, container.width - half - margin));
  const below = point.y + 12;
  const flipped = point.y - 12 - menu.height;
  const top =
    below + menu.height + margin <= container.height
      ? below
      : Math.max(margin, flipped);
  return { left, top };
}

/** Leaflet 링(latlng 쌍 배열들)에 대한 점 포함 판정 — 짝홀(even-odd) 레이캐스팅. */
export function pointInLeafletRings(
  lat: number,
  lon: number,
  rings: Array<Array<[number, number]>>,
): boolean {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const [latI, lonI] = ring[i];
      const [latJ, lonJ] = ring[j];
      const crosses =
        latI > lat !== latJ > lat &&
        lon < ((lonJ - lonI) * (lat - latI)) / (latJ - latI) + lonI;
      if (crosses) inside = !inside;
    }
  }
  return inside;
}

export interface ClickPointFeatureInfo {
  address?: string | null;
  zoneType?: string | null;
  officialPricePerSqm?: number | null;
  buildingAgeYears?: number | null;
}

/**
 * 클릭 지점을 포함하는 오버레이 피처를 찾는다(첫 매치).
 * ringsOf: 피처 → Leaflet 링 변환(지도측 geoJsonToLeafletRings 주입 — 순수성 유지).
 */
export function findFeatureAtPoint<F extends ClickPointFeatureInfo>(
  lat: number,
  lon: number,
  features: F[],
  ringsOf: (feature: F) => Array<Array<[number, number]>>,
): F | null {
  for (const feature of features) {
    const rings = ringsOf(feature);
    if (rings.length > 0 && pointInLeafletRings(lat, lon, rings)) return feature;
  }
  return null;
}
