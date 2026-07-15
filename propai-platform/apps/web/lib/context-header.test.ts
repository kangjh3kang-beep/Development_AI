import { describe, it, expect } from "vitest";
import {
  deriveContextHeaderData,
  zoneDisplayLabel,
  deriveSitePipelineSteps,
  deriveFeasibilityPipelineSteps,
  deriveMarketPipelineSteps,
  type ContextHeaderInput,
} from "./context-header";
import type { SiteAnalysisData, ProjectContextState } from "@/store/useProjectContextStore";

function fd(
  partial: Partial<NonNullable<ProjectContextState["feasibilityData"]>>,
): NonNullable<ProjectContextState["feasibilityData"]> {
  return partial as NonNullable<ProjectContextState["feasibilityData"]>;
}

// 검증과 무관한 필수 필드는 부분 객체로 구성(site-area.test.ts 패턴과 동일).
function sa(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return partial as SiteAnalysisData;
}
function ctx(partial: Partial<ContextHeaderInput>): ContextHeaderInput {
  return {
    projectId: null,
    projectName: "",
    siteAnalysis: null,
    ...partial,
  };
}

describe("deriveContextHeaderData — 대상 컨텍스트 파생(무목업)", () => {
  it("컨텍스트 전무: hasContext=false, 모든 값 null(대상 미선택 정직 안내)", () => {
    const d = deriveContextHeaderData(ctx({}));
    expect(d.hasContext).toBe(false);
    expect(d.projectName).toBeNull();
    expect(d.address).toBeNull();
    expect(d.pnu).toBeNull();
    expect(d.zoneLabel).toBeNull();
    expect(d.landAreaSqm).toBeNull();
    expect(d.isMultiParcel).toBe(false);
  });

  it("프로젝트만 선택(projectId): hasContext=true", () => {
    const d = deriveContextHeaderData(ctx({ projectId: "p1", projectName: "역삼 개발" }));
    expect(d.hasContext).toBe(true);
    expect(d.projectName).toBe("역삼 개발");
  });

  it("주소만 확보(프로젝트 미선택): hasContext=true", () => {
    const d = deriveContextHeaderData(
      ctx({ siteAnalysis: sa({ address: "서울 강남구 역삼동 737" }) }),
    );
    expect(d.hasContext).toBe(true);
    expect(d.address).toBe("서울 강남구 역삼동 737");
  });

  it("단일필지: landAreaSqm 그대로, isMultiParcel=false", () => {
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({
          address: "A",
          pnu: "1168010100107370000",
          landAreaSqm: 540,
          parcelCount: 1,
        }),
      }),
    );
    expect(d.landAreaSqm).toBe(540);
    expect(d.isMultiParcel).toBe(false);
    expect(d.parcelCount).toBe(1);
    expect(d.pnu).toBe("1168010100107370000");
  });

  it("다필지: 통합면적(landAreaSqmTotal) 우선 + isMultiParcel=true + parcelCount 유지", () => {
    // 대표 236㎡이지만 통합 779㎡·2필지면 통합면적을 우선 표시해야 한다(경합 면역).
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({
          address: "상도동",
          landAreaSqm: 236,
          landAreaSqmTotal: 779,
          parcelCount: 2,
        }),
      }),
    );
    expect(d.landAreaSqm).toBe(779);
    expect(d.isMultiParcel).toBe(true);
    expect(d.parcelCount).toBe(2);
  });

  it("용도지역 정규화: 통합 dominantZoneCode 우선 + 표시 라벨 정규화", () => {
    // dominantZoneCode="2R"(다필지 우세) → "제2종일반주거지역"으로 정규화 표시.
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({
          address: "A",
          zoneCode: "자연녹지지역",
          dominantZoneCode: "2R",
          landAreaSqmTotal: 779,
          parcelCount: 2,
        }),
      }),
    );
    // 통합 우세 용도(dominant)가 대표필지 단일 zoneCode를 이긴다.
    expect(d.zoneLabel).toBe("제2종일반주거지역");
  });

  it("용도지역: 통합값 없으면 단일 zoneCode로 폴백해 정규화", () => {
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({ address: "A", zoneCode: "제3종일반주거지역" }),
      }),
    );
    expect(d.zoneLabel).toBe("제3종일반주거지역");
    expect(d.zoneSource).toBe("site");
  });

  it("용도지역 폴백: 부지분석에 용도지역이 없으면 설계값(designData.zoneCode)을 '직접 입력'으로 표기", () => {
    // 시나리오(사용자 지적): projectId만 있고 siteAnalysis에 용도지역이 없어 상단이 "용도지역 —"이던
    // 상황 — 설계 콘솔이 아는 '자연녹지지역'(직접 입력/시드)을 폴백 표기해야 한다(zoneSource="design").
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({ address: "A" }), // 용도지역 부재
        designData: { zoneCode: "자연녹지지역" },
      }),
    );
    expect(d.zoneLabel).toBe("자연녹지지역");
    expect(d.zoneSource).toBe("design");
  });

  it("용도지역: 부지분석 용도지역이 있으면 설계값보다 우선(site) — 설계 폴백은 부재 시에만", () => {
    const d = deriveContextHeaderData(
      ctx({
        projectId: "p1",
        siteAnalysis: sa({ address: "A", zoneCode: "제2종일반주거지역" }),
        designData: { zoneCode: "자연녹지지역" },
      }),
    );
    expect(d.zoneLabel).toBe("제2종일반주거지역");
    expect(d.zoneSource).toBe("site");
  });

  it("용도지역: 부지분석·설계 모두 없으면 null + zoneSource=null(무날조)", () => {
    const d = deriveContextHeaderData(ctx({ projectId: "p1" }));
    expect(d.zoneLabel).toBeNull();
    expect(d.zoneSource).toBeNull();
  });
});

