import { describe, expect, it } from "vitest";

import { buildSeniorInputs } from "./build-inputs";

describe("buildSeniorInputs", () => {
  it("심의: 설계 bcr/far + 실효한도 → CSP inputs(actual/limit)", () => {
    const r = buildSeniorInputs("senior_deliberation_member", {
      designData: { bcr: 55, far: 240 },
      siteAnalysis: { effectiveBcrPct: 60, effectiveFarPct: 250, nationalBcrPct: 70, nationalFarPct: 300 },
    });
    expect(r).toEqual({ bcr_actual: 55, bcr_limit: 60, far_actual: 240, far_limit: 250 });
  });

  it("심의: 설계 높이 + 법정 높이한도 → height_actual/height_limit 추가", () => {
    const r = buildSeniorInputs("senior_deliberation_member", {
      designData: { heightM: 38, maxHeightM: 35 },
    });
    expect(r).toEqual({ height_actual: 38, height_limit: 35 });
  });

  it("심의: 높이한도 0/null(무제한·미산정) → height 생략(무목업)", () => {
    expect(
      buildSeniorInputs("senior_deliberation_member", { designData: { heightM: 38, maxHeightM: 0 } }),
    ).toBeUndefined();
    expect(
      buildSeniorInputs("senior_deliberation_member", { designData: { heightM: 38, maxHeightM: null } }),
    ).toBeUndefined();
  });

  it("심의: 실효한도 없으면 법정상한으로 폴백", () => {
    const r = buildSeniorInputs("senior_deliberation_member", {
      designData: { far: 240 },
      siteAnalysis: { effectiveFarPct: null, nationalFarPct: 300 },
    });
    expect(r).toEqual({ far_actual: 240, far_limit: 300 });
  });

  it("심의: 한도 0·음수(미확보)면 해당 조항 생략(무목업)", () => {
    const r = buildSeniorInputs("senior_deliberation_member", {
      designData: { bcr: 55, far: 240 },
      siteAnalysis: { effectiveBcrPct: 0, effectiveFarPct: 250, nationalBcrPct: null, nationalFarPct: null },
    });
    expect(r).toEqual({ far_actual: 240, far_limit: 250 }); // bcr 생략(한도 0)
  });

  it("심의: 설계값 전무 → undefined(프레임워크만)", () => {
    expect(
      buildSeniorInputs("senior_deliberation_member", {
        designData: { bcr: null, far: null },
        siteAnalysis: { effectiveBcrPct: 60, effectiveFarPct: 250 },
      }),
    ).toBeUndefined();
  });

  it("금융: 자기자본/총사업비 → equity/total_cost", () => {
    const r = buildSeniorInputs("senior_financial_advisor", {
      feasibilityData: { equityWon: 1_000_000_000, totalCostWon: 10_000_000_000 },
    });
    expect(r).toEqual({ equity: 1_000_000_000, total_cost: 10_000_000_000 });
  });

  it("금융: 총사업비 0/결측 → undefined(분모 무효)", () => {
    expect(
      buildSeniorInputs("senior_financial_advisor", {
        feasibilityData: { equityWon: 1_000_000_000, totalCostWon: 0 },
      }),
    ).toBeUndefined();
    expect(buildSeniorInputs("senior_financial_advisor", {})).toBeUndefined();
  });

  it("자기자본 0(전액 차입)도 유효 actual(0 허용)", () => {
    const r = buildSeniorInputs("senior_financial_advisor", {
      feasibilityData: { equityWon: 0, totalCostWon: 10_000_000_000 },
    });
    expect(r).toEqual({ equity: 0, total_cost: 10_000_000_000 });
  });

  it("미매핑 도메인(설계·세무·회계·BIM·도시계획) → undefined", () => {
    for (const k of [
      "senior_architect", "senior_tax_advisor", "senior_accountant",
      "senior_bim_specialist", "senior_urban_planner",
    ]) {
      expect(buildSeniorInputs(k, { designData: { bcr: 50, far: 200 } })).toBeUndefined();
    }
  });
});
