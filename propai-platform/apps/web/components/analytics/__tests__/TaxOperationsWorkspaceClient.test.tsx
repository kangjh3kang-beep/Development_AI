import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TaxOperationsWorkspaceClient } from "@/components/analytics/TaxOperationsWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";

// 이 워크스페이스는 의도적으로 로컬(오프라인) 계산기로 진화했다.
// 프로젝트 목록 쿼리는 빈 배열을 반환하고, 세금 계산은 @/lib/kr-tax-calculator로
// 클라이언트에서 즉시 수행한다 — 라이브 tax API(apiClient.post)를 호출하지 않는다.
// 따라서 테스트는 컴포넌트의 '현재 실제 동작'(로컬 계산 결과 렌더)을 검증한다.
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

describe("TaxOperationsWorkspaceClient", () => {
  it("renders the tax workspace and computes a local tax scenario on submit", async () => {
    renderWithQueryClient(<TaxOperationsWorkspaceClient locale="en" />);

    // 히어로/작업공간 헤더가 렌더된다.
    expect(await screen.findByText("Tax live workspace")).toBeInTheDocument();
    // 기본 폼은 취득세(acquisition) + 과세표준 12억으로 설정되어 있다.
    expect(
      screen.getByRole("button", { name: "Calculate tax" }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Calculate tax" }),
    );

    // 라이브 API를 호출하지 않고 로컬 계산기로 결과를 산출한다.
    expect(apiClient.post).not.toHaveBeenCalled();

    // 취득세 12억 → 세율 3.00%(>9억 구간) 가 적용 세율로 표기된다.
    expect(await screen.findByText("3.00%")).toBeInTheDocument();

    // 비-생애최초 기본 취득세 시나리오의 절세 팁이 렌더된다.
    expect(
      await screen.findByText((content) =>
        content.includes("취득일 기준 60일 이내 신고/납부 필요"),
      ),
    ).toBeInTheDocument();

    // 공제 항목(취득세/농특세/교육세)이 목록으로 렌더된다.
    expect(
      await screen.findByText((content) => content.includes("취득세")),
    ).toBeInTheDocument();

    // 법령 근거 칩(지방세법)이 표기된다.
    expect(
      (await screen.findAllByText((content) => content.includes("지방세법")))
        .length,
    ).toBeGreaterThan(0);
  });

  it("renders an empty local project picker without crashing or calling the live API", async () => {
    renderWithQueryClient(<TaxOperationsWorkspaceClient locale="en" />);

    // 라이브 프로젝트가 없으므로 빈 픽커 안내 문구가 노출된다.
    expect(
      await screen.findByText(
        "No live projects are available yet. Enter an existing UUID manually.",
      ),
    ).toBeInTheDocument();

    // 수동 UUID 입력이 활성 대상으로 반영된다(로컬 데이터흐름 검증).
    const manualInput = screen.getByPlaceholderText("Manual project UUID");
    await userEvent.type(manualInput, "manual-uuid-123");

    await waitFor(() => {
      expect(screen.getByText("manual-uuid-123")).toBeInTheDocument();
    });

    // 컴포넌트는 라이브 프로젝트 목록 API를 호출하지 않는다.
    expect(apiClient.get).not.toHaveBeenCalled();
  });
});
