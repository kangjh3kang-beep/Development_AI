import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DigitalTwinControlTowerWorkspaceClient } from "@/components/digital-twin/DigitalTwinControlTowerWorkspaceClient";
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

describe("DigitalTwinControlTowerWorkspaceClient", () => {
  it("renders the latest status, risk, and permit snapshots", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [{ id: "project-ops-01", name: "Songdo Ops Tower", total_area_sqm: 4800 }],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }
      if (path === "/digital-twin/status/project-ops-01/latest") {
        return {
          status: "watch",
          operational_readiness_score: 74.5,
          eui_grade: "B",
          eui: 157.2,
          sensor_health_ratio: 0.92,
          highest_anomaly_severity: "warning",
        };
      }
      if (path === "/risk/unified/project-ops-01/latest") {
        return {
          composite_risk_score: 48.6,
          grade: "C",
          var_95_ratio: 0.091,
          p90_adjusted_cost_krw: 20230000000,
          summary: "Unified risk grade C with manageable downside.",
        };
      }
      if (path === "/permits/project-ops-01/latest") {
        return {
          status: "submitted",
          current_stage: "submitted",
          readiness_score: 100,
          progress_pct: 40,
          submission_reference: "SEUMTER-20260325-OPS01-ABC123",
          missing_required_documents: [],
        };
      }
      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<DigitalTwinControlTowerWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Digital twin, risk, and permit readiness"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Songdo Ops Tower")).toBeInTheDocument();
    expect(await screen.findByText("watch")).toBeInTheDocument();
    expect(await screen.findByText("Unified risk grade C with manageable downside.")).toBeInTheDocument();
    expect(await screen.findByText(/SEUMTER-20260325-OPS01-ABC123/)).toBeInTheDocument();
  });

  it("submits status, risk, and permit actions", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [{ id: "project-ops-02", name: "Busan Ready Hub", total_area_sqm: 3600 }],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }
      if (
        path === "/digital-twin/status/project-ops-02/latest" ||
        path === "/risk/unified/project-ops-02/latest" ||
        path === "/permits/project-ops-02/latest"
      ) {
        return null;
      }
      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockResolvedValue({});

    renderWithQueryClient(<DigitalTwinControlTowerWorkspaceClient locale="en" />);

    await screen.findByText("Busan Ready Hub");
    await userEvent.click(screen.getByRole("button", { name: "Save status snapshot" }));
    await userEvent.click(screen.getByRole("button", { name: "Analyze unified risk" }));
    await userEvent.click(screen.getByRole("button", { name: "Submit permit package" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/digital-twin/status/snapshot",
        expect.objectContaining({ useMock: false }),
      );
      expect(apiClient.post).toHaveBeenCalledWith(
        "/risk/unified/analyze",
        expect.objectContaining({ useMock: false }),
      );
      expect(apiClient.post).toHaveBeenCalledWith(
        "/permits/submit",
        expect.objectContaining({ useMock: false }),
      );
    });
  });
});
