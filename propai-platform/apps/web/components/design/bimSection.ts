/**
 * §4-E BIM 3D 단면(slicer) 순수 코어 — 절단 높이·가시 층수 계산(결정론).
 *
 * 3D 뷰어(R3F)에서 분리해 단위 테스트 가능하게 한다. 수직축은 Three.js 기본 Y(층은
 * y=f*floorHeight로 적층). 전역 클립평면 THREE.Plane((0,-1,0), cutHeight)가 y<=cutHeight를
 * 남기고 위를 잘라낸다(절단선 아래만 보임). 본 모듈은 그 cutHeight와 가시 층수를 산출한다.
 */

/** 건물 전체 높이(m) = 층수 × 층고. 0/음수 입력은 0(가짜 높이 금지). */
export function buildingHeightM(floorCount: number, floorHeightM: number): number {
  return Math.max(0, floorCount || 0) * Math.max(0, floorHeightM || 0);
}

/** 슬라이더 %(0~100) → 절단 높이(m). 100%=전체(절단 없음), 0%=바닥. 범위 밖은 클램프. */
export function sectionCutHeightM(pct: number, heightM: number): number {
  const p = Math.min(100, Math.max(0, pct || 0)) / 100;
  return Math.max(0, heightM || 0) * p;
}

/** 절단선 아래로 완전히 노출되는 층수 = floor(cutHeight/floorHeight), numFloors로 클램프. */
export function visibleFloorCount(
  cutHeightM: number,
  floorHeightM: number,
  numFloors: number,
): number {
  if (!(floorHeightM > 0)) return 0;
  const n = Math.floor(cutHeightM / floorHeightM + 1e-9);
  return Math.min(Math.max(0, numFloors || 0), Math.max(0, n));
}
