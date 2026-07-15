import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DesignWorkspace } from "@/components/design/DesignWorkspace";
import { useProjectContextStore, type DesignData, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

vi.mock("@/components/design/DesignStudio", () => ({
  DesignStudio: ({ onOpen3D }: { onOpen3D?: () => void }) => (
    <div>
      <span>mock site panel</span>
      <button type="button" onClick={onOpen3D}>
        mock open draw
      </button>
    </div>
  ),
}));

vi.mock("@/components/design/DesignGenPanel", () => ({
  DesignGenPanel: () => <div>mock design generation panel</div>,
}));

vi.mock("@/components/design/CadBimIntegrationPanel", () => ({
  CadBimIntegrationPanel: () => <div>mock cad bim panel</div>,
}));

vi.mock("@/components/design/MetricBar", () => ({
  MetricBar: () => <div>mock metric bar</div>,
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

function makeDesign(partial: Partial<DesignData>): DesignData {
  return {
    totalGfaSqm: null,
    floorCount: null,
    buildingType: null,
    bcr: null,
    far: null,
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

describe("DesignWorkspace", () => {
  beforeEach(() => {
    resetStores();
  });

  it("현 프로젝트와 다른 주소의 부지분석·설계값이 있으면 추천안과 CAD 패널을 차단한다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "경기도 성남시 분당구 정자동 178-1",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1200, floorCount: 8, far: 240 }),
    });

    render(<DesignWorkspace projectId="p1" />);

    expect(screen.getByText("주소 정합성 차단")).toBeInTheDocument();
    expect(screen.getByText(/정본 메트릭 잠금/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));
    expect(screen.getByText("현 프로젝트 기준 부지분석이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock design generation panel")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("도면 편집 전에 건축개요 추천안이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock cad bim panel")).not.toBeInTheDocument();
  });

  it("부지 기준은 맞지만 추천안이 없으면 생성 패널만 열고 CAD는 잠근다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
    });

    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));
    expect(screen.getByText("mock design generation panel")).toBeInTheDocument();
    expect(screen.getByText("mock metric bar")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("도면 편집 전에 건축개요 추천안이 필요합니다.")).toBeInTheDocument();
    expect(screen.queryByText("mock cad bim panel")).not.toBeInTheDocument();
  });

  it("현재 부지 기준 설계안이 있으면 CAD·BIM 편집실을 연다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1000, floorCount: 5, buildingType: "공동주택" }),
    });

    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /도면 편집/ }));
    expect(screen.getByText("mock cad bim panel")).toBeInTheDocument();
  });

  // 리뷰 지적 #1 회귀 테스트: 완료된 프로젝트(1차·2차 모두 complete)를 site 뷰(기본 진입 뷰)로
  //   재진입하면 — 흔한 진입경로 — 흐름 바 CTA는 dock이 "다음"으로 강조하는 것과 동일한 단계
  //   (nextView=첫 미완료 단계=draw)를 가리켜야 한다. 예전엔 sequentialNext[view]가 "site의
  //   순차 다음"인 이미 끝난 generate를 다시 가리켜 "추천안 생성 시작"을 오지시했다.
  it("완료 프로젝트를 site 뷰로 재진입하면 흐름 바 CTA가 첫 미완료 단계(draw)를 가리킨다", () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      designData: makeDesign({ totalGfaSqm: 1000, floorCount: 5, buildingType: "공동주택" }),
    });

    render(<DesignWorkspace projectId="p1" />);

    // 기본 진입 뷰=site, siteState·generateState 모두 complete → CTA는 draw(nextView)를 가리켜야 한다.
    expect(screen.getByRole("button", { name: /CAD·BIM 편집 열기/ })).toBeInTheDocument();
    // 예전 버그: 이미 complete인 generate로 되돌아가라는 CTA가 떴다 — 회귀 방지.
    expect(screen.queryByRole("button", { name: /추천안 생성 시작/ })).not.toBeInTheDocument();
  });

  // 리뷰 지적 #2 회귀 테스트: generate가 blocked인 이유가 "주소 불일치"가 아니라 "부지분석 자체가
  //   아직 없음"(!hasSiteBasis)일 때, 흐름 바 hint는 뷰포트 PipelineBlocker와 동일한 근본원인에서
  //   파생된 동일 문구를 써야 한다(단일 소스). 예전엔 view==="generate"라는 이유만으로
  //   flowHintNeedDesign("추천안을 적용하라")을 오안내했다 — 정작 필요한 건 부지분석이었다.
  it("부지분석 자체가 없어 generate가 차단되면 흐름 바 hint가 뷰포트 블로커와 동일 문구를 쓴다", async () => {
    // resetStores() 기본값 그대로: siteAnalysis=null → hasSiteBasis=false·hasAddressMismatch=false.
    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));

    // 뷰포트 블로커와 흐름 바 hint가 동일 텍스트를 공유(단일 소스) — 최소 2곳(블로커 본문 + 흐름 바)에서 노출.
    const sharedReason = screen.getAllByText(
      "주소·용도지역·대지면적이 준비되면 건축개요 Top-N을 생성할 수 있습니다.",
    );
    expect(sharedReason.length).toBeGreaterThanOrEqual(2);
    // 예전 오안내 문구("추천안을 하나 적용하면...")는 나타나지 않아야 한다(회귀 방지).
    expect(screen.queryByText(/추천안\(건축개요\)을 하나 적용하면/)).not.toBeInTheDocument();
  });

  // R2 리뷰 회귀 테스트(HIGH): 앞선 리뷰 봉합(#1 CTA 타깃 nextView 정렬)이 hint 분기를
  //   `ctaTarget===null ? flowTerminal : ...`로 바꾸면서 새 결함을 유입했다 — ctaTarget은
  //   "현재 뷰 자체가 곧 nextView(아직 미완료인 최전선 단계)"일 때도 null이 되므로, 신규/미확정
  //   프로젝트의 기본 진입 뷰(site·ready)에서도 무조건 "마지막 단계 — 도면 편집"을 오표기했다
  //   (1단계인데 "마지막 단계"라 날조). 봉합: hint의 terminal 분기를 view==="draw"에만 매핑.
  it("신규/미확정 프로젝트의 기본 진입(site·ready)에서 흐름 바가 '마지막 단계'를 오표기하지 않는다", () => {
    // resetStores() 기본값 그대로: siteAnalysis=null → siteState="ready"(미완료·미차단).
    render(<DesignWorkspace projectId="p1" />);

    // 오표기 회귀 방지 — 1단계(site)인데 draw 전용 종료 문구가 뜨면 안 된다.
    expect(
      screen.queryByText("마지막 단계 — 검증된 도면을 CAD·BIM으로 편집합니다."),
    ).not.toBeInTheDocument();
    // 복원된 선행요건 안내 — site가 ready일 때 이 라벨이 실제로 표시돼야 한다(사문화 회귀 방지).
    expect(
      screen.getByText("부지 조건(주소·용도지역·대지면적)을 확정하면 다음 단계가 열립니다."),
    ).toBeInTheDocument();
  });

  it("부지확정·설계 전(generate·ready)에서 흐름 바가 선행요건 안내를 보여주고 '마지막 단계'를 오표기하지 않는다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
      // designData 없음 → hasDesignBasis=false → generateState="ready"(complete도 blocked도 아님).
    });

    render(<DesignWorkspace projectId="p1" />);

    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));

    // 복원된 선행요건 안내 — generate가 ready일 때 이 라벨이 실제로 표시돼야 한다(사문화 회귀 방지).
    expect(
      screen.getByText("추천안(건축개요)을 하나 적용하면 다음 단계가 열립니다."),
    ).toBeInTheDocument();
    // 오표기 회귀 방지 — 2단계(generate)인데 draw 전용 종료 문구가 뜨면 안 된다.
    expect(
      screen.queryByText("마지막 단계 — 검증된 도면을 CAD·BIM으로 편집합니다."),
    ).not.toBeInTheDocument();
  });
});
