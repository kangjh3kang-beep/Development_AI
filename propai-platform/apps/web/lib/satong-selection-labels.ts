/**
 * 선택 필지 라벨 — **계획(순수)** 과 **그리기(L 주입)** 를 컴포넌트에서 떼어낸 모듈.
 *
 * ★왜 떼어냈나 (2026-09-03 · #954 적대 리뷰 실측):
 *   토글 배선을 `SatongMultiMap` 의 effect 안에 두고 **소스 문자열 검사**로 잠갔더니,
 *   리뷰어가 넣은 다음 변이가 **통과**했다:
 *
 *       const selectionLabelsOn = satongSelectionLabelsVisible(layerState) || true;
 *
 *   `|| true` 는 토글을 **아무 일도 안 하게** 만든다 = 이 PR 이 고치려던 결함의 부활인데,
 *   락이 본 것은 «그 줄에 그 함수 이름이 있는가» 였다. **이름은 있고 값은 안 실린다.**
 *   jsdom 은 Leaflet CDN 을 못 읽어 `mapReady` 가 영영 false 라 effect 를 태울 수 없었고,
 *   그래서 «소스 검사밖에 못 한다» 고 적었다. ★그런데 **형제가 이미 그 답을 갖고 있었다** —
 *   `lib/satong-layout-overlay.ts` 는 같은 이유로 로직을 빼고 `!mapReady` 조기반환을
 *   **일부러 두지 않아** jsdom 에서도 위임 호출이 일어나게 했다(그 파일 주석에 명문으로 적혀 있다).
 *   여기서는 그 선례를 그대로 따른다.
 *
 * ★계획을 먼저 세우는 이유: 그릴 것이 없으면 layerGroup 을 **아예 만들지 않는다.**
 *   종전 코드는 그룹을 만든 뒤 `points.length === 0` 이면 반환해 **보이지 않는 빈 그룹**을
 *   남겼다(리뷰가 지적). 계획이 앞서면 그 경로 자체가 사라진다.
 */
import { bindSatongLabel } from "@/lib/satong-map-labels";

export type SelectionLabelAnchor = { lat: number; lon: number; label: string };

/**
 * 라벨 계획. ★`hidden` 과 `empty` 를 **가른다** — 둘 다 «아무것도 안 그린다» 지만
 * 원인이 다르다(토글로 껐다 vs 그릴 필지가 없다). 뭉치면 «껐는데 안 꺼진 것» 과
 * «켰는데 데이터가 없는 것» 이 테스트에서 같은 모양이 된다.
 */
export type SelectionLabelPlan =
  | { kind: "hidden" }
  | { kind: "empty" }
  | { kind: "rollup"; anchors: SelectionLabelAnchor[] }
  | { kind: "each"; anchors: SelectionLabelAnchor[] };

export type SelectionLabelFeature = {
  address: string;
  pnu?: string | null;
  lat?: number | null;
  lon?: number | null;
  areaSqm?: number | null;
  geometry?: unknown;
};

export type PlanSelectionLabelsArgs = {
  /** 「선택 필지」 컨트롤 판정 결과. false 면 **어떤 필지가 있어도** 그리지 않는다. */
  visible: boolean;
  /** 줌 LOD 롤업 여부(hover-only 구간). */
  rollup: boolean;
  features: SelectionLabelFeature[];
  /** 좌표가 없는 피처의 대표점 — 주입(순수 유지). */
  representativePoint: (geometry: unknown) => { lat: number; lon: number } | null | undefined;
  /** 짧은 지번 라벨 — 주입. */
  shortLabel: (feature: SelectionLabelFeature) => string;
};

