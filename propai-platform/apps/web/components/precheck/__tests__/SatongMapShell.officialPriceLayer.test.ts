/**
 * [map-layer-official-price-label-mismatch] 회귀 테스트.
 *
 * 정직 라벨 원칙: 공시지가(official-price) 레이어는 백엔드가
 * VWorld NED getLandCharacteristics(토지특성) API 로부터
 * official_price_per_sqm 을 실반환하고
 * (apps/api/app/services/external_api/vworld_service.py get_land_characteristics),
 * SatongMultiMap 이 officialPricePerSqm 기반 가격 색상 폴리곤을 실제로
 * 렌더링한다(unit-price mapEffect 연동 완료). 따라서 레이어 source 라벨이
 * '연동 필요'(미연동)로 표기되면 실제 연동 상태와 모순되는 오기표다.
 */
import { describe, expect, it } from "vitest";

import { isRenderableSatongMapLayer } from "@/lib/satong-map-layers";

import { SATONG_MAP_SHELL_LAYERS } from "../SatongMapShell";

describe("SatongMapShell 레이어 정직 라벨 — 공시지가(official-price)", () => {
  const layer = SATONG_MAP_SHELL_LAYERS.find((l) => l.id === "official-price");

  it("official-price 레이어가 레지스트리에 존재하고 지도 렌더러와 연결되어 있다", () => {
    expect(layer).toBeDefined();
    expect(isRenderableSatongMapLayer("official-price")).toBe(true);
  });

  it("official-price 레이어는 지도에 실제 렌더링되는(mapEffect) ㎡당 단가 컨트롤을 가진다", () => {
    const unitPrice = layer?.controls.find((control) => control.id === "unit-price");
    expect(unitPrice).toBeDefined();
    expect(unitPrice?.mapEffect).toBe(true);
  });

  it("연동 완료된 official-price 레이어의 source 는 '연동 필요'로 오기표되지 않는다", () => {
    // 실데이터(VWorld NED 개별공시지가)가 이미 지도에 렌더링되므로
    // '연동 필요' 문구는 무날조 원칙 위반(연동됐는데 미연동 표기).
    expect(layer?.source).not.toContain("연동 필요");
  });

  it("official-price 레이어 source 는 실제 연동 원천(VWorld NED)을 기술한다", () => {
    expect(layer?.source).toContain("VWorld NED");
  });
});
