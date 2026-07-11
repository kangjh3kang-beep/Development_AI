// 배선 캠페인 2차(워크스페이스 클러스터 6건) 요청 조립 단위테스트.
// 목적: 백엔드 Pydantic 계약(필드명·타입)을 프론트 바디/쿼리 조립 함수에 고정(계약 핀 6건+).
import { describe, it, expect } from "vitest";
import {
  buildWorkspaceExtendedContext,
  permitCaseInitialValues,
  buildPermitCaseQuery,
  costEscalationInitialValues,
  buildCostEscalationBody,
  underwritingInitialValues,
  buildUnderwritingBody,
  constructionScheduleInitialValues,
  buildConstructionScheduleBody,
  zebEnergyInitialValues,
  buildZebEnergyBody,
  constructionClimateInitialValues,
  buildConstructionClimateBody,
  defectClassificationInitialValues,
  buildDefectClassificationBody,
  cadCorrectionInitialValues,
  buildCadCheckBody,
  cadAutoCorrectInitialValues,
  buildCadAutoCorrectBody,
  facilityReserveInitialValues,
  buildFacilityReserveBody,
  buildFacilityCancelBody,
  maintenanceAnomalyInitialValues,
  buildMaintenanceAnomalyBody,
  marketingContentInitialValues,
  buildMarketingContentBody,
  omReportInitialValues,
  buildOmReportBody,
  c2rBriefInitialValues,
  buildC2rBriefBody,
} from "./workspace-extended-panels";

describe("buildWorkspaceExtendedContext", () => {
  it("전 필드 확보 시 SSOT 값을 그대로 매핑", () => {
    const ctx = buildWorkspaceExtendedContext({
      projectId: "p1",
      projectName: "테스트 프로젝트",
      siteAnalysis: {
        pnu: "1111010100100010000",
        coordinates: { lat: 37.5, lon: 127.0 },
        landAreaSqm: 500,
        effectiveBcrPct: 55,
        effectiveFarPct: 200,
        estimatedValue: 3_000_000_000,
      },
      designData: {
        totalGfaSqm: 1200,
        floorCount: 10,
        maxHeightM: 45,
        massGeom: { footprintSqm: 300 },
      },
      feasibilityData: { totalCostWon: 5_000_000_000, totalRevenueWon: 7_000_000_000, equityWon: 500_000_000 },
      costData: { totalConstructionCostWon: 4_000_000_000 },
    });
    expect(ctx).toEqual({
      projectId: "p1",
      projectName: "테스트 프로젝트",
      pnu: "1111010100100010000",
      lat: 37.5,
      lon: 127.0,
      totalGfaSqm: 1200,
      floorCount: 10,
      landAreaSqm: 500,
      buildingFootprintSqm: 300,
      effectiveBcrPct: 55,
      effectiveFarPct: 200,
      maxHeightM: 45,
      totalCostWon: 5_000_000_000,
      totalRevenueWon: 7_000_000_000,
      equityWon: 500_000_000,
      estimatedLandValueWon: 3_000_000_000,
      totalConstructionCostWon: 4_000_000_000,
    });
  });

  it("미확보 필드는 전부 null(무날조) — 빈 projectName은 null로 정규화", () => {
    const ctx = buildWorkspaceExtendedContext({ projectId: "p2", projectName: "" });
    expect(ctx.projectName).toBeNull();
    expect(ctx.pnu).toBeNull();
    expect(ctx.lat).toBeNull();
    expect(ctx.landAreaSqm).toBeNull();
    expect(ctx.buildingFootprintSqm).toBeNull();
    expect(ctx.estimatedLandValueWon).toBeNull();
  });

  it("건폐율/용적률: 실효값(effective) 우선, 없으면 법정(national)으로 폴백", () => {
    const withEffective = buildWorkspaceExtendedContext({
      projectId: "p3",
      siteAnalysis: { effectiveBcrPct: 50, nationalBcrPct: 60, effectiveFarPct: 150, nationalFarPct: 250 },
    });
    expect(withEffective.effectiveBcrPct).toBe(50);
    expect(withEffective.effectiveFarPct).toBe(150);

    const nationalOnly = buildWorkspaceExtendedContext({
      projectId: "p4",
      siteAnalysis: { nationalBcrPct: 60, nationalFarPct: 250 },
    });
    expect(nationalOnly.effectiveBcrPct).toBe(60);
    expect(nationalOnly.effectiveFarPct).toBe(250);
  });
});

