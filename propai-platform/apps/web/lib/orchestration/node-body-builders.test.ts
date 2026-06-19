// node-body-builders 단위테스트 — B6-1
// 노드별 SSOT 슬롯 → 백엔드 평면 body 매핑·필수 누락(missing) 게이트·통합면적 사용 검증.
// 순수 함수라 store/apiClient mock 불필요(컨텍스트 객체를 직접 시드).

import { describe, it, expect } from "vitest";

import { buildNodeBody, type NodeBodyContext } from "./node-body-builders";
import type {
  SiteAnalysisData,
  DesignData,
  CostData,
  FeasibilityData,
} from "@/store/useProjectContextStore";

/** 상도동 다필지 시나리오 — 통합면적 779㎡(직전 작업 기준값). */
function multiSite(over: Partial<SiteAnalysisData> = {}): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: 300, // 대표 1필지(작은값) — 통합면적이 우선되어야 함
    zoneCode: "제2종일반주거지역", // 한글 용도지역명(코드 아님)
    address: "서울특별시 동작구 상도동 123",
    pnu: "1159010300101230000",
    landAreaSqmTotal: 779,
    repLandAreaSqm: 300,
    parcelCount: 3,
    ...over,
  } as SiteAnalysisData;
}

function design(over: Partial<DesignData> = {}): DesignData {
  return {
    totalGfaSqm: 2400,
    floorCount: 12,
    buildingType: "공동주택",
    bcr: 55,
    far: 240,
    ...over,
  };
}

