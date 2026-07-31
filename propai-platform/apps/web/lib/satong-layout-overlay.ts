/**
 * 배치 미리보기 지도 오버레이 그리기(W3) — Leaflet 호출을 **주입**받는 순수 로직.
 *
 * ★왜 컴포넌트에서 떼어냈나(R1 MEDIUM):
 *   오버레이 layerGroup의 생성·제거 로직이 `SatongMultiMap`의 effect 안에 있었고, jsdom은
 *   Leaflet을 초기화하지 못해(이 저장소는 `window.L`을 억지로 모킹하지 않는 방침) **어떤
 *   테스트도 그 지점에 닿지 못했다**. 리뷰어가 "이전 레이어 제거 가드 + cleanup"을 통째로
 *   지우는 변이를 넣었는데 1550개 테스트가 전부 통과했다 — 이 PR 자신이 "잔존 시 두 대안의 동이
 *   겹쳐 보이는 오도"를 핵심 위험으로 지목했는데 그 실패모드 커버리지가 0이었다.
 *   → Leaflet(L)과 링 변환기(toRings)를 **인자로 주입**해 순수 함수로 만들면 가짜 L로 호출
 *     순서·개수를 검증할 수 있다(같은 저장소의 `satong-click-menu.ts`가 `ringsOf`를 주입받는
 *     선례와 동일한 패턴).
 */
import type { SiteLayoutOverlay } from "@/lib/site-layout";

/** Leaflet 최소 표면 — 이 모듈이 실제로 쓰는 것만(테스트에서 가짜로 대체 가능). */
export type LeafletLike = {
  layerGroup: () => LeafletLayerGroupLike;
  polygon: (rings: [number, number][][], style: Record<string, unknown>) => LeafletPolygonLike;
};

export type LeafletLayerGroupLike = {
  addTo: (map: unknown) => LeafletLayerGroupLike;
};

export type LeafletPolygonLike = {
  addTo: (group: unknown) => LeafletPolygonLike;
  bindTooltip?: (content: string, options?: Record<string, unknown>) => unknown;
};

export type LeafletMapLike = {
  removeLayer: (layer: unknown) => void;
};

/** 건축가능 영역(세트백 오프셋 후) — 점선·저채도. 대지와의 차이가 곧 세트백 밴드다. */
export const BUILDABLE_STYLE = {
  color: "#7C98F2",
  weight: 1.5,
  dashArray: "5,4",
  fillColor: "#7C98F2",
  fillOpacity: 0.1,
  interactive: false,
  bubblingMouseEvents: false,
} as const;

/**
 * ★W3-b 정북 일조 금지 띠 — **경고 색(앰버)·사선 없는 반투명 면**.
 *
 * 건축가능 영역(파랑 점선)과 **색으로 구분**한다: 파랑은 "지을 수 있는 곳", 앰버는 "이 높이로는
 * 지을 수 없는 곳"이라 의미가 반대다. 같은 색 계열로 그리면 두 밴드가 같은 종류로 읽힌다.
 * 동(불투명 파랑)보다 아래에 깔리도록 **먼저** 그린다.
 */
export const NORTH_LIGHT_BAND_STYLE = {
  color: "#f59e0b",
  weight: 1,
  dashArray: "2,3",
  fillColor: "#f59e0b",
  fillOpacity: 0.18,
  interactive: true,
  bubblingMouseEvents: false,
} as const;

/** 밴드 툴팁 — ★근사임과 '높이 기준'임을 문구에 박는다(도면으로 오독 방지). */
export function northLightTooltip(setbackM: unknown, heightM: unknown): string {
  const d = typeof setbackM === "number" ? `${setbackM}m` : "필요 이격";
  const h = typeof heightM === "number" ? `${heightM}m 기준` : "선택 안 높이 기준";
  return `정북 일조 이격 ${d} (${h} · 이 띠에는 그 높이로 건축 불가 · 북측 경계 직선 근사)`;
}

/** 동 풋프린트 — 실선·불투명도 높임(선택 대안만). */
export const BUILDING_STYLE = {
  color: "#135bec",
  weight: 2,
  fillColor: "#135bec",
  fillOpacity: 0.42,
  interactive: true,
  bubblingMouseEvents: false,
} as const;

