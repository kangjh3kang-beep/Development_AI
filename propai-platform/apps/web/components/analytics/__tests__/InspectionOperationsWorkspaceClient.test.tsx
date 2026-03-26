import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InspectionOperationsWorkspaceClient } from "@/components/analytics/InspectionOperationsWorkspaceClient";
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

describe("InspectionOperationsWorkspaceClient", () => {
  it("renders the inspection workspace and submits drone inspection", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-inspection-001",
          name: "Guro Tech Campus",
          status: "construction",
          address: "Seoul Guro-gu",
          total_area_sqm: 15600,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/drone/inspect") {
        return {
          id: "inspection-001",
          project_id: "project-inspection-001",
          inspection_date: "2026-03-22T00:00:00Z",
          defects_found: 2,
          defects: [
            {
              defect_type: "water_leak",
              confidence: 0.91,
              severity: "HIGH",
            },
          ],
          severity_summary: {
            EMERGENCY: 0,
            HIGH: 1,
            MEDIUM: 1,
            LOW: 0,
          },
          images_processed: 2,
          created_at: "2026-03-22T00:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<InspectionOperationsWorkspaceClient locale="en" />);

    expect(await screen.findByText("Inspection live workspace")).toBeInTheDocument();
    expect(await screen.findByText("Guro Tech Campus")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Run inspection" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/drone/inspect",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(
      await screen.findByText((content) =>
        content.includes("water_leak / HIGH / 91.0%"),
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText("HIGH: 1")).toBeInTheDocument();
  });

  it("shows the live auth banner when the inspection call is rejected with 401", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-inspection-002",
          name: "Busan Harbor Yard",
          status: "construction",
          address: "Busan Jung-gu",
          total_area_sqm: 14400,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    const UnauthorizedApiClientError = (await import("@/lib/api-client"))
      .ApiClientError;

    vi.mocked(apiClient.post).mockRejectedValue(
      new UnauthorizedApiClientError("Unauthorized", 401, {
        detail: "Unauthorized",
      }),
    );

    renderWithQueryClient(<InspectionOperationsWorkspaceClient locale="en" />);

    await userEvent.click(screen.getByRole("button", { name: "Run inspection" }));

    expect(
      await screen.findByText("API authentication is required for live workspace calls."),
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
        throw new Error("Inspection projects unavailable");
      }

      return {
        items: [
          {
            id: "project-inspection-retry-001",
            name: "Recovered Inspection Campus",
            status: "construction",
            address: "Ulsan",
            total_area_sqm: 11100,
            updated_at: "2026-03-22T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(<InspectionOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Project list unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Inspection projects unavailable"),
    ).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText("project-inspection-retry-001"),
    ).toBeInTheDocument();
  });
});