describe("① buildPermitCaseQuery — GET /permit-cases 쿼리 계약 핀(routers/permit_cases.py)", () => {
  it("pnu·kind·page·page_size 조립, kind 기본은 arch", () => {
    const q = buildPermitCaseQuery({ pnu: " 1111010100 ", kind: "arch" });
    expect(q).toEqual({ pnu: "1111010100", kind: "arch", page: "1", page_size: "20" });
  });

  it("kind=hs 선택 시 그대로 반영, 미인식 값은 arch로 안전 폴백", () => {
    expect(buildPermitCaseQuery({ pnu: "1", kind: "hs" }).kind).toBe("hs");
    expect(buildPermitCaseQuery({ pnu: "1", kind: "bogus" as never }).kind).toBe("arch");
  });

  it("프리필: siteAnalysis.pnu가 있으면 초기값으로 사용, 기본 kind=arch", () => {
    expect(permitCaseInitialValues({ pnu: "1111010100" })).toEqual({
      pnu: "1111010100",
      kind: "arch",
    });
    expect(permitCaseInitialValues({ pnu: null }).pnu).toBe("");
  });
});

describe("② buildCostEscalationBody — CostEscalationRequest 계약 핀(routers/cost_intelligence.py)", () => {
  it("필드명·타입 1:1, 선택 비율 필드는 생략(백엔드 기본값 위임)", () => {
    const values = {
      baseConstructionCostKrw: "5000000000",
      baselineYear: "2026",
      targetYear: "2029",
      constructionDurationMonths: "24",
      regionCode: "KR",
    };
    const body = buildCostEscalationBody(values, { projectId: "proj-1" });
    expect(body).toEqual({
      project_id: "proj-1",
      base_construction_cost_krw: 5000000000,
      baseline_year: 2026,
      target_year: 2029,
      construction_duration_months: 24,
      region_code: "KR",
    });
    expect(Object.keys(body)).not.toContain("material_share_ratio");
  });

  it("프리필: totalConstructionCostWon 있으면 초기값, baselineYear는 현재 연도", () => {
    const initial = costEscalationInitialValues({ totalConstructionCostWon: 4_000_000_000 });
    expect(initial.baseConstructionCostKrw).toBe("4000000000");
    expect(initial.baselineYear).toBe(String(new Date().getFullYear()));
    expect(initial.targetYear).toBe("");
    expect(initial.constructionDurationMonths).toBe("18");
    expect(initial.regionCode).toBe("KR");
  });
});

describe("③ buildUnderwritingBody — UnderwritingRequest 계약 핀(routers/underwriting.py)", () => {
  it("필드명·타입 1:1, jeonseRatio 빈 값은 null(옵셔널 유지)", () => {
    const values = {
      projectName: "테스트 프로젝트",
      totalCostKrw: "10000000000",
      projectedRevenueKrw: "14000000000",
      acquisitionPriceKrw: "3000000000",
      equityKrw: "2000000000",
      debtKrw: "8000000000",
      jeonseRatio: "",
    };
    const body = buildUnderwritingBody(values, { projectId: "proj-2" });
    expect(body).toEqual({
      project_id: "proj-2",
      project_name: "테스트 프로젝트",
      total_cost_krw: 10000000000,
      projected_revenue_krw: 14000000000,
      acquisition_price_krw: 3000000000,
      equity_krw: 2000000000,
      debt_krw: 8000000000,
      jeonse_ratio: null,
      assumptions_json: {},
      data_room_documents: [],
    });
  });

  it("jeonseRatio 입력 시 숫자로 변환", () => {
    const body = buildUnderwritingBody(
      { projectName: "x", totalCostKrw: "1", projectedRevenueKrw: "1", acquisitionPriceKrw: "1", equityKrw: "1", debtKrw: "0", jeonseRatio: "0.4" },
      { projectId: "p" },
    );
    expect(body.jeonse_ratio).toBe(0.4);
  });

  it("프리필: 부채=총사업비-자기자본 산술 파생(둘 다 있을 때만), 취득가는 estimatedLandValueWon", () => {
    const initial = underwritingInitialValues({
      projectName: "테스트",
      totalCostWon: 10_000_000_000,
      totalRevenueWon: 14_000_000_000,
      equityWon: 2_000_000_000,
      estimatedLandValueWon: 3_000_000_000,
    });
    expect(initial.debtKrw).toBe("8000000000");
    expect(initial.acquisitionPriceKrw).toBe("3000000000");

    const noEquity = underwritingInitialValues({
      projectName: null,
      totalCostWon: 10_000_000_000,
      totalRevenueWon: null,
      equityWon: null,
      estimatedLandValueWon: null,
    });
    expect(noEquity.debtKrw).toBe(""); // 무날조: 하나라도 없으면 공란
    expect(noEquity.projectName).toBe("");
  });
});

