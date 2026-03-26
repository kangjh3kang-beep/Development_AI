import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectDroneWorkspaceClient } from "@/components/projects/ProjectDroneWorkspaceClient";
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

describe("ProjectDroneWorkspaceClient", () => {
  it("runs a live drone inspection for the routed project", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-drone-001",
      name: "Busan Inspection Site",
      status: "construction",
      address: "Busan Suyeong-gu",
      total_area_sqm: 4200,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    vi.mocked(apiClient.post).mockResolvedValue({
      id: "inspection-001",
      project_id: "project-drone-001",
      inspection_date: "2026-03-22T02:00:00Z",
      defects_found: 3,
      defects: [
        {
          defect_type: "crack",
          confidence: 0.92,
          severity: "high",
        },
      ],
      severity_summary: {
        high: 1,
        medium: 2,
      },
      images_processed: 2,
      created_at: "2026-03-22T02:00:00Z",
    });

    renderWithQueryClient(
      <ProjectDroneWorkspaceClient locale="en" projectId="project-drone-001" />,
    );

    expect(await screen.findByText("Busan Inspection Site")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Run project inspection" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/drone/inspect",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(await screen.findByText("crack / high / 92.0%")).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the inspection context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Drone project metadata unavailable");
      }

      return {
        id: "project-drone-retry-001",
        name: "Recovered Drone Site",
        status: "construction",
        address: "Gwangju",
        total_area_sqm: 3800,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectDroneWorkspaceClient locale="en" projectId="project-drone-retry-001" />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Drone project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Drone Site")).toBeInTheDocument();
  });
});
