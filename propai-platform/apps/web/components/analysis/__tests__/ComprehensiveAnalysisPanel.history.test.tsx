/**
 * ComprehensiveAnalysisPanel — 분석 히스토리 카드(AnalysisHistoryCard) 배선 검증.
 *
 * 정답 기준선(Market/Regulations/PermitAi WorkspaceClient)과 달리, 이 표면은 카드를
 * result 블록 최하단(evidence/ai_interpretation 등 전 섹션 뒤)에 둔다 — 렌더 전에는
 * 카드가 없고(over 조건: result 존재), 종합분석 성공 후에만 나타나며 result.address/
 * result.pnu·analysisType="site_analysis"로 배선되는지를 검증한다.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

// 지도(SatongMapShell)는 SSR 없이 동적 로드되는 무거운 지도 엔진 — 히스토리 카드 배선 검증과
// 무관하므로 스텁 처리(다른 워크스페이스 클라이언트 테스트의 확립된 관례와 동일 — dashboard-route-shells.test.tsx).
vi.mock("@/components/precheck/SatongMapShell", () => ({
  SatongMapShell: () => null,
}));

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: getMock, post: postMock },
  };
});

const { historyCardCalls } = vi.hoisted(() => ({ historyCardCalls: [] as Record<string, unknown>[] }));
vi.mock("@/components/common/AnalysisHistoryCard", () => ({
  AnalysisHistoryCard: (props: Record<string, unknown>) => {
    historyCardCalls.push(props);
    return <div data-testid="history-card" data-analysis-type={String(props.analysisType)} />;
  },
}));

function resetStore() {
  act(() => {
    useProjectContextStore.setState({
      projectId: "p1",
      projectName: "테스트 프로젝트",
      siteAnalysis: {
        estimatedValue: null,
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
        address: "서울시 강남구 테스트로 1",
        pnu: null,
        parcels: [],
      },
    } as never);
  });
}

describe("ComprehensiveAnalysisPanel — 분석 히스토리 카드 배선", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    historyCardCalls.length = 0;
    getMock.mockRejectedValue(new Error("providers unavailable"));
    resetStore();
  });

  it("분석 실행 전에는 히스토리 카드를 렌더하지 않는다(result 조건 게이트)", () => {
    render(<ComprehensiveAnalysisPanel />);
    expect(screen.queryByTestId("history-card")).not.toBeInTheDocument();
  });

  it("종합분석 성공 후 result 블록 최하단에 site_analysis 히스토리 카드를 배선한다", async () => {
    postMock.mockResolvedValue({
      address: "서울시 강남구 테스트로 1",
      pnu: "1168010100100010000",
      zone_type: "제2종일반주거지역",
      land_area_sqm: 500,
      analyzed_at: "2026-07-19T00:00:00Z",
    });

    render(<ComprehensiveAnalysisPanel />);
    await userEvent.click(screen.getByRole("button", { name: "종합 분석 시작" }));

    await waitFor(() => expect(screen.getByTestId("history-card")).toBeInTheDocument());

    // "분석 시간" 텍스트(결과 블록의 실제 최하단 콘텐츠) 바로 뒤에 카드가 오는지 DOM 순서로 확인.
    const timeText = screen.getByText(/분석 시간:/);
    const historyCard = screen.getByTestId("history-card");
    // compareDocumentPosition: DOCUMENT_POSITION_FOLLOWING(4) — historyCard가 timeText 뒤에 위치.
    expect(timeText.compareDocumentPosition(historyCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(historyCardCalls.at(-1)).toMatchObject({
      analysisType: "site_analysis",
      address: "서울시 강남구 테스트로 1",
      pnu: "1168010100100010000",
      reanalyzing: false,
      refreshSignal: 1,
    });
    expect(historyCardCalls.at(-1)?.currentSignatureParts).toEqual([
      "서울시 강남구 테스트로 1",
      "1168010100100010000",
      "1",
      "true",
      "",
    ]);
  });
});
