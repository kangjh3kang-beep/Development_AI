/**
 * "고른 값이 곧 적용값" 계약 — 수동 선택은 자동확대를 **끈다**.
 *
 * ★두 모집단을 함께 단언한다: "수동이면 끈다"만 잠그면 **항상 끔**도 통과하고,
 *   그러면 자동 모드(기본)가 죽어 지방 필지가 다시 1km 에 갇힌다(#736 이 고친 그 결함).
 */
import { describe, expect, it } from "vitest";

import { MARKET_RADIUS_DEFAULT_M, marketRadiusRequest } from "@/lib/market/market-radius";

describe("marketRadiusRequest", () => {
  it("★수동 선택 — 고른 값 그대로, 확대는 끈다", () => {
    expect(marketRadiusRequest(1000)).toEqual({ radius_m: 1000, auto_expand_radius: false });
    expect(marketRadiusRequest(10000)).toEqual({ radius_m: 10000, auto_expand_radius: false });
  });

  it("★대조군 — 자동(null/undefined)이면 기본 반경 + 확대 **켬**", () => {
    // 이것이 없으면 "항상 끔"도 위 테스트를 통과해 #736 의 효과가 사라진다.
    expect(marketRadiusRequest(null)).toEqual({
      radius_m: MARKET_RADIUS_DEFAULT_M, auto_expand_radius: true,
    });
    expect(marketRadiusRequest(undefined)).toEqual({
      radius_m: MARKET_RADIUS_DEFAULT_M, auto_expand_radius: true,
    });
  });

  it("0·음수는 수동으로 보지 않는다(잘못된 값으로 반경이 붕괴하지 않게)", () => {
    expect(marketRadiusRequest(0).auto_expand_radius).toBe(true);
    expect(marketRadiusRequest(0).radius_m).toBe(MARKET_RADIUS_DEFAULT_M);
    expect(marketRadiusRequest(-5).radius_m).toBe(MARKET_RADIUS_DEFAULT_M);
  });
});
