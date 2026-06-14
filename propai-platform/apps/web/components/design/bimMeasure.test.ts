import { describe, expect, it } from "vitest";
import { distance3D, formatLength, midpoint3D } from "./bimMeasure";

describe("distance3D — 3D 유클리드 거리(결정론)", () => {
  it("3-4-5 직각삼각형", () => {
    expect(distance3D({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 })).toBe(5);
  });
  it("1-2-2 → 3", () => {
    expect(distance3D({ x: 0, y: 0, z: 0 }, { x: 1, y: 2, z: 2 })).toBe(3);
  });
  it("같은 점 → 0", () => {
    expect(distance3D({ x: 5, y: 5, z: 5 }, { x: 5, y: 5, z: 5 })).toBe(0);
  });
});

describe("midpoint3D — 중점(라벨 배치용)", () => {
  it("두 점의 평균", () => {
    expect(midpoint3D({ x: 0, y: 0, z: 0 }, { x: 4, y: 6, z: 8 })).toEqual({ x: 2, y: 3, z: 4 });
  });
});

describe("formatLength — m/mm 표기(정직)", () => {
  it("1m 이상 → 소수 2자리 m", () => {
    expect(formatLength(12.345)).toBe("12.35 m");
    expect(formatLength(1)).toBe("1.00 m");
  });
  it("1m 미만 → mm(정수)", () => {
    expect(formatLength(0.5)).toBe("500 mm");
    expect(formatLength(0.123)).toBe("123 mm");
  });
  it("유효하지 않은 값 → — (가짜 수치 금지)", () => {
    expect(formatLength(NaN)).toBe("—");
    expect(formatLength(-1)).toBe("—");
    expect(formatLength(Infinity)).toBe("—");
  });
});
