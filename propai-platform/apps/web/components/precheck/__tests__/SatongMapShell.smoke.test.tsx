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
  it("★B4: defaultCollapsed면 지도 스텁 없이 요약+\"지도 열기\" 토글만 뜨고, 클릭하면 펼쳐져 지도가 마운트된다", () => {
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

  it("★모바일 IA P0: 접힌 셸의 유일 진입점 \"지도 열기\"는 44px 터치 타깃 하한을 지킨다", () => {
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
