import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectDesignWorkspaceClient } from "@/components/projects/ProjectDesignWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { useGenerationStore } from "@/store/useGenerationStore";
import { renderWithQueryClient } from "@/test/render-with-query-client";

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;

    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiClient: {
    getRuntimeConfig: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
}));

// 클라이언트 컴포넌트(useDictionary 훅)의 로딩 게이트(`if (!dictionary)`)를 통과시키기 위해
// 동기 로드된 사전을 주입한다. 위저드/콘솔이 참조하는 pages.generation 키만 채운다.
const { DICT } = vi.hoisted(() => ({
  DICT: {
    pages: {
      generation: {
        title: "AI Design & Project Generation Sets",
        residential: "Residential Studio Set",
        logistics: "Logistics Hub Set",
        ecoOffice: "Eco-Green Office Set",
        inputsTitle: "Set Parameters",
        startAction: "Launch AI Generation",
        runningAction: "Generating AI Assets...",
        unitsLabel: "Target Units",
        parkingLabel: "Parking Ratio",
        efficiencyLabel: "Target Efficiency",
        docksLabel: "Dock Count",
        loadLabel: "Floor Load Capacity",
        clearHeightLabel: "Clear Height",
        rampLabel: "Ramp Type",
        pvRatioLabel: "Solar PV Ratio",
        insulationLabel: "Insulation Grade",
        leedLabel: "Target LEED Rating",
        structureType: "Structure Type",
        styleLabel: "Design Style",
        rampSpiral: "Spiral Ramp",
        rampLinear: "Linear Ramp",
        leedSilver: "LEED Silver",
        leedGold: "LEED Gold",
        leedPlatinum: "LEED Platinum",
        insulationGrade: "Grade {grade} (Premium)",
        terminalTitle: "Harness Engineering Live Telemetry Console",
        terminalReady: "AI automation orchestrator standing by...",
        activeEngine: "Active AI Module",
      },
    },
  },
}));

vi.mock("@/hooks/use-dictionary", () => ({
  useDictionary: () => ({ dictionary: DICT, isLoading: false }),
}));

afterEach(() => {
  // zustand 스토어는 모듈 싱글톤이라 테스트 간 상태가 누수된다 — 명시적으로 초기화.
  act(() => {
    useGenerationStore.getState().resetStore();
  });
});

describe("ProjectDesignWorkspaceClient", () => {
  it("renders the live project context, the generation wizard, and store-driven deliverables", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-design-001",
      name: "Songdo Design Hub",
      status: "design",
      address: "Incheon Songdo",
      total_area_sqm: 9800,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    renderWithQueryClient(
      <ProjectDesignWorkspaceClient
        locale="en"
        projectId="project-design-001"
      />,
    );

    // 라이브 프로젝트 메타데이터가 컨텍스트 카드에 렌더된다.
    expect(await screen.findByText("Songdo Design Hub")).toBeInTheDocument();

    // 라이브 모드 뱃지와 프로젝트 메타(주소)가 사용자에게 노출된다.
    expect(screen.getByText("LIVE ENGINE")).toBeInTheDocument();
    expect(screen.getByText("Incheon Songdo")).toBeInTheDocument();

    // 직접 floor-plan/IFC API POST 버튼이 아니라, 위저드 제출 액션이 생성 파이프라인을 구동한다.
    expect(
      screen.getByRole("button", { name: "Launch AI Generation" }),
    ).toBeInTheDocument();

    // 컴포넌트는 라이브 프로젝트 조회만 수행하고, 생성은 스토어가 담당한다(직접 POST 없음).
    expect(apiClient.get).toHaveBeenCalledWith("/projects/project-design-001", {
      useMock: false,
    });
    expect(apiClient.post).not.toHaveBeenCalled();

    // 생성 파이프라인(브라우저 내 시뮬레이션)이 완료되면 스토어 results가 채워지고,
    // 합성 산출물(IFC 버전·BIM 수량·탄소 저감 권고안)이 컴포넌트에 렌더된다.
    const reductionTip = "Reduce concrete intensity in the wall package.";
    act(() => {
      useGenerationStore.setState({
        status: "success",
        isGenerating: false,
        results: {
          cadFloorPlanUrl: "https://cdn.example.com/design-001.png",
          ifcFileUrl: "https://cdn.example.com/design-001.ifc",
          totalVolumeM3: 12450.5,
          totalAreaSqm: 9800,
          elementCount: 160,
          ifcVersion: "IFC4_ADD2",
          totalCarbon: 1920000,
          embodiedCarbon: 420000,
          operationalCarbon: 1500000,
          estimatedCost: 25000000000,
          feasibilityScore: 82,
          reductionTips: [reductionTip],
        },
      });
    });

    expect(await screen.findByText("IFC4_ADD2")).toBeInTheDocument();
    expect(screen.getByText(reductionTip)).toBeInTheDocument();
    expect(screen.getByText("82 / 100")).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the design context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Design project metadata unavailable");
      }

      return {
        id: "project-design-retry-001",
        name: "Recovered Design Hub",
        status: "design",
        address: "Daejeon",
        total_area_sqm: 8700,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectDesignWorkspaceClient
        locale="en"
        projectId="project-design-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Design project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Design Hub")).toBeInTheDocument();
  });
});
