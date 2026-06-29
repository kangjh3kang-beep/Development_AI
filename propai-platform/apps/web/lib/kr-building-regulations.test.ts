import { describe, expect, it } from "vitest";
import {
  bcrLimitForZone,
  farLimitForZone,
  getZoningList,
  getZoningSpec,
  zoningToCode,
} from "@/lib/kr-building-regulations";

describe("kr-building-regulations zoning coverage", () => {
  it("자연녹지지역을 설계엔진 폴백 없이 한글 키로 전달한다", () => {
    expect(zoningToCode("자연녹지지역")).toBe("자연녹지지역");
    expect(zoningToCode("자연녹지")).toBe("자연녹지지역");
  });

  it("기존 축약코드 대상은 하위호환 코드로 유지한다", () => {
    expect(zoningToCode("제2종일반주거지역")).toBe("2R");
    expect(zoningToCode("일반상업지역")).toBe("GC");
    expect(zoningToCode("준공업지역")).toBe("QI");
  });

  it("표준 21개 용도지역 한도를 조회한다", () => {
    expect(getZoningList()).toHaveLength(21);
    expect(getZoningSpec("자연녹지지역")).toMatchObject({
      buildingCoverageMax: 20,
      floorAreaRatioMax: 100,
    });
    expect(bcrLimitForZone("중심상업지역")).toBe(90);
    expect(farLimitForZone("계획관리")).toBe(100);
    expect(farLimitForZone("자연환경보전지역")).toBe(80);
  });
});
