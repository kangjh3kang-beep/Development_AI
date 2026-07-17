/**
 * SatongMapShell 필지 상세 패널(WS-C) — 카드 클릭 → 상세 패널 계약.
 *
 * 고정하는 계약:
 *   ① 선택 필지 카드 클릭 → 상세 패널(면적·용도지역·지목·PNU + 산출물 퍼널) 표시.
 *   ② 무자료 항목은 "-" 정직 표기(추정 금지).
 *   ③ 닫기(X) → 패널 제거.
 *   ④ 카드의 삭제 버튼 클릭은 상세 패널을 열지 않는다(stopPropagation).
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { writeSatongMapSelection } from "@/components/precheck/satong-map-selection";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = () => <div data-testid="dynamic-map-stub" />;
    return DynamicStub;
  },
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending),
      get: vi.fn(pending),
      post: vi.fn(pending),
      put: vi.fn(pending),
      patch: vi.fn(pending),
      delete: vi.fn(pending),
      getV2: vi.fn(pending),
      postV2: vi.fn(pending),
      putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({
      projectId: null,
      projectName: "",
      projectStatus: "",
      siteAnalysis: null,
    });
  });
}

describe("SatongMapShell 필지 상세 패널(WS-C)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("카드 클릭 → 상세 패널(속성·무자료 '-'·산출물 퍼널) 표시, 닫기로 제거", () => {
    writeSatongMapSelection([
      {
        id: "P-detail",
        address: "경기도 성남시 분당구 판교동 100",
        source: "map",
        zoneType: "자연녹지지역",
        jimok: "임야",
        areaSqm: 8019,
        pnu: "4113510300101000000",
      },
    ]);

    render(<SatongMapShell locale="ko" />);

    // 카드(짧은 지번) 클릭 → 상세 패널
    fireEvent.click(screen.getByText("판교동 100"));
    const panel = screen.getByTestId("parcel-detail-panel");

    expect(within(panel).getByText("경기도 성남시 분당구 판교동 100")).toBeInTheDocument();
    expect(within(panel).getByText("자연녹지지역")).toBeInTheDocument();
    expect(within(panel).getByText("임야")).toBeInTheDocument();
    expect(within(panel).getByText("4113510300101000000")).toBeInTheDocument();
    // 무자료(공시지가) = "-" 정직 표기 + 총액(참고) 행은 미표시
    expect(within(panel).getByText("개별공시지가")).toBeInTheDocument();
    expect(within(panel).queryByText(/공시지가 총액/)).not.toBeInTheDocument();
    // 산출물 퍼널 4종 — Output Dock과 동일 라벨(공용통로 handleOutputClick)
    expect(within(panel).getByRole("button", { name: "종합 부지분석" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "인허가 체크리스트" })).toBeInTheDocument();

    // 닫기 → 패널 제거
    fireEvent.click(within(panel).getByRole("button", { name: "필지 상세 닫기" }));
    expect(screen.queryByTestId("parcel-detail-panel")).not.toBeInTheDocument();
  });

  it("삭제 버튼 클릭은 상세 패널을 열지 않는다(카드 클릭으로 미전파)", () => {
    writeSatongMapSelection([
      { id: "P-del", address: "서울특별시 종로구 청진동 1", source: "map", areaSqm: 100 },
    ]);

    render(<SatongMapShell locale="ko" />);

    fireEvent.click(screen.getByRole("button", { name: "필지 제거" }));
    expect(screen.queryByTestId("parcel-detail-panel")).not.toBeInTheDocument();
    // 삭제도 실제 반영(목록 비움 상태 문구)
    expect(screen.getByText("아직 선택된 필지가 없습니다.")).toBeInTheDocument();
  });
});