describe("④-1 buildConstructionScheduleBody — ConstructionScheduleRequest 계약 핀(routers/construction.py)", () => {
  it("필드명·타입 1:1", () => {
    const body = buildConstructionScheduleBody(
      { totalAreaSqm: "12500", floorsAbove: "15", floorsBelow: "2", structureType: "SRC" },
      { projectId: "proj-3" },
    );
    expect(body).toEqual({
      project_id: "proj-3",
      total_area_sqm: 12500,
      floors_above: 15,
      floors_below: 2,
      structure_type: "SRC",
    });
  });

  it("프리필: GFA←totalGfaSqm, floorsAbove←floorCount, floorsBelow/structureType은 백엔드 기본값", () => {
    const initial = constructionScheduleInitialValues({ totalGfaSqm: 12500, floorCount: 15 });
    expect(initial.totalAreaSqm).toBe("12500");
    expect(initial.floorsAbove).toBe("15");
    expect(initial.floorsBelow).toBe("1");
    expect(initial.structureType).toBe("RC");
  });
});

describe("④-2 buildZebEnergyBody — ZEBEnergyRequest 계약 핀(routers/construction.py)", () => {
  it("필드명·타입 1:1, insulationGrade 손상값 재현 금지", () => {
    const body = buildZebEnergyBody(
      { totalAreaSqm: "12500", floors: "15", windowWallRatio: "0.4", insulationGrade: "1등급" },
      { projectId: "proj-4" },
    );
    expect(body).toEqual({
      project_id: "proj-4",
      total_area_sqm: 12500,
      floors: 15,
      window_wall_ratio: 0.4,
      insulation_grade: "1등급",
    });
  });

  it("프리필: GFA/floors는 설계 SSOT, windowWallRatio/insulationGrade는 백엔드 기본값", () => {
    const initial = zebEnergyInitialValues({ totalGfaSqm: 12500, floorCount: 20 });
    expect(initial.totalAreaSqm).toBe("12500");
    expect(initial.floors).toBe("20");
    expect(initial.windowWallRatio).toBe("0.35");
    expect(initial.insulationGrade).toBe("1등급");
  });
});

describe("④-3 buildConstructionClimateBody — ClimateRiskRequest 계약 핀(routers/construction.py)", () => {
  it("필드명·타입 1:1, construction_period_months 기본 24 유지", () => {
    const body = buildConstructionClimateBody(
      { lat: "37.5665", lon: "126.9780", constructionPeriodMonths: "24" },
      { projectId: "proj-5" },
    );
    expect(body).toEqual({
      project_id: "proj-5",
      lat: 37.5665,
      lon: 126.978,
      construction_period_months: 24,
    });
  });

  it("프리필: 좌표는 부지 SSOT, 없으면 공란(위경도는 필수 검증 미적용 — 1차 climate 패널과 동일 판단)", () => {
    const initial = constructionClimateInitialValues({ lat: 37.5, lon: 127.0 });
    expect(initial).toEqual({ lat: "37.5", lon: "127", constructionPeriodMonths: "24" });
    expect(constructionClimateInitialValues({ lat: null, lon: null }).lat).toBe("");
  });
});

