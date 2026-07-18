/**
 * PreCheckWorkspace — 분석 히스토리 카드(AnalysisHistoryCard) 배선 검증.
 *
 * 정답 기준선과 동일 패턴이되 배치 위치만 다르다: instant 결과 렌더(<PreCheckInstantPanel/>)
 * 바로 뒤, "instant" 탭 내부에만 존재한다(PreCheckInstantPanel 스탠드얼론 사용처는 이 카드를
 * 갖지 않는다 — 이 워크스페이스 전용 배선임을 확인).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PreCheckWorkspace } from "@/components/precheck/PreCheckWorkspace";
import { SATONG_MAP_SELECTION_KEY } from "@/components/precheck/satong-map-selection";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ locale: "ko" }),
}));

vi.mock("@/components/common/GlobalAddressSearch", () => ({
  // 실제 컴포넌트는 Daum/VWorld 주소검색 위젯 — 히스토리 카드 배선 검증과 무관하므로
  // onChange(entries)만 흉내 내는 단순 입력으로 대체(ComprehensiveAnalysisPanel 테스트와
  // 동일하게 무거운 외부 검색 위젯은 스텁).
  GlobalAddressSearch: ({ onChange }: { onChange: (entries: Array<{ jibunAddress: string }>) => void }) => (
    <input
      aria-label="주소"
      onChange={(e) => onChange([{ jibunAddress: e.target.value } as never])}
    />
  ),
}));
vi.mock("@/components/common/BulkParcelBatchPanel", () => ({
  BulkParcelBatchPanel: () => null,
}));
vi.mock("@/components/common/DevelopmentScenarioCard", () => ({
  DevelopmentScenarioCard: () => null,
}));
vi.mock("@/components/precheck/ZoningSignalMap", () => ({ ZoningSignalMap: () => null }));

vi.mock("@/components/precheck/PreCheckInstantPanel", () => ({
  PreCheckInstantPanel: () => <div data-testid="instant-panel" />,
}));

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: { ...actual.apiClient, post: postMock },
  };
});

const { historyCardCalls } = vi.hoisted(() => ({ historyCardCalls: [] as Record<string, unknown>[] }));
vi.mock("@/components/common/AnalysisHistoryCard", () => ({
  AnalysisHistoryCard: (props: Record<string, unknown>) => {
    historyCardCalls.push(props);
    return <div data-testid="history-card" data-analysis-type={String(props.analysisType)} />;
  },
}));

describe("PreCheckWorkspace — 분석 히스토리 카드 배선", () => {
  beforeEach(() => {
    postMock.mockReset();
    historyCardCalls.length = 0;
    window.sessionStorage.removeItem(SATONG_MAP_SELECTION_KEY);
  });

  it("주소 미확정(초기 렌더)에는 히스토리 카드를 렌더하지 않는다", () => {
    render(<PreCheckWorkspace />);
    expect(screen.getByTestId("instant-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("history-card")).not.toBeInTheDocument();
  });

  it("90초 진단 성공 후 instant 결과 렌더 뒤에 precheck 히스토리 카드를 배선한다", async () => {
    postMock.mockImplementation((path: string) => {
      if (path === "/precheck/instant") {
        return Promise.resolve({
          ok: true,
          address: "서울시 강남구 테헤란로 152",
          pnu: "1168010100100010000",
          zone_type: "제2종일반주거지역",
          area_sqm: 500,
          elapsed_ms: 1200,
          summary: { pass: 1, warn: 0, fail: 0, best: "M06", llm_note: null },
          legal_limits: { bcr_pct: 60, far_pct: 200, height_m: null, source: "test" },
          methods: [],
          sources: [],
        });
      }
      if (path === "/precheck/zoning-signals") {
        return Promise.resolve({ ok: true, signals: [] });
      }
      return Promise.reject(new Error(`unexpected path ${path}`));
    });

    render(<PreCheckWorkspace />);
    await userEvent.type(screen.getByLabelText(/주소/), "서울시 강남구 테헤란로 152");
    await userEvent.click(screen.getByRole("button", { name: "90초 사업성 진단" }));

    await waitFor(() => expect(screen.getByTestId("history-card")).toBeInTheDocument());

    const instantPanel = screen.getByTestId("instant-panel");
    const historyCard = screen.getByTestId("history-card");
    expect(instantPanel.compareDocumentPosition(historyCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(historyCardCalls.at(-1)).toMatchObject({
      analysisType: "precheck",
      address: "서울시 강남구 테헤란로 152",
      pnu: "1168010100100010000",
      reanalyzing: false,
      refreshSignal: 1,
    });
    expect(historyCardCalls.at(-1)?.currentSignatureParts).toEqual([
      "서울시 강남구 테헤란로 152",
      "1168010100100010000",
      "1",
      "false",
      "",
    ]);
  });

  it("2필지 이상 등록(사통맵 선택) 상태에서도 시그니처 idx2(parcel_count)는 '1' 상수를 유지한다(P2 — write/read parcel_count 불일치 봉합, 백엔드 precheck.py는 항상 parcel_count=1로 적재)", async () => {
    // 사통맵에서 2필지를 선택/등록한 상태를 시뮬레이션(precheck.py는 이 등록수와 무관하게
    // parcel_count=1을 하드코딩하므로, 프론트 read 시그니처도 등록 필지수와 무관하게 "1"이어야 한다).
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({
        savedAt: new Date().toISOString(),
        parcels: [
          { id: "p1", address: "서울시 강남구 테헤란로 152", source: "map" },
          { id: "p2", address: "서울시 강남구 테헤란로 154", source: "map" },
        ],
      }),
    );
    postMock.mockImplementation((path: string) => {
      if (path === "/precheck/instant") {
        return Promise.resolve({
          ok: true,
          address: "서울시 강남구 테헤란로 152",
          pnu: "1168010100100010000",
          zone_type: "제2종일반주거지역",
          area_sqm: 500,
          elapsed_ms: 1200,
          summary: { pass: 1, warn: 0, fail: 0, best: "M06", llm_note: null },
          legal_limits: { bcr_pct: 60, far_pct: 200, height_m: null, source: "test" },
          methods: [],
          sources: [],
        });
      }
      if (path === "/precheck/zoning-signals") {
        return Promise.resolve({ ok: true, signals: [] });
      }
      return Promise.reject(new Error(`unexpected path ${path}`));
    });

    render(<PreCheckWorkspace />);
    // 사통맵 선택 useEffect가 마운트 시 address를 자동 채운다(별도 타이핑 불요) — 버튼 활성화 대기.
    await waitFor(() => expect(screen.getByRole("button", { name: "90초 사업성 진단" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "90초 사업성 진단" }));

    await waitFor(() => expect(screen.getByTestId("history-card")).toBeInTheDocument());

    expect(historyCardCalls.at(-1)?.currentSignatureParts).toEqual([
      "서울시 강남구 테헤란로 152",
      "1168010100100010000",
      "1",
      "false",
      "",
    ]);
  });
});
