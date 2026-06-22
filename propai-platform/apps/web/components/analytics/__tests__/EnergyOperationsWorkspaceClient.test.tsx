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

    // The project picker is a stubbed empty live feed; certification persists
    // against a real project FK, so the operator supplies a UUID manually and
    // a gross area for the (>0) backend schema before the call is allowed.
    await userEvent.type(
      screen.getByPlaceholderText("Manual project UUID"),
      "project-energy-001",
    );
    await userEvent.type(
      screen.getByPlaceholderText("Gross area (sqm)"),
      "12000",
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Estimate certification" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/energy/certification",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            project_id: "project-energy-001",
            total_area_sqm: 12000,
          }),
        }),
      );
    });

    // The grade renders both as a metric tile and in the evidence panel.
    expect((await screen.findAllByText("A+")).length).toBeGreaterThan(0);
    expect(
      await screen.findByText((content) =>
        content.includes("Increase rooftop PV capacity."),
      ),
    ).toBeInTheDocument();
  });

  it("blocks certification with an honest error when no project target is provided", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    renderWithQueryClient(<EnergyOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Energy certification workspace"),
    ).toBeInTheDocument();

    // No live projects, no manual UUID: submitting must not fire a backend call
    // and must surface the honest "real project UUID required" guard instead.
    await userEvent.click(
      screen.getByRole("button", { name: "Estimate certification" }),
    );

    expect(
      await screen.findByText("A real project UUID is required."),
    ).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
