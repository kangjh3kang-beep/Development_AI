import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DesignWorkspace } from "@/components/design/DesignWorkspace";
import { useProjectContextStore, type DesignData, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";
import { SATONG_CONTENT_Z } from "@/lib/satong-map-z";
import { createsStackingContext } from "@/lib/stacking-context";

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

  // ── Pillar C(준비 대시보드) — 잠긴 단계는 빈 자물쇠 화면 대신 해제 요건 체크리스트 +
  //    산출물 '예시 구조' 미리보기를 보여준다. 미충족 항목엔 바로가기 버튼이 붙는다. ──
  it("생성 단계가 부지 기준 미충족으로 잠기면 준비 대시보드가 요건 체크리스트와 예시 구조를 보여준다", async () => {
    // 주소·면적은 있으나 용도지역이 없어 hasSiteBasis=false → generate 잠금(부분 충족 상태).
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: null,
      }),
    });

    render(<DesignWorkspace projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: /추천안 만들기/ }));

    // 해제 요건 체크리스트 — 3요건(주소·용도지역·대지면적)이 표기된다.
    expect(screen.getByText("해제 요건")).toBeInTheDocument();
    expect(screen.getByText("용도지역")).toBeInTheDocument();
    // 미충족 항목(용도지역)엔 부지 조건으로 이동하는 바로가기 버튼이 있다(정확히 1개 — 나머지 2요건은 충족).
    expect(screen.getByRole("button", { name: "부지 조건 확인하러 가기" })).toBeInTheDocument();
    // 산출물 미리보기는 '예시 구조'로 정직 라벨링(무목업 — 날조 아님).
    expect(screen.getByText("예시 구조")).toBeInTheDocument();
    // 생성 패널 본체는 잠겨 아직 렌더되지 않는다.
    expect(screen.queryByText("mock design generation panel")).not.toBeInTheDocument();
  });

  // ── Pillar A(중복 제거·레일 단일화) — dock(좌측 파이프라인 레일)이 펼쳐진 기본 상태에선
  //    흐름바의 3단계 진행 dots를 숨겨 파이프라인 표현을 레일 하나로 단일화한다. dock을 접으면
  //    컴팩트 진행 인디케이터가 흐름바에 나타난다. 또 '분석 주소'는 상단 ContextHeader 정본으로
  //    이관돼 우측 레일에서 제거된다(3중 중복 해소). ──
  it("dock 펼침 시 흐름바 진행 dots를 숨기고(레일 단일화) 우측 레일에서 '분석 주소'를 제거한다", async () => {
    useProjectContextStore.setState({
      siteAnalysis: makeSite({
        address: "서울특별시 강남구 역삼동 737",
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
      }),
    });

    render(<DesignWorkspace projectId="p1" />);

    // dock 펼침(기본) → 흐름바 진행 dots(role=group)는 중복이라 숨긴다.
    expect(
      screen.queryByRole("group", { name: /설계 흐름 진행 상태/ }),
    ).not.toBeInTheDocument();
    // 분석 주소 카드는 우측 레일에서 제거(상단 ContextHeader가 정본).
    expect(screen.queryByText("분석 주소")).not.toBeInTheDocument();

    // dock 접기 → 컴팩트 진행 인디케이터(dots)가 흐름바에 나타난다.
    await userEvent.click(screen.getByRole("button", { name: "단계 패널 접기" }));
    expect(
      screen.getByRole("group", { name: /설계 흐름 진행 상태/ }),
    ).toBeInTheDocument();
  });
});