describe("zoneDisplayLabel — 용도지역 표시 라벨", () => {
  it("코드/변형을 정식 한글 라벨로 정규화", () => {
    expect(zoneDisplayLabel("2R")).toBe("제2종일반주거지역");
    expect(zoneDisplayLabel("일반상업")).toBe("일반상업지역");
  });

  it("정규화 실패 시 원문 그대로 표시(미상 코드를 버리지 않음·정직)", () => {
    expect(zoneDisplayLabel("미상코드XYZ")).toBe("미상코드XYZ");
  });

  it("미확보(빈값/null): null", () => {
    expect(zoneDisplayLabel(null)).toBeNull();
    expect(zoneDisplayLabel("")).toBeNull();
    expect(zoneDisplayLabel("   ")).toBeNull();
  });
});

describe("deriveSitePipelineSteps — 후보지진단 분석 3단계 파생(무목업)", () => {
  it("siteAnalysis 없음: 3단계 전부 idle", () => {
    const steps = deriveSitePipelineSteps(null);
    expect(steps.map((s) => s.status)).toEqual(["idle", "idle", "idle"]);
  });

  it("주소만 확보(면적 미확보): collect=running(부분 수집 정직 표기)", () => {
    const steps = deriveSitePipelineSteps(sa({ address: "A" }));
    expect(steps[0].status).toBe("running");
    expect(steps[1].status).toBe("idle");
    expect(steps[2].status).toBe("idle");
  });

  it("주소+면적 확보: collect=done, verify/expert는 근거·해석 없으면 idle", () => {
    const steps = deriveSitePipelineSteps(sa({ address: "A", landAreaSqm: 500 }));
    expect(steps[0].status).toBe("done");
    expect(steps[1].status).toBe("idle");
    expect(steps[2].status).toBe("idle");
  });

  it("evidence 확보: verify=done", () => {
    const steps = deriveSitePipelineSteps(
      sa({ address: "A", landAreaSqm: 500, evidence: [{ claim: "far" }] }),
    );
    expect(steps[1].status).toBe("done");
  });

  it("legalRefs만 있어도 verify=done", () => {
    const steps = deriveSitePipelineSteps(
      sa({ address: "A", landAreaSqm: 500, legalRefs: [{ law: "건축법" }] }),
    );
    expect(steps[1].status).toBe("done");
  });

  it("specialParcel 확보: expert=done", () => {
    const steps = deriveSitePipelineSteps(
      sa({
        address: "A",
        landAreaSqm: 500,
        specialParcel: { isSpecial: true, developability: "POSSIBLE", resolvable: "YES", factors: [], honest: null },
      }),
    );
    expect(steps[2].status).toBe("done");
  });

  it("upzoningScenarios 확보: expert=done", () => {
    const steps = deriveSitePipelineSteps(
      sa({
        address: "A",
        landAreaSqm: 500,
        upzoningScenarios: [{ path: "준주거→일반상업", targetZone: null, feasibility: "중", expectedFarLowPct: null, expectedFarHighPct: null, legalBasis: null, rationale: null }],
      }),
    );
    expect(steps[2].status).toBe("done");
  });
});

