/**
 * [MAP-001 P0] 레이어 상태 정직 라벨 회귀 테스트.
 *
 * 무날조 원칙(양방향):
 *  1) 원천이 미연동('연동 필요')인데 status를 ready로 위장 금지.
 *  2) 실데이터가 이미 렌더링되는데 source를 '연동 필요'(미연동)로 위장 금지.
 *
 * 실연동 근거(코드):
 *  - zoning: SatongMultiMap.tsx 용도지역 폴리곤(feature.zoneType) 렌더링
 *    ← apps/api/routers/auto_zoning.py parcel-at-point zone_type(L744).
 *  - official-price: 공시지가 폴리곤(officialPricePerSqm) 렌더링
 *    ← auto_zoning.py official_price_per_sqm(L748-749).
 *  - age: 노후도 폴리곤(buildingAgeYears) 렌더링 ← built_year(L755-766).
 *  - terrain: 기본/위성/항공 타일이 VWorld WMTS 프록시(/tiles/vworld/wmts)로
 *    실제 렌더링(createOfficialBaseMapLayer).
 * 미연동 근거(코드):
 *  - transactions: SatongMapShell이 market 계열 props를 전달하지 않고
 *    컨트롤 전부 mapEffect:false → 이 화면에서 렌더 경로 없음.
 *  - poi: SatongMultiMap에 POI 렌더 경로 자체가 없음.
 */
import { describe, expect, it, vi } from "vitest";

// SatongMapShell은 모듈 스코프에서 next/dynamic을 호출하므로 메타데이터 검증용으로 무해화한다.
vi.mock("next/dynamic", () => ({
  default: () => () => null,
}));

import { SATONG_MAP_SHELL_LAYERS } from "../SatongMapShell";

describe("MAP-001 SatongMapShell 레이어 status 정직 라벨", () => {
  it("source가 '연동 필요'인 레이어는 ready/active로 위장하지 않는다", () => {
    const dishonest = SATONG_MAP_SHELL_LAYERS.filter(
      (layer) => layer.source.includes("연동 필요") && layer.status !== "needs-source",
    ).map((layer) => layer.id);
    expect(dishonest).toEqual([]);
  });

  it("이 화면에서 렌더 경로가 없는 transactions·poi는 needs-source다", () => {
    for (const id of ["transactions", "poi"]) {
      const layer = SATONG_MAP_SHELL_LAYERS.find((candidate) => candidate.id === id);
      expect(layer, id).toBeDefined();
      expect(layer?.status, id).toBe("needs-source");
    }
  });

  it("mapEffect 컨트롤이 하나도 없는 레이어는 ready/active일 수 없다", () => {
    const offenders = SATONG_MAP_SHELL_LAYERS.filter(
      (layer) =>
        !layer.controls.some((control) => control.mapEffect) &&
        layer.status !== "needs-source",
    ).map((layer) => layer.id);
    expect(offenders).toEqual([]);
  });

  it("실데이터가 렌더링되는 zoning·official-price·age·terrain은 '연동 필요'(미연동)로 위장하지 않는다", () => {
    for (const id of ["zoning", "official-price", "age", "terrain"]) {
      const layer = SATONG_MAP_SHELL_LAYERS.find((candidate) => candidate.id === id);
      expect(layer, id).toBeDefined();
      // 실제 지도 반영 컨트롤(mapEffect)이 존재한다 = 렌더 경로가 배선돼 있다.
      expect(layer?.controls.some((control) => control.mapEffect), id).toBe(true);
      // 렌더링되는 레이어를 미연동('연동 필요')으로 표기하면 반대 방향 위장이다.
      expect(layer?.source, id).not.toContain("연동 필요");
    }
  });
});
