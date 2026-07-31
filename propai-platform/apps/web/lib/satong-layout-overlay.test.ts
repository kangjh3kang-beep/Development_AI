/**
 * 배치 오버레이 그리기(W3) — 가짜 Leaflet으로 **정리·생성 순서**를 고정한다.
 *
 * ★이 파일이 존재하는 이유(R1 MEDIUM 실증): 이 로직이 `SatongMultiMap`의 effect 안에 있을 때는
 *   jsdom이 Leaflet을 초기화하지 못해(이 저장소는 `window.L`을 억지로 모킹하지 않는 방침)
 *   "이전 레이어 제거 가드 + cleanup"을 통째로 지우는 변이가 **1550개 테스트를 전부 통과**했다.
 *   이 PR 자신이 "잔존 시 두 대안의 동이 겹쳐 보이는 오도"를 핵심 위험으로 지목했는데
 *   그 실패모드의 커버리지가 0이었다. L을 주입받는 순수 함수로 떼어내 그 지점을 잠근다.
 */
import { describe, expect, it, vi } from "vitest";

import {
  BUILDABLE_STYLE,
  NORTH_LIGHT_BAND_STYLE,
  northLightTooltip,
  BUILDING_STYLE,
  buildingTooltip,
  clearLayoutOverlay,
  renderLayoutOverlay,
} from "@/lib/satong-layout-overlay";
import type { SiteLayoutOverlay } from "@/lib/site-layout";

/** 호출 순서를 기록하는 가짜 Leaflet. */
function fakeLeaflet() {
  const calls: string[] = [];
  const polygons: Array<{ rings: unknown; style: Record<string, unknown>; tooltip?: string }> = [];
  const groups: unknown[] = [];
  const map = {
    removed: [] as unknown[],
    removeLayer(layer: unknown) {
      calls.push("removeLayer");
      this.removed.push(layer);
    },
  };
  const L = {
    layerGroup() {
      calls.push("layerGroup");
      const g = { id: `g${groups.length}`, addTo: () => g };
      groups.push(g);
      return g as never;
    },
    polygon(rings: [number, number][][], style: Record<string, unknown>) {
      calls.push("polygon");
      // ★대역 충실도(R1 F3): 실제 Leaflet은 `interactive:false`면 마우스 이벤트를 받지 않아
      //   **툴팁이 뜨지 않는다**. 대역이 이를 모델링하지 않으면 "툴팁 사망" 변이가 생존한다.
      const interactive = style.interactive !== false;
      const rec: { rings: unknown; style: Record<string, unknown>; tooltip?: string } = { rings, style };
      polygons.push(rec);
      const poly = {
        addTo: () => poly,
        bindTooltip: (content: string) => {
          if (interactive) rec.tooltip = content;
          return poly;
        },
      };
      return poly as never;
    },
  };
  return { L, map, calls, polygons, groups };
}

const GEOM = (tag: string) => ({ type: "Polygon", coordinates: [[[0, 0]]], tag }) as unknown;

const OVERLAY = (buildingCount: number, tag = "a"): SiteLayoutOverlay => ({
  northLightBand: null,
  buildable: GEOM(`buildable-${tag}`) as never,
  buildings: {
    type: "FeatureCollection",
    features: Array.from({ length: buildingCount }, (_, i) => ({
      type: "Feature" as const,
      properties: { dong: i + 1, floors: 5 },
      geometry: GEOM(`b${i}-${tag}`) as never,
    })),
  },
});

/** 링 변환기 — 좌표 재계산 없이 통과만(주입 계약 확인용). */
const toRings = () => [[[37, 127]]] as [number, number][][];

