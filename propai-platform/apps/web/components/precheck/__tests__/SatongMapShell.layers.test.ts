/**
 * [map-layer-age-label-mismatch] 회귀 테스트.
 *
 * 정직 라벨 원칙: 노후도(age) 레이어는 백엔드 auto_zoning 이
 * building_registry.get_title_by_pnu() 로부터 built_year/building_age_years 를
 * 반환하고, SatongMultiMap 이 buildingAgeYears 기반 색상 폴리곤을 실제로
 * 렌더링한다(mapEffect 연동 완료). 따라서 레이어 source 라벨이
 * '연동 필요'(미연동)로 표기되면 실제 연동 상태와 모순되는 오기표다.
 */
import { describe, expect, it } from "vitest";

import { SATONG_MAP_SHELL_LAYERS } from "../SatongMapShell";

describe("SatongMapShell 레이어 정직 라벨 — 노후도(age)", () => {
  const ageLayer = SATONG_MAP_SHELL_LAYERS.find((layer) => layer.id === "age");

  it("age 레이어가 레지스트리에 존재한다", () => {
    expect(ageLayer).toBeDefined();
  });

  it("age 레이어는 지도에 실제 렌더링되는(mapEffect) 건축연도 컨트롤을 가진다", () => {
    const buildingAge = ageLayer?.controls.find(
      (control) => control.id === "building-age",
    );
    expect(buildingAge).toBeDefined();
    expect(buildingAge?.mapEffect).toBe(true);
  });

  it("연동 완료된 age 레이어의 source 는 '연동 필요'로 오기표되지 않는다", () => {
    // 실데이터(건축물대장 building_age_years)가 이미 지도에 렌더링되므로
    // '연동 필요' 문구는 무날조 원칙 위반(연동됐는데 미연동 표기).
    expect(ageLayer?.source).not.toContain("연동 필요");
  });

  it("age 레이어 source 는 실제 연동 원천(건축물대장)을 기술한다", () => {
    expect(ageLayer?.source).toContain("건축물대장");
  });
});
