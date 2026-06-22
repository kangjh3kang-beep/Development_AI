import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsOverviewClient } from "@/components/projects/ProjectsOverviewClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";
import { useProjectStore as useProjectListStore } from "@/store/useProjectStore";

// 컴포넌트는 백엔드 동기화 스토어(useProjectStore from @/store/useProjectStore)를
// 통해 apiClient.get("/projects")를 호출하고 응답을 { items: BackendProject[] } 로
// 파싱한다. 따라서 mock은 get/post/delete 표면을 모두 제공해야 한다.
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const LABELS = {
  viewGridLabel: "Grid view",
  viewListLabel: "List view",
  selectProjectLabel: "Select project",
  selectedLabel: "Selected",
  lastUpdatedLabel: "Last updated",
  nextActionLabel: "Next action",
  modulesLabel: "Modules",
  openProjectLabel: "Open project",
  emptyStateTitle: "No projects yet",
  emptyStateDescription:
    "Create or sync a project to populate the live portfolio view.",
  errorStateTitle: "Project list is unavailable",
  errorStateDescription:
    "The live project list could not be loaded. Check the API connection and try again.",
  retryLabel: "Retry",
};

const MODULE_LABELS = {
  design: "Design",
  bim: "BIM",
  finance: "Finance",
  drone: "Drone",
  blockchain: "Blockchain",
  report: "Report",
  tax: "Tax",
  inspection: "Inspection",
};

// 백엔드 응답 형상: { items: BackendProject[] } (store._mapBackend가 소비).
// 컴포넌트는 카드의 modules를 항상 ["design","finance","report"]로 고정 렌더하고
// location은 address(+ 다필지 표기), name은 p.name을 그대로 보여준다.
const PROJECTS_RESPONSE = {
  items: [
    {
      id: "project-001",
      name: "Mapo Growth Center",
      status: "planning",
      address: "Seoul Mapo-gu",
      total_area_sqm: 1200,
      building_type: "office",
      created_at: "2026-03-22T02:00:00Z",
    },
    {
      id: "project-002",
      name: "Yeoksam Office Loop",
      status: "construction",
      address: "Seoul Gangnam-gu",
      total_area_sqm: 2400,
      building_type: "office",
      created_at: "2026-03-22T01:00:00Z",
    },
  ],
};

const EMPTY_PROJECTS_RESPONSE = { items: [] };

function resetListStore() {
  act(() => {
    useProjectListStore.setState({ projects: [], syncing: false });
  });
}

describe("ProjectsOverviewClient", () => {
  beforeEach(() => {
    resetListStore();
    act(() => {
      useAppStore.setState({ projectViewMode: "grid" });
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    resetListStore();
    act(() => {
      useAppStore.setState({ projectViewMode: "grid" });
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  it("shows skeleton cards while the project list sync is pending", async () => {
    let resolveProjects: (value: typeof PROJECTS_RESPONSE) => void = () => {};

    vi.mocked(apiClient.get).mockReturnValue(
      new Promise<typeof PROJECTS_RESPONSE>((resolve) => {
        resolveProjects = resolve;
      }),
    );

    const { container } = renderWithQueryClient(
      <ProjectsOverviewClient
        locale="en"
        labels={LABELS}
        moduleLabels={MODULE_LABELS}
      />,
    );

    // SkeletonLoader count={4} → 4개의 .animate-pulse 스켈레톤이 sync 중 노출된다.
    await waitFor(() => {
      expect(container.querySelectorAll(".animate-pulse")).toHaveLength(4);
    });

    act(() => {
      resolveProjects(PROJECTS_RESPONSE);
    });

    await screen.findByText("Mapo Growth Center");
  });

  it("renders live project cards and switches from grid to list view", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(PROJECTS_RESPONSE);

    const { container } = renderWithQueryClient(
      <ProjectsOverviewClient
        locale="en"
        labels={LABELS}
        moduleLabels={MODULE_LABELS}
      />,
    );

    expect(await screen.findByText("Mapo Growth Center")).toBeInTheDocument();
    expect(screen.getByText("Yeoksam Office Loop")).toBeInTheDocument();
    // "Last updated" 라벨이 각 카드의 메타 행에 노출된다(헤더 메타 + 카드들 = 다중 매칭).
    expect(screen.getAllByText("Last updated").length).toBeGreaterThan(0);
    // 카드 modules는 ["design","finance","report"]로 고정 → 라벨 Design/Finance/Report.
    expect(screen.getAllByText("Design").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finance").length).toBeGreaterThan(0);

    const listButton = screen.getByRole("button", { name: "List view" });
    act(() => {
      listButton.click();
    });

    await waitFor(() => {
      expect(useAppStore.getState().projectViewMode).toBe("list");
      // 활성 뷰 버튼은 accent-strong 배경 + 흰 글자로 강조된다.
      expect(listButton.className).toContain("bg-[var(--accent-strong)]");
      expect(listButton.className).toContain("text-white");
    });

    // 리스트 뷰에서는 grid 컬럼 클래스가 사라진다.
    expect(container.querySelector(".md\\:grid-cols-2")).toBeNull();
  });

  it("marks the selected project and links to the routed site-analysis page", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(PROJECTS_RESPONSE);

    renderWithQueryClient(
      <ProjectsOverviewClient
        locale="en"
        labels={LABELS}
        moduleLabels={MODULE_LABELS}
      />,
    );

    expect(await screen.findByText("Mapo Growth Center")).toBeInTheDocument();

    act(() => {
      screen.getAllByRole("button", { name: "Select project" })[0]!.click();
    });

    await waitFor(() => {
      expect(useProjectStore.getState().currentProjectId).toBe("project-001");
      expect(useProjectStore.getState().recentProjectIds).toEqual([
        "project-001",
      ]);
      expect(screen.getByText("Selected")).toBeInTheDocument();
    });

    // "Open project"는 라우팅된 부지분석 진입점으로 연결된다.
    expect(
      screen.getAllByRole("link", { name: /Open project/ })[0],
    ).toHaveAttribute("href", "/en/projects/project-001/site-analysis");
  });

  it("renders an empty-state card when the project list is empty", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(EMPTY_PROJECTS_RESPONSE);

    renderWithQueryClient(
      <ProjectsOverviewClient
        locale="en"
        labels={LABELS}
        moduleLabels={MODULE_LABELS}
      />,
    );

    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Create or sync a project to populate the live portfolio view.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select project" })).toBeNull();
  });

  it("keeps the view resilient when the sync fails and recovers on the next sync", async () => {
    // 동기화 스토어는 실패 시 마지막 정상 목록을 유지하고 throw하지 않는다(오프라인 내성).
    // 따라서 첫 sync 실패 시 빈 상태가 노출되고, 회복 후 재동기화하면 카드가 채워진다.
    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(new Error("Projects API offline"))
      .mockResolvedValueOnce(PROJECTS_RESPONSE);

    renderWithQueryClient(
      <ProjectsOverviewClient
        locale="en"
        labels={LABELS}
        moduleLabels={MODULE_LABELS}
      />,
    );

    // 실패해도 크래시 없이 빈 상태 카드가 렌더된다.
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledTimes(1);

    // 백엔드 회복 후 재동기화 → 라이브 카드가 채워진다.
    await act(async () => {
      await useProjectListStore.getState().syncFromBackend();
    });

    expect(await screen.findByText("Mapo Growth Center")).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });
});
