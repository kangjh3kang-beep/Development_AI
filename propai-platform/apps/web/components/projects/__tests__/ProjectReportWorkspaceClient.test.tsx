import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectReportWorkspaceClient } from "@/components/projects/ProjectReportWorkspaceClient";
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

describe("ProjectReportWorkspaceClient", () => {
  it("generates a live investor report for the routed project", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-report-001",
      name: "Gangnam Report Tower",
      status: "design",
      address: "Seoul Gangnam-gu",
      total_area_sqm: 11200,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    vi.mocked(apiClient.post).mockResolvedValue({
      project_id: "project-report-001",
      report_type: "investor",
      generated_sections: ["executive-summary", "market"],
      variants: [
        {
          report_id: "report-ko-001",
          target_language: "ko",
          title: "Gangnam Report Tower Investor Brief",
          quality_score: 0.94,
          translated_text: "Prime Seoul office exposure with strong leasing momentum.",
        },
      ],
    });

    renderWithQueryClient(
      <ProjectReportWorkspaceClient
        locale="en"
        projectId="project-report-001"
      />,
    );

    expect(await screen.findByText("Gangnam Report Tower")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Generate investor report" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/reports/investor/generate",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("investor")).toBeInTheDocument();
    expect(await screen.findByText("ko")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Prime Seoul office exposure with strong leasing momentum.",
      ),
    ).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the report context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Report project metadata unavailable");
      }

      return {
        id: "project-report-retry-001",
        name: "Recovered Report Tower",
        status: "design",
        address: "Seongnam Bundang-gu",
        total_area_sqm: 9300,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectReportWorkspaceClient
        locale="en"
        projectId="project-report-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Report project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Report Tower")).toBeInTheDocument();
  });
});
