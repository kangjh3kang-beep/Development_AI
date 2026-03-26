import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EnergyOperationsWorkspaceClient } from "@/components/analytics/EnergyOperationsWorkspaceClient";
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

describe("EnergyOperationsWorkspaceClient", () => {
  it("renders the energy workspace and submits certification analysis", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-energy-001",
          name: "Songdo Green Tower",
          status: "design",
          address: "Incheon Songdo",
          total_area_sqm: 12000,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/energy/certification") {
        return {
          energy_grade: "A+",
          zeb_grade: "1",
          annual_energy_demand_kwh: 540000,
          annual_renewable_generation_kwh: 210000,
          energy_independence_rate: 0.389,
          bems_saving_rate: 0.08,
          bems_saving_kwh: 47000,
          recommendations: [
            "Increase rooftop PV capacity.",
            "Optimize BEMS control schedules.",
          ],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<EnergyOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Energy certification workspace"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Songdo Green Tower")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Estimate certification" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/energy/certification",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("A+")).toBeInTheDocument();
    expect(
      await screen.findByText((content) =>
        content.includes("Increase rooftop PV capacity."),
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
        throw new Error("Projects feed unavailable");
      }

      return {
        items: [
          {
            id: "project-energy-retry-001",
            name: "Recovery Energy Tower",
            status: "operations",
            address: "Busan",
            total_area_sqm: 8600,
            updated_at: "2026-03-22T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(<EnergyOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Project list unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Projects feed unavailable"),
    ).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText("project-energy-retry-001"),
    ).toBeInTheDocument();
  });
});