export function planSelectionLabels(args: PlanSelectionLabelsArgs): SelectionLabelPlan {
  // ★가장 먼저 판정한다 — 이 한 줄이 토글의 전부다.
  if (!args.visible) return { kind: "hidden" };

  const points: { feature: SelectionLabelFeature; lat: number; lon: number }[] = [];
  for (const feature of args.features) {
    const p =
      feature.lat != null && feature.lon != null
        ? { lat: feature.lat, lon: feature.lon }
        : args.representativePoint(feature.geometry);
    if (p && p.lat != null && p.lon != null) points.push({ feature, lat: p.lat, lon: p.lon });
  }
  if (points.length === 0) return { kind: "empty" };

  // ★줌 롤업(U-라벨 파일업): 줌아웃 다필지에서 주소 라벨을 전부 상시 표시하면 한 점에
  //   겹겹이 쌓인다. 집계 칩 1개로 접고, 줌인에서만 필지별 짧은 지번을 단다.
  //   단일 필지는 어느 줌에서도 개별 라벨(초기 진입 식별 — PR#329 LOW1 의도 유지).
  if (args.rollup && points.length > 1) {
    const lat = points.reduce((s, e) => s + e.lat, 0) / points.length;
    const lon = points.reduce((s, e) => s + e.lon, 0) / points.length;
    // ★정직표기: 면적은 라벨이 세는 피처와 **같은 모집단**으로 합산하고, 결측이 하나라도
    //   있으면 부분합을 전체합처럼 보이게 하지 않도록 면적 표기를 생략한다.
    const hasAllAreas = points.every((e) => (e.feature.areaSqm ?? 0) > 0);
    const totalArea = points.reduce((s, e) => s + (e.feature.areaSqm || 0), 0);
    const label = `선택 ${points.length}필지${
      hasAllAreas && totalArea > 0 ? ` · ${Math.round(totalArea).toLocaleString()}㎡` : ""
    }`;
    return { kind: "rollup", anchors: [{ lat, lon, label }] };
  }

  return {
    kind: "each",
    anchors: points.map((e) => ({ lat: e.lat, lon: e.lon, label: args.shortLabel(e.feature) })),
  };
}

/** 이 모듈이 실제로 쓰는 Leaflet 표면만(테스트에서 가짜로 대체 가능). */
export type SelectionLabelL = {
  layerGroup: () => { addTo: (map: unknown) => unknown };
  circleMarker: (
    latlng: [number, number],
    style: Record<string, unknown>,
  ) => { addTo: (g: unknown) => { bindTooltip: (content: unknown, options: unknown) => unknown } };
};

export type RenderSelectionLabelsArgs = {
  L: SelectionLabelL | undefined | null;
  map: unknown;
  previousLayer: { remove?: () => void } | null | undefined;
  plan: SelectionLabelPlan;
};

/**
 * 계획을 그린다.
 *
 * ★★`previousLayer` 정리는 **방어적 경로이고, 프로덕션에서는 도달하지 않는다.**
 *   (2026-09-03 2차 적대 리뷰 실측 — 그리고 나는 **정반대를 이 자리에 적었었다.**)
 *   유일한 프로덕션 호출부는 `SatongMultiMap` 의 라벨 이펙트인데, React 가 deps 변경 시
 *   **이전 클린업을 먼저** 돌리고 그 클린업이 ref 를 null 로 만든다 → 여기 도달할 때
 *   `previousLayer` 는 **항상 null** 이다. 낡은 라벨을 실제로 걷어내는 것은 **그 클린업**이다.
 *   ★그러므로 *"이 정리가 순서 의존을 없앤다"* 는 **틀린 주장이었다.** 지웠다.
 *   이 경로를 남기는 이유는 ①이 모듈이 다른 호출부에서 재사용될 때의 안전망 ②`!L||!map`
 *   구간에서 이전 레이어가 남는 것을 막는 것뿐이다 — **변이가 생존해도 구멍이 아니다.**
 *   실제 잠금은 `satong-selection-label-toggle.test.tsx` 의 **언마운트** 케이스에 있다.
 * ★`!L || !map` 이면 그리지 않고 정리만 한다(jsdom 안전 — 형제 모듈과 같은 계약).
 */
export function renderSelectionLabels(args: RenderSelectionLabelsArgs): unknown {
  try {
    args.previousLayer?.remove?.();
  } catch {
    /* noop */
  }
  const { L, map, plan } = args;
  if (!L || !map) return null;
  if (plan.kind === "hidden" || plan.kind === "empty") return null;

  const group = L.layerGroup().addTo(map) as { remove?: () => void };
  for (const a of plan.anchors) {
    // 시각 마커(폴리곤·staged 초록점)는 다른 이펙트가 이미 그리므로 여기서는 **투명 앵커**에
    // 라벨만 부착한다(중복 마커 방지).
    const anchor = L.circleMarker([a.lat, a.lon], {
      radius: 0,
      opacity: 0,
      fillOpacity: 0,
      interactive: false,
    }).addTo(group);
    bindSatongLabel(anchor, a.label, { permanent: true, offsetY: 2 });
  }
  return group;
}