/** 동 툴팁 — ★"도면"으로 오독되지 않게 근사임을 문구에 박는다. */
export function buildingTooltip(dong: unknown, floors: unknown): string {
  const head = typeof dong === "number" ? `${dong}동` : "동";
  const tail = typeof floors === "number" ? ` · ${floors}층` : "";
  return `${head}${tail} (볼륨 감 · 축정렬 근사)`;
}

/** 기존 오버레이 레이어를 지도에서 제거한다(예외는 무시 — 지도 파괴 후 cleanup 등). */
export function clearLayoutOverlay(map: LeafletMapLike | null, layer: unknown): void {
  if (!map || !layer) return;
  try {
    map.removeLayer(layer);
  } catch {
    /* noop — 이미 제거됐거나 지도가 파괴된 경우 */
  }
}

/**
 * 오버레이를 그린다. **항상 이전 레이어를 먼저 제거**한 뒤 새 layerGroup을 만든다.
 *
 * ★부분 갱신을 하지 않는 이유: 대안을 전환하면 이전 대안의 동이 남아 두 대안이 겹쳐 보이고,
 *   사용자는 있지도 않은 밀도를 본다. 통째로 갈아끼우는 것이 유일하게 안전하다.
 *
 * @returns 새로 만든 layerGroup(없으면 null — overlay가 없거나 그릴 기하가 없을 때)
 */
export function renderLayoutOverlay(args: {
  L: LeafletLike | null | undefined;
  map: LeafletMapLike | null | undefined;
  /** 이전에 그린 layerGroup — 항상 먼저 제거된다. */
  previousLayer: unknown;
  overlay: SiteLayoutOverlay | null | undefined;
  /** GeoJSON geometry → Leaflet 링. 지도측 공용 변환기를 주입받는다(좌표 재계산 없음). */
  toRings: (geometry: unknown) => [number, number][][];
  /** ★W3-b 밴드 툴팁용 — 선택 대안의 이격·높이(없으면 문구가 일반형으로 떨어진다). */
  northLightSetbackM?: number | null;
  northLightHeightM?: number | null;
}): LeafletLayerGroupLike | null {
  const { L, map, previousLayer, overlay, toRings } = args;

  // ★언제나 먼저 정리한다 — overlay가 null이어도(조회 실패·필지 전환) 잔존은 허용하지 않는다.
  clearLayoutOverlay(map ?? null, previousLayer);

  if (!L || !map || !overlay) return null;

  const group = L.layerGroup().addTo(map);
  let drawn = 0;

  // ★정북 금지 띠를 **가장 먼저** 그린다 — 동·건축가능 영역이 위에 오도록(가림 방지).
  if (overlay.northLightBand) {
    const rings = toRings(overlay.northLightBand);
    if (rings.length > 0) {
      const band = L.polygon(rings, { ...NORTH_LIGHT_BAND_STYLE }).addTo(group);
      try {
        band.bindTooltip?.(
          northLightTooltip(args.northLightSetbackM, args.northLightHeightM),
          { direction: "top", opacity: 0.92 },
        );
      } catch {
        /* 툴팁 실패는 도형 표시를 막지 않는다 */
      }
      drawn += 1;
    }
  }

  if (overlay.buildable) {
    const rings = toRings(overlay.buildable);
    if (rings.length > 0) {
      L.polygon(rings, { ...BUILDABLE_STYLE }).addTo(group);
      drawn += 1;
    }
  }

  for (const f of overlay.buildings?.features ?? []) {
    const rings = toRings(f.geometry);
    if (rings.length === 0) continue;
    const poly = L.polygon(rings, { ...BUILDING_STYLE }).addTo(group);
    try {
      poly.bindTooltip?.(buildingTooltip(f.properties?.dong, f.properties?.floors), {
        direction: "top",
        opacity: 0.92,
      });
    } catch {
      /* 툴팁 실패는 도형 표시를 막지 않는다 */
    }
    drawn += 1;
  }

  // 그릴 것이 하나도 없었으면 빈 그룹을 지도에 남기지 않는다(유령 레이어 방지).
  if (drawn === 0) {
    clearLayoutOverlay(map, group);
    return null;
  }
  return group;
}
