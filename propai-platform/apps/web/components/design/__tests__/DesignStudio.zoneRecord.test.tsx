import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DesignStudio } from "@/components/design/DesignStudio";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";
import { renderWithQueryClient } from "@/test/render-with-query-client";

// SolarEnvelopeCard(항상 마운트 유지 — details 접힘과 무관) 등 자식 컴포넌트가 실제 네트워크
// 호출을 시도하지 않도록 apiClient를 격리(느린/불안정 테스트 방지 — 이 테스트의 관심사는
// designData.zoneCode 기록 우선순위이지 네트워크 응답이 아니다).
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn().mockRejectedValue(new Error("network disabled in test")),
    post: vi.fn().mockRejectedValue(new Error("network disabled in test")),
    getRuntimeConfig: vi.fn().mockReturnValue({ apiBaseUrl: "http://localhost:8000/api/latest" }),
  },
}));

function makeProject(partial: Partial<Project>): Project {
  return {
    id: "p1",
    name: "테스트 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 강남구 역삼동 737",
    area: "500㎡",
    status: "design",
    createdAt: "2026-06-30T00:00:00.000Z",
    ...partial,
  };
}

function makeSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

function resetStores() {
  window.localStorage.clear();
  useProjectStore.setState({
    projects: [makeProject({})],
    syncing: false,
  });
  useProjectContextStore.setState({
    projectId: "p1",
    projectName: "테스트 프로젝트",
    projectStatus: "design",
    completedStages: [],
    currentStage: null,
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    analysisResults: [],
    snapshots: {},
    updatedAt: {},
    analysisCache: {},
    manualFields: {},
    parcelEnrichPending: false,
    decisionBrief: null,
  });
}

// R2(PR#316 리뷰) 회귀 테스트 — H1 수정의 zoneCode 기록 우선순위가 계산(effectiveZoning:483 —
// zoneEdited 최우선)과 일치해야 한다. 신규 19건(1차 리뷰 반영분)은 "부지값이 없을 때만 사용자값이
// 채택되는" 케이스만 커버했고, "부지값이 있는데 사용자가 그 값을 정정하는" 반례를 놓쳤다 — 그
// 결과 부지 자동감지("제2종일반주거 250%")를 사용자가 "자연녹지 100%"로 정정해도 기록은 여전히
// 부지값을 써 ContextHeader가 정정 전 값을 표기하는(칩=설계값과 모순) 결함이 재발했었다.
describe("DesignStudio — designData.zoneCode 기록 우선순위(R2 회귀 방지)", () => {
  beforeEach(() => {
    resetStores();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("매칭+용도지역 있는 부지에서 사용자가 용도지역을 편집하면 기록값은 사용자값이다(부지값이 이겨서는 안 됨)", async () => {
    const user = userEvent.setup();
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737", // 프로젝트 주소와 정확히 일치 → isSiteMatched=true
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    // 편집은 "직접 조정(고급)" 서랍 안에 있다 — 펼친다.
    await user.click(screen.getByRole("button", { name: /직접 조정\(고급\)/ }));

    // 용도지역 select — 부지값(제2종일반주거지역)으로 시드됐는지 대기 후 유일하게 식별.
    const zoningSelect = await screen.findByDisplayValue("제2종일반주거지역");
    await user.selectOptions(zoningSelect, "자연녹지지역");

    // 기록값은 사용자가 방금 고른 "자연녹지지역"이어야 한다(부지값 "제2종일반주거지역"이 아님).
    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.zoneCode).toBe("자연녹지지역");
    });
    expect(useProjectContextStore.getState().designData?.zoneCode).not.toBe("제2종일반주거지역");
  });

  it("사용자 편집이 없으면 종전대로 부지 확정값을 기록한다(무회귀)", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제3종일반주거지역",
      }),
    });

    renderWithQueryClient(<DesignStudio projectId="p1" />);

    await waitFor(() => {
      expect(useProjectContextStore.getState().designData?.zoneCode).toBe("제3종일반주거지역");
    });
  });
});
