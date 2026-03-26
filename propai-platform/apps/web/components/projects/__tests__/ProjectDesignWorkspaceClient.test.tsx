import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectDesignWorkspaceClient } from "@/components/projects/ProjectDesignWorkspaceClient";
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

describe("ProjectDesignWorkspaceClient", () => {
  it("chains live floor-plan, auto-ifc, and carbon requests for the project route", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-design-001",
      name: "Songdo Design Hub",
      status: "design",
      address: "Incheon Songdo",
      total_area_sqm: 9800,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/design/floor-plan") {
        return {
          design_id: "design-001",
          file_url: "https://cdn.example.com/design-001.png",
          room_count: 3,
          generation_method: "sdxl",
          vision_validation: {
            detected_rooms: 3,
            expected_rooms: 3,
            confidence: 0.88,
            match: true,
          },
        };
      }

      if (path === "/bim/generate-ifc") {
        return {
          id: "bim-001",
          project_id: "project-design-001",
          total_volume_m3: 12450.5,
          total_area_sqm: 9800,
          material_breakdown: [{ type: "IfcWall", count: 40 }],
          element_count: 160,
          ifc_version: "IFC4",
          created_at: "2026-03-22T03:00:00Z",
        };
      }

      if (path === "/bim/carbon") {
        return {
          total_embodied_carbon: 420000,
          total_operational_carbon: 1500000,
          total_carbon: 1920000,
          breakdown: [],
          reduction_tips: ["Reduce concrete intensity in the wall package."],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(
      <ProjectDesignWorkspaceClient
        locale="en"
        projectId="project-design-001"
      />,
    );

    expect(await screen.findByText("Songdo Design Hub")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Generate floor plan" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/design/floor-plan",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("sdxl")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Generate IFC and carbon" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/bim/generate-ifc",
        expect.objectContaining({
          useMock: false,
        }),
      );
      expect(apiClient.post).toHaveBeenCalledWith(
        "/bim/carbon",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("IFC4")).toBeInTheDocument();
    expect(
      await screen.findByText("Reduce concrete intensity in the wall package."),
    ).toBeInTheDocument();
  });

  it("renders a retryable project metadata error and recovers the design context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Design project metadata unavailable");
      }

      return {
        id: "project-design-retry-001",
        name: "Recovered Design Hub",
        status: "design",
        address: "Daejeon",
        total_area_sqm: 8700,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectDesignWorkspaceClient
        locale="en"
        projectId="project-design-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Design project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Design Hub")).toBeInTheDocument();
  });
});