// ── 층위 계약: 이 워크스페이스가 **스태킹 컨텍스트를 만들지 않는다** ──
//   ★왜 계약인가: 배경(absolute inset-0)과 본문(relative)이 각각 z 를 가지면 본문이 스태킹
//   컨텍스트가 되고, 그 안의 CAD **전체화면**(fixed z-[9990])이 실효 10 으로 갇힌다 —
//   앱 헤더(1000)·FAB(95) 아래로 깔려 "전체화면"이 전역 크롬을 못 덮었다. z 를 올려도
//   소용없는 상태였으므로 **컨텍스트 자체를 만들지 않는 것**이 계약이다.
//   ★소스 grep 이 아니라 **렌더된 class** 로 본다(주석 처리 변이 면역 — CLAUDE.md 회귀망 규율 A-3).
describe("DesignWorkspace 층위 계약 — 스태킹 컨텍스트 금지", () => {
  it("★워크스페이스 **직계 래퍼**가 스태킹 컨텍스트를 만들지 않는다", () => {
    resetStores();
    const { container } = render(<DesignWorkspace projectId="p1" />);

    // ★스코프를 직계 자식으로 한정한다(리뷰 지적 H3):
    //   · 넓게 훑으면 CadBim 등 하위 패널의 **정상적인** 내부 z(relative z-10·z-30)가 위반으로
    //     잡혀 위양성이 된다(규율 A-6).
    //   · 반대로 종전 셀렉터는 `absolute|relative` 만 봐서 실재하는 `sticky z-20` 컨텍스트를
    //     **못 봤다**(거짓 초록). 전체화면이 갇히느냐는 **직계 래퍼**가 컨텍스트인지에 달렸다.
    const root = container.firstElementChild;
    expect(root, "워크스페이스 루트를 찾지 못했다").not.toBeNull();
    const direct = Array.from(root!.children) as HTMLElement[];
    // 공허 진리 방지 — 직계 자식이 없으면 아래 검사가 무의미하다.
    expect(direct.length, "직계 자식이 없다 — 렌더가 비었다").toBeGreaterThan(0);

    // 스태킹 컨텍스트 판정은 **공용 판정기**에 맡긴다(lib/stacking-context.ts).
    //   ★왜 공용인가: 종전 이 자리의 정규식은 `isolate` **하나만** 봤는데 바로 위 주석은
    //     "transform/filter 유틸"까지 본다고 적혀 있었다 — 코드가 갖지 않은 면역을 주장한
    //     주석이다(규율 C-11). 같은 판정을 주소 팝오버 가드도 따로 들고 있었고, 그쪽은
    //     Tailwind **v3** 토큰을 찾고 있었다(저장소는 v4 — `backdrop-blur-*` 120건 미탐).
    //     판정을 한 곳으로 모아 한 곳을 고치면 두 가드가 함께 따라오게 한다.
    const scanDirect = () =>
      [root as HTMLElement, ...direct]
        .filter((el) => createsStackingContext((el.className ?? "").toString()))
        .map((el) => (el.className ?? "").toString().slice(0, 80));

    const contexts = scanDirect();

    expect(
      contexts,
      `워크스페이스 직계에 스태킹 컨텍스트가 생겼다 — 내부 전체화면(z-${SATONG_CONTENT_Z.appFullscreen})이 갇힌다:\n${contexts.join("\n")}`,
    ).toHaveLength(0);

    // ★★"위반 0"이 참인 이유가 **판정기가 아무것도 안 잡기 때문**일 수 있다.
    //   실제로 그랬다: `createsStackingContext` 를 통째로 `false` 로 만들어도 이 테스트는
    //   초록이었다(적대검증 실측). 위 단언은 **차가 0인 픽스처** 위에 서 있었던 셈이다
    //   — 이 PR 이 팝오버 가드에서 고친 바로 그 결함을 여기엔 적용하지 않았다(규율 D-16).
    //   그래서 같은 필터에 **알려진 위반 모양**을 태워 판별력을 함께 확인한다.
    const probe = direct[0];
    const original = probe.className;
    probe.className = `${original} sticky z-20`;
    try {
      expect(
        scanDirect().length,
        "판정기가 `sticky z-20` 조차 잡지 못한다 — 위 '위반 0' 은 공허하다",
      ).toBeGreaterThan(0);
    } finally {
      probe.className = original;
    }
  });

});
