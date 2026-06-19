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

  it("sales: address★ + pnu(lawd_cd 도출 보조)", () => {
    const { body, missing } = buildNodeBody(
      "sales",
      { siteAnalysis: multiSite() },
      "p1",
    );
    expect(missing).toEqual([]);
    expect(body.address).toBe("서울특별시 동작구 상도동 123");
    expect(body.pnu).toBe("1159010300101230000");
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
