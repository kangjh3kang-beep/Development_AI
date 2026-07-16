import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectFinanceWorkspaceClient } from "@/components/projects/ProjectFinanceWorkspaceClient";
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

describe("ProjectFinanceWorkspaceClient", () => {
  it("chains the live avm and jeonse-risk requests for the project route", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-finance-001",
      name: "Mapo Finance Asset",
      status: "planning",
      address: "Seoul Mapo-gu 100",
      total_area_sqm: 1450,
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/avm") {
        return {
          id: "avm-001",
          project_id: "project-finance-001",
          estimated_price: 2400000000,
          price_per_sqm: 1655172,
          confidence_score: 0.82,
          comparable_count: 9,
          model_version: "v43-avm",
          created_at: "2026-03-22T02:00:00Z",
        };
      }

      if (path === "/finance/jeonse-risk") {
        return {
          jeonse_ratio: 0.75,
          risk_level: "MEDIUM",
          risk_score: 0.48,
          analysis: "The jeonse ratio remains below the highest-risk band.",
          factors: [
            {
              factor: "ratio-band",
              detail: "The ratio remains below 80 percent.",
            },
          ],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(
      <ProjectFinanceWorkspaceClient
        locale="en"
        projectId="project-finance-001"
      />,
    );

    expect(await screen.findByText("Mapo Finance Asset")).toBeInTheDocument();

    // ★전용면적은 사용자가 직접 입력한다(새 계약) — 종전에는 projects.total_area_sqm(연면적)이
    //   자동 프리필돼 틀린 축(GFA)으로 AVM 이 실행됐다(±15㎡ 실거래 매칭 전멸 → 합성 폴백).
    //   프리필 제거 후에는 면적 미입력 제출이 검증에 막히므로, 실제 사용자 흐름대로 입력한다.
    await userEvent.type(
      screen.getByPlaceholderText("Exclusive area (sqm)"),
      "84",
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Run finance analysis" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenNthCalledWith(
        1,
        "/avm",
        expect.objectContaining({
          useMock: false,
          // 사용자 입력 전용면적이 그대로 전달돼야 한다(GFA 1450 아님 — 프리필 제거 회귀 앵커).
          body: expect.objectContaining({ area_sqm: 84 }),
        }),
      );
      expect(apiClient.post).toHaveBeenNthCalledWith(
        2,
        "/finance/jeonse-risk",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("MEDIUM")).toBeInTheDocument();
    expect(await screen.findByText("75.0%")).toBeInTheDocument();
    expect(
      await screen.findByText("The jeonse ratio remains below the highest-risk band."),
    ).toBeInTheDocument();
  });

  it("does not prefill area from project total_area_sqm (GFA) — submission without user input is blocked", async () => {
    // ★프리필 제거 회귀 앵커: projects.total_area_sqm 은 연면적(GFA)이지 전용면적이 아니다.
    //   이 값이 자동 프리필되면 틀린 축으로 /avm 이 실행된다(±15㎡ 매칭 전멸 → 합성 폴백).
    //   면적 미입력 제출은 검증 에러로 막히고 /avm 은 호출되지 않아야 한다.
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });
    vi.mocked(apiClient.get).mockResolvedValue({
      id: "project-finance-002",
      name: "Prefill Guard Asset",
      status: "planning",
      address: "Seoul Mapo-gu 200",
      total_area_sqm: 1450, // 연면적 — 프리필되면 안 되는 값
      created_at: "2026-03-22T00:00:00Z",
      updated_at: "2026-03-22T01:00:00Z",
    });

    renderWithQueryClient(
      <ProjectFinanceWorkspaceClient locale="en" projectId="project-finance-002" />,
    );
    expect(await screen.findByText("Prefill Guard Asset")).toBeInTheDocument();

    // 면적 입력창이 비어 있어야 한다(1450 프리필 금지).
    expect(
      (screen.getByPlaceholderText("Exclusive area (sqm)") as HTMLInputElement).value,
    ).toBe("");

    await userEvent.click(screen.getByRole("button", { name: "Run finance analysis" }));

    expect(await screen.findByText("A positive area value is required.")).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("renders a retryable project metadata error and recovers the route context", async () => {
    let shouldFailProject = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async () => {
      if (shouldFailProject) {
        throw new Error("Finance project metadata unavailable");
      }

      return {
        id: "project-finance-retry-001",
        name: "Recovered Finance Asset",
        status: "planning",
        address: "Incheon Yeonsu-gu",
        total_area_sqm: 5100,
        created_at: "2026-03-22T00:00:00Z",
        updated_at: "2026-03-22T01:00:00Z",
      };
    });

    renderWithQueryClient(
      <ProjectFinanceWorkspaceClient
        locale="en"
        projectId="project-finance-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Finance project metadata unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Finance Asset")).toBeInTheDocument();
  });
});
