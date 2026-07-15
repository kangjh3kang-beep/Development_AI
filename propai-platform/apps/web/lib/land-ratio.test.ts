import { describe, it, expect } from "vitest";
import { landRatio } from "./land-ratio";

type Row = { area_sqm?: number | null; ok?: boolean };

describe("landRatio", () => {
  it("면적 가중과 건수 비율이 다르게 나온다 — 회귀 방지 핵심 사례", () => {
    // 큰 필지 1개 미동의 + 작은 필지 9개 동의.
    // 건수 90%지만 면적은 8.3% → 법정(면적) 요건 미달을 건수가 가리면 안 된다.
    const rows: Row[] = [
      { area_sqm: 10000, ok: false },
      ...Array.from({ length: 9 }, () => ({ area_sqm: 100, ok: true })),
    ];
    const r = landRatio(rows, (x) => !!x.ok);

    expect(r.countRatio).toBeCloseTo(0.9, 5);
    expect(r.areaRatio).toBeCloseTo(900 / 10900, 5); // ≈ 0.0826
    expect(r.areaRatio).toBeLessThan(r.countRatio);
    expect(r.matchedAreaSqm).toBe(900);
    expect(r.totalAreaSqm).toBe(10900);
  });

  it("전건 동의면 양축 모두 1", () => {
    const rows: Row[] = [
      { area_sqm: 500, ok: true },
      { area_sqm: 1500, ok: true },
    ];
    const r = landRatio(rows, (x) => !!x.ok);
    expect(r.areaRatio).toBe(1);
    expect(r.countRatio).toBe(1);
  });

  it("빈 배열은 0으로 떨어진다(0 나눗셈 금지)", () => {
    const r = landRatio([] as Row[], () => true);
    expect(r.areaRatio).toBe(0);
    expect(r.countRatio).toBe(0);
    expect(Number.isNaN(r.areaRatio)).toBe(false);
  });

  it("면적 미입력(null/0/음수/NaN)은 면적 축에서 제외되고 건수에는 남는다", () => {
    const rows: Row[] = [
      { area_sqm: null, ok: true },
      { area_sqm: 0, ok: true },
      { area_sqm: -50, ok: true },
      { area_sqm: Number.NaN, ok: true },
      { area_sqm: 200, ok: false },
    ];
    const r = landRatio(rows, (x) => !!x.ok);
    expect(r.totalAreaSqm).toBe(200); // 유효 면적은 200 하나뿐
    expect(r.matchedAreaSqm).toBe(0); // 동의한 4건은 전부 면적 0
    expect(r.areaRatio).toBe(0);
    expect(r.countRatio).toBeCloseTo(4 / 5, 5);
  });

  it("면적이 전무하면 areaRatio는 0 — 건수로 대체 추정하지 않는다(정직)", () => {
    const rows: Row[] = [
      { ok: true },
      { ok: true },
    ];
    const r = landRatio(rows, (x) => !!x.ok);
    expect(r.countRatio).toBe(1);
    expect(r.areaRatio).toBe(0); // 면적 근거가 없으면 면적 요건 충족을 주장하지 않는다
    expect(r.totalAreaSqm).toBe(0);
  });
});
