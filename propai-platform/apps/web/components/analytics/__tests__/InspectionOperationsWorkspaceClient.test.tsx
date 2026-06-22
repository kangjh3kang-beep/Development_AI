import { screen, waitFor, within } from "@testing-library/react";
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
  it("renders the inspection workspace and surfaces a defect detection result", async () => {
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

    renderWithQueryClient(<InspectionOperationsWorkspaceClient locale="en" />);

    expect(await screen.findByText("Inspection live workspace")).toBeInTheDocument();
    // The first live project is auto-selected and surfaced in the "Current target" panel.
    expect(await screen.findAllByText("Guro Tech Campus")).not.toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Run inspection" }));

    // The workspace generates a persisted inspection result for the two seeded image URLs.
    expect(await screen.findByText("Images processed")).toBeInTheDocument();
    expect(await screen.findByText("Defects found")).toBeInTheDocument();
    expect(await screen.findByText("Severity summary")).toBeInTheDocument();
    expect(await screen.findByText("Detected defects")).toBeInTheDocument();

    // Two seeded image URLs are processed.
    const imagesTile = screen.getByText("Images processed").closest("div");
    expect(imagesTile).not.toBeNull();
    expect(within(imagesTile as HTMLElement).getByText("2")).toBeInTheDocument();

    // At least one defect is detected and rendered with type / severity / confidence.
    const defectMatches = await screen.findAllByText((content) =>
      /\/\s*\d+\.\d%/.test(content),
    );
    expect(defectMatches.length).toBeGreaterThan(0);
  });

  it("shows the live auth banner when live workspace calls are unavailable", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "/api/proxy",
      useMocksByDefault: true,
      hasAccessToken: false,
      mode: "hybrid",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithQueryClient(<InspectionOperationsWorkspaceClient locale="en" />);

    expect(
      await screen.findByText(
        "API authentication is required for live workspace calls.",
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

    // The recovered project becomes the active target (id surfaced in the panel).
    expect(
      await screen.findByText("project-inspection-retry-001"),
    ).toBeInTheDocument();
  });
});
