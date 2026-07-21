import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DesignStudio } from "@/components/design/DesignStudio";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";
import { renderWithQueryClient } from "@/test/render-with-query-client";

// SolarEnvelopeCard 등 자식 컴포넌트의 네트워크 호출을 격리(느린/불안정 테스트 방지).
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn().mockRejectedValue(new Error("network disabled in test")),
    post: vi.fn().mockRejectedValue(new Error("network disabled in test")),
    getRuntimeConfig: vi.fn().mockReturnValue({ apiBaseUrl: "http://localhost:8000/api/latest" }),
  },
}));

function makeProject(partial: Partial<Project>): Project {
  return {
    id: "p1",
    name: "테스트 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 강남구 역삼동 737",
    area: "500㎡",
    status: "design",
    createdAt: "2026-06-30T00:00:00.000Z",
    ...partial,
  };
}

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

function resetStores() {
  window.localStorage.clear();
  useProjectStore.setState({
    projects: [makeProject({})],
    syncing: false,
  });
  useProjectContextStore.setState({
    projectId: "p1",
    projectName: "테스트 프로젝트",
    projectStatus: "design",
    completedStages: [],
    currentStage: null,
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    analysisResults: [],
    snapshots: {},
    updatedAt: {},
    analysisCache: {},
    manualFields: {},
    parcelEnrichPending: false,
    decisionBrief: null,
  });
}

// 설계스튜디오 실효FAR 전파 봉합 회귀 테스트 — 공용 리졸버(zoning-ssot.resolveFarWithBasis)가
// ordinance.effectiveFar(조례·구조상한 실효 — 예: 자연녹지 건폐20%×4층=80%)를 4번째 계층으로
// 흡수한 뒤, DesignStudio의 자동계산(calc)·designData 기록이 이를 그대로 반영해야 한다.
// 종전엔 이 값이 "지역 실측 전형 매스 비교" 카드(seedEffectiveFarPct)에만 반영되고, calc·
// designData·하류(MetricBar·CAD/BIM)는 법정상한(자연녹지 100%)으로 낙하했다.
describe("DesignStudio — ordinance.effectiveFar(조례·구조상한 실효) 전파(설계스튜디오 실효FAR 봉합)", () => {
  beforeEach(() => {
    resetStores();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("ordinance.effectiveFar만 있고 다른 실효 계층이 없으면 designData.far·farIsEffective가 그 값을 반영한다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "자연녹지지역",
        ordinance: {
          sido: "서울특별시",
          sigungu: "강남구",
          nationalBcr: null,
          nationalFar: null,
          ordinanceBcr: null,
          ordinanceFar: null,
          effectiveBcr: 20,
          effectiveFar: 80,
          source: "구조상한(건폐율×층수)",
          legalBasis: "",
        },
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.far).toBe(80);
    });
    expect(useProjectContextStore.getState().designData?.farIsEffective).toBe(true);
    // 화면(자동계산 칩)도 같은 80%를 보여준다 — "매스카드에만 80% 반영" 결함의 회귀 방지.
    expect(await screen.findAllByText("80%")).not.toHaveLength(0);
  });

  it("실효 계층이 전혀 없으면(법정상한만) designData.farIsEffective=false로 정직 표기한다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.totalGfaSqm).not.toBeNull();
    });
    expect(useProjectContextStore.getState().designData?.farIsEffective).toBe(false);
  });

  it("★R1 P2 회귀앵커: nationalFarPct만 있으면(리졸버가 값을 돌려줘도 basis=national) farIsEffective=false", async () => {
    // 종전 술어(effFarPct != null)는 이 케이스에서 true 를 반환해 법정폴백을 '실효'로 오표기했다
    // (CadBim/seed 의 basis!=="national" 술어와 같은 부지 상반 라벨). basis 기준 통일 회귀 고정.
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "자연녹지지역",
        nationalFarPct: 100,
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.totalGfaSqm).not.toBeNull();
    });
    expect(useProjectContextStore.getState().designData?.farIsEffective).toBe(false);
  });

  it("다필지(parcels.length>1)면 ordinance 계층을 건너뛰어 법정상한으로 정직 강등한다(대표필지 오염 방지)", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "자연녹지지역",
        parcelCount: 2,
        parcels: [
          { pnu: "1", address: "1", areaSqm: 250, landCategory: "대", ownerType: "개인" },
          { pnu: "2", address: "2", areaSqm: 250, landCategory: "대", ownerType: "개인" },
        ],
        ordinance: {
          sido: "서울특별시",
          sigungu: "강남구",
          nationalBcr: null,
          nationalFar: null,
          ordinanceBcr: null,
          ordinanceFar: null,
          effectiveBcr: 20,
          effectiveFar: 80,
          source: "구조상한(건폐율×층수)",
          legalBasis: "",
        },
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.totalGfaSqm).not.toBeNull();
    });
    // 다필지에서는 대표 1필지 유래 ordinance 계층이 무시돼 법정상한(100%)으로 강등된다.
    expect(useProjectContextStore.getState().designData?.far).toBe(100);
    expect(useProjectContextStore.getState().designData?.farIsEffective).toBe(false);
  });
});