describe("④-4 buildDefectClassificationBody — DefectClassificationRequest 계약 핀(routers/construction.py)", () => {
  it("필드명·타입 1:1, image_url/location은 trim", () => {
    const body = buildDefectClassificationBody(
      { imageUrl: " https://example.com/defect.jpg ", location: " 3층 발코니 " },
      { projectId: "proj-6" },
    );
    expect(body).toEqual({
      project_id: "proj-6",
      image_url: "https://example.com/defect.jpg",
      location: "3층 발코니",
    });
  });

  it("프리필은 전부 공란(SSOT 프리필 원천 없음 — 무날조)", () => {
    expect(defectClassificationInitialValues()).toEqual({ imageUrl: "", location: "" });
  });
});

describe("⑤ buildCadCheckBody / buildCadAutoCorrectBody — CheckRequest/AutoCorrectRequest 계약 핀(routers/cad_correction.py)", () => {
  it("check: building/regulation 중첩 조립, project_id 없음(라우터 계약 확인 결과)", () => {
    const body = buildCadCheckBody({
      siteAreaSqm: "500",
      buildingAreaSqm: "250",
      numFloors: "10",
      floorHeightM: "3.2",
      maxBcr: "55",
      maxFar: "200",
      maxHeightM: "45",
    });
    expect(body).toEqual({
      building: { site_area_sqm: 500, building_area_sqm: 250, num_floors: 10, floor_height_m: 3.2 },
      regulation: { max_bcr: 55, max_far: 200, max_height_m: 45 },
    });
    expect(body).not.toHaveProperty("project_id");
  });

  it("auto-correct: check와 동일 building/regulation + max_iter 추가", () => {
    const values = {
      siteAreaSqm: "500",
      buildingAreaSqm: "250",
      numFloors: "10",
      floorHeightM: "3",
      maxBcr: "55",
      maxFar: "200",
      maxHeightM: "0",
      maxIter: "50",
    };
    const body = buildCadAutoCorrectBody(values);
    expect(body.max_iter).toBe(50);
    expect(body.building).toEqual({ site_area_sqm: 500, building_area_sqm: 250, num_floors: 10, floor_height_m: 3 });
    expect(body.regulation).toEqual({ max_bcr: 55, max_far: 200, max_height_m: 0 });
  });

  it("프리필: 대지면적←landAreaSqm, 건축면적←buildingFootprintSqm(massGeom), 층수←floorCount, 한도←effective*Pct", () => {
    const initial = cadCorrectionInitialValues({
      landAreaSqm: 500,
      buildingFootprintSqm: 250,
      floorCount: 10,
      effectiveBcrPct: 55,
      effectiveFarPct: 200,
      maxHeightM: 45,
    });
    expect(initial).toEqual({
      siteAreaSqm: "500",
      buildingAreaSqm: "250",
      numFloors: "10",
      floorHeightM: "3",
      maxBcr: "55",
      maxFar: "200",
      maxHeightM: "45",
    });
  });

  it("프리필: maxHeightM 미확보 시 0(백엔드 '무제한' sentinel, 발명 아님)", () => {
    const initial = cadCorrectionInitialValues({
      landAreaSqm: null,
      buildingFootprintSqm: null,
      floorCount: null,
      effectiveBcrPct: null,
      effectiveFarPct: null,
      maxHeightM: null,
    });
    expect(initial.maxHeightM).toBe("0");
    expect(initial.siteAreaSqm).toBe("");
  });

  it("auto-correct 프리필: check 프리필 + maxIter=100(백엔드 기본값)", () => {
    const initial = cadAutoCorrectInitialValues({
      landAreaSqm: 500,
      buildingFootprintSqm: null,
      floorCount: null,
      effectiveBcrPct: null,
      effectiveFarPct: null,
      maxHeightM: null,
    });
    expect(initial.maxIter).toBe("100");
    expect(initial.siteAreaSqm).toBe("500");
  });
});

