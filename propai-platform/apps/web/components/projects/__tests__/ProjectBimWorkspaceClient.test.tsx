import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectBimWorkspaceClient } from "@/components/projects/ProjectBimWorkspaceClient";
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

describe("ProjectBimWorkspaceClient", () => {
  it("generates live BIM quantities and loads geometry for the routed project", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects/project-bim-001") {
        return {
          id: "project-bim-001",
          name: "Yeouido BIM Center",
          status: "design",
          address: "Seoul Yeongdeungpo-gu",
          total_area_sqm: 8600,
          created_at: "2026-03-22T00:00:00Z",
          updated_at: "2026-03-22T01:00:00Z",
        };
      }

      if (path === "/bim/threejs/project-bim-001") {
        return {
          project_id: "project-bim-001",
          format: "threejs_buffergeometry",
          total_elements: 12,
          geometries: [
            { id: "g1", type: "IfcWall" },
            { id: "g2", type: "IfcWall" },
            { id: "g3", type: "IfcSlab" },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockResolvedValue({
      id: "bim-001",
      project_id: "project-bim-001",
      total_volume_m3: 9812.5,
      total_area_sqm: 8600,
      material_breakdown: [{ type: "IfcWall", count: 20 }],
      element_count: 120,
      ifc_version: "IFC4",
      created_at: "2026-03-22T02:00:00Z",
    });

    renderWithQueryClient(
      <ProjectBimWorkspaceClient locale="en" projectId="project-bim-001" />,
    );

    expect(await screen.findByText("Yeouido BIM Center")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Generate BIM quantities" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/bim/generate-ifc",
        expect.objectContaining({
          useMock: false,
        }),
      );
      expect(apiClient.get).toHaveBeenCalledWith(
        "/bim/threejs/project-bim-001",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("IFC4")).toBeInTheDocument();
    expect(await screen.findByText("threejs_buffergeometry")).toBeInTheDocument();
    expect(await screen.findByText("IfcWall: 2")).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the BIM context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("BIM project metadata unavailable");
      }

      return {
        id: "project-bim-retry-001",
        name: "Recovered BIM Center",
        status: "design",
        address: "Daegu",
        total_area_sqm: 7600,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectBimWorkspaceClient locale="en" projectId="project-bim-retry-001" />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("BIM project metadata unavailable")).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered BIM Center")).toBeInTheDocument();
  });
});
