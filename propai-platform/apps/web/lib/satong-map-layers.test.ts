import { describe, expect, it } from "vitest";

import {
  hasSatongLayer,
  hasSatongLayerControl,
  mergeSatongMapFeatures,
  resolveVWorldBaseLayer,
  satongMapFeatureKey,
  zoneColor,
  type SatongMapLayerState,
} from "./satong-map-layers";

describe("satong-map-layers", () => {
  it("오른쪽 레이어 탭 상태를 VWorld 베이스 지도 모드로 해석한다", () => {
    expect(resolveVWorldBaseLayer(undefined)).toBe("Base");

    const satellite: SatongMapLayerState = {
      enabledLayerIds: ["cadastre", "terrain"],
      controlsByLayer: { terrain: ["satellite"] },
    };
    expect(resolveVWorldBaseLayer(satellite)).toBe("Satellite");

    const hybrid: SatongMapLayerState = {
      enabledLayerIds: ["cadastre", "terrain"],
      controlsByLayer: { terrain: ["hybrid"] },
    };
    expect(resolveVWorldBaseLayer(hybrid)).toBe("Hybrid");

    const ignoredWhenDisabled: SatongMapLayerState = {
      enabledLayerIds: ["cadastre"],
      controlsByLayer: { terrain: ["satellite"] },
    };
    expect(resolveVWorldBaseLayer(ignoredWhenDisabled)).toBe("Base");
  });

  it("레이어와 세부 컨트롤 활성 상태를 분리해 판정한다", () => {
    const state: SatongMapLayerState = {
      enabledLayerIds: ["cadastre", "zoning"],
      controlsByLayer: { zoning: ["land-use"] },
    };

    expect(hasSatongLayer(state, "zoning")).toBe(true);
    expect(hasSatongLayer(state, "official-price")).toBe(false);
    expect(hasSatongLayerControl(state, "zoning", "land-use")).toBe(true);
    expect(hasSatongLayerControl(state, "zoning", "district-unit")).toBe(false);
  });

  it("선택 필지와 boundary 보강 필드를 같은 PNU 기준으로 병합한다", () => {
    const merged = mergeSatongMapFeatures([
      {
        id: "p1",
        pnu: "1111010100100010000",
        address: "서울특별시 종로구 청진동 1",
        source: "search",
      },
      {
        id: "p1-boundary",
        pnu: "1111010100100010000",
        address: "서울특별시 종로구 청진동 1",
        areaSqm: 120,
        zoneType: "일반상업지역",
        officialPricePerSqm: 10_000_000,
        geometry: { type: "Polygon", coordinates: [] },
        source: "boundary",
      },
    ]);

    expect(merged).toHaveLength(1);
    expect(merged[0]).toMatchObject({
      pnu: "1111010100100010000",
      areaSqm: 120,
      zoneType: "일반상업지역",
      officialPricePerSqm: 10_000_000,
      source: "boundary",
    });
    expect(satongMapFeatureKey(merged[0])).toBe("1111010100100010000");
  });

  it("용도지역명에 따라 지도 색상을 결정한다", () => {
    expect(zoneColor("제2종일반주거지역", 0)).toBe("#14b8a6");
    expect(zoneColor("일반상업지역", 0)).toBe("#ec4899");
    expect(zoneColor("자연녹지지역", 0)).toBe("#65a30d");
  });
});
