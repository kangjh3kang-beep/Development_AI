// roughResultToFeasibilityPatch 단위테스트 — 개략수지 결과 → 모세혈관(feasibilityData) 매핑.
// 순수 함수라 store/apiClient mock 불필요(백엔드 응답 형태를 직접 시드).

import { describe, it, expect } from "vitest";

import { roughResultToFeasibilityPatch, type RoughScenarioLike } from "./rough-scenario-commit";

/** 정상 응답(모든 축 확보) — 매핑 대상 8필드가 전부 채워지는 기준 시나리오. */
function fullResult(over: Partial<RoughScenarioLike> = {}): RoughScenarioLike {
  return {
    project_id: "p1",
    summary: {
      total_cost_won: 50_000_000_000,
      total_revenue_won: 60_000_000_000,
      net_profit_won: 10_000_000_000,
      roi_pct: 20,
      npv_won: 5_000_000_000,
      grade: "B",
    },
    revenue: {
      sale_price_per_pyeong: 30_000_000,
    },
    inputs: {
      gfa_sqm: 22_059,
    },
    cashflow: {
      summary: {
        profit_rate_pct: 16.7,
      },
    },
    ...over,
  };
}

describe("roughResultToFeasibilityPatch", () => {
  it("정상 결과 → 8필드 매핑(단위 무변환 확인 포함)", () => {
    const patch = roughResultToFeasibilityPatch(fullResult());
    expect(patch).not.toBeNull();
    expect(patch!.totalCostWon).toBe(50_000_000_000);
    expect(patch!.totalRevenueWon).toBe(60_000_000_000);
    expect(patch!.roiPct).toBe(20);
    expect(patch!.npvWon).toBe(5_000_000_000);
    expect(patch!.grade).toBe("B");
    expect(patch!.profitRatePct).toBe(16.7);
    // 원/평 단위 무변환(백엔드 값 그대로 전달).
    expect(patch!.salePricePerPyeongWon).toBe(30_000_000);
    expect(patch!.totalGfaSqm).toBe(22_059);
  });

  it("null/undefined 결과 → null 반환", () => {
    expect(roughResultToFeasibilityPatch(null)).toBeNull();
    expect(roughResultToFeasibilityPatch(undefined)).toBeNull();
  });

  it("summary 전부 null(다른 축도 없음) → null 반환", () => {
    const result: RoughScenarioLike = {
      project_id: "p1",
      summary: {
        total_cost_won: null,
        total_revenue_won: null,
        net_profit_won: null,
        roi_pct: null,
        npv_won: null,
        grade: null,
      },
    };
    expect(roughResultToFeasibilityPatch(result)).toBeNull();
  });

  it("equity 키(equityWon/equityIsManual/equityRatioPct)가 patch에 절대 없음", () => {
    const patch = roughResultToFeasibilityPatch(fullResult());
    expect(patch).not.toBeNull();
    expect("equityWon" in patch!).toBe(false);
    expect("equityIsManual" in patch!).toBe(false);
    expect("equityRatioPct" in patch!).toBe(false);
  });

  it("profitRatePct: cashflow.summary.profit_rate_pct 우선 채택", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: { summary: { profit_rate_pct: 16.7 } },
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: 999_999_999, // cashflow 값이 있으면 이 값은 무시돼야 함.
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch!.profitRatePct).toBe(16.7);
  });

  it("profitRatePct: cashflow 없으면 net_profit_won/total_revenue_won×100 산술파생", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: 10_000_000_000,
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch!.profitRatePct).toBeCloseTo((10_000_000_000 / 60_000_000_000) * 100, 6);
  });

  it("profitRatePct: cashflow도 없고 net_profit_won/total_revenue_won도 없으면 키 생략", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: null,
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch).not.toBeNull();
    expect("profitRatePct" in patch!).toBe(false);
  });

  it("grade 빈 문자열/공백 → 생략", () => {
    for (const bad of ["", "  "]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({
          summary: {
            total_cost_won: 50_000_000_000,
            total_revenue_won: 60_000_000_000,
            net_profit_won: 10_000_000_000,
            roi_pct: 20,
            npv_won: 5_000_000_000,
            grade: bad,
          },
        }),
      );
      expect(patch).not.toBeNull();
      expect("grade" in patch!).toBe(false);
    }
  });

  it("salePricePerPyeongWon: 0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({ revenue: { sale_price_per_pyeong: bad } }),
      );
      expect(patch).not.toBeNull();
      expect("salePricePerPyeongWon" in patch!).toBe(false);
    }
  });

  it("totalGfaSqm: 0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(fullResult({ inputs: { gfa_sqm: bad } }));
      expect(patch).not.toBeNull();
      expect("totalGfaSqm" in patch!).toBe(false);
    }
  });

  it("totalHouseholds(H1): 양수 정수(inputs.total_households)만 매핑", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({ inputs: { gfa_sqm: 22_059, total_households: 200 } }),
    );
    expect(patch).not.toBeNull();
    expect(patch!.totalHouseholds).toBe(200);
  });

  it("totalHouseholds(H1): 미확보/0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [undefined, null, 0, -5]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({ inputs: { gfa_sqm: 22_059, total_households: bad } }),
      );
      expect(patch).not.toBeNull();
      expect("totalHouseholds" in patch!).toBe(false);
    }
  });

  it("totalCostWon/totalRevenueWon(L1): 0/음수는 미주입(degraded 0이 STEP2 게이트를 열지 않음)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({
          summary: {
            total_cost_won: bad,
            total_revenue_won: bad,
            net_profit_won: 10_000_000_000,
            roi_pct: 20,
            npv_won: 5_000_000_000,
            grade: "B",
          },
        }),
      );
      expect(patch).not.toBeNull();
      expect("totalCostWon" in patch!).toBe(false);
      expect("totalRevenueWon" in patch!).toBe(false);
    }
  });

  it("profitRatePct(L1): 손실 프로젝트(음수 net_profit_won)는 음수 profitRatePct로 정상 커밋된다", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 40_000_000_000,
          net_profit_won: -10_000_000_000, // 손실.
          roi_pct: -20,
          npv_won: -3_000_000_000,
          grade: "D",
        },
      }),
    );
    expect(patch).not.toBeNull();
    expect(patch!.profitRatePct).toBeCloseTo((-10_000_000_000 / 40_000_000_000) * 100, 6);
    expect(patch!.profitRatePct as number).toBeLessThan(0);
  });
});
