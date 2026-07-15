import { describe, expect, it } from "vitest";

import {
  geometryRepresentativePoint,
  hasSatongLayer,
  hasSatongLayerControl,
  mergeSatongMapFeatures,
  resolveSelectionAnchor,
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

  it("GeoJSON 경계의 대표점(경계상자 중심)을 [lat, lon]으로 파생한다", () => {
    // GeoJSON 좌표는 [lng, lat] 순 — 반환은 {lat, lon}으로 뒤집혀야 한다.
    const polygon = {
      type: "Polygon",
      coordinates: [[[127.0, 37.0], [127.2, 37.0], [127.2, 37.4], [127.0, 37.4], [127.0, 37.0]]],
    };
    expect(geometryRepresentativePoint(polygon)).toEqual({ lat: 37.2, lon: 127.1 });

    const multi = {
      type: "MultiPolygon",
      coordinates: [[[[126.0, 36.0], [126.4, 36.0], [126.4, 36.2], [126.0, 36.2], [126.0, 36.0]]]],
    };
    const pt = geometryRepresentativePoint(multi);
    expect(pt?.lat).toBeCloseTo(36.1);
    expect(pt?.lon).toBeCloseTo(126.2);

    // 비정상 입력은 null(무날조) — 가짜 좌표를 만들지 않는다.
    expect(geometryRepresentativePoint(null)).toBeNull();
    expect(geometryRepresentativePoint({ type: "Point", coordinates: [127, 37] })).toBeNull();
    expect(geometryRepresentativePoint({ type: "Polygon", coordinates: [[["a", "b"]]] })).toBeNull();
  });

  it("좌표 앵커를 ①좌표 필지 ②경계 대표점 ③(무선택시) 지도중심 순으로 해석한다", () => {
    const mapCenter = { lat: 37.5665, lon: 126.978 };
    const geom = {
      type: "Polygon",
      coordinates: [[[127.0, 37.0], [127.2, 37.0], [127.2, 37.4], [127.0, 37.4], [127.0, 37.0]]],
    };

    // ① 좌표 보유 필지가 최우선 — 첫 필지가 좌표 없어도 뒤 필지의 좌표를 쓴다(첫필지 단선 해소).
    //    ★주소·PNU는 좌표와 같은 앵커 필지의 것 — 첫 필지 주소와 조합되던 불일치 차단.
    expect(
      resolveSelectionAnchor(
        [
          { lat: null, lon: null, address: "서울 종로구 청진동 1", pnu: "p-first" },
          { lat: 37.7446, lon: 127.0469, address: "경기 의정부시 의정부동 224", pnu: "p-anchor" },
        ],
        mapCenter,
      ),
    ).toEqual({
      lat: 37.7446,
      lon: 127.0469,
      source: "parcel",
      address: "경기 의정부시 의정부동 224",
      pnu: "p-anchor",
    });

    // ② 좌표는 없지만 경계가 있으면 대표점 — 엑셀 PNU행이 경계보강 후 자동으로 살아나는 경로.
    expect(
      resolveSelectionAnchor(
        [{ lat: null, lon: null, geometry: geom, address: "경계필지", pnu: "p-geo" }],
        mapCenter,
      ),
    ).toEqual({ lat: 37.2, lon: 127.1, source: "boundary", address: "경계필지", pnu: "p-geo" });

    // ③ 선택이 아예 없을 때만 지도중심 폴백(브라우즈 모드) — 필지가 없으므로 주소도 null.
    expect(resolveSelectionAnchor([], mapCenter)).toEqual({
      lat: 37.5665,
      lon: 126.978,
      source: "map-center",
      address: null,
      pnu: null,
    });

    // 선택이 있는데 좌표·경계가 전무하면 null — 엉뚱한 지도중심 조회 역전 차단(기존 계약).
    expect(
      resolveSelectionAnchor([{ lat: null, lon: null, address: "무좌표", pnu: null }], mapCenter),
    ).toBeNull();
    // 무선택 + 지도중심도 없으면 null(정직).
    expect(resolveSelectionAnchor([], null)).toBeNull();
  });
});
