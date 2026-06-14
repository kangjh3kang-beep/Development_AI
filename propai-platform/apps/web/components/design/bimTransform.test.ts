import { describe, it, expect } from "vitest";
import {
  cycleTransformMode,
  radToDeg,
  formatAngleDeg,
  formatPositionM,
  transformReadout,
  type TransformMode,
  type Vec3,
} from "./bimTransform";

describe("cycleTransformMode", () => {
  it("translate ↔ rotate 를 순환한다", () => {
    expect(cycleTransformMode("translate")).toBe("rotate");
    expect(cycleTransformMode("rotate")).toBe("translate");
  });

  it("두 번 순환하면 원래 모드", () => {
    const m: TransformMode = "translate";
    expect(cycleTransformMode(cycleTransformMode(m))).toBe(m);
  });
});

describe("radToDeg", () => {
  it("π → 180°", () => {
    expect(radToDeg(Math.PI)).toBeCloseTo(180, 6);
  });
  it("0 → 0°", () => {
    expect(radToDeg(0)).toBe(0);
  });
});

describe("formatAngleDeg", () => {
  it("π/4 → 45°", () => {
    expect(formatAngleDeg(Math.PI / 4)).toBe("45°");
  });
  it("음수 라디안도 정수 도(°)로 반올림", () => {
    expect(formatAngleDeg(-Math.PI / 2)).toBe("-90°");
  });
  it("무효값은 '—'(가짜 금지)", () => {
    expect(formatAngleDeg(Number.NaN)).toBe("—");
    expect(formatAngleDeg(Infinity)).toBe("—");
  });
});

describe("formatPositionM", () => {
  it("(x, z) 평면 좌표를 소수1자리 m로 표기 — 이동은 x·z만 의미", () => {
    const v: Vec3 = { x: 1.23, y: 0.0, z: -3.48 };
    expect(formatPositionM(v)).toBe("X 1.2 · Z -3.5 m");
  });
  it("무효 좌표는 '—'", () => {
    expect(formatPositionM({ x: Number.NaN, y: 0, z: 0 })).toBe("—");
  });
});

describe("transformReadout", () => {
  it("이동(위치) + 회전Y를 한 줄로 — 비전문가 표기", () => {
    const v: Vec3 = { x: 2, y: 0, z: 4 };
    expect(transformReadout(v, Math.PI / 2)).toBe("X 2.0 · Z 4.0 m · 회전 90°");
  });
  it("회전이 무효면 위치만 표기", () => {
    const v: Vec3 = { x: 0, y: 0, z: 0 };
    expect(transformReadout(v, Number.NaN)).toBe("X 0.0 · Z 0.0 m");
  });
});
