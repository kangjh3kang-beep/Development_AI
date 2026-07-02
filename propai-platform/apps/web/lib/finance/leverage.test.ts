import { describe, expect, it } from "vitest";

import {
  DEFAULT_EQUITY_RATIO_PCT,
  deriveLeverage,
  resolveEquityWon,
} from "./leverage";

describe("resolveEquityWon", () => {
  it("명시 입력(절대액) 우선", () => {
    expect(
      resolveEquityWon({ equityWon: 3_000_000_000, totalCostWon: 10_000_000_000, equityRatioPct: 10 }),
    ).toBe(3_000_000_000);
  });

  it("자기자본 0(전액 차입)도 유효 입력으로 인정", () => {
    expect(
      resolveEquityWon({ equityWon: 0, totalCostWon: 10_000_000_000, equityRatioPct: 30 }),
    ).toBe(0);
  });

  it("절대액 없으면 비율×총사업비 자동산출(기본 10%)", () => {
    expect(
      resolveEquityWon({ equityWon: null, totalCostWon: 10_000_000_000, equityRatioPct: DEFAULT_EQUITY_RATIO_PCT }),
    ).toBe(1_000_000_000);
  });

  it("총사업비 없으면(0/결측) 자동산출 불가 → null(무날조)", () => {
    expect(resolveEquityWon({ totalCostWon: 0, equityRatioPct: 10 })).toBeNull();
    expect(resolveEquityWon({ equityRatioPct: 10 })).toBeNull();
  });

  it("비율 없으면(0/결측) 자동산출 불가 → null", () => {
    expect(resolveEquityWon({ totalCostWon: 10_000_000_000, equityRatioPct: 0 })).toBeNull();
    expect(resolveEquityWon({ totalCostWon: 10_000_000_000 })).toBeNull();
  });
});

describe("deriveLeverage", () => {
  it("총사업비만 있어도 기본 10%로 자기자본·타인자본·LTV 자동산출(0원 표시 금지)", () => {
    const r = deriveLeverage({
      netProfitWon: 2_000_000_000,
      totalCostWon: 10_000_000_000,
      equityRatioPct: DEFAULT_EQUITY_RATIO_PCT,
    });
    expect(r.equityWon).toBe(1_000_000_000);
    expect(r.debtWon).toBe(9_000_000_000);
    expect(r.ltvPct).toBe(90);
    expect(r.roePct).toBe(200); // 20억/10억 ×100
    expect(r.effectiveEquityRatioPct).toBe(10);
  });

  it("자기자본 명시 입력 시 비율 무시하고 입력값으로 파생", () => {
    const r = deriveLeverage({
      netProfitWon: 1_500_000_000,
      totalCostWon: 10_000_000_000,
      equityWon: 3_000_000_000,
      equityRatioPct: 10,
    });
    expect(r.equityWon).toBe(3_000_000_000);
    expect(r.debtWon).toBe(7_000_000_000);
    expect(r.ltvPct).toBe(70);
    expect(r.roePct).toBe(50); // 15억/30억 ×100
    expect(r.effectiveEquityRatioPct).toBe(30);
  });

  it("자기자본/총사업비 결측 → equity=null·LTV=null·ROE=null(정직 미산출)", () => {
    const r = deriveLeverage({ netProfitWon: 1_000_000_000 });
    expect(r.equityWon).toBeNull();
    expect(r.debtWon).toBeNull();
    expect(r.ltvPct).toBeNull();
    expect(r.roePct).toBeNull();
    expect(r.effectiveEquityRatioPct).toBeNull();
  });

  it("자기자본 0(전액 차입) → LTV 100%·ROE null(분모 0)", () => {
    const r = deriveLeverage({
      netProfitWon: 1_000_000_000,
      totalCostWon: 10_000_000_000,
      equityWon: 0,
    });
    expect(r.equityWon).toBe(0);
    expect(r.debtWon).toBe(10_000_000_000);
    expect(r.ltvPct).toBe(100);
    expect(r.roePct).toBeNull();
  });
});