describe("renderLayoutOverlay — ★이전 레이어를 항상 먼저 제거한다", () => {
  it("첫 렌더: 제거할 게 없으면 layerGroup만 만든다", () => {
    const { L, map, calls, groups } = fakeLeaflet();
    const g = renderLayoutOverlay({ L, map, previousLayer: null, overlay: OVERLAY(2), toRings });

    expect(g).toBe(groups[0]);
    expect(calls[0]).toBe("layerGroup"); // 제거 호출 없이 시작
    expect(map.removed).toHaveLength(0);
  });

  it("★재렌더(대안 전환): 새 그룹을 만들기 **전에** 이전 그룹을 제거한다", () => {
    const { L, map, calls } = fakeLeaflet();
    const prev = { id: "prev" };
    renderLayoutOverlay({ L, map, previousLayer: prev, overlay: OVERLAY(2, "b"), toRings });

    // ★순서가 핵심: removeLayer가 layerGroup보다 앞이어야 잔존이 불가능하다.
    expect(calls.indexOf("removeLayer")).toBeLessThan(calls.indexOf("layerGroup"));
    expect(map.removed).toEqual([prev]);
  });

  it("★overlay가 null이어도(조회 실패·필지 전환) 이전 레이어는 제거한다", () => {
    const { L, map, calls } = fakeLeaflet();
    const prev = { id: "prev" };
    const g = renderLayoutOverlay({ L, map, previousLayer: prev, overlay: null, toRings });

    expect(g).toBeNull();
    expect(map.removed).toEqual([prev]); // 잔존 금지
    expect(calls).not.toContain("layerGroup"); // 새로 그리지도 않는다
  });

  it("L·map이 없으면 그리지 않지만 이전 레이어 제거는 시도한다", () => {
    const { map } = fakeLeaflet();
    const prev = { id: "prev" };
    expect(
      renderLayoutOverlay({ L: null, map, previousLayer: prev, overlay: OVERLAY(1), toRings }),
    ).toBeNull();
    expect(map.removed).toEqual([prev]);
  });
});

describe("renderLayoutOverlay — 그리는 내용", () => {
  it("건축가능 영역 1개 + 동 N개를 그린다(개수가 서버 feature 수와 일치)", () => {
    const { L, map, polygons } = fakeLeaflet();
    renderLayoutOverlay({ L, map, previousLayer: null, overlay: OVERLAY(3), toRings });

    expect(polygons).toHaveLength(4); // buildable 1 + 동 3
    expect(polygons[0].style).toMatchObject({ dashArray: BUILDABLE_STYLE.dashArray });
    expect(polygons[1].style).toMatchObject({ fillOpacity: BUILDING_STYLE.fillOpacity });
  });

  it("★동 툴팁에 근사임이 박힌다 — '도면'으로 오독되지 않게", () => {
    const { L, map, polygons } = fakeLeaflet();
    renderLayoutOverlay({ L, map, previousLayer: null, overlay: OVERLAY(1), toRings });

    expect(polygons[1].tooltip).toBe("1동 · 5층 (볼륨 감 · 축정렬 근사)");
    expect(polygons[1].tooltip).toContain("근사");
  });

  it("링이 비면 그 도형을 건너뛴다(빈 폴리곤 생성 금지)", () => {
    const { L, map, polygons, groups, map: m } = fakeLeaflet();
    const g = renderLayoutOverlay({
      L, map, previousLayer: null, overlay: OVERLAY(2), toRings: () => [],
    });
    expect(polygons).toHaveLength(0);
    // 그릴 것이 없으면 빈 그룹을 지도에 남기지 않는다(유령 레이어 방지).
    expect(g).toBeNull();
    expect(m.removed).toContain(groups[0]);
  });

  it("건축가능 영역만 있어도 그린다(세트백 밴드는 유효 정보)", () => {
    const { L, map, polygons } = fakeLeaflet();
    const g = renderLayoutOverlay({
      L, map, previousLayer: null,
      overlay: { buildable: GEOM("only") as never, buildings: null, northLightBand: null },
      toRings,
    });
    expect(g).not.toBeNull();
    expect(polygons).toHaveLength(1);
  });
});

describe("clearLayoutOverlay", () => {
  it("map·layer가 없으면 아무 것도 하지 않는다", () => {
    expect(() => clearLayoutOverlay(null, { id: "x" })).not.toThrow();
    const { map } = fakeLeaflet();
    clearLayoutOverlay(map, null);
    expect(map.removed).toHaveLength(0);
  });

  it("removeLayer가 던져도 전파하지 않는다(지도 파괴 후 cleanup)", () => {
    const map = { removeLayer: vi.fn(() => { throw new Error("destroyed"); }) };
    expect(() => clearLayoutOverlay(map, { id: "x" })).not.toThrow();
    expect(map.removeLayer).toHaveBeenCalled();
  });
});

