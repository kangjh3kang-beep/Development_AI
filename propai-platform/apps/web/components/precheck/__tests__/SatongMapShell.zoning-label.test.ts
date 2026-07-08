/**
 * [map-layer-zoning-label-mismatch] 회귀 테스트.
 *
 * 정직 라벨 원칙: 용도지역(zoning) 레이어는 백엔드 auto_zoning 의
 * parcel_at_point 가 vworld.get_land_characteristics() 로부터
 * zone_type / zone_type_2 를 반환하고(routers/auto_zoning.py L744-745),
 * SatongMultiMap 이 land-use 컨트롤 기준 용도지역 폴리곤을 실제로
 * 렌더링한다(showZoning, mapEffect 연동 완료). 따라서 status='active'(실데이터
 * 렌더 중 — official-price·age 와 동일 등급, #187)이면서 source 가 '연동 필요'
 * (미연동)로 표기되면 실제 연동 상태와 모순되는 오기표다(무날조 원칙 위반).
 */
import { describe, expect, it } from "vitest";

import { SATONG_MAP_SHELL_LAYERS } from "../SatongMapShell";

describe("SatongMapShell 레이어 정직 라벨 — 용도지역(zoning)", () => {
  const zoningLayer = SATONG_MAP_SHELL_LAYERS.find(
    (layer) => layer.id === "zoning",
  );

  it("zoning 레이어가 레지스트리에 존재하고 status='active' 다", () => {
    expect(zoningLayer).toBeDefined();
    expect(zoningLayer?.status).toBe("active");
  });

  it("zoning 레이어는 지도에 실제 렌더링되는(mapEffect) 용도지역 컨트롤을 가진다", () => {
    const landUse = zoningLayer?.controls.find(
      (control) => control.id === "land-use",
    );
    expect(landUse).toBeDefined();
    expect(landUse?.mapEffect).toBe(true);
  });

  it("연동 완료된 zoning 레이어의 source 는 '연동 필요'로 오기표되지 않는다", () => {
    // 실데이터(토지특성 zone_type)가 이미 지도에 렌더링되므로
    // '연동 필요' 문구는 실제 연동 상태와 모순이다.
    expect(zoningLayer?.source).not.toContain("연동 필요");
  });

  it("zoning 레이어 source 는 실제 연동 원천(공간정보/토지특성 API)을 기술한다", () => {
    expect(zoningLayer?.source).toContain("토지특성");
    expect(zoningLayer?.source).toContain("연동");
  });
});
