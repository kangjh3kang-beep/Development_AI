import { describe, it, expect } from "vitest";
import { mapZoningRich, normalizeUpzoningScenarios } from "@/lib/zoning-ssot";

describe("normalizeUpzoningScenarios", () => {
  it("배열이 아니면 null", () => {
    expect(normalizeUpzoningScenarios(null)).toBeNull();
    expect(normalizeUpzoningScenarios(undefined)).toBeNull();
    expect(normalizeUpzoningScenarios("nope")).toBeNull();
    expect(normalizeUpzoningScenarios({})).toBeNull();
  });

  it("백엔드 per-scenario(rich)를 UpzoningScenarioData[]로 정규화", () => {
    const out = normalizeUpzoningScenarios([
      {
        path: "준주거 → 일반상업",
        target_zone: "일반상업지역",
        expected_far_pct_low: 400,
        expected_far_pct_high: 600,
        feasibility: "중",
        feasibility_reason: "역세권 입지",
        legal_basis: "국토계획법 시행령 제30조",
      },
    ]);
    expect(out).toEqual([
      {
        path: "준주거 → 일반상업",
        targetZone: "일반상업지역",
        feasibility: "중",
        expectedFarLowPct: 400,
        expectedFarHighPct: 600,
        legalBasis: "국토계획법 시행령 제30조",
        rationale: "역세권 입지",
      },
    ]);
  });

  it("의미 있는 필드가 전혀 없는 항목은 제외하고, 전부 비면 null", () => {
    expect(normalizeUpzoningScenarios([{}, { foo: "bar" }])).toBeNull();
  });

  it("숫자가 아닌 용적률은 null로 거른다(가짜값 금지)", () => {
    const out = normalizeUpzoningScenarios([
      { path: "종상향", expected_far_pct_high: "600" as unknown as number },
    ]);
    expect(out).not.toBeNull();
    expect(out![0].expectedFarHighPct).toBeNull();
  });
});

describe("mapZoningRich — upzoningScenarios(stale 방지)", () => {
  it("upzoning.scenarios가 있으면 정규화해 patch에 보존", () => {
    const patch = mapZoningRich({
      upzoning: {
        scenarios: [
          {
            path: "역세권 종상향",
            target_zone: "준주거지역",
            feasibility: "상",
            expected_far_pct_high: 500,
            legal_basis: "역세권 활성화 지침",
          },
        ],
      },
    });
    expect(patch.upzoningScenarios).toHaveLength(1);
    expect(patch.upzoningScenarios![0].feasibility).toBe("상");
  });

  it("upzoning 정보가 없으면 upzoningScenarios=null로 명시(직전 부지 잔류 차단)", () => {
    const patch = mapZoningRich({ effective_far: { effective_far_pct: 200 } });
    expect(patch.upzoningScenarios).toBeNull();
  });
});
