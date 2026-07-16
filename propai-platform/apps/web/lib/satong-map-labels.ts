/**
 * 사통맵 라벨(마커 상시 툴팁) 시스템 공용화 — 라벨 폭주·이중 박스·겹침(S1) 봉합의 단일 계약.
 *
 * 종전엔 실거래·분양·경매·POI·개발계획 5곳이 각자 인라인 `bindTooltip` 을 호출하고,
 * 레이어별로 `개수 ≤ 32` 만 판정해 합산 최대 ~160개 상시 라벨이 지도를 살포했다.
 * 여기서 (1) 전역 라벨 버짓 + 줌 LOD 판정을 순수 함수로 모으고,
 *        (2) 라벨 부착을 `bindSatongLabel` 한 곳으로 단일화한다.
 *
 * ★박스 스타일은 `.satong-tooltip` 전역(무레이어) CSS 가 담당한다(globals.css) —
 *   Leaflet 기본 흰 박스·테두리·padding·화살표를 무력화해 '이중 박스'를 제거한다.
 *   이 헬퍼는 라벨 내용을 textContent(안전한 텍스트 노드)로만 넣어 XSS 여지를 없앤다.
 */

/** z≥17(근접)에서 허용하는 전역 상시 라벨 상한(모든 레이어 합산). */
export const SATONG_LABEL_BUDGET = 48;
/** 15~16(중간 줌)에서 허용하는 축소 상한 — '상위 N'만 상시 표시. */
export const SATONG_LABEL_BUDGET_MID = 16;

export type SatongLabelLOD = "all" | "top" | "hover-only";

/**
 * 줌 레벨 → 라벨 LOD(Level of Detail).
 *   z≥17: 전체(버짓 한도 내) · 15~16: 상위 N · <15: hover-only(상시 라벨 0, 겹침 방지).
 */
export function satongLabelLOD(zoom: number): SatongLabelLOD {
  if (zoom >= 17) return "all";
  if (zoom >= 15) return "top";
  return "hover-only";
}

/** 줌 레벨에 대응하는 전역 상시 라벨 버짓(상한). */
export function satongLabelBudget(zoom: number): number {
  const lod = satongLabelLOD(zoom);
  if (lod === "all") return SATONG_LABEL_BUDGET;
  if (lod === "top") return SATONG_LABEL_BUDGET_MID;
  return 0;
}

/** 레이어별 라벨 후보 수(좌표 있는 마커 수). */
export interface SatongLabelLayerCount {
  id: string;
  count: number;
}

/**
 * 전역 버짓을 레이어 우선순위 순서로 배분한다.
 * 반환: layer id → 그 레이어에서 상시(permanent)로 표시 가능한 라벨 수(선두 N개).
 *
 * ★핵심: 합산이 버짓을 넘지 않는다(∑ 반환값 ≤ satongLabelBudget(zoom)). 앞 레이어가 버짓을
 *   먼저 소진하면 뒤 레이어는 0(=전부 hover)이 된다. 각 레이어는 마커를 순서대로 그리며
 *   `순번 < 반환값` 인 마커만 상시 라벨을 붙인다(줌아웃·밀집 시 자동 hover 강등).
 */
export function planSatongLabels(
  zoom: number,
  layers: SatongLabelLayerCount[],
): Record<string, number> {
  let remaining = satongLabelBudget(zoom);
  const out: Record<string, number> = {};
  for (const layer of layers) {
    const take = Math.max(0, Math.min(Math.max(0, layer.count), remaining));
    out[layer.id] = take;
    remaining -= take;
  }
  return out;
}

/** bindSatongLabel 옵션. */
export interface BindSatongLabelOptions {
  /** 상시(true) / hover(false) 표시 — planSatongLabels 판정 결과를 넘긴다. */
  permanent: boolean;
  /** 마커 위쪽 오프셋(px, 양수). 마커 반경만큼 띄운다. 기본 8. */
  offsetY?: number;
}

/**
 * 사통맵 마커에 표준 라벨 툴팁을 부착한다(인라인 bindTooltip 5곳의 단일 대체).
 *
 * @param L       window.L (Leaflet 전역)
 * @param marker  대상 Leaflet 마커/서클마커
 * @param text    라벨 텍스트(원문 — textContent로 안전하게 삽입, 이스케이프 불필요)
 * @param opts    permanent/offsetY
 */
export function bindSatongLabel(
  L: unknown,
  marker: { bindTooltip: (content: unknown, options: unknown) => unknown },
  text: string,
  opts: BindSatongLabelOptions,
): unknown {
  // 내용은 텍스트 노드로만 — HTML 주입(XSS) 여지 제거. 박스 스타일은 .satong-tooltip CSS 담당.
  const el = typeof document !== "undefined" ? document.createElement("span") : null;
  const content: unknown = el ? ((el.textContent = text), el) : text;
  return marker.bindTooltip(content, {
    permanent: opts.permanent,
    direction: "top",
    offset: [0, -(opts.offsetY ?? 8)],
    className: "satong-tooltip",
  });
}
