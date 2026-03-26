import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TaxOperationsWorkspaceClient } from "@/components/analytics/TaxOperationsWorkspaceClient";
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

describe("TaxOperationsWorkspaceClient", () => {
  it("renders the tax workspace and submits a live tax calculation", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-tax-001",
          name: "Yeouido River One",
          status: "planning",
          address: "Seoul Yeongdeungpo-gu",
          total_area_sqm: 9800,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/tax/calculate") {
        return {
          id: "tax-001",
          project_id: "project-tax-001",
          tax_type: "acquisition",
          amount: 96000000,
          taxable_value: 1200000000,
          tax_rate: 0.08,
          deductions: [{ name: "first_home_credit", amount: 2000000 }],
          optimization_tips: ["Consider acquisition timing before final closing."],
          created_at: "2026-03-22T00:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<TaxOperationsWorkspaceClient locale="en" />);

    expect(await screen.findByText("Tax live workspace")).toBeInTheDocument();
    expect(await screen.findByText("Yeouido River One")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Calculate tax" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/tax/calculate",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("8.00%")).toBeInTheDocument();
    expect(
      await screen.findByText((content) =>
        content.includes("Consider acquisition timing before final closing."),
      ),
    ).toBeInTheDocument();
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
        throw new Error("Tax projects unavailable");
      }

      return {
        items: [
          {
            id: "project-tax-retry-001",
            name: "Recovered Tax Tower",
            status: "planning",
            address: "Incheon",
            total_area_sqm: 7200,
            updated_at: "2026-03-22T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(<TaxOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Project list unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Tax projects unavailable")).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("project-tax-retry-001")).toBeInTheDocument();
  });
});
