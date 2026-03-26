import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import { apiClient } from "@/lib/api-client";

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

describe("OperationsIntelligenceWorkspaceClient", () => {
  it("renders only the requested maintenance section", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-ops-001",
          name: "Yongsan Smart Office",
          status: "operations",
          address: "Seoul Yongsan-gu",
          total_area_sqm: 8200,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient
        locale="en"
        sections={["maintenance"]}
        showHero={false}
      />,
    );

    expect(
      await screen.findByRole("button", { name: "Run maintenance analysis" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Tenant experience")).not.toBeInTheDocument();
    expect(screen.queryByText("Asset intelligence")).not.toBeInTheDocument();
  });

  it("submits asset intelligence analysis in the combined workspace", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-ops-002",
          name: "Bundang Prime Tower",
          status: "operations",
          address: "Seongnam Bundang-gu",
          total_area_sqm: 9200,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/digital-twin/asset-intelligence") {
        return {
          snapshot_id: "snapshot-001",
          project_id: "project-ops-002",
          composite_score: 84.2,
          grade: "B",
          adjusted_value_krw: 20150000000,
          component_scores: {
            maintenance: 78.1,
            tenant: 81.2,
            market: 88.5,
            climate: 79.0,
          },
          capex_recommendations: [
            {
              strategy_name: "HVAC reliability retrofit",
              expected_roi: 0.16,
              payback_months: 24,
            },
          ],
          created_at: "2026-03-22T00:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient locale="en" />,
    );

    expect(
      await screen.findByText("Operations intelligence workspace"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Run asset analysis" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/digital-twin/asset-intelligence",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("84.20")).toBeInTheDocument();
    expect(await screen.findByText("HVAC reliability retrofit")).toBeInTheDocument();
  });

  it("renders the project query error state and retries the live picker", async () => {
    let shouldFailProjects = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProjects) {
        throw new Error("Operations projects unavailable");
      }

      return {
        items: [
          {
            id: "project-ops-retry-001",
            name: "Recovered Operations Hub",
            status: "operations",
            address: "Daegu",
            total_area_sqm: 6400,
            updated_at: "2026-03-22T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient
        locale="en"
        sections={["maintenance"]}
        showHero={false}
      />,
    );

    expect(
      await screen.findByText("Project list unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Operations projects unavailable"),
    ).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("project-ops-retry-001")).toBeInTheDocument();
  });
});