describe("buildNodeBody — 노드별 평면 body 매핑", () => {
  it("land: address★ 채움 + pnu 전달(통합 컨텍스트)", () => {
    const ctx: NodeBodyContext = { siteAnalysis: multiSite() };
    const { body, missing } = buildNodeBody("land", ctx, "p1");
    expect(missing).toEqual([]);
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
    expect(body.pnu).toBe("1159010300101230000");
  });

  it("land: 주소 미확보 → missing=[address](호출 금지)", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite({ address: null }),
    };
    const { body, missing } = buildNodeBody("land", ctx, "p1");
    expect(missing).toContain("address");
    expect(body.address).toBeUndefined();
  });

  it("legal: address★ + pnu (land과 동일 매핑)", () => {
    const { body, missing } = buildNodeBody(
      "legal",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
    expect(body.pnu).toBe("1159010300101230000");
  });

  it("recommend: 단일 주소를 addresses★ 배열로 래핑", () => {
    const { body, missing } = buildNodeBody(
      "recommend",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.addresses).toEqual(["서울특별시 동작구 상도동 123"]);
  });

  it("recommend: 주소 미확보 → missing=[addresses]", () => {
    const { missing } = buildNodeBody(
      "recommend",
      { siteAnalysis: multiSite({ address: null }) },
      "p1",
    );
    expect(missing).toContain("addresses");
  });

  it("design: 통합면적(779)→land_area_sqm, 한글 zoneCode는 생략(함정 회피), floor_count 전달", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design(),
    };
    const { body, missing } = buildNodeBody("design", ctx, "proj-42");
    expect(missing).toEqual([]); // design은 필수 강제 없음(백엔드 폴백)
    expect(body.land_area_sqm).toBe(779); // ★대표(300)가 아닌 통합면적(779)
    expect(body.zone_code).toBeUndefined(); // 한글 용도지역명 → 생략
    expect(body.floor_count).toBe(12);
  });

  it("design: 영문 zoneCode(2R)면 zone_code로 전달", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite({ zoneCode: "2R" }),
      designData: design(),
    };
    const { body } = buildNodeBody("design", ctx, "proj-42");
    expect(body.zone_code).toBe("2R");
  });

  it("sales: address★ + pnu(lawd_cd 도출 보조) + pnu 앞10자리 bcode 파생", () => {
    const { body, missing } = buildNodeBody(
      "sales",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
    expect(body.pnu).toBe("1159010300101230000");
    // ★pnu 앞 10자리(법정동코드)를 bcode로 함께 전송 → 백엔드 _resolve bcode 경로 보조.
    expect(body.bcode).toBe("1159010300");
  });

  it("sales(Issue2): pnu·bcode 모두 미확보면 missing=[pnu](백엔드 400 대신 needs-input)", () => {
    const { body, missing } = buildNodeBody(
      "sales",
      // 주소는 있으나 pnu 없음(주소 직접입력 등) → lawd_cd 도출 불가 → 게이트.
      { siteAnalysis: multiSite({ pnu: null }) },
      "p1",
    );
    expect(missing).toContain("pnu");
    expect(body.pnu).toBeUndefined();
    expect(body.bcode).toBeUndefined();
    // 주소는 그대로 담긴다(누락은 pnu뿐).
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
  });

  it("sales(Issue2): pnu 보유 정상 폐포는 무회귀(missing 없음·pnu 전송)", () => {
    const { missing } = buildNodeBody(
      "sales",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
  });

  it("qto: total_gfa_sqm★(gt0) + floor_count_above + building_type", () => {
    const { body, missing } = buildNodeBody(
      "qto",
      { designData: design() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.total_gfa_sqm).toBe(2400);
    expect(body.floor_count_above).toBe(12);
    expect(body.building_type).toBe("공동주택");
  });

  it("qto: GFA 미확보(0)면 missing=[total_gfa_sqm]", () => {
    const { body, missing } = buildNodeBody(
      "qto",
      { designData: design({ totalGfaSqm: 0 }) },
      "p1",
    );
    expect(missing).toContain("total_gfa_sqm");
    expect(body.total_gfa_sqm).toBeUndefined();
  });

  it("feasibility: development_type 기본(M06) + 통합면적(779)·GFA★ 채움", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design(),
    };
    const { body, missing } = buildNodeBody("feasibility", ctx, "p1");
    expect(missing).toEqual([]);
    expect(body.development_type).toBe("M06");
    expect(body.total_land_area_sqm).toBe(779); // ★통합면적
    expect(body.total_gfa_sqm).toBe(2400);
    expect(body.building_type).toBe("공동주택");
  });

  it("feasibility(Phase C-1): 추천 환류값(M08)이 development_type으로 우선 채택", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design(),
      // 상류 recommend가 환류한 추천 개발방식(오피스텔=M08).
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        developmentType: "M08",
      } as FeasibilityData,
    };
    const { body, missing } = buildNodeBody("feasibility", ctx, "p1");
    expect(missing).toEqual([]);
    expect(body.development_type).toBe("M08"); // ★고정 M06이 아니라 추천값
  });

  it("feasibility(Phase C-1): 추천 미환류(developmentType 부재)면 백엔드 기본 M06 폴백(무회귀)", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design(),
      feasibilityData: {
        totalCostWon: 100,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        // developmentType 미설정(구 스냅샷·추천 미실행).
      } as FeasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    expect(body.development_type).toBe("M06");
  });

  it("feasibility(Phase C-1): 비정상 코드(빈/소문자/범위밖)는 M06 폴백(날조 차단)", () => {
    for (const bad of ["", "  ", "m06", "M00", "M16", "X1", "재개발"]) {
      const ctx: NodeBodyContext = {
        siteAnalysis: multiSite(),
        designData: design(),
        feasibilityData: {
          totalCostWon: null,
          totalRevenueWon: null,
          profitRatePct: null,
          grade: null,
          developmentType: bad,
        } as FeasibilityData,
      };
      const { body } = buildNodeBody("feasibility", ctx, "p1");
      expect(body.development_type).toBe("M06");
    }
  });

  it("feasibility(Phase C-1): 경계 코드 M01·M15는 그대로 채택", () => {
    for (const ok of ["M01", "M15"]) {
      const ctx: NodeBodyContext = {
        siteAnalysis: multiSite(),
        designData: design(),
        feasibilityData: {
          totalCostWon: null,
          totalRevenueWon: null,
          profitRatePct: null,
          grade: null,
          developmentType: ok,
        } as FeasibilityData,
      };
      const { body } = buildNodeBody("feasibility", ctx, "p1");
      expect(body.development_type).toBe(ok);
    }
  });

  it("feasibility(Phase C-2): 분양가(원/평)·세대수·세대 전용면적이 폐루프로 채워진다", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design({ unitCount: 40 }), // 설계가 산출한 총세대수(buildingType=공동주택)
      // sales가 환류한 적정분양가(원/평) — store에 백엔드 단위로 보관됨.
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        salePricePerPyeongWon: 111_610_000, // 11161 만원/평 × 10000
      } as FeasibilityData,
    };
    const { body, missing } = buildNodeBody("feasibility", ctx, "p1");
    expect(missing).toEqual([]);
    // ★분양가가 무변환으로 그대로 전달(store=백엔드 단위 원/평).
    expect(body.avg_sale_price_per_pyeong).toBe(111_610_000);
    // ★co-requisite: 세대수·세대 전용면적도 채워져 분양수입이 0이 아니게 산출됨.
    expect(body.total_households).toBe(40);
    // ★면적정합(HIGH 수정): 전용단가에 곱하는 면적은 "전용면적 평"이어야 한다.
    //  공동주택 표준 전용률 0.76 적용 → 전용평 = GFA(2400㎡) × 0.76 ÷ 3.305785 ÷ 40세대 ≈ 13.79평.
    //  (종전 18.15평=연면적 그대로 → 과대. 0.76배로 축소됨.)
    expect(body.avg_area_pyeong).toBeCloseTo((2400 * 0.76) / 3.305785 / 40, 2);
  });

  it("feasibility(Phase C-2·면적정합): 설계 전용률(efficiencyPct) 실값이 있으면 그 값으로 전용면적 환산", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      // 설계가 실제 전용률 72%를 환류 → 표준 테이블이 아닌 실값을 우선 사용해야 함.
      designData: design({ unitCount: 40, efficiencyPct: 72 }),
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        salePricePerPyeongWon: 111_610_000,
      } as FeasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    // 전용평 = GFA(2400㎡) × 0.72 ÷ 3.305785 ÷ 40세대.
    expect(body.avg_area_pyeong).toBeCloseTo((2400 * 0.72) / 3.305785 / 40, 2);
  });

  it("feasibility(Phase C-2·면적정합): 전용률·유형 모두 미확보면 표준 기본 전용률(0.75)로 폴백", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      // buildingType 미상(표준 테이블 미적중) + efficiencyPct 미확보 → 기본 0.75.
      designData: design({ unitCount: 40, buildingType: null, efficiencyPct: null }),
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        salePricePerPyeongWon: 111_610_000,
      } as FeasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    expect(body.avg_area_pyeong).toBeCloseTo((2400 * 0.75) / 3.305785 / 40, 2);
  });

  it("feasibility(Phase C-2·면적정합): 전용면적은 항상 종전 연면적 기준보다 작다(과대 해소)", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design({ unitCount: 40 }), // 공동주택 0.76
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
        salePricePerPyeongWon: 111_610_000,
      } as FeasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    const grossPyeong = 2400 / 3.305785 / 40; // 종전(연면적 그대로)
    expect(body.avg_area_pyeong as number).toBeLessThan(grossPyeong);
  });

  it("feasibility(Phase C-2): 분양가/세대수 미확보면 해당 필드 미주입(백엔드 기본 0, 무회귀)", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite(),
      designData: design(), // unitCount 미설정
      // salePricePerPyeongWon 미설정(구 스냅샷·sales 미실행).
      feasibilityData: {
        totalCostWon: null,
        totalRevenueWon: null,
        profitRatePct: null,
        grade: null,
      } as FeasibilityData,
    };
    const { body } = buildNodeBody("feasibility", ctx, "p1");
    expect(body.avg_sale_price_per_pyeong).toBeUndefined();
    expect(body.total_households).toBeUndefined();
    expect(body.avg_area_pyeong).toBeUndefined();
  });

  it("feasibility(Phase C-2): 분양가 비양수(0/음수)는 미주입(0 강제 금지)", () => {
    for (const bad of [0, -5]) {
      const ctx: NodeBodyContext = {
        siteAnalysis: multiSite(),
        designData: design({ unitCount: 40 }),
        feasibilityData: {
          totalCostWon: null,
          totalRevenueWon: null,
          profitRatePct: null,
          grade: null,
          salePricePerPyeongWon: bad,
        } as FeasibilityData,
      };
      const { body } = buildNodeBody("feasibility", ctx, "p1");
      expect(body.avg_sale_price_per_pyeong).toBeUndefined();
    }
  });

  it("feasibility: 면적·GFA 둘 다 미확보면 missing 둘 다", () => {
    const { missing } = buildNodeBody(
      "feasibility",
      { siteAnalysis: multiSite({ landAreaSqm: 0, landAreaSqmTotal: 0 }) },
      "p1",
    );
    expect(missing).toContain("total_land_area_sqm");
    expect(missing).toContain("total_gfa_sqm");
  });

  it("finance: total_project_cost_won★ + construction_cost_won", () => {
    const feasibilityData: FeasibilityData = {
      totalCostWon: 50_000_000_000,
      totalRevenueWon: 60_000_000_000,
      profitRatePct: 20,
      grade: "B",
    };
    const costData: CostData = {
      totalConstructionCostWon: 30_000_000_000,
      perSqmWon: null,
      perPyeongWon: null,
      abovegroundWon: null,
      undergroundWon: null,
      landscapeWon: null,
      directWon: null,
      indirectWon: null,
      rangeMinWon: null,
      rangeMaxWon: null,
      source: "overview",
    };
    const { body, missing } = buildNodeBody(
      "finance",
      { feasibilityData, costData },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.total_project_cost_won).toBe(50_000_000_000);
    expect(body.construction_cost_won).toBe(30_000_000_000);
  });

  it("finance: 총사업비 미확보면 missing=[total_project_cost_won]", () => {
    const { missing } = buildNodeBody("finance", {}, "p1");
    expect(missing).toContain("total_project_cost_won");
  });

  it("permit: address★ + pnu 전달(인허가 분석)", () => {
    const { body, missing } = buildNodeBody(
      "permit",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
    expect(body.pnu).toBe("1159010300101230000");
  });

  it("permit: 주소 미확보 → missing=[address](호출 금지)", () => {
    const { body, missing } = buildNodeBody(
      "permit",
      { siteAnalysis: multiSite({ address: null }) },
      "p1",
    );
    expect(missing).toContain("address");
    expect(body.address).toBeUndefined();
  });

  it("permit: 다필지면 추가 필지 주소를 parcels로 전달(대표주소·빈값 제외)", () => {
    const ctx: NodeBodyContext = {
      siteAnalysis: multiSite({
        parcels: [
          // 대표 주소(동일)는 제외돼야 함.
          { pnu: "1", address: "서울특별시 동작구 상도동 123", areaSqm: 300, landCategory: "대", ownerType: "개인" },
          { pnu: "2", address: "서울특별시 동작구 상도동 124", areaSqm: 240, landCategory: "대", ownerType: "개인" },
          { pnu: "3", address: "서울특별시 동작구 상도동 125", areaSqm: 239, landCategory: "대", ownerType: "개인" },
        ],
      }),
    };
    const { body, missing } = buildNodeBody("permit", ctx, "p1");
    expect(missing).toEqual([]);
    expect(body.parcels).toEqual([
      "서울특별시 동작구 상도동 124",
      "서울특별시 동작구 상도동 125",
    ]);
  });

  it("permit: 단일필지(parcels 없음)면 parcels 키 생략", () => {
    const { body } = buildNodeBody(
      "permit",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(body.parcels).toBeUndefined();
  });

  it("단일필지(parcelCount 미설정)는 landAreaSqm을 그대로 면적으로 사용", () => {
    const single: SiteAnalysisData = {
      estimatedValue: null,
      landAreaSqm: 500,
      zoneCode: null,
      address: "서울 강남구 역삼동 736",
      pnu: null,
    } as SiteAnalysisData;
    const { body } = buildNodeBody(
      "feasibility",
      { siteAnalysis: single, designData: design() },
      "p1",
    );
    expect(body.total_land_area_sqm).toBe(500);
  });
});
