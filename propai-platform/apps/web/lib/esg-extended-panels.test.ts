// 확장 ESG 패널(RE100/LCC/EU Taxonomy/기후리스크/에너지인증) 요청 바디 조립 단위테스트.
// 목적: 백엔드 Pydantic 계약(필드명·타입)을 프론트 바디 조립 함수에 고정(계약 핀 5건).
import { describe, it, expect } from "vitest";
import { ApiClientError } from "@/lib/api-client";
import {
  buildEsgExtendedContext,
  buildRe100Body,
  buildLccBody,
  buildEuTaxonomyBody,
  buildClimateBody,
  buildEnergyCertificationBody,
  re100InitialValues,
  lccInitialValues,
  euTaxonomyInitialValues,
  climateInitialValues,
  energyCertificationInitialValues,
  extractApiErrorMessage,
  formatPercent01,
  formatPercent100,
  validatePositiveFields,
} from "./esg-extended-panels";

describe("formatPercent01 vs formatPercent100 — QA F1 회귀(에너지자립률 ×100 재곱 버그)", () => {
  it("formatPercent01: 0.0~1.0 비율 입력 시 ×100 후 표시(re100_rate 등)", () => {
    expect(formatPercent01(0.453)).toBe("45.3%");
    expect(formatPercent01(0.6)).toBe("60.0%");
  });

  it("formatPercent100: 이미 0~100 스케일 입력은 ×100 없이 그대로 표시(energy_independence_rate 등)", () => {
    // ★회귀 방지: energy_independence_rate=45.3(이미 %)을 formatPercent01에 넣으면
    // "4530.0%"가 되는 버그였다 — formatPercent100은 그대로 "45.3%"를 내야 한다.
    expect(formatPercent100(45.3)).toBe("45.3%");
    expect(formatPercent100(100)).toBe("100.0%");
  });

  it("둘 다 null/NaN은 정직하게 '-' 표시(가짜 0% 금지)", () => {
    expect(formatPercent01(null)).toBe("-");
    expect(formatPercent100(undefined)).toBe("-");
    expect(formatPercent100(Number.NaN)).toBe("-");
  });
});

describe("validatePositiveFields — QA F3(gt=0 필수 필드 클라이언트 검증)", () => {
  it("빈 문자열·0·음수·NaN은 전부 에러 처리", () => {
    const errors = validatePositiveFields(
      { totalElectricityMwh: "" },
      ["totalElectricityMwh"],
    );
    expect(errors.totalElectricityMwh).toBeTruthy();
    expect(validatePositiveFields({ x: "0" }, ["x"]).x).toBeTruthy();
    expect(validatePositiveFields({ x: "-5" }, ["x"]).x).toBeTruthy();
    expect(validatePositiveFields({ x: "abc" }, ["x"]).x).toBeTruthy();
  });

  it("양수 문자열은 에러 없음(빈 객체)", () => {
    expect(validatePositiveFields({ x: "12500" }, ["x"])).toEqual({});
  });

  it("검사 대상이 아닌 키는 무시(선택 필드 강제 금지)", () => {
    expect(validatePositiveFields({ optional: "" }, [])).toEqual({});
  });
});

describe("extractApiErrorMessage", () => {
  it("401/403은 인증 안내 메시지로 치환", () => {
    expect(extractApiErrorMessage(new ApiClientError("x", 401, null), "AUTH")).toBe("AUTH");
    expect(extractApiErrorMessage(new ApiClientError("x", 403, null), "AUTH")).toBe("AUTH");
  });

  it("그 외 상태코드는 상태코드를 노출", () => {
    expect(extractApiErrorMessage(new ApiClientError("x", 500, null), "AUTH")).toBe(
      "API request failed with status 500.",
    );
  });

  it("일반 Error는 메시지 그대로, 알 수 없는 값은 정직한 기본 문구", () => {
    expect(extractApiErrorMessage(new Error("boom"), "AUTH")).toBe("boom");
    expect(extractApiErrorMessage("weird", "AUTH")).toBe("Request failed.");
  });
});

