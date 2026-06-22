import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import { apiClient } from "@/lib/api-client";

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

describe("OperationsIntelligenceWorkspaceClient", () => {
  it("renders only the requested maintenance section", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: "project-ops-001",
          name: "Yongsan Smart Office",
          status: "operations",
          address: "Seoul Yongsan-gu",
          total_area_sqm: 8200,
          updated_at: "2026-03-22T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient
        locale="en"
        sections={["maintenance"]}
        showHero={false}
      />,
    );

    expect(
      await screen.findByRole("button", { name: "Run maintenance analysis" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Tenant experience")).not.toBeInTheDocument();
    expect(screen.queryByText("Asset intelligence")).not.toBeInTheDocument();
  });

  it("submits asset intelligence analysis in the combined workspace", async () => {
    // 컴포넌트는 로컬-컴퓨트 모드로 진화했다: apiClient.post를 호출하지 않고
    // 입력값으로부터 자산 종합 점수를 결정론적으로 산출해 렌더한다.
    // 따라서 "제출 → 산출 결과 렌더"라는 사용자 핵심 동작을 단언한다.
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient locale="en" />,
    );

    expect(
      await screen.findByText("Operations intelligence workspace"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Run asset analysis" }),
    );

    // 기본 입력(baseValue 18.8B, maintScore 0.3, nps 30) → composite = round(0.7*40 + 30*0.6) = 46.
    // composite_score 타일과 component_scores.asset 칩에 동일 값이 노출되므로 getAllByText.
    expect(
      (await screen.findAllByText("46.00")).length,
    ).toBeGreaterThan(0);
    expect(
      await screen.findByText("CAPEX recommendations"),
    ).toBeInTheDocument();
    // CAPEX 권고 카드가 산출되어 ROI/회수기간 메타가 렌더된다(권고 2건).
    expect(
      (await screen.findAllByText(/ROI .* · .* months/)).length,
    ).toBeGreaterThan(0);
  });

  it("falls back to the empty live picker with manual UUID targeting", async () => {
    // 라이브 프로젝트 피커가 정적 빈 목록으로 진화했다(외부 호출 없음).
    // 따라서 빈 목록 안내 + 수동 UUID 입력으로의 우아한 폴백을 단언한다.
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    renderWithQueryClient(
      <OperationsIntelligenceWorkspaceClient
        locale="en"
        sections={["maintenance"]}
        showHero={false}
      />,
    );

    // 라이브 프로젝트가 없을 때 안내 라벨이 노출된다.
    expect(
      await screen.findByText(
        "No live projects are available yet. Enter an existing UUID manually.",
      ),
    ).toBeInTheDocument();

    // 수동 UUID 입력 → "Current target" 패널에 활성 프로젝트로 반영된다.
    const manualInput = screen.getByPlaceholderText("Manual project UUID");
    await userEvent.type(manualInput, "project-ops-retry-001");

    expect(
      await screen.findByText("project-ops-retry-001"),
    ).toBeInTheDocument();
  });
});
