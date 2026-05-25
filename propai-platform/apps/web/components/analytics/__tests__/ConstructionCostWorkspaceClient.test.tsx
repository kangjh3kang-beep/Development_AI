import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConstructionCostWorkspaceClient } from "@/components/analytics/ConstructionCostWorkspaceClient";
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

describe("ConstructionCostWorkspaceClient", () => {
  it("renders live material and escalation data", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-001",
              name: "Songdo Smart Yard",
              status: "planning",
              total_area_sqm: 4200,
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path.startsWith("/cost-intelligence/material-prices/latest")) {
        return {
          as_of: "2026-03-25T00:00:00Z",
          region_code: "KR",
          items: [
            {
              material_code: "ready_mix_concrete",
              material_name: "Ready-mix concrete 25-240-15",
              current_unit_price_krw: 108000,
              latest_price_index: 114.3,
              mom_change_ratio: 0.028,
              yoy_change_ratio: 0.082,
              estimated_project_cost_krw: 195000000,
              alert_level: "normal",
              history: [{ source_name: "kcci-simulated" }],
            },
          ],
          alerts: [],
        };
      }

      if (path === "/cost-intelligence/escalation/project-001/latest") {
        return {
          adjusted_cost_krw: 20125000000,
          overall_escalation_ratio: 0.088,
          ppi_source: "ecos-simulated",
          summary: "Songdo Smart Yard cost projection escalates into the target year.",
          material_impacts: [
            {
              material_code: "ready_mix_concrete",
              material_name: "Ready-mix concrete 25-240-15",
              weight_ratio: 0.29,
              delta_ratio: 0.143,
              cost_impact_krw: 514000000,
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<ConstructionCostWorkspaceClient locale="ko" />);

    expect(
      await screen.findByText("KCCI 자재가와 PPI 공사비 보정 시뮬레이션"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Songdo Smart Yard")).toBeInTheDocument();
    expect(
      (await screen.findAllByText("Ready-mix concrete 25-240-15")).length,
    ).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Songdo Smart Yard cost projection/i),
    ).toBeInTheDocument();
  });

  it("submits refresh and analysis actions", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-002",
              name: "Yeouido Prime",
              status: "planning",
              total_area_sqm: 3200,
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path.startsWith("/cost-intelligence/material-prices/latest")) {
        return { as_of: "2026-03-25T00:00:00Z", region_code: "KR", items: [], alerts: [] };
      }

      if (path === "/cost-intelligence/escalation/project-002/latest") {
        return {
          adjusted_cost_krw: 19300000000,
          overall_escalation_ratio: 0.043,
          ppi_source: "ecos-simulated",
          summary: "Yeouido Prime baseline scenario is available.",
          material_impacts: [],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/cost-intelligence/material-prices/refresh") {
        return {
          as_of: "2026-03-25T00:00:00Z",
          region_code: "KR",
          items: [
            {
              material_code: "rebar_sd400_d13",
              material_name: "Rebar SD400 D13",
              current_unit_price_krw: 921000,
              latest_price_index: 108.6,
              mom_change_ratio: 0.021,
              yoy_change_ratio: 0.064,
              estimated_project_cost_krw: 88000000,
              alert_level: "normal",
              history: [{ source_name: "kcci-simulated" }],
            },
          ],
          alerts: [],
        };
      }

      if (path === "/cost-intelligence/escalation/analyze") {
        return {
          adjusted_cost_krw: 19840000000,
          overall_escalation_ratio: 0.072,
          ppi_source: "ecos-simulated",
          summary: "Yeouido Prime has a manageable escalation profile.",
          material_impacts: [
            {
              material_code: "rebar_sd400_d13",
              material_name: "Rebar SD400 D13",
              weight_ratio: 0.24,
              delta_ratio: 0.086,
              cost_impact_krw: 273000000,
            },
          ],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<ConstructionCostWorkspaceClient locale="ko" />);

    await screen.findByText("Yeouido Prime");

    const buttons = await screen.findAllByRole("button");
    const refreshBtn = buttons.find((button) => button.textContent?.includes("자재가"));
    const analyzeBtn = buttons.find((button) => button.textContent?.includes("에스컬레이션"));
    
    if (!refreshBtn || !analyzeBtn) {
       throw new Error("Could not find refresh or analyze buttons");
    }

    await userEvent.click(refreshBtn);
    await userEvent.click(analyzeBtn);

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/cost-intelligence/material-prices/refresh",
        expect.objectContaining({ useMock: false }),
      );
      expect(apiClient.post).toHaveBeenCalledWith(
        "/cost-intelligence/escalation/analyze",
        expect.objectContaining({ useMock: false }),
      );
    });

    expect((await screen.findAllByText("Rebar SD400 D13")).length).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Yeouido Prime has a manageable escalation profile/i),
    ).toBeInTheDocument();
  });
});
