import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DesignWorkspace } from "@/components/design/DesignWorkspace";
import { useProjectContextStore, type DesignData, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

vi.mock("@/components/design/DesignStudio", () => ({
  DesignStudio: ({ onOpen3D }: { onOpen3D?: () => void }) => (
    <div>
      <span>mock site panel</span>
      <button type="button" onClick={onOpen3D}>
        mock open draw
      </button>
    </div>
  ),
}));

vi.mock("@/components/design/DesignGenPanel", () => ({
  DesignGenPanel: () => <div>mock design generation panel</div>,
}));

vi.mock("@/components/design/CadBimIntegrationPanel", () => ({
  CadBimIntegrationPanel: () => <div>mock cad bim panel</div>,
}));

vi.mock("@/components/design/MetricBar", () => ({
  MetricBar: () => <div>mock metric bar</div>,
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

function makeDesign(partial: Partial<DesignData>): DesignData {
  return {
    totalGfaSqm: null,
    floorCount: null,
    buildingType: null,
    bcr: null,
    far: null,
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

describe("DesignWorkspace", () => {
  beforeEach(() => {
    resetStores();
  });

  it("현 프로젝트와 다른 주소의 부지분석·설계값이 있으면 추천안과 CAD 패널을 차단한다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "경기도 성남시 분당구 정자동 178-1",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1200, floorCount: 8, far: 240 }),
    });

    render(<DesignWorkspace projectId="p1" />);

    expect(screen.getByText("주소 정합성 차단")).toBeInTheDocument();
    expect(screen.getByText(/정본 메트릭 잠금/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));
    expect(screen.getByText("현 프로젝트 기준 부지분석이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock design generation panel")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("도면 편집 전에 건축개요 추천안이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock cad bim panel")).not.toBeInTheDocument();
  });

  it("부지 기준은 맞지만 추천안이 없으면 생성 패널만 열고 CAD는 잠근다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
    });

    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));
    expect(screen.getByText("mock design generation panel")).toBeInTheDocument();
    expect(screen.getByText("mock metric bar")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("도면 편집 전에 건축개요 추천안이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock cad bim panel")).not.toBeInTheDocument();
  });

  it("현재 부지 기준 설계안이 있으면 CAD·BIM 편집실을 연다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1000, floorCount: 5, buildingType: "공동주택" }),
    });

    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("mock cad bim panel")).toBeInTheDocument();
  });
});
