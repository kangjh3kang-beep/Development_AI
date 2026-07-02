import { describe, it, expect } from "vitest";
import {
  mapZoningRich,
  normalizeUpzoningScenarios,
  guardMultiParcelRich,
  nationalFarLimitForZone,
  capFarToLegal,
} from "@/lib/zoning-ssot";

describe("nationalFarLimitForZone — 용도지역 법정상한(%) 공용 맵(백엔드 정합)", () => {
  it("정확 매칭(자연녹지=100·제2종일반주거=250·일반상업=1300)", () => {
    expect(nationalFarLimitForZone("자연녹지지역")).toBe(100);
    expect(nationalFarLimitForZone("제2종일반주거지역")).toBe(250);
    expect(nationalFarLimitForZone("일반상업지역")).toBe(1300);
  });

  it("부분 포함 매칭(층수·부기 접미 있어도 매칭)", () => {
    expect(nationalFarLimitForZone("제2종일반주거지역(7층이하)")).toBe(250);
  });

  it("미상 용도지역·빈값은 null(0/임의값 금지)", () => {
    expect(nationalFarLimitForZone("알수없는지역")).toBeNull();
    expect(nationalFarLimitForZone(null)).toBeNull();
    expect(nationalFarLimitForZone(undefined)).toBeNull();
    expect(nationalFarLimitForZone("")).toBeNull();
  });
});

describe("capFarToLegal — 법정상한 캡(백엔드 min(base+incentive, cap_far) 정합)", () => {
  it("상한 초과면 캡 + isCapped=true(자연녹지 150→100)", () => {
    expect(capFarToLegal(150, 100)).toEqual({ value: 100, isCapped: true });
  });

  it("상한 이하면 원값 유지 + isCapped=false", () => {
    expect(capFarToLegal(90, 100)).toEqual({ value: 90, isCapped: false });
    expect(capFarToLegal(100, 100)).toEqual({ value: 100, isCapped: false });
  });

  it("상한 미상(null/undefined)이면 캡 미적용(없는 상한 지어내지 않음)", () => {
    expect(capFarToLegal(999, null)).toEqual({ value: 999, isCapped: false });
    expect(capFarToLegal(999, undefined)).toEqual({ value: 999, isCapped: false });
  });
});

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

describe("guardMultiParcelRich — 다필지 SSOT 오염 차단(혼재 대표필지)", () => {
  it("혼재 다필지: 대표 1필지(자연녹지 100%/20%) 유래 실효/법정 한도를 제거해 통합값(192.4%)이 살아남게 한다", () => {
    // 대표가 자연녹지인 /zoning/analyze 응답 → mapZoningRich 결과(대표필지 100%/20%).
    const rich = mapZoningRich({
      effective_far: {
        national_far_pct: 100, national_bcr_pct: 20,
        effective_far_pct: 100, effective_bcr_pct: 20,
        far_basis: "자연녹지지역 법정상한",
      },
    });
    expect(rich.effectiveFarPct).toBe(100); // 가드 전: 대표필지 자연녹지급
    const guarded = guardMultiParcelRich(rich, true);
    // 다필지에서는 단일유래 실효/법정 한도를 제거 → 통합 경로(192.4%)가 store에 살아남는다.
    expect("effectiveFarPct" in guarded).toBe(false);
    expect("effectiveBcrPct" in guarded).toBe(false);
    expect("nationalFarPct" in guarded).toBe(false);
    expect("nationalBcrPct" in guarded).toBe(false);
    expect("farBasis" in guarded).toBe(false);
  });

  it("단일필지(isMultiParcel=false): 패치를 그대로 둔다(무회귀)", () => {
    const rich = mapZoningRich({
      effective_far: { effective_far_pct: 250, effective_bcr_pct: 60 },
    });
    const guarded = guardMultiParcelRich(rich, false);
    expect(guarded.effectiveFarPct).toBe(250);
    expect(guarded.effectiveBcrPct).toBe(60);
    expect(guarded).toBe(rich); // 단일필지는 동일 참조 반환(부작용 없음)
  });

  it("순수 함수: 입력 패치를 변형하지 않는다", () => {
    const rich = mapZoningRich({ effective_far: { effective_far_pct: 100 } });
    guardMultiParcelRich(rich, true);
    expect(rich.effectiveFarPct).toBe(100); // 원본 보존
  });
});