describe("buildEsgExtendedContext", () => {
  it("공사비 우선순위: costData 존재 시 그 값을 constructionCostWon으로 사용", () => {
    const ctx = buildEsgExtendedContext({
      projectId: "p1",
      costData: { totalConstructionCostWon: 900 },
      feasibilityData: { totalCostWon: 1500 },
    });
    expect(ctx.constructionCostWon).toBe(900);
    // 자산가치는 반대 우선순위(총사업비 우선)
    expect(ctx.assetValueWon).toBe(1500);
  });

  it("폴백: costData 없으면 feasibilityData.totalCostWon으로 대체", () => {
    const ctx = buildEsgExtendedContext({
      projectId: "p1",
      feasibilityData: { totalCostWon: 2000 },
    });
    expect(ctx.constructionCostWon).toBe(2000);
    expect(ctx.assetValueWon).toBe(2000);
  });

  it("내재탄소/㎡ 파생: 둘 다 양수일 때만 계산, 하나라도 없으면 null(무날조)", () => {
    const ok = buildEsgExtendedContext({
      projectId: "p1",
      designData: { totalGfaSqm: 1000 },
      esgData: { embodiedCarbonKg: 500000 },
    });
    expect(ok.embodiedCarbonPerSqm).toBe(500);

    const missingGfa = buildEsgExtendedContext({
      projectId: "p1",
      esgData: { embodiedCarbonKg: 500000 },
    });
    expect(missingGfa.embodiedCarbonPerSqm).toBeNull();

    const zeroCarbon = buildEsgExtendedContext({
      projectId: "p1",
      designData: { totalGfaSqm: 1000 },
      esgData: { embodiedCarbonKg: 0 },
    });
    expect(zeroCarbon.embodiedCarbonPerSqm).toBeNull();
  });

  it("좌표 프리필: siteAnalysis.coordinates에서 lat/lon 추출, 없으면 null", () => {
    const withCoords = buildEsgExtendedContext({
      projectId: "p1",
      siteAnalysis: { coordinates: { lat: 37.5, lon: 127.0 } },
    });
    expect(withCoords.lat).toBe(37.5);
    expect(withCoords.lon).toBe(127.0);

    const noCoords = buildEsgExtendedContext({ projectId: "p1" });
    expect(noCoords.lat).toBeNull();
    expect(noCoords.lon).toBeNull();
  });
});

describe("buildRe100Body — Re100TrackRequest 계약 핀(routers/re100.py)", () => {
  it("필드명·타입이 백엔드 스키마와 1:1 일치", () => {
    const values = {
      trackingYear: "2026",
      totalElectricityMwh: "1200.5",
      renewableElectricityMwh: "300",
      ktsUnitPriceKrw: "18000",
    };
    const body = buildRe100Body(values, { projectId: "proj-1" });
    expect(body).toEqual({
      project_id: "proj-1",
      tracking_year: 2026,
      total_electricity_mwh: 1200.5,
      renewable_electricity_mwh: 300,
      kts_unit_price_krw: 18000,
    });
  });

  it("빈 입력은 0으로 안전 폴백(NaN 전송 방지)", () => {
    const body = buildRe100Body(re100InitialValues(), { projectId: "p" });
    expect(body.total_electricity_mwh).toBe(0);
    expect(body.renewable_electricity_mwh).toBe(0);
    expect(body.kts_unit_price_krw).toBe(18000); // 백엔드 기본값과 동일한 초기값
    expect(Number.isFinite(body.tracking_year)).toBe(true);
  });
});

describe("buildLccBody — LccCalculateRequest 계약 핀(routers/lcc.py)", () => {
  it("핵심 3필드만 조립, 선택 필드(rate 등)는 생략해 백엔드 기본값에 위임", () => {
    const values = {
      initialConstructionCost: "5000000000",
      annualMaintenanceCost: "50000000",
      annualEnergyCost: "20000000",
    };
    const body = buildLccBody(values, { projectId: "proj-2" });
    expect(body).toEqual({
      project_id: "proj-2",
      initial_construction_cost: 5000000000,
      annual_maintenance_cost: 50000000,
      annual_energy_cost: 20000000,
    });
    // nominal_rate/inflation_rate/analysis_period_years 등 옵셔널 키는 바디에 없어야 함.
    expect(Object.keys(body)).toEqual([
      "project_id",
      "initial_construction_cost",
      "annual_maintenance_cost",
      "annual_energy_cost",
    ]);
  });

  it("프리필: constructionCostWon이 있으면 초기건설비 초기값으로 사용", () => {
    const initial = lccInitialValues({ constructionCostWon: 777 });
    expect(initial.initialConstructionCost).toBe("777");
    const empty = lccInitialValues({ constructionCostWon: null });
    expect(empty.initialConstructionCost).toBe("");
  });
});

