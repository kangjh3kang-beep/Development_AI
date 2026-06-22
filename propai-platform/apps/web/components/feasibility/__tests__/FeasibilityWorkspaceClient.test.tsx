import type { ReactNode } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FeasibilityWorkspaceClient } from "@/components/feasibility/FeasibilityWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="recharts-responsive">{children}</div>
  ),
  BarChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="recharts-bar-chart">{children}</div>
  ),
  CartesianGrid: () => null,
  Legend: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Bar: () => null,
}));

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
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("FeasibilityWorkspaceClient", () => {
  it("renders the latest feasibility snapshot and runs a local DCF scenario", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-001",
              name: "Mapo Feasibility One",
              status: "planning",
              address: "Seoul Mapo-gu",
              total_area_sqm: 4200,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/finance/feasibility/project-001/latest") {
        return {
          id: "analysis-001",
          project_id: "project-001",
          scenario_name: "stored-case",
          npv: 1200000000,
          irr: 0.118,
          payback_period_months: 72,
          total_investment_krw: 1500000000,
          total_revenue_krw: 3100000000,
          risk_score: 0.31,
          discount_rate: 0.05,
          annual_growth_rate: 0.02,
          analysis_years: 10,
          exit_value_krw: 1800000000,
          cashflows: [
            {
              year: 1,
              revenue_krw: 280000000,
              operating_cost_krw: 95000000,
              net_cashflow_krw: 185000000,
              discounted_cashflow_krw: 176190476.19,
            },
          ],
          assumptions: {},
          created_at: "2026-03-23T00:00:00Z",
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<FeasibilityWorkspaceClient />);

    expect(await screen.findByText("Feasibility and LCC")).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Mapo Feasibility One" })).toBeInTheDocument();
    // The persisted snapshot (npv 1,200,000,000) is rendered from the latest read model.
    expect(await screen.findByText(/₩1,200,000,000/)).toBeInTheDocument();

    // "Run live feasibility" performs a deterministic local DCF computation from the
    // default scenario inputs — it does not call the feasibility POST endpoint.
    await userEvent.click(screen.getByRole("button", { name: "Run live feasibility" }));

    // Locally computed report replaces the persisted snapshot: NPV ₩1,189,301,076,
    // payback 96 months derived from DEFAULT_FORM (10 years, 0.05 discount, 0.02 growth).
    expect(await screen.findByText(/₩1,189,301,076/)).toBeInTheDocument();
    expect(await screen.findByText("96m")).toBeInTheDocument();
    expect(screen.getByTestId("recharts-responsive")).toBeInTheDocument();

    // The current component computes locally and never posts to the feasibility API.
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("renders the project query error state and retries the live picker", async () => {
    let shouldFailProjects = true;

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path !== "/projects?page=1&page_size=20") {
        throw new Error(`Unhandled GET path: ${path}`);
      }

      if (shouldFailProjects) {
        throw new Error("Feasibility projects unavailable");
      }

      return {
        items: [
          {
            id: "project-002",
            name: "Recovered Feasibility Tower",
            status: "planning",
            address: "Busan",
            total_area_sqm: 3800,
            updated_at: "2026-03-23T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(<FeasibilityWorkspaceClient />);

    expect(await screen.findByText("Project list unavailable")).toBeInTheDocument();
    expect(
      await screen.findByText("Feasibility projects unavailable"),
    ).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByRole("option", { name: "Recovered Feasibility Tower" }),
    ).toBeInTheDocument();
  });
});
