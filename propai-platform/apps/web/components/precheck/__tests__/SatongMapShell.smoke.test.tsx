/**
 * SatongMapShell 스모크(W3-2) — "크래시 없이 마운트 + 핵심 랜드마크 존재"만 확인.
 * 내부 지도(SatongMultiMap)는 next/dynamic 로드라 스텁으로 대체하고,
 * 마운트 시 프로젝트 동기화(syncFromBackend → /projects)는 pending으로 고정한다.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore, type SiteAnalysisData } from "@/store/useProjectContextStore";
import { useProjectStore, type Project } from "@/store/useProjectStore";

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

// next/dynamic(SatongMultiMap)은 jsdom에서 Leaflet 실로드가 불가 — 스텁으로 대체.
// ★F6: 스텁이 받은 props(특히 onPickMany)를 캡처해두면, 지도에서 필지를 고른 것처럼
//   테스트에서 직접 호출할 수 있다(가드 발화 통합테스트용). vi.mock은 파일 상단으로 호이스트
//   되므로 캡처 변수는 vi.hoisted로 선언한다(ParcelMapWrapper.test.tsx와 동일 패턴).
const { capturedMapPropsRef } = vi.hoisted(() => ({
  capturedMapPropsRef: { current: null as null | { onPickMany?: (parcels: unknown[]) => void } },
}));

vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = (props: { onPickMany?: (parcels: unknown[]) => void }) => {
      // eslint-disable-next-line react-hooks/immutability -- 테스트 전용 스텁: 지도 props(onPickMany)를 캡처해 가드 통합테스트에서 직접 호출하기 위한 의도적 렌더 부작용
      capturedMapPropsRef.current = props;
      return <div data-testid="dynamic-map-stub" />;
    };
    return DynamicStub;
  },
}));

// 네트워크 차단: /projects 동기화·검색·레이어 조회 전부 영구 pending으로 고정.
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

describe("SatongMapShell 스모크", () => {
  it("크래시 없이 마운트되고 헤더·필지 입력 패널·지도 스텁이 보인다", () => {
    render(<SatongMapShell locale="ko" />);

    expect(
      screen.getByRole("heading", { name: /지도 위에서 입력부터 산출물 생성까지/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "통합 필지 입력" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("dynamic-map-stub")).toBeInTheDocument();
  });
});

// ── UX 트랙 B R2(리뷰어 LOW): B4 접힘·B1 h2 강등 무회귀망 ──
//   collapsed 경로를 실제로 렌더/클릭하는 테스트가 없어, early-return 무력화나 h2→h1
//   되돌림 같은 변이가 통과해도 아무 테스트도 잡지 못했다. 이 스위트가 그 공백을 메운다.
describe("SatongMapShell 접힘(B4)·문서 위계(B1) 회귀망", () => {
  // ★테스트 간 격리 — useProjectContextStore 는 모듈 전역이라 앞 케이스가 넣은 대상이 그대로
  //   남는다. 이게 없으면 "대상 없음" 케이스가 **앞 케이스의 잔존 대상으로 오염**돼, 실행 순서에
  //   따라 결과가 갈린다(실제로 그렇게 실패했다). 이 스위트가 이 describe 안에서 store 를
  //   건드리게 된 것은 P1 부터이므로 격리도 여기서 시작한다.
  beforeEach(() => {
    act(() => {
      useProjectContextStore.setState({ projectId: null, siteAnalysis: null });
      // 프로젝트 목록도 초기화한다 — P1 판정이 이 목록(주소 보유 여부)을 정착 신호로 쓴다.
      useProjectStore.setState({ projects: [], syncing: false });
    });
  });

  /**
   * ★모바일 IA P1 이후 접힘은 **대상 유무에 종속**한다 — 접힘 경로를 테스트하려면 대상을 준다.
   *   이 헬퍼가 필요해진 것 자체가 정책 변경의 증거다(종전엔 대상 없이도 접혔다).
   *
   *   ★hasTarget 은 세 항의 OR 이다(selectedParcels / siteAnalysis.address / siteAnalysis.parcels).
   *   한 항만 발화시키는 픽스처를 쓰면 나머지 항을 지우는 변이가 **생존**한다(이 저장소 규율:
   *   픽스처가 두 모집단을 갈라야 배선 변이가 죽는다). 그래서 항을 골라 시드할 수 있게 한다.
   */
  function seedTarget(via: "address" | "parcels" = "address") {
    act(() => {
      useProjectContextStore.setState({
        siteAnalysis: (via === "address"
          ? { address: "서울시 강남구 역삼동 736" }
          : { parcels: [{ pnu: "1168010100107360000", address: "역삼동 736" }] }) as SiteAnalysisData,
      });
    });
  }

  it("★B4: 대상이 있고 defaultCollapsed면 지도 스텁 없이 요약+\"지도 열기\" 토글만 뜨고, 클릭하면 펼쳐져 지도가 마운트된다", () => {
    seedTarget();
    render(<SatongMapShell locale="ko" defaultCollapsed />);

    // 접힌 상태 — 무거운 지도(스텁이라도)는 아직 마운트되지 않는다.
    expect(screen.queryByTestId("dynamic-map-stub")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "통합 필지 입력" }),
    ).not.toBeInTheDocument();
    const openButton = screen.getByRole("button", { name: /지도 열기/ });
    expect(openButton).toBeInTheDocument();

    // 펼치기 — 같은 컴포넌트 인스턴스에서 지도가 비로소 마운트된다.
    fireEvent.click(openButton);

    expect(screen.getByTestId("dynamic-map-stub")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "통합 필지 입력" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /지도 열기/ })).not.toBeInTheDocument();
  });

  it("★모바일 IA P1: 대상이 없으면 defaultCollapsed 여도 펼쳐서 렌더한다 — 유일한 주소 진입 경로를 접지 않는다", () => {
    // ★이 셸은 착지 3페이지(분석·시장·토지조서)의 **유일한 주소 진입 경로**다(그 페이지들에
    //   자체 주소 입력이 없다). 대상이 없는데 접으면 사용자가 할 수 있는 일이 "지도 열기" 한
    //   번뿐이고, 그게 사용자 지적("모바일에서 주소 입력을 못 찾겠다")의 나머지 절반이었다.
    //   ★대상을 주지 않는다 — 위 beforeEach 가 store 를 비운 상태다(그 격리가 없으면 앞
    //   케이스의 대상이 남아 이 검사가 조용히 반대 경로를 타고 통과한다).
    render(<SatongMapShell locale="ko" defaultCollapsed />);

    // 펼쳐졌다 = 주소·엑셀·프로젝트 연결이 들어 있는 입력 패널이 처음부터 보인다.
    expect(screen.getByRole("heading", { name: "통합 필지 입력" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /지도 열기/ })).not.toBeInTheDocument();
    // ★껍데기만 바뀌는 변경을 막는다 — 펼쳤으면 지도도 실제로 마운트돼야 한다(B4 비용 교환의 실체).
    expect(screen.getByTestId("dynamic-map-stub")).toBeInTheDocument();
  });

  it("★모바일 IA P1: siteAnalysis.parcels 만으로도 대상으로 친다 — hasTarget 세 항이 각각 하중을 받는다", () => {
    // ★address 로만 시드하면 parcels 항을 지우는 변이가 생존한다(픽스처가 한 모집단만 발화).
    seedTarget("parcels");
    render(<SatongMapShell locale="ko" defaultCollapsed />);

    expect(screen.getByRole("button", { name: /지도 열기/ })).toBeInTheDocument();
  });

  it("★모바일 IA P1: 대상이 늦게 도착해도(프로젝트 복원 대기) 조기 단정으로 접힘을 깨지 않는다", () => {
    // ★projectId 가 있고 **목록의 그 프로젝트가 주소를 가진** 상태 = 스냅샷 복원 비동기 대기.
    //   여기서 "대상 없음"으로 확정해 펼쳐 버리면, 복원된 프로젝트의 접힘이 깨진다.
    vi.useFakeTimers();
    try {
      act(() => {
        useProjectContextStore.setState({ projectId: "p-1", siteAnalysis: null });
      });
      render(<SatongMapShell locale="ko" defaultCollapsed />);

      // 유예 안에는 접힌 채다 — 대상 없음으로 단정하지 않았다.
      expect(screen.getByRole("button", { name: /지도 열기/ })).toBeInTheDocument();

      // 유예 안에 도착 → 이펙트 재실행 + cleanup 이 타이머를 취소해 접힘이 유지된다.
      act(() => {
        useProjectContextStore.setState({
          siteAnalysis: { address: "서울시 강남구 역삼동 736" } as SiteAnalysisData,
        });
      });
      act(() => {
        vi.advanceTimersByTime(10_000); // 유예를 한참 넘겨도 펼쳐지지 않아야 한다
      });
      expect(screen.getByRole("button", { name: /지도 열기/ })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("★모바일 IA P1: 연결됐는데 대상이 끝내 안 오면 유예 후 펼친다 — 영구 접힘 금지", () => {
    // ★R2 지적 HIGH 2건의 봉합 회귀망. 종전 2판은 프로젝트 **목록**으로 "대상이 올지"를 추론했는데
    //   ①`syncing` 은 렌더 시점 캡처값이라 콜드 스타트에서 항상 false 라 가드가 발화하지 않았고
    //   ②목록은 page_size=20 으로 잘려 오고 실패 시 조용히 비어 "목록에 없음=삭제"가 거짓이었다.
    //   지금은 목록을 아예 보지 않는다 — 기다려 보고 판정한다.
    //   ★이 케이스는 주소 없이 만든 프로젝트(setProject 를 address 없이 호출)와, 21번째 이후라
    //   목록에 안 잡히는 프로젝트, 동기화 실패를 **한꺼번에** 덮는다.
    vi.useFakeTimers();
    try {
      act(() => {
        useProjectContextStore.setState({ projectId: "p-2", siteAnalysis: null });
      });
      render(<SatongMapShell locale="ko" defaultCollapsed />);

      // 유예 전 — 아직 접힘(복원이 올 수도 있으므로 성급히 펼치지 않는다).
      expect(screen.getByRole("button", { name: /지도 열기/ })).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(2_000);
      });

      expect(screen.getByRole("heading", { name: "통합 필지 입력" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /지도 열기/ })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("★모바일 IA P1: 접힌 뒤 대상이 사라지면 다시 펼친다 — 입력이 접힌 채 갇히지 않는다", () => {
    // ★이 케이스가 1회 래치(ref)를 철회하게 만든 근거다. 래치가 있으면 "대상 있음"으로 확정된
    //   뒤 **프로젝트 연결을 해제**해도(clearProject → siteAnalysis null) 접힌 채 남아, 이 수정이
    //   없애려던 "할 게 없는 화면"으로 되돌아간다. 펼침이 (이 마운트 수명 안에서) 단방향이라
    //   래치가 막을 사용자 조작도 애초에 없었다.
    //   ※ "필지를 전부 지우는" 경로는 여기 해당하지 않는다 — clearParcels 는 parcels 만 비우고
    //     address 를 보존하므로 hasTarget 이 계속 참이다(R1 지적 MEDIUM: 초판 주석의 인과 오기).
    seedTarget();
    render(<SatongMapShell locale="ko" defaultCollapsed />);
    expect(screen.getByRole("button", { name: /지도 열기/ })).toBeInTheDocument();

    act(() => {
      useProjectContextStore.setState({ siteAnalysis: null });
    });

    expect(screen.getByRole("heading", { name: "통합 필지 입력" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /지도 열기/ })).not.toBeInTheDocument();
  });

  it("★모바일 IA P0: 접힌 셸의 유일 진입점 \"지도 열기\"는 44px 터치 타깃 하한을 지킨다", () => {
    seedTarget();
    render(<SatongMapShell locale="ko" defaultCollapsed />);

    const openButton = screen.getByRole("button", { name: /지도 열기/ });
    // packages/ui Button 의 min-h-11 플로어는 이 raw <button> 에 닿지 않는다
    // (__tests__/button.44px-floor.contract.test.tsx 스코프 밖) — 여기서 직접 잠근다.
    expect(openButton.className).toContain("min-h-11");
    // 종전 h-9(36px) 고정 높이로 되돌리는 변경을 명시적으로 막는다.
    expect(openButton.className).not.toMatch(/(^|\s)h-9(\s|$)/);
  });

  it("★B1: 지도셸 제목은 h1이 아니라 h2다(문서 개요 h1은 히어로/온보딩이 담당)", () => {
    render(<SatongMapShell locale="ko" />);

    expect(
      screen.getByRole("heading", { level: 2, name: /지도 위에서 입력부터 산출물 생성까지/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 1, name: /지도 위에서 입력부터 산출물 생성까지/ }),
    ).not.toBeInTheDocument();
  });
});

// ── 모바일 IA P0: 입력이 지도보다 먼저 온다(DOM 순서) 회귀망 ──
//   ★이 계약이 필요한 이유: 종전 결함은 `order-2/order-1`(CSS)로 <xl 에서 **시각 순서만**
//   뒤집은 것이었다. DOM 순서는 그대로였으므로 "DOM 순서만 보는" 테스트로는 재발을 못 잡는다.
//   그래서 두 축을 함께 잠근다 — ①DOM 순서(스크린리더·탭 순서의 진실) ②order 클래스 부재
//   (화면 순서의 진실). 둘 중 하나만 잠그면 나머지 축으로 결함이 되돌아온다.
describe("SatongMapShell 모바일 IA(P0) — 입력 우선 배치", () => {
  function renderShellAndGetPanes() {
    render(<SatongMapShell locale="ko" />);

    const intake = screen
      .getByRole("heading", { name: "통합 필지 입력" })
      .closest("aside");
    const map = screen.getByTestId("dynamic-map-stub").closest("section");

    // ★공허 진리 방지 — 못 찾았는데 뒤 단언들이 조용히 통과하는 일이 없도록 먼저 못 박는다.
    expect(intake, "필지 입력 aside 를 찾지 못했다").not.toBeNull();
    expect(map, "지도 section 을 찾지 못했다").not.toBeNull();
    // 둘이 같은 그리드의 형제여야 순서 비교가 의미를 갖는다(엉뚱한 조상 매칭 방지).
    expect(intake!.parentElement).toBe(map!.parentElement);

    return { intake: intake!, map: map! };
  }

  it("①DOM 순서: 필지 입력(aside)이 지도(section)보다 먼저 온다", () => {
    const { intake, map } = renderShellAndGetPanes();

    // Node.DOCUMENT_POSITION_FOLLOWING = 4 — map 이 intake '뒤'에 있다는 뜻.
    expect(intake.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("②order 클래스 금지: CSS order 로 시각 순서를 되뒤집는 회귀를 막는다", () => {
    const { intake, map } = renderShellAndGetPanes();

    // order-1 / order-2 / xl:order-none / -order-1 등 어떤 형태의 order 유틸도 허용하지 않는다.
    // (DOM 순서가 곧 화면 순서라는 정책 — ComprehensiveAnalysisPanel 관점 스토리라인과 동일)
    // ★`\S*order-` 처럼 느슨하게 쓰면 `border-[...]` 를 오탐한다(첫 작성 시 실제로 걸렸다) —
    //   반드시 유틸 경계(선행 공백/변형자, 후행 공백)와 order 값 문법까지 못 박는다.
    const ORDER_UTIL = /(?:^|\s)-?(?:[a-z0-9-]+:)*-?order-(?:none|first|last|\d+|\[[^\]]*\])(?=\s|$)/;
    expect(intake.className).not.toMatch(ORDER_UTIL);
    expect(map.className).not.toMatch(ORDER_UTIL);
  });
});

// ── F6: 교차오염 가드 발화 시 선택 유지 통합테스트 ──
//   기존 프로젝트(상도동)에 연결된 상태에서 지역이 다른 필지(용인 고기동)를 지도에서 고르면
//   addParcels 가드가 detachProjectCarryingSelection으로 프로젝트를 해제하는데, 이 해제가
//   PR#221 전환 이펙트에 '프로젝트 전환'으로 오인돼 방금 고른 선택을 지워버리면 안 된다(F1 회귀).
function makeGuardTestProject(partial: Partial<Project>): Project {
  return {
    id: "proj-sangdo",
    name: "상도동 프로젝트",
    type: "residential",
    pnu: "",
    address: "서울특별시 동작구 상도동 123",
    area: "500㎡",
    status: "draft",
    createdAt: "2026-06-01T00:00:00.000Z",
    ...partial,
  };
}

function makeGuardTestSite(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

describe("SatongMapShell 연결 프로젝트 가드", () => {
  beforeEach(() => {
    capturedMapPropsRef.current = null;
    act(() => {
      useProjectStore.setState({ projects: [makeGuardTestProject({})], syncing: false });
      useProjectContextStore.setState({
        projectId: "proj-sangdo",
        projectName: "상도동 프로젝트",
        projectStatus: "draft",
        siteAnalysis: makeGuardTestSite({ address: "서울특별시 동작구 상도동 123" }),
      });
    });
  });

  afterEach(() => {
    act(() => {
      useProjectStore.setState({ projects: [], syncing: false });
      useProjectContextStore.setState({
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
      });
    });
  });

  it("가드가 프로젝트를 해제해도 방금 고른 지역불일치 필지 선택은 유지된다", () => {
    render(<SatongMapShell locale="ko" />);

    // 지도에서 상도동 프로젝트와 지역이 다른 용인 고기동 필지를 고른 상황을 재현.
    act(() => {
      capturedMapPropsRef.current?.onPickMany?.([
        {
          found: true,
          address: "경기도 용인시 수지구 고기동 689",
          pnu: "4146025629108900000",
          lat: 37.32,
          lon: 127.11,
        },
      ]);
    });

    // 선택 필지 카드에 방금 고른 주소가 남아있어야 한다(F1 회귀 없음 — 전환 이펙트가 와이프 안 함).
    // U4 카드 압축: 목록엔 짧은 지번, 전체 주소는 카드 title 속성에 보존.
    expect(screen.getByText("고기동 689")).toBeInTheDocument();
    expect(screen.getByTitle(/경기도 용인시 수지구 고기동 689/)).toBeInTheDocument();
    // 가드가 발화해 '새 프로젝트로 등록' 모드로 전환했다는 안내도 함께 보여야 한다.
    expect(
      screen.getByText("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다."),
    ).toBeInTheDocument();
  });
});
