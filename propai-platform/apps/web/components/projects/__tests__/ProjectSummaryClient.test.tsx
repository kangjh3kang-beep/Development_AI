import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectSummaryClient } from "@/components/projects/ProjectSummaryClient";
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
  },
}));

describe("ProjectSummaryClient", () => {
  it("renders the live backend project overview and module coverage", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-overview-001",
      name: "Mapo Live Overview",
      status: "planning",
      address: "Seoul Mapo-gu",
      latitude: 37.55,
      longitude: 126.91,
      total_area_sqm: 3200,
      created_at: "2026-03-20T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    renderWithQueryClient(
      <ProjectSummaryClient
        locale="en"
        projectId="project-overview-001"
        moduleLabels={{
          contracts: "Contracts",
          design: "Design",
          bim: "BIM",
          finance: "Finance",
          drone: "Drone",
          blockchain: "Blockchain",
          report: "Report",
        }}
      />,
    );

    expect(await screen.findByText("Mapo Live Overview")).toBeInTheDocument();
    expect(await screen.findByText("Module routes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CAD" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contracts" })).toBeInTheDocument();
    expect(await screen.findByText("Live route coverage")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Keep CAD on the editor-only route until the current Three.js and dependency blockers are resolved.",
      ),
    ).toBeInTheDocument();
  });
});