describe("⑥ buildFacilityReserveBody/buildFacilityCancelBody — CreateReservationRequest/CancelReservationRequest 계약 핀(routers/facility_reservations.py)", () => {
  it("초기값은 전부 빈 문자열(무날조 — 프로젝트 선택은 별도 목록에서 사용자가 고른다)", () => {
    expect(facilityReserveInitialValues()).toEqual({
      facilityName: "",
      startTime: "",
      endTime: "",
      notes: "",
    });
  });

  it("reserve 바디 필드명·타입 1:1, notes 공란은 null", () => {
    const body = buildFacilityReserveBody(
      {
        facilityName: "커뮤니티 라운지",
        startTime: "2026-08-01T10:00",
        endTime: "2026-08-01T12:00",
        notes: "",
      },
      { projectId: "proj-fac-1" },
    );
    expect(body).toEqual({
      project_id: "proj-fac-1",
      facility_name: "커뮤니티 라운지",
      start_time: "2026-08-01T10:00",
      end_time: "2026-08-01T12:00",
      notes: null,
    });
  });

  it("cancel 바디는 reservation_id 단일 필드(트림)", () => {
    expect(buildFacilityCancelBody("  res-123  ")).toEqual({ reservation_id: "res-123" });
  });
});

describe("⑦ buildMaintenanceAnomalyBody — MaintenanceAnomalyRequest 계약 핀(packages/schemas/models.py:1177)", () => {
  it("초기값: equipment_type은 백엔드 기본값이 없어 빈 문자열(무날조), 나머지는 Field default(vibration=0·temperature=0·efficiency=1)", () => {
    expect(maintenanceAnomalyInitialValues()).toEqual({
      equipmentName: "",
      equipmentType: "",
      location: "",
      vibrationMmS: "0",
      temperatureC: "0",
      energyEfficiencyRatio: "1",
    });
  });

  it("바디 필드명·타입 1:1, location 공란은 null", () => {
    const body = buildMaintenanceAnomalyBody(
      {
        equipmentName: "AHU-3",
        equipmentType: "hvac",
        location: "",
        vibrationMmS: "9.2",
        temperatureC: "31.5",
        energyEfficiencyRatio: "0.71",
      },
      { projectId: "proj-maint-1" },
    );
    expect(body).toEqual({
      project_id: "proj-maint-1",
      equipment_name: "AHU-3",
      equipment_type: "hvac",
      location: null,
      vibration_mm_s: 9.2,
      temperature_c: 31.5,
      energy_efficiency_ratio: 0.71,
    });
  });

  it("효율비 0(설비 완전정지 앵커값)은 1로 치환되지 않고 그대로 전달(QA MEDIUM 회귀 고정)", () => {
    const body = buildMaintenanceAnomalyBody(
      { equipmentName: "x", equipmentType: "hvac", location: "", vibrationMmS: "1", temperatureC: "1", energyEfficiencyRatio: "0" },
      { projectId: "p" },
    );
    expect(body.energy_efficiency_ratio).toBe(0);
  });

  it("효율비 빈값은 백엔드 기본 1로 폴백(빈값/NaN만)", () => {
    const body = buildMaintenanceAnomalyBody(
      { equipmentName: "x", equipmentType: "hvac", location: "", vibrationMmS: "1", temperatureC: "1", energyEfficiencyRatio: "" },
      { projectId: "p" },
    );
    expect(body.energy_efficiency_ratio).toBe(1);
  });

  it("equipment_type은 폴백 없이 그대로 전달(빈 값을 임의 종류로 지어내지 않음)", () => {
    const body = buildMaintenanceAnomalyBody(
      { equipmentName: "x", equipmentType: "", location: "", vibrationMmS: "1", temperatureC: "1", energyEfficiencyRatio: "1" },
      { projectId: "p" },
    );
    expect(body.equipment_type).toBe("");
  });

  it("음수 온도(영하)도 그대로 전달(ge=-30 허용 — 0 폴백으로 뭉개지 않음)", () => {
    const body = buildMaintenanceAnomalyBody(
      { equipmentName: "x", equipmentType: "hvac", location: "", vibrationMmS: "1", temperatureC: "-10", energyEfficiencyRatio: "1" },
      { projectId: "p" },
    );
    expect(body.temperature_c).toBe(-10);
  });
});