describe("deriveFeasibilityPipelineSteps — 사업성검토 분석 3단계 파생(무목업)", () => {
  it("feasibilityData 없음: 3단계 전부 idle", () => {
    const steps = deriveFeasibilityPipelineSteps(null);
    expect(steps.map((s) => s.status)).toEqual(["idle", "idle", "idle"]);
  });

  it("매출만 확보(원가 미확보): collect=running", () => {
    const steps = deriveFeasibilityPipelineSteps(fd({ totalRevenueWon: 1000, totalCostWon: null }));
    expect(steps[0].status).toBe("running");
  });

  it("매출+원가 확보: collect=done", () => {
    const steps = deriveFeasibilityPipelineSteps(fd({ totalRevenueWon: 1000, totalCostWon: 800 }));
    expect(steps[0].status).toBe("done");
  });

  it("verify는 교차검증 트레이스 미보유로 항상 idle(날조 금지)", () => {
    const steps = deriveFeasibilityPipelineSteps(
      fd({ totalRevenueWon: 1000, totalCostWon: 800, grade: "A" }),
    );
    expect(steps[1].status).toBe("idle");
  });

  it("grade 확보: expert=done", () => {
    const steps = deriveFeasibilityPipelineSteps(fd({ grade: "A" }));
    expect(steps[2].status).toBe("done");
  });

  it("grade 미확보: expert=idle", () => {
    const steps = deriveFeasibilityPipelineSteps(fd({ totalRevenueWon: 1000, totalCostWon: 800 }));
    expect(steps[2].status).toBe("idle");
  });
});

describe("deriveMarketPipelineSteps — 시장분양리포트 분석 3단계 파생(무목업)", () => {
  it("보고서 생성 전: collect=idle", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: null, useLlm: true });
    expect(steps[0].status).toBe("idle");
  });

  it("생성 중(genState=report): collect=running", () => {
    const steps = deriveMarketPipelineSteps({ genState: "report", report: null, useLlm: true });
    expect(steps[0].status).toBe("running");
  });

  it("report 확보: collect=done", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: { narrative: null }, useLlm: true });
    expect(steps[0].status).toBe("done");
  });

  it("verify는 교차검증 트레이스 미보유로 항상 idle(날조 금지)", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: { narrative: { summary: "x" } }, useLlm: true });
    expect(steps[1].status).toBe("idle");
  });

  it("narrative 확보 + useLlm true: expert=done", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: { narrative: { summary: "x" } }, useLlm: true });
    expect(steps[2].status).toBe("done");
  });

  it("narrative 확보했지만 useLlm false: expert=idle + 정직배지(규칙 기반)", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: { narrative: { summary: "x" } }, useLlm: false });
    expect(steps[2].status).toBe("idle");
    expect(steps[2].honestBadge).toBe("규칙 기반(LLM 미실행)");
  });

  it("narrative 미확보: expert=idle", () => {
    const steps = deriveMarketPipelineSteps({ genState: "", report: { narrative: null }, useLlm: true });
    expect(steps[2].status).toBe("idle");
  });
});
