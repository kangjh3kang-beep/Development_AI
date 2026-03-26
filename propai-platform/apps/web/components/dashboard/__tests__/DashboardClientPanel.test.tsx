import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardClientPanel } from "@/components/dashboard/DashboardClientPanel";
import { apiClient } from "@/lib/api-client";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";
import { renderWithQueryClient } from "@/test/render-with-query-client";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    getRuntimeConfig: vi.fn(),
    get: vi.fn(),
  },
}));

const LABELS = {
  connectionTitle: "Connections",
  sourceLabel: "Sources",
  onlineLabel: "Online",
  offlineLabel: "Offline",
  featuredProjectLabel: "Featured project",
  openProjectLabel: "Open project",
  integrationRestLabel: "REST API",
  integrationGraphqlLabel: "GraphQL",
  integrationRealtimeLabel: "Realtime stream",
  modeMock: "Mock",
  modeLive: "Live",
  modeWaiting: "Waiting",
};

describe("DashboardClientPanel", () => {
  beforeEach(() => {
    act(() => {
      useAppStore.setState({
        online: true,
        restMode: "mock",
        graphqlEnabled: false,
        realtimeConnected: false,
      });
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
      useAppStore.setState({
        online: true,
        restMode: "mock",
        graphqlEnabled: false,
        realtimeConnected: false,
      });
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  it("renders mock dashboard data, uses the mock integration status, and stores the featured project", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: true,
      hasAccessToken: false,
      mode: "mock",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/dashboard/overview") {
        return {
          metrics: [
            { id: "m1", label: "Projects", value: "12" },
            { id: "m2", label: "AI budget", value: "$240.00" },
          ],
          featuredProjectId: "mock-project-001",
        };
      }

      if (path === "/integration/status") {
        return {
          channels: [
            {
              id: "rest",
              label: "REST",
              mode: "mock",
              detail: "Mock REST adapter",
            },
            {
              id: "graphql",
              label: "GraphQL",
              mode: "live",
              detail: "GraphQL is connected",
            },
            {
              id: "realtime",
              label: "Realtime",
              mode: "waiting",
              detail: "Realtime stream is warming up",
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(
      <DashboardClientPanel
        locale="en"
        summaryTitle="Summary panel"
        labels={LABELS}
      />,
    );

    expect(await screen.findByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("$240.00")).toBeInTheDocument();
    expect(screen.getByText("Mock REST adapter")).toBeInTheDocument();
    expect(screen.getByText("GraphQL is connected")).toBeInTheDocument();
    expect(screen.getByText("Realtime stream is warming up")).toBeInTheDocument();
    expect(screen.getByText("mock-project-001")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open project" })).toHaveAttribute(
      "href",
      "/en/projects/mock-project-001",
    );

    await waitFor(() => {
      expect(useProjectStore.getState().currentProjectId).toBe("mock-project-001");
      expect(useAppStore.getState().restMode).toBe("mock");
      expect(useAppStore.getState().graphqlEnabled).toBe(true);
      expect(useAppStore.getState().realtimeConnected).toBe(false);
    });
  });

  it("renders live dashboard summaries and live integration health when the workspace is in live mode", async () => {
    act(() => {
      useProjectStore.setState({
        currentProjectId: "live-project-777",
        recentProjectIds: ["live-project-777"],
        activeModule: null,
      });
      useAppStore.setState({
        online: false,
        restMode: "mock",
        graphqlEnabled: false,
        realtimeConnected: false,
      });
    });

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/dashboard/stats") {
        return {
          total_projects: 21,
          active_webhooks: 6,
          active_api_keys: 4,
          ai_cost_month_usd: 1243.56,
          ai_tokens_month: 880000,
          projects_by_status: {
            planning: 7,
            execution: 9,
            completed: 5,
          },
        };
      }

      if (path === "/system/version") {
        return {
          app_name: "PropAI API",
          version: "30.0.0",
          environment: "production",
          api_prefixes: ["/api/v1", "/api/latest"],
        };
      }

      if (path === "/system/health/full") {
        return {
          status: "healthy",
          version: "30.0.0",
          environment: "production",
          services: {
            qdrant: "healthy",
            redis: "healthy",
          },
          checked_at: "2026-03-22T11:00:00Z",
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(
      <DashboardClientPanel
        locale="en"
        summaryTitle="Summary panel"
        labels={LABELS}
      />,
    );

    expect(await screen.findByText("21")).toBeInTheDocument();
    expect(screen.getByText("$1243.56")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("PropAI API 30.0.0 (production)")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Hasura live binding is still pending in the dashboard workspace.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Realtime dependencies are reachable for websocket and streaming modules.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(screen.getByText("live-project-777")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open project" })).toHaveAttribute(
      "href",
      "/en/projects/live-project-777",
    );

    await waitFor(() => {
      expect(useAppStore.getState().restMode).toBe("live");
      expect(useAppStore.getState().graphqlEnabled).toBe(false);
      expect(useAppStore.getState().realtimeConnected).toBe(true);
    });
  });

  it("renders dashboard and integration fallback cards when live queries fail", async () => {
    let shouldFailDashboard = true;
    let shouldFailVersion = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/dashboard/stats") {
        if (shouldFailDashboard) {
          throw new Error("Dashboard stats unavailable");
        }

        return {
          total_projects: 18,
          active_webhooks: 5,
          active_api_keys: 3,
          ai_cost_month_usd: 802.25,
          ai_tokens_month: 540000,
          projects_by_status: {
            planning: 6,
            execution: 8,
            completed: 4,
          },
        };
      }

      if (path === "/system/version") {
        if (shouldFailVersion) {
          throw new Error("System version unavailable");
        }

        return {
          app_name: "PropAI API",
          version: "30.0.0",
          environment: "production",
          api_prefixes: ["/api/v1", "/api/latest"],
        };
      }

      if (path === "/system/health/full") {
        return {
          status: "healthy",
          version: "30.0.0",
          environment: "production",
          services: {
            qdrant: "healthy",
            redis: "healthy",
          },
          checked_at: "2026-03-22T11:00:00Z",
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(
      <DashboardClientPanel
        locale="en"
        summaryTitle="Summary panel"
        labels={LABELS}
      />,
    );

    expect(
      await screen.findByText("Live dashboard data is unavailable."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The dashboard summary query failed. Retry after restoring API connectivity or access token state.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Dashboard stats unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Integration status is unavailable."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The live integration health query failed. Retry after restoring API connectivity or access token state.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("System version unavailable")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(2);
    expect(screen.getByText("sample-project")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open project" })).toHaveAttribute(
      "href",
      "/en/projects/sample-project",
    );

    shouldFailDashboard = false;
    shouldFailVersion = false;

    const [retryOverview, retryIntegration] = screen.getAllByRole("button", {
      name: "Retry",
    });

    await userEvent.click(retryOverview);
    await userEvent.click(retryIntegration);

    expect(await screen.findByText("18")).toBeInTheDocument();
    expect(await screen.findByText("$802.25")).toBeInTheDocument();
    expect(
      await screen.findByText("PropAI API 30.0.0 (production)"),
    ).toBeInTheDocument();
  });
});
