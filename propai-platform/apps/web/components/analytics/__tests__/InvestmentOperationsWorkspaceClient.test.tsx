import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InvestmentOperationsWorkspaceClient } from "@/components/analytics/InvestmentOperationsWorkspaceClient";
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

describe("InvestmentOperationsWorkspaceClient", () => {
  it("renders live metrics and saves a budget gate", async () => {
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
              name: "Mapo Prime Asset",
              status: "planning",
              address: "Seoul Mapo-gu",
              total_area_sqm: 2450,
              updated_at: "2026-03-22T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/ai-costs/dashboard") {
        return {
          month: "2026-03",
          total_cost_usd: 321.45,
          total_tokens: 420000,
          by_service: [
            {
              service_name: "reports",
              model_name: "claude-sonnet-4-5",
              request_count: 42,
              total_tokens: 210000,
              total_cost_usd: 180.12,
            },
          ],
        };
      }

      if (path === "/portals/market-data/11-680") {
        return {
          region_code: "11-680",
          active_listing_count: 7,
          average_price_krw: 12800000000,
          average_area_sqm: 2321.4,
          average_inquiry_count: 11.4,
          top_portals: [
            {
              portal_name: "naver",
              listing_count: 4,
              average_inquiry_count: 13.5,
            },
          ],
        };
      }

      if (path === "/ai-costs/budget-gate/reports/investor/generate") {
        return {
          endpoint: "reports/investor/generate",
          monthly_budget_usd: 150,
          current_cost_usd: 75.5,
          remaining_budget_usd: 74.5,
          allowed: true,
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/ai-costs/budget") {
        return {
          budget_id: "budget-001",
          endpoint: "reports/investor/generate",
          month: "2026-03",
          monthly_budget_usd: 150,
          alert_threshold_ratio: 0.8,
          created_at: "2026-03-22T00:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<InvestmentOperationsWorkspaceClient locale="ko" />);

    expect(await screen.findByText("투자 운영 컨트롤타워")).toBeInTheDocument();
    expect(await screen.findByText("Mapo Prime Asset")).toBeInTheDocument();
    expect(await screen.findByText("reports")).toBeInTheDocument();
    expect(await screen.findByText("naver")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "예산 저장" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/ai-costs/budget",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(
      await screen.findByText(/잔여 예산: US\$74.50/i),
    ).toBeInTheDocument();
  });

  it("renders query error cards and retries failed live lookups", async () => {
    let shouldFailProjects = true;
    let shouldFailCosts = true;
    let shouldFailMarket = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        if (shouldFailProjects) {
          throw new Error("Projects unavailable");
        }

        return {
          items: [
            {
              id: "project-retry-001",
              name: "Retry Asset One",
              status: "planning",
              address: "Seoul",
              total_area_sqm: 3400,
              updated_at: "2026-03-22T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/ai-costs/dashboard") {
        if (shouldFailCosts) {
          throw new Error("AI costs unavailable");
        }

        return {
          month: "2026-03",
          total_cost_usd: 120.5,
          total_tokens: 220000,
          by_service: [
            {
              service_name: "sync",
              model_name: "gpt-5",
              request_count: 8,
              total_tokens: 44000,
              total_cost_usd: 38.25,
            },
          ],
        };
      }

      if (path === "/portals/market-data/11-680") {
        if (shouldFailMarket) {
          throw new Error("Market feed unavailable");
        }

        return {
          region_code: "11-680",
          active_listing_count: 3,
          average_price_krw: 9800000000,
          average_area_sqm: 1820.5,
          average_inquiry_count: 7.5,
          top_portals: [
            {
              portal_name: "naver",
              listing_count: 2,
              average_inquiry_count: 8.1,
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<InvestmentOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Project list unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Projects unavailable")).toBeInTheDocument();
    expect(
      await screen.findByText("AI cost dashboard unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("AI costs unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Market feed unavailable")).toBeInTheDocument();

    shouldFailProjects = false;
    shouldFailCosts = false;
    shouldFailMarket = false;

    const retryButtons = await screen.findAllByRole("button", { name: "Retry" });
    await userEvent.click(retryButtons[0]);
    await userEvent.click(retryButtons[1]);
    await userEvent.click(retryButtons[2]);

    expect(await screen.findByText("project-retry-001")).toBeInTheDocument();
    expect(await screen.findByText("sync")).toBeInTheDocument();
    expect(await screen.findByText("naver")).toBeInTheDocument();
  });
});
