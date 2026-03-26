import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectFinanceWorkspaceClient } from "@/components/projects/ProjectFinanceWorkspaceClient";
import { apiClient } from "@/lib/api-client";
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

describe("ProjectFinanceWorkspaceClient", () => {
  it("chains the live avm and jeonse-risk requests for the project route", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-finance-001",
      name: "Mapo Finance Asset",
      status: "planning",
      address: "Seoul Mapo-gu 100",
      total_area_sqm: 1450,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/avm") {
        return {
          id: "avm-001",
          project_id: "project-finance-001",
          estimated_price: 2400000000,
          price_per_sqm: 1655172,
          confidence_score: 0.82,
          comparable_count: 9,
          model_version: "v43-avm",
          created_at: "2026-03-22T02:00:00Z",
        };
      }

      if (path === "/finance/jeonse-risk") {
        return {
          jeonse_ratio: 0.75,
          risk_level: "MEDIUM",
          risk_score: 0.48,
          analysis: "The jeonse ratio remains below the highest-risk band.",
          factors: [
            {
              factor: "ratio-band",
              detail: "The ratio remains below 80 percent.",
            },
          ],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(
      <ProjectFinanceWorkspaceClient
        locale="en"
        projectId="project-finance-001"
      />,
    );

    expect(await screen.findByText("Mapo Finance Asset")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Run finance analysis" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenNthCalledWith(
        1,
        "/avm",
        expect.objectContaining({
          useMock: false,
        }),
      );
      expect(apiClient.post).toHaveBeenNthCalledWith(
        2,
        "/finance/jeonse-risk",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("MEDIUM")).toBeInTheDocument();
    expect(await screen.findByText("75.0%")).toBeInTheDocument();
    expect(
      await screen.findByText("The jeonse ratio remains below the highest-risk band."),
    ).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the route context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Finance project metadata unavailable");
      }

      return {
        id: "project-finance-retry-001",
        name: "Recovered Finance Asset",
        status: "planning",
        address: "Incheon Yeonsu-gu",
        total_area_sqm: 5100,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectFinanceWorkspaceClient
        locale="en"
        projectId="project-finance-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Finance project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Finance Asset")).toBeInTheDocument();
  });
});
