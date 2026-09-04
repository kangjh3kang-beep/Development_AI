import { describe, expect, it } from "vitest";

import { buildSelectionGeoJson, buildSelectionKml, kakaoRoadviewUrl } from "./satong-export";

const GEOM = { type: "Polygon", coordinates: [[[127.08, 37.3], [127.09, 37.3], [127.09, 37.31], [127.08, 37.3]]] };

describe("buildSelectionGeoJson (I5)", () => {
  it("geometry 보유 필지만 Feature로 포함하고 제외 건수를 정직 보고한다", () => {
    const out = buildSelectionGeoJson([
      { id: "a", address: "판교동 100", pnu: "PNU-A", areaSqm: 500, zoneType: "자연녹지지역", geometry: GEOM },
      { id: "b", address: "판교동 200" }, // 무기하 → 제외
    ] as never);
    expect(out.included).toBe(1);
    expect(out.skipped).toBe(1);
    const parsed = JSON.parse(out.json);
    expect(parsed.type).toBe("FeatureCollection");
    expect(parsed.features).toHaveLength(1);
    expect(parsed.features[0].properties.pnu).toBe("PNU-A");
    expect(parsed.features[0].geometry).toEqual(GEOM);
  });

  it("R1: 비-GeoJSON 임의 객체 geometry는 skipped로 계상(얕은 검증)", () => {
    const out = buildSelectionGeoJson([
      { id: "bad1", address: "a", geometry: {} },
      { id: "bad2", address: "b", geometry: { foo: 1 } },
      { id: "ok", address: "c", geometry: GEOM },
    ] as never);
    expect(out.included).toBe(1);
    expect(out.skipped).toBe(2);
  });

  it("전부 무기하면 included 0(파일 생성 게이트)", () => {
    const out = buildSelectionGeoJson([{ id: "x", address: "y" }] as never);
    expect(out.included).toBe(0);
    expect(JSON.parse(out.json).features).toHaveLength(0);
  });
});

describe("kakaoRoadviewUrl (I3 — 2026-07-17 라이브 302 검증 계약)", () => {
  it("좌표 → /link/roadview/{lat},{lng}", () => {
    expect(kakaoRoadviewUrl(37.40219, 127.10111)).toBe("https://map.kakao.com/link/roadview/37.40219,127.10111");
  });
  it("좌표 결측/비정상 → null(버튼 미표시 정직)", () => {
    expect(kakaoRoadviewUrl(null, 127.1)).toBeNull();
    expect(kakaoRoadviewUrl(37.4, undefined)).toBeNull();
    expect(kakaoRoadviewUrl(Number.NaN, 127.1)).toBeNull();
  });
});

describe("buildSelectionKml (V3)", () => {
  it("Polygon → Placemark(외곽 링·lon,lat,0) + name/desc XML 이스케이프", () => {
    const out = buildSelectionKml([
      { id: "a", address: "판교동 <100>", pnu: "PNU&A", areaSqm: 500.4, zoneType: "자연녹지지역", geometry: GEOM },
      { id: "b", address: "무기하" },
    ] as never);
    expect(out.included).toBe(1);
    expect(out.skipped).toBe(1);
    expect(out.json).toContain("<kml ");
    expect(out.json).toContain("판교동 &lt;100&gt;");
    expect(out.json).toContain("PNU&amp;A · 자연녹지지역 · 500㎡");
    expect(out.json).toContain("<coordinates>127.08,37.3,0 127.09,37.3,0");
  });

  it("R1 M3: 구멍(내부 링)은 innerBoundaryIs로 보존 — GeoJSON과 기하 동일성", () => {
    const holed = {
      type: "Polygon",
      coordinates: [
        [[127.08, 37.3], [127.09, 37.3], [127.09, 37.31], [127.08, 37.3]],
        [[127.083, 37.302], [127.085, 37.302], [127.085, 37.304], [127.083, 37.302]],
      ],
    };
    const out = buildSelectionKml([{ id: "h", address: "도넛", geometry: holed }] as never);
    expect(out.json).toContain("<innerBoundaryIs>");
    expect(out.json).toContain("127.083,37.302,0");
  });

  it("MultiPolygon → MultiGeometry, 전부 무기하면 included 0", () => {
    const multi = { type: "MultiPolygon", coordinates: [GEOM.coordinates, GEOM.coordinates] };
    const out = buildSelectionKml([{ id: "m", address: "멀티", geometry: multi }] as never);
    expect(out.included).toBe(1);
    expect(out.json).toContain("<MultiGeometry>");
    expect(buildSelectionKml([{ id: "x", address: "y" }] as never).included).toBe(0);
  });
});