describe("buildingTooltip — 결손 필드 정직 처리", () => {
  it("동·층 정보가 없으면 만들어내지 않는다", () => {
    expect(buildingTooltip(undefined, undefined)).toBe("동 (볼륨 감 · 축정렬 근사)");
    expect(buildingTooltip(2, undefined)).toBe("2동 (볼륨 감 · 축정렬 근사)");
  });
});


describe("정북 일조 밴드(W3-b) — 그리는 순서와 정직 문구", () => {
  it("★밴드는 **가장 먼저** 그린다 — 동·건축가능 영역이 위에 와야 가려지지 않는다", () => {
    const { L, map, polygons } = fakeLeaflet();
    renderLayoutOverlay({
      L, map, previousLayer: null,
      overlay: { buildable: GEOM("b") as never, buildings: null, northLightBand: GEOM("nl") as never },
      toRings,
    });
    // 첫 폴리곤이 밴드(앰버), 그 다음이 건축가능(파랑 점선).
    expect(polygons).toHaveLength(2);
    expect(polygons[0].style).toMatchObject({ fillColor: NORTH_LIGHT_BAND_STYLE.fillColor });
    expect(polygons[1].style).toMatchObject({ dashArray: BUILDABLE_STYLE.dashArray });
  });

  it("★밴드 색은 건축가능 영역과 **다르다** — 의미가 반대라 같은 색이면 같은 종류로 읽힌다", () => {
    expect(NORTH_LIGHT_BAND_STYLE.fillColor).not.toBe(BUILDABLE_STYLE.fillColor);
  });

  it("★밴드는 **반투명**이고 상호작용 가능하다 — 계획서 문언이 '반투명 밴드'이고, 불투명하면 "
     + "필지·지적을 가리며 interactive:false면 툴팁(한계 고지)이 아예 안 뜬다", () => {
    expect(NORTH_LIGHT_BAND_STYLE.fillOpacity).toBeLessThan(0.5);
    expect(NORTH_LIGHT_BAND_STYLE.fillOpacity).toBeGreaterThan(0);
    expect(NORTH_LIGHT_BAND_STYLE.interactive).toBe(true);
  });

  it("밴드가 없으면(미적용 용도지역) 그리지 않는다", () => {
    const { L, map, polygons } = fakeLeaflet();
    renderLayoutOverlay({
      L, map, previousLayer: null,
      overlay: { buildable: GEOM("b") as never, buildings: null, northLightBand: null },
      toRings,
    });
    expect(polygons).toHaveLength(1);
  });

  it("★밴드만 있어도 그린다(대안 기하가 없어도 제약은 보여준다)", () => {
    const { L, map, polygons } = fakeLeaflet();
    const g = renderLayoutOverlay({
      L, map, previousLayer: null,
      overlay: { buildable: null, buildings: null, northLightBand: GEOM("nl") as never },
      toRings,
    });
    expect(g).not.toBeNull();
    expect(polygons).toHaveLength(1);
  });

  it("★툴팁에 '높이 기준'과 '근사'가 박힌다 — 확정 도면으로 오독되면 안 된다", () => {
    const { L, map, polygons } = fakeLeaflet();
    renderLayoutOverlay({
      L, map, previousLayer: null,
      overlay: { buildable: null, buildings: null, northLightBand: GEOM("nl") as never },
      toRings, northLightSetbackM: 24, northLightHeightM: 48,
    });
    const t = polygons[0].tooltip ?? "";
    expect(t).toContain("24m");
    expect(t).toContain("48m 기준");
    expect(t).toContain("건축 불가");
    expect(t).toContain("근사");
  });

  it("수치가 없으면 지어내지 않는다(일반 문구로 떨어진다)", () => {
    expect(northLightTooltip(undefined, undefined)).toContain("필요 이격");
    expect(northLightTooltip(undefined, undefined)).toContain("선택 안 높이 기준");
  });
});
