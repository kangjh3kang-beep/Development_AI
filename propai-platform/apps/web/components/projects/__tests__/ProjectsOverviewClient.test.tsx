import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectsOverviewClient } from "@/components/projects/ProjectsOverviewClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
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
  emptyStateDescription: "Create or sync a project to populate the live portfolio view.",
  errorStateTitle: "Project list is unavailable",
  errorStateDescription: "The live project list could not be loaded. Check the API connection and try again.",
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

const PROJECTS_RESPONSE = {
  total: 2,
  updatedAt: "2026-03-22T03:00:00Z",
  projects: [
    {
      id: "project-001",
      name: "Mapo Growth Center",
      location: "Seoul Mapo-gu",
      phase: "planning",
      updatedAt: "2026-03-22T02:00:00Z",
      nextAction: "Review underwriting memo",
      modules: ["design", "finance", "report"] as const,
    },
    {
      id: "project-002",
      name: "Yeoksam Office Loop",
      location: "Seoul Gangnam-gu",
      phase: "execution",
      updatedAt: "2026-03-22T01:00:00Z",
      nextAction: "Run drone inspection",
      modules: ["drone", "inspection", "bim"] as const,
    },
  ],
};

const EMPTY_PROJECTS_RESPONSE = {
  total: 0,
  updatedAt: "2026-03-22T03:30:00Z",
  projects: [],
};

describe("ProjectsOverviewClient", () => {
  beforeEach(() => {
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
    act(() => {
      useAppStore.setState({ projectViewMode: "grid" });
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  it("shows skeleton cards while the project list query is pending", async () => {
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

    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(3);

    resolveProjects(PROJECTS_RESPONSE);

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
    expect(
      screen.getAllByText(
        (_, element) => element?.textContent?.startsWith("Last updated:") ?? false,
      ),
    ).not.toHaveLength(0);
    expect(screen.getByText("Design")).toBeInTheDocument();
    expect(screen.getByText("Inspection")).toBeInTheDocument();

    const listButton = screen.getByRole("button", { name: "List view" });
    act(() => {
      listButton.click();
    });

    await waitFor(() => {
      expect(useAppStore.getState().projectViewMode).toBe("list");
      expect(listButton.className).toContain("bg-[var(--foreground)]");
    });

    expect(container.querySelector(".md\\:grid-cols-2")).toBeNull();
  });

  it("marks the selected project and links to the routed project detail page", async () => {
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

    expect(
      screen.getAllByRole("link", { name: "Open project" })[0],
    ).toHaveAttribute("href", "/en/projects/project-001");
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

  it("renders an error-state card and retries loading the project list", async () => {
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

    expect(
      await screen.findByText("Project list is unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The live project list could not be loaded. Check the API connection and try again.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Projects API offline")).toBeInTheDocument();

    act(() => {
      screen.getByRole("button", { name: "Retry" }).click();
    });

    expect(await screen.findByText("Mapo Growth Center")).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });
});