describe("⑧ buildMarketingContentBody/buildOmReportBody — MarketingContentRequest/OMReportRequest 계약 핀(routers/marketing.py)", () => {
  it("marketing content 초기값: channel은 백엔드 기본값이 없어 빈 문자열(무날조), tone은 백엔드 기본값(professional)", () => {
    expect(marketingContentInitialValues()).toEqual({
      channel: "",
      assetType: "",
      targetAudience: "",
      tone: "professional",
      highlights: "",
    });
  });

  it("marketing content 바디: highlights는 콤마 구분 → 배열 분해", () => {
    const body = buildMarketingContentBody(
      {
        channel: "instagram",
        assetType: "residential",
        targetAudience: "MZ 세대",
        tone: "energetic",
        highlights: "역세권, 신축, 남향",
      },
      { projectId: "proj-mkt-1", projectName: "테스트 프로젝트" },
    );
    expect(body).toEqual({
      project_id: "proj-mkt-1",
      project_name: "테스트 프로젝트",
      channel: "instagram",
      asset_type: "residential",
      target_audience: "MZ 세대",
      tone: "energetic",
      highlights: ["역세권", "신축", "남향"],
    });
  });

  it("om report 초기값은 백엔드 기본값과 동일(targetAudience=institutional·outputFormat=markdown)", () => {
    expect(omReportInitialValues()).toEqual({
      assetType: "",
      investmentHighlights: "",
      targetAudience: "institutional",
      riskFactors: "",
      outputFormat: "markdown",
    });
  });

  it("om report 바디: investment_highlights/risk_factors 콤마 구분 → 배열 분해", () => {
    const body = buildOmReportBody(
      {
        assetType: "office",
        investmentHighlights: "핵심상권, 장기임차인",
        targetAudience: "institutional",
        riskFactors: "금리 변동",
        outputFormat: "pdf",
      },
      { projectId: "proj-mkt-2", projectName: "OM 테스트" },
    );
    expect(body).toEqual({
      project_id: "proj-mkt-2",
      project_name: "OM 테스트",
      asset_type: "office",
      investment_highlights: ["핵심상권", "장기임차인"],
      target_audience: "institutional",
      risk_factors: ["금리 변동"],
      output_format: "pdf",
    });
  });

  it("빈 콤마 목록은 빈 배열(무날조 — 임의 항목 생성 금지)", () => {
    const body = buildMarketingContentBody(
      { channel: "web", assetType: "x", targetAudience: "y", tone: "professional", highlights: "" },
      { projectId: "p", projectName: "n" },
    );
    expect(body.highlights).toEqual([]);
  });
});

describe("⑨ buildC2rBriefBody — BriefRequest 계약 핀(apps/api/app/routers/c2r.py)", () => {
  it("프리필: pnu는 siteAnalysis.pnu, address는 옵션 전달값(SSOT 미확보 시 빈 문자열)", () => {
    const withPnu = c2rBriefInitialValues({ pnu: "1111010100100010000", address: "서울시 종로구" });
    expect(withPnu).toEqual({
      pnu: "1111010100100010000",
      address: "서울시 종로구",
      buildingUse: "",
      scale: "",
      useLlm: false,
    });

    const empty = c2rBriefInitialValues({ pnu: null, address: null });
    expect(empty.pnu).toBe("");
    expect(empty.address).toBe("");
  });

  it("바디: pnu/address 둘 다 그대로 전달(라우터가 pnu 우선 처리) — 공란은 null", () => {
    const body = buildC2rBriefBody({
      pnu: "1111010100100010000",
      address: "",
      buildingUse: "",
      scale: "",
      useLlm: false,
    });
    expect(body).toEqual({
      pnu: "1111010100100010000",
      address: null,
      options: null,
      use_llm: false,
    });
  });

  it("options: building_use/scale 하나라도 있으면 채운 필드만 담고, 둘 다 없으면 null", () => {
    const body = buildC2rBriefBody({
      pnu: "",
      address: "서울시 종로구",
      buildingUse: "오피스텔",
      scale: "",
      useLlm: true,
    });
    expect(body).toEqual({
      pnu: null,
      address: "서울시 종로구",
      options: { building_use: "오피스텔" },
      use_llm: true,
    });
  });
});