describe("buildEuTaxonomyBody — EuTaxonomyCheckRequest 계약 핀(routers/eu_taxonomy.py)", () => {
  it("9개 필드 전부 조립(project_id 없음 — 라우터 계약 확인 결과), 타입 1:1", () => {
    const values = {
      primaryEnergyDemandKwhM2: "85.5",
      renewableEnergyRatio: "0.3",
      embodiedCarbonKgco2eM2: "450",
      waterUsageLitersPerDay: "120",
      wasteRecyclingRate: "0.7",
      greenRatio: "0.25",
      hasClimateRiskAssessment: true,
      hasSocialSafeguards: false,
      grossFloorAreaSqm: "12500",
    };
    const body = buildEuTaxonomyBody(values);
    expect(body).toEqual({
      primary_energy_demand_kwh_m2: 85.5,
      renewable_energy_ratio: 0.3,
      embodied_carbon_kgco2e_m2: 450,
      water_usage_liters_per_day: 120,
      waste_recycling_rate: 0.7,
      green_ratio: 0.25,
      has_climate_risk_assessment: true,
      has_social_safeguards: false,
      gross_floor_area_sqm: 12500,
    });
    expect(body).not.toHaveProperty("project_id");
  });

  it("프리필: GFA는 designData.totalGfaSqm, 내재탄소/㎡는 파생 컨텍스트에서", () => {
    const initial = euTaxonomyInitialValues({
      totalGfaSqm: 12500,
      embodiedCarbonPerSqm: 36.4,
    });
    expect(initial.grossFloorAreaSqm).toBe("12500");
    expect(initial.embodiedCarbonKgco2eM2).toBe("36.4");
    expect(initial.hasClimateRiskAssessment).toBe(false);
    expect(initial.hasSocialSafeguards).toBe(false);
  });
});

describe("buildClimateBody — ClimateRiskAssessmentRequest 계약 핀", () => {
  it("필드명·타입 1:1, construction_period_months 기본 24 유지", () => {
    const values = {
      lat: "37.5665",
      lon: "126.9780",
      assetValueKrw: "10000000000",
      constructionPeriodMonths: "24",
    };
    const body = buildClimateBody(values, { projectId: "proj-3" });
    expect(body).toEqual({
      project_id: "proj-3",
      lat: 37.5665,
      lon: 126.978,
      asset_value_krw: 10000000000,
      construction_period_months: 24,
    });
  });

  it("프리필: 좌표·자산가치를 컨텍스트에서 채운다", () => {
    const initial = climateInitialValues({
      lat: 37.5,
      lon: 127.0,
      assetValueWon: 5000000000,
    });
    expect(initial).toEqual({
      lat: "37.5",
      lon: "127",
      assetValueKrw: "5000000000",
      constructionPeriodMonths: "24",
    });
  });
});

describe("buildEnergyCertificationBody — EnergyCertificationRequest 계약 핀(routers/energy.py)", () => {
  it("필드명·타입 1:1, insulation_grade는 손상값 아닌 정상 문자열 기본", () => {
    const values = {
      totalAreaSqm: "12500",
      floors: "15",
      windowWallRatio: "0.4",
      insulationGrade: "1등급",
      bemsSavingRate: "0.1",
    };
    const body = buildEnergyCertificationBody(values, { projectId: "proj-4" });
    expect(body).toEqual({
      project_id: "proj-4",
      total_area_sqm: 12500,
      floors: 15,
      window_wall_ratio: 0.4,
      insulation_grade: "1등급",
      bems_saving_rate: 0.1,
    });
  });

  it("프리필: GFA←designData.totalGfaSqm, floors←designData.floorCount", () => {
    const initial = energyCertificationInitialValues({
      totalGfaSqm: 12500,
      floorCount: 20,
    });
    expect(initial.totalAreaSqm).toBe("12500");
    expect(initial.floors).toBe("20");
    expect(initial.insulationGrade).toBe("1등급"); // 손상값 재현 금지
  });
});
