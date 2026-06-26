import { describe, expect, it } from "vitest";

import { regionFromAddress } from "./region";

describe("regionFromAddress", () => {
  it("서울 자치구는 구를 반환", () => {
    expect(regionFromAddress("서울특별시 강남구 역삼동 123-4")).toBe("강남구");
  });

  it("경기 시는 시를 반환(특별/광역시 토큰은 무시)", () => {
    expect(regionFromAddress("경기도 화성시 동탄대로 123")).toBe("화성시");
  });

  it("광역시 산하 구를 반환(광역시 자체 아님)", () => {
    expect(regionFromAddress("대구광역시 수성구 범어동")).toBe("수성구");
  });

  it("군을 반환", () => {
    expect(regionFromAddress("강원특별자치도 양양군 강현면")).toBe("양양군");
  });

  it("빈값/미매칭은 undefined(임의 추정 금지)", () => {
    expect(regionFromAddress("")).toBeUndefined();
    expect(regionFromAddress(null)).toBeUndefined();
    expect(regionFromAddress(undefined)).toBeUndefined();
    expect(regionFromAddress("주소미상")).toBeUndefined();
  });
});
