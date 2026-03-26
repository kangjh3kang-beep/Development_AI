import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KdxMonitoringWorkspaceClient } from "@/components/dashboard/kdx/KdxMonitoringWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";

vi.mock("@/components/dashboard/kdx/KdxRealtimeChart", () => ({
  default: () => <div data-testid="kdx-realtime-chart">KDX realtime chart</div>,
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
  },
}));

describe("KdxMonitoringWorkspaceClient", () => {
  it("renders the live KDX overview with recent logs", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      connection_status: "stable",
      throughput_tps: 168,
      data_sync_latency_ms: 420,
      latest_metric: {
        region_code: "11110",
        metric_type: "transaction_volume",
        value: 128,
        currency: "INDEX",
        recorded_at: "2026-03-23T00:00:00Z",
      },
      recent_logs: [
        {
          id: "log-001",
          source: "KDX-Webhook",
          event_type: "market_tick",
          status: "processed",
          created_at: "2026-03-23T00:00:00Z",
        },
      ],
    });

    renderWithQueryClient(<KdxMonitoringWorkspaceClient />);

    expect(await screen.findByText("KDX Monitoring Center")).toBeInTheDocument();
    expect(await screen.findByText("168")).toBeInTheDocument();
    expect(await screen.findByText("420")).toBeInTheDocument();
    expect(await screen.findByText("transaction_volume · 11110")).toBeInTheDocument();
    expect(await screen.findByText("KDX-Webhook")).toBeInTheDocument();
    expect(screen.getByTestId("kdx-realtime-chart")).toBeInTheDocument();
  });

  it("renders the query error state and retries the overview fetch", async () => {
    let shouldFail = true;

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFail) {
        throw new Error("KDX overview unavailable");
      }

      return {
        connection_status: "stable",
        throughput_tps: 144,
        data_sync_latency_ms: 360,
        latest_metric: null,
        recent_logs: [],
      };
    });

    renderWithQueryClient(<KdxMonitoringWorkspaceClient />);

    expect(
      await screen.findByText("KDX overview is unavailable."),
    ).toBeInTheDocument();
    expect(await screen.findByText("KDX overview unavailable")).toBeInTheDocument();

    shouldFail = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("144")).toBeInTheDocument();
  });
});
