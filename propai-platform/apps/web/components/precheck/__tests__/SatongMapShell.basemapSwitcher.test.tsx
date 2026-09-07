/**
 * 베이스맵 스위처 — terrain 컨트롤 상호배타 계약 + 우상단 레일 통합(2026-07-23).
 *   ① 레일 '베이스맵' 버튼으로 열기 전에는 스와치가 없다(도크 잔재 회귀 방지).
 *   ② 기본은 '일반' 활성. ③ '위성' 클릭 → 위성만 활성(상호배타). ④ '일반' 복귀 가능.
 *   ⑤ 레이어 팝오버와 상호배타(같은 좌표를 쓰므로 동시 표시 금지). ⑥ Esc 닫힘.
 */
import type { ReactNode } from "react";
import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell, SATONG_MAP_SHELL_LAYERS } from "@/components/precheck/SatongMapShell";
import {
  isRenderableSatongMapLayer,
  resolveVWorldBaseLayer,
  type SatongMapLayerState,
} from "@/lib/satong-map-layers";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import {
  defaultEnabledLayerIds,
  defaultSatongMapControls,
  useSatongMapPrefs,
} from "@/store/useSatongMapPrefsStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// ★R1(M): 스텁이 슬롯을 '안 그리는' 것만으로는 도크 잔재를 감시할 수 없다(누가
//   bottomDockSlot을 되돌려도 스텁이 삼켜 테스트가 통과한다). props를 캡처해 전달
//   계약 자체를 단언한다.
const capturedMapProps: Record<string, unknown>[] = [];
vi.mock("next/dynamic", () => ({
  default: () => {
    // ★H2 봉합 이후 필수: 레일·팝오버·배지행은 topRightSlot으로 지도 래퍼 '안'에 렌더된다
    //   (풀스크린에서 살아남게 하는 봉합). 스텁도 실컴포넌트와 동일하게 슬롯을 렌더한다.
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub">{props.topRightSlot as ReactNode}</div>;
    };
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
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending), put: vi.fn(pending),
      patch: vi.fn(pending), delete: vi.fn(pending), getV2: vi.fn(pending), postV2: vi.fn(pending),
      putV2: vi.fn(pending), deleteV2: vi.fn(pending),
    },
  };
});

function resetStores() {
  act(() => {
    useProjectStore.setState({ projects: [], syncing: false });
    useProjectContextStore.setState({ projectId: null, projectName: "", projectStatus: "", siteAnalysis: null });
    // ★★2026-09-07 — **지도 설정 스토어가 빠져 있었다.** 종전엔 `cadastre` 가 기본 ON 이라
    //   레이어를 켜는 테스트가 있어도 «원래 켜져 있음» 과 구별되지 않아 누수가 보이지 않았다.
    //   기본이 꺼짐이 되자 **앞 테스트가 켠 지적이 다음 테스트로 샜다**(단독 실행은 통과,
    //   전체 실행은 실패 — 순서 의존의 전형). 여기서 함께 초기화한다.
    useSatongMapPrefs.setState({
      enabledLayerIds: defaultEnabledLayerIds(),
      enabledLayersCustomized: false,
      controlsByLayer: defaultSatongMapControls(),
    });
  });
}

// ★R1 MEDIUM-A: jsdom의 fireEvent.click은 선행 mouseenter를 합성하지 않는다. 실브라우저는
//   반드시 mouseenter→click 순서라, click만 쏘는 테스트는 '현실에 없는 순서'를 고정한다
//   (그래서 첫 클릭이 팝오버를 닫는 HIGH-A가 초록으로 통과했다). 레일 상호작용은 전부 이 헬퍼로.
function hoverClick(el: HTMLElement) {
  fireEvent.mouseEnter(el);
  fireEvent.click(el);
}

function openBasemapPopover() {
  hoverClick(screen.getByRole("button", { name: "베이스맵 선택" }));
}

describe("SatongMapShell 베이스맵 스위처(레일 통합)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });
  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("★하단 도크로 스위처를 전달하지 않는다(도크 잔재 회귀 방지 — props 계약 단언)", () => {
    capturedMapProps.length = 0;
    render(<SatongMapShell locale="ko" />);
    expect(capturedMapProps.length).toBeGreaterThan(0);
    expect(capturedMapProps.at(-1)).not.toHaveProperty("bottomDockSlot");
  });

  it("★레일 버튼으로 열기 전에는 스와치가 없다", () => {
    render(<SatongMapShell locale="ko" />);
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("기본 '일반' 활성 → '위성' 클릭 시 상호배타 전환, '일반' 복귀 가능", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();

    const base = screen.getByRole("button", { name: "베이스맵: 일반" });
    const satellite = screen.getByRole("button", { name: "베이스맵: 위성" });

    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(satellite);
    expect(satellite).toHaveAttribute("aria-pressed", "true");
    expect(base).toHaveAttribute("aria-pressed", "false");
    // 상호배타 — 하이브리드/회색도 비활성 유지
    expect(screen.getByRole("button", { name: "베이스맵: 하이브리드" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(base);
    expect(base).toHaveAttribute("aria-pressed", "true");
    expect(satellite).toHaveAttribute("aria-pressed", "false");
  });

  it("★레이어 팝오버와 상호배타 — 같은 좌표(right-20 top-20)에 둘이 겹치지 않는다", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();

    // 레일의 레이어 버튼(지적도)을 누르면 베이스맵 팝오버는 닫힌다.
    hoverClick(screen.getByRole("button", { name: "지적도" }));
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();

    // 다시 베이스맵을 열면 정상 표시(토글 무결성).
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  // ★UX 트랙 C2(2026-07-24, 사용자 지적 — '편의성 부조화'): 이 테스트는 종전에 좌상단
  //   활성 레이어 칩이 <button>이라 클릭하면 handleLayerClick을 거쳐 베이스맵 팝오버를
  //   닫던 "근원 봉합" 경로를 고정했었다. 그런데 그 button 자체가 버그였다 — 클릭하면
  //   레이어를 끄면서 동시에(방금 끈) 레이어의 설정 팝오버를 여는 이중 조작이 됐다.
  //   레이어 조작은 우상단 레일 하나로 일원화하고 칩은 표시 전용 배지로 강등했으므로,
  //   "칩 클릭이 팝오버를 닫는다"는 이 계약은 의도적으로 폐기한다(대체 경로=레일, 바로
  //   위 "★레이어 팝오버와 상호배타" 테스트가 이미 그 경로로 동일 불변식을 고정한다).
  //   대신 "칩이 더 이상 클릭 가능한 button이 아니다"라는 새 계약을 고정해 회귀를 막는다.
  it("★UX C2: 좌상단 활성 레이어 칩은 비인터랙티브 배지다 — button이 아니고 클릭해도 무동작", () => {
    render(<SatongMapShell locale="ko" />);
    // ★2026-09-07 — 종전엔 «지적도는 초기 활성이라 칩이 이미 존재한다» 로 **기본값에 얹혀** 있었다.
    //   기본이 꺼짐으로 바뀌자 이 테스트가 빨개졌다. **명제(칩은 비인터랙티브 배지)는 그대로**이므로
    //   ***그 상태를 만들어서*** 검사한다 — 조건부 렌더 요소는 상태를 만들어 태우는 것이 규율이다.
    const railButton = screen.getByRole("button", { name: "지적도" });
    hoverClick(railButton);
    fireEvent.click(screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ }));
    fireEvent.keyDown(window, { key: "Escape" });

    // 칩의 접근성 명칭은 레일 버튼과 동일(aria-label="지적도")이지만, 칩은 button 역할이
    // 아니므로 getByRole("button", ...)은 레일 버튼 단 하나만 찾는다(칩=button 2개였다면
    // 실패 — 조건부 단언 없이 명시적으로 개수를 고정).
    expect(screen.getAllByRole("button", { name: "지적도" })).toEqual([railButton]);

    // 배지 자체(표시 기능)는 그대로 화면에 남는다 — 텍스트 노드로 존재(aria-label이 아닌
    // 실제 렌더 텍스트라 getByText로 잡힌다. 레일 버튼은 아이콘뿐이라 겹치지 않는다).
    const chip = screen.getByText("지적도");
    expect(chip.tagName).toBe("SPAN");

    // 클릭해도 베이스맵 팝오버 상태에 아무 영향이 없다(무동작 확인).
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
    fireEvent.click(chip);
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });

  it("Esc로 닫힌다(레이어 팝오버와 동일 닫힘 계약)", () => {
    render(<SatongMapShell locale="ko" />);
    openBasemapPopover();
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
  });
});

/**
 * 레일 상호작용 재설계(2026-07-23 사용자 UX 요청2) — 탐색(browse)과 확정(commit) 분리.
 *   ① 레일 롤오버/클릭은 팝오버만 연다(지도 레이어를 켜지 않는다).
 *   ② 다른 항목으로 이동하면 그 항목 팝오버로 전환된다.
 *   ③ 확정은 팝오버 안(헤더 on/off·컨트롤)에서만 일어나고, 확정 후에도 팝오버는 열려 있다.
 */
describe("SatongMapShell 레일 — 탐색/확정 분리", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });
  afterEach(() => {
    window.sessionStorage.clear();
    resetStores();
  });

  it("★레일 클릭은 팝오버만 열고 레이어를 켜지 않는다(보기=적용 결합 해제)", () => {
    render(<SatongMapShell locale="ko" />);
    // 용도지역는 기본 OFF인 렌더 가능 레이어.
    hoverClick(screen.getByRole("button", { name: "용도지역" }));
    // 팝오버는 열렸고
    expect(screen.getByRole("button", { name: /지도에 표시/ })).toBeTruthy();
    // 확정 전이므로 '지도 표시 중'이 아니다(=아직 안 켜짐).
    expect(screen.queryByRole("button", { name: "지도 표시 중" })).toBeNull();
  });

  it("★롤오버로 팝오버가 열리고, 다른 항목으로 이동하면 전환된다", () => {
    // ★hover '전환' 의도 지연(A안) 이후 갱신: **첫 열기는 여전히 즉시**지만, 이미 팝오버가
    //   열려 있을 때의 **전환**은 임계(150ms) 체류를 요구한다(2열 레일에서 팝오버로 가는 길에
    //   스치는 아이콘이 팝오버를 갈아치우던 사용자 지적 회귀의 봉합).
    //   이 테스트가 지키는 계약은 "다른 항목으로 이동하면 전환된다"이므로, 계약은 그대로 두고
    //   체류를 만들어 준다(즉시성은 railHoverIntent 테스트가 ①/②로 분리해 고정한다).
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      fireEvent.mouseEnter(screen.getByRole("button", { name: "용도지역" }));
      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();

      fireEvent.mouseEnter(screen.getByRole("button", { name: "지적도" }));
      act(() => { vi.advanceTimersByTime(300); }); // 머물렀다 = 의도적 전환
      expect(screen.getByRole("heading", { level: 3, name: "지적도" })).toBeTruthy();
      expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("★확정은 팝오버 안에서 — 누른 뒤에도 팝오버가 닫히지 않는다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: "용도지역" }));

    fireEvent.click(screen.getByRole("button", { name: "지도에 표시" }));
    // 켜졌고(라벨 전환) 팝오버는 그대로 열려 있다(결과 확인 가능).
    expect(screen.getByRole("button", { name: "지도 표시 중" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
  });

  it("베이스맵 롤오버도 팝오버를 연다(레일 형제 동일 계약)", () => {
    render(<SatongMapShell locale="ko" />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: "베이스맵 선택" }));
    expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
  });
});

/**
 * R1 MEDIUM-6 — 변이 생존 구간 봉합: hover 경로의 3패널 배타·닫힘 경로·재진입 무깜빡임.
 */
describe("SatongMapShell 레일 — 팝오버 배타·닫힘 계약", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★같은 항목에 재진입해도 닫히지 않는다(롤오버 깜빡임 방지 계약)", () => {
    render(<SatongMapShell locale="ko" />);
    const btn = screen.getByRole("button", { name: /용도지역/ });
    fireEvent.mouseEnter(btn);
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    fireEvent.mouseEnter(btn); // 재진입
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
  });

  it("★레일 클릭으로 팝오버를 닫을 수 있다(R1 LOW-1 닫기 경로 복원)", () => {
    render(<SatongMapShell locale="ko" />);
    const btn = screen.getByRole("button", { name: /용도지역/ });
    hoverClick(btn);
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    hoverClick(btn); // 같은 항목 재클릭 = 닫기(고정분만)
    expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
  });

  it("★X 버튼으로 닫힌다(닫힘 경로 회귀 보호)", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: /용도지역/ }));
    fireEvent.click(screen.getByRole("button", { name: "레이어 설정 닫기" }));
    expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
  });

  // ★★2026-09-07(사용자 신고②) — 종전 계약은 *"terrain 은 on/off 를 노출하지 않는다"* 였고
  //   사유는 *"끄면 베이스맵이 조용히 롤백되고 라벨이 거짓이 된다"* 였다. **사유는 여전히 참**이다.
  //   달라진 것은 처방이다 — 토글을 **숨기는 대신** 레일 항목 자체를 없앴다(그 항목이 베이스맵
  //   스위처의 **복제본**이었다). 끌 수 있는 UI 가 존재하지 않으므로 롤백도 도달 불가다.
  //   ⇒ 명제를 **더 강한 형태로 교체**한다: 「토글이 없다」 → 「레일에 없다」.
  it("★terrain 은 레일 레이어가 **아니다** — 끄는 UI 자체가 없어 베이스맵 롤백이 도달 불가다", () => {
    expect(SATONG_MAP_SHELL_LAYERS.some((l) => l.id === "terrain")).toBe(false);
    render(<SatongMapShell locale="ko" />);
    expect(screen.queryByRole("button", { name: /지형도·항공뷰/ })).toBeNull();
    // ★대조군 — 레일 자체는 살아 있다(조회기 생존). 이게 없으면 «전부 사라짐»도 통과한다.
    expect(screen.getByRole("button", { name: /지적도/ })).toBeTruthy();
  });
});

/**
 * R1 재검증 HIGH-A/B 자물쇠 — 실브라우저 이벤트 순서에서만 드러나던 결함.
 */
describe("SatongMapShell 레일 — 실이벤트 순서 계약", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★HIGH-A: hover 후 클릭해도 팝오버가 열려 있다(첫 클릭이 닫으면 안 된다)", () => {
    render(<SatongMapShell locale="ko" />);
    const btn = screen.getByRole("button", { name: /용도지역/ });
    fireEvent.mouseEnter(btn);          // 실브라우저는 click 앞에 반드시 발생
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    fireEvent.click(btn);               // 클릭 = 고정 승격(닫기 아님)
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
  });

  it("★HIGH-B: hover로 연 뒤 레일을 벗어나도 팝오버로 이동하면 유지된다(확정 도달성)", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const btn = screen.getByRole("button", { name: /용도지역/ });
      fireEvent.mouseEnter(btn);
      const popover = screen.getByRole("dialog", { name: "용도지역" });

      fireEvent.mouseLeave(btn.closest("div")!); // 레일 이탈(유예 시작)
      fireEvent.mouseEnter(popover);             // 팝오버 진입 → 유예 취소
      act(() => { vi.advanceTimersByTime(400); });

      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("★클릭 고정분은 레일 이탈로 닫히지 않는다(컨트롤 조작 도달성)", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const btn = screen.getByRole("button", { name: /용도지역/ });
      hoverClick(btn); // 고정
      fireEvent.mouseLeave(btn.closest("div")!);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  /**
   * ★★2026-09-07 계약 변경 — 이 락은 **옛 계약을 잠그고 있었다.**
   *
   * 종전: *"cadastre 는 on/off 미노출 — 끌 수 없어 토글이 죽은 버튼이 된다"*.
   * 사용자 신고로 뒤집혔다 — *"지적 경계선이 항상 나타나는데 기본은 없어야 하지 않나?"*
   * 그리고 「끌 수 없다」의 **사유가 실재하지 않았다**(선택은 지적 타일과 독립).
   *
   * ★***락이 옛 계약을 잠그고 있으면 그것은 회귀 신호가 아니라 「낡은 잠금」이다.***
   *   계약이 바뀌면 락도 바뀐다 — 다만 **무엇이 바뀌었는지 여기 남긴다.**
   */
  it("★cadastre(지적도)는 이제 on/off 를 노출한다 — 죽은 버튼이 살아났다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: "지적도" }));
    expect(screen.getByRole("heading", { level: 3, name: "지적도" })).toBeTruthy();
    // ★종전엔 이 버튼이 **없었다**(queryBy → null). 이제 있어야 한다.
    expect(screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ })).toBeTruthy();
  });

  it("★★기본은 꺼져 있고, 켜고 끌 수 있다 — 두 모집단을 같은 실행에서", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: "지적도" }));
    // ★공허 진리 가드 — 팝오버가 실제로 열렸는가(대상 부재면 아래가 공허하다).
    expect(screen.getByRole("heading", { level: 3, name: "지적도" })).toBeTruthy();

    // ① 기본 = 꺼짐. 버튼 문구가 「지도에 표시」(켜라는 권유)여야 한다.
    const before = screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ });
    expect(before.textContent).toContain("지도에 표시");

    // ② 켠다 → 문구가 바뀐다(상태가 실제로 움직였는가).
    fireEvent.click(before);
    expect(
      screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ }).textContent,
    ).toContain("지도 표시 중");

    // ★③ **끈다** — 종전엔 스토어가 같은 참조를 돌려줘 **무동작**이었다.
    //   한 방향만 보면 「항상 켬」도 통과하므로 두 모집단을 같은 실행에서 본다.
    fireEvent.click(screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ }));
    expect(
      screen.getByRole("button", { name: /지도에 표시|지도 표시 중/ }).textContent,
    ).toContain("지도에 표시");
  });
});

/**
 * R1 3차 HIGH-1 자물쇠 — 클릭 확정 후 다른 경로로 닫으면 stale 핀이 무관한 hover 팝오버를
 *   눌러붙게 하던 누수. cross-item 시퀀스라 단일 항목 테스트로는 잡히지 않았다.
 */
describe("SatongMapShell 레일 — 핀 stale 누수(HIGH-1)", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★STALE: 클릭확정→X로 닫음→다른 항목 hover→레일 이탈이면 닫힌다(핀 잔류 누수 방지)", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const rail = screen.getByRole("button", { name: /용도지역/ }).closest("div")!;
      hoverClick(screen.getByRole("button", { name: /용도지역/ })); // 클릭 확정(pin=용도지역)
      fireEvent.click(screen.getByRole("button", { name: "레이어 설정 닫기" })); // X로 닫음
      expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();

      fireEvent.mouseEnter(screen.getByRole("button", { name: "공시지가" })); // 순수 hover분
      expect(screen.getByRole("heading", { level: 3, name: "공시지가" })).toBeTruthy();
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      // stale 핀(용도지역)이 있어도 지금 보이는 건 hover분(공시지가)이므로 닫혀야 한다.
      expect(screen.queryByRole("heading", { level: 3, name: "공시지가" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("★LEAK: 클릭확정→이탈→재진입→다른 항목 hover→이탈이면 닫힌다", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const rail = screen.getByRole("button", { name: /용도지역/ }).closest("div")!;
      hoverClick(screen.getByRole("button", { name: /용도지역/ })); // pin
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); }); // 고정분이라 유지
      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();

      fireEvent.mouseEnter(screen.getByRole("button", { name: "공시지가" })); // 다른 hover분
      act(() => { vi.advanceTimersByTime(300); }); // ★전환을 실제로 일으킨다(A안 지연 경유)
      expect(screen.getByRole("heading", { level: 3, name: "공시지가" })).toBeTruthy();
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.queryByRole("heading", { level: 3, name: "공시지가" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("★유예: 150ms(이내)면 팝오버 유지·250ms(이후)면 닫힘", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const rail = screen.getByRole("button", { name: /용도지역/ }).closest("div")!;
      fireEvent.mouseEnter(screen.getByRole("button", { name: /용도지역/ })); // 순수 hover
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(150); });
      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
      act(() => { vi.advanceTimersByTime(120); }); // 누적 270ms
      expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });
});

/**
 * R1 4차 HIGH-2 자물쇠 — 유예 타이머 콜백·팝오버 onMouseLeave가 raw setState라 남긴 stale 핀이
 *   '같은 정체성' 재hover를 고정분으로 오판해 눌러붙던 잔여 누수. 상태 동기 이펙트로 종결.
 */
describe("SatongMapShell 레일 — 핀 잔여 누수(HIGH-2)", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★RESIDUAL-A: 베이스맵 클릭확정→레이어로 전환(hover)→이탈→베이스맵 재hover→이탈이면 닫힌다", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const bmBtn = screen.getByRole("button", { name: "베이스맵 선택" });
      const rail = bmBtn.closest("div")!;
      hoverClick(bmBtn); // pin="basemap"
      fireEvent.mouseEnter(screen.getByRole("button", { name: /용도지역/ })); // 전환(basemapOpen=false)
      act(() => { vi.advanceTimersByTime(300); }); // ★A안: 전환은 임계 체류 후 발화
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); }); // 타이머가 닫음 → 이펙트가 핀 정리
      expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();

      fireEvent.mouseEnter(bmBtn); // 베이스맵 순수 재hover(stale이면 오판)
      expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.queryByRole("button", { name: "베이스맵: 일반" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("★RESIDUAL-C: 팝오버 onMouseLeave로 닫힌 뒤 같은 항목 재hover→이탈이면 닫힌다", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const btn = screen.getByRole("button", { name: /용도지역/ });
      const rail = btn.closest("div")!;
      hoverClick(btn); // pin=용도지역
      expect(screen.getByRole("dialog", { name: "용도지역" })).toBeTruthy();
      fireEvent.mouseEnter(screen.getByRole("button", { name: "공시지가" })); // 전환 → pin 정리(이펙트)
      act(() => { vi.advanceTimersByTime(300); }); // ★A안: 전환은 임계 체류 후 발화
      // 위 전환으로 활성이 공시지가; 팝오버 mouseleave로 닫아본다
      fireEvent.mouseLeave(screen.getByRole("dialog", { name: "공시지가" }));
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.queryByRole("heading", { level: 3, name: "공시지가" })).toBeNull();

      fireEvent.mouseEnter(screen.getByRole("button", { name: /용도지역/ })); // 재hover
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });
});

/**
 * R1 5차 HIGH-3 자물쇠 — 핀 정리 이펙트가 '전환'이 아니라 '완전 닫힘'에만 발화해야 한다.
 *   A 클릭확정 후 레일 안에서 B를 스쳤다 A로 돌아오면, 클릭 확정분(A)은 유지되어야 한다
 *   (round2 MEDIUM-B가 봉합했던 계약 — 4차 조건식 오류로 회귀했던 것).
 */
describe("SatongMapShell 레일 — 전환 vs 완전닫힘(HIGH-3·Q2-c)", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  it("★Q2-c(레이어): 클릭확정→다른 항목 스침→원항목 복귀→레일 이탈이면 유지된다", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const aBtn = screen.getByRole("button", { name: /용도지역/ });
      const rail = aBtn.closest("div")!;
      hoverClick(aBtn); // pin=용도지역(클릭 확정)
      // ★hover 전환 지연(A안) 이후 필수: 체류 없이는 전환 자체가 일어나지 않아
      //   이 줄이 **무동작**이 되고 테스트가 아무것도 지키지 않는다(R1 HIGH-2 적발 —
      //   핀 정리 이펙트를 옛 조건식으로 되돌리는 변이가 CAUGHT→SURVIVED로 퇴화했다).
      fireEvent.mouseEnter(screen.getByRole("button", { name: "공시지가" })); // B 스침(전환)
      act(() => { vi.advanceTimersByTime(300); }); // 실제로 전환시킨다
      fireEvent.mouseEnter(aBtn); // A 복귀 — ★고정분 복귀는 지연 없이 즉시(R1 HIGH-1)
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      // 스침이 있었어도 클릭 확정분은 살아야 한다(전환은 강등이 아니다).
      expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();
    } finally { vi.useRealTimers(); }
  });

  it("★Q2-c(베이스맵): 베이스맵 클릭확정→레이어 스침→베이스맵 복귀→이탈이면 유지된다", () => {
    vi.useFakeTimers();
    try {
      render(<SatongMapShell locale="ko" />);
      const bmBtn = screen.getByRole("button", { name: "베이스맵 선택" });
      const rail = bmBtn.closest("div")!;
      hoverClick(bmBtn); // pin=basemap(클릭 확정)
      // ★hover 전환 지연(A안) 이후 필수: 체류 없이는 전환 자체가 일어나지 않아
      //   이 줄이 **무동작**이 되고 테스트가 아무것도 지키지 않는다(R1 HIGH-2 적발 —
      //   핀 정리 이펙트를 옛 조건식으로 되돌리는 변이가 CAUGHT→SURVIVED로 퇴화했다).
      fireEvent.mouseEnter(screen.getByRole("button", { name: /용도지역/ })); // 레이어 스침(basemapOpen=false)
      act(() => { vi.advanceTimersByTime(300); }); // 실제로 전환시킨다
      fireEvent.mouseEnter(bmBtn); // 베이스맵 복귀 — ★고정분 복귀는 즉시
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
    } finally { vi.useRealTimers(); }
  });
});

/**
 * ★★사용자 신고②(2026-09-07) — 「베이스맵」과 「지형도·항공뷰」가 **같은 컨트롤**이었다.
 *
 * 실측(계획서 §1): 컨트롤 id 4/5 동일 · 같은 `handleLayerControlClick("terrain", …)` ·
 * 같은 `controlsByLayer.terrain` · 같은 `resolveVWorldBaseLayer()`. **라벨만 둘이었다.**
 * ★목은 이 파일이 이미 갖고 있다 — 새 파일에 복제하지 않고 형제에 합친다(§29).
 */
describe("★신고② — 베이스맵의 단일 소유자", () => {
  beforeEach(() => { window.sessionStorage.clear(); resetStores(); });
  afterEach(() => { window.sessionStorage.clear(); resetStores(); });

  const layerState = (): SatongMapLayerState => {
    const st = useSatongMapPrefs.getState();
    return { enabledLayerIds: st.enabledLayerIds, controlsByLayer: st.controlsByLayer };
  };

  it("★★두 모집단 — `terrain` 은 레일에서 사라졌고, 베이스맵 스위처는 **그대로 4종**이다", () => {
    // ① 지워져야 할 것
    expect(SATONG_MAP_SHELL_LAYERS.some((l) => l.id === "terrain")).toBe(false);
    render(<SatongMapShell locale="ko" />);
    expect(screen.queryByRole("button", { name: /지형도·항공뷰/ })).toBeNull();

    // ② 남아야 할 것 — ①만 재면 «레일을 통째로 비우는» 구현도 초록이다.
    hoverClick(screen.getByRole("button", { name: /베이스맵/ }));
    for (const label of ["일반", "위성", "하이브리드", "회색"]) {
      expect(screen.getByRole("button", { name: `베이스맵: ${label}` }), label).toBeTruthy();
    }
  });

  it("★기능이 안 죽었다 — 스위처 클릭이 `resolveVWorldBaseLayer` 의 **값**을 바꾼다(라벨 아님)", () => {
    render(<SatongMapShell locale="ko" />);
    // ★공허 진리 가드 — 시작 값이 「위성」이면 아래 전이가 아무것도 증명하지 않는다.
    expect(resolveVWorldBaseLayer(layerState())).not.toBe("Satellite");

    hoverClick(screen.getByRole("button", { name: /베이스맵/ }));
    fireEvent.click(screen.getByRole("button", { name: "베이스맵: 위성" }));
    expect(resolveVWorldBaseLayer(layerState())).toBe("Satellite");

    // ★대칭 — 되돌아온다(한쪽만 재면 「항상 위성」도 만점이다).
    fireEvent.click(screen.getByRole("button", { name: "베이스맵: 일반" }));
    expect(resolveVWorldBaseLayer(layerState())).toBe("Base");
  });

  it("★배타 전환 — 배경을 바꾸면 **이전 선택이 지워진다**(둘이 동시에 남지 않는다)", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: /베이스맵/ }));
    fireEvent.click(screen.getByRole("button", { name: "베이스맵: 위성" }));
    fireEvent.click(screen.getByRole("button", { name: "베이스맵: 하이브리드" }));

    const ids = useSatongMapPrefs.getState().controlsByLayer.terrain ?? [];
    expect(ids).toContain("hybrid");
    expect(ids).not.toContain("satellite"); // ★이게 없으면 두 배경이 동시에 선택된다
  });

  it("★배타는 **베이스맵 id 에만** 걸린다 — 비-베이스맵 컨트롤이 배경 선택을 지우지 않는다", () => {
    // ★종전 손 목록은 `layerId === "terrain"` 이면 **컨트롤을 가리지 않고** 배타 분기를 탔다.
    //   `elevation` 이 나중에 `mapEffect:true` 로 구현되면 그 클릭이 배경 선택을 지운다.
    //   오늘은 도달 불가(`mapEffect:false`)이므로 **오늘의 결함이 아니라** 구조로 막는 것이다.
    // ★`enabledLayerIds` 에 terrain 을 넣는다 — `resolveVWorldBaseLayer` 의 첫 줄이
    //   `if (!hasSatongLayer(state,"terrain")) return "Base"` 라, 안 넣으면 이 단언이
    //   **배타와 무관한 이유로** 통과/실패한다(내 초판이 그렇게 틀렸다).
    act(() => {
      useSatongMapPrefs.setState({ enabledLayerIds: ["terrain"] });
      useSatongMapPrefs.getState().setControlsByLayer((prev) => ({
        ...prev,
        terrain: ["satellite", "elevation"],
      }));
    });
    const ids = useSatongMapPrefs.getState().controlsByLayer.terrain ?? [];
    // 두 축이 **공존 가능**하다 = 배경 축과 표고 축이 서로를 지우지 않는다.
    expect(ids).toContain("satellite");
    expect(ids).toContain("elevation");
    expect(resolveVWorldBaseLayer(layerState())).toBe("Satellite");
  });

  it("★죽은 면제가 없다 — 레일의 모든 **렌더러블** 레이어가 on/off 토글을 노출한다", () => {
    const renderable = SATONG_MAP_SHELL_LAYERS.filter((l) => isRenderableSatongMapLayer(l.id));
    // ★공허 진리 가드 — 대상이 0개면 아래 루프가 아무것도 안 본다.
    expect(renderable.length).toBeGreaterThan(3);

    render(<SatongMapShell locale="ko" />);
    for (const layer of renderable) {
      hoverClick(screen.getByRole("button", { name: new RegExp(layer.label) }));
      expect(
        screen.queryByRole("button", { name: /지도에 표시|지도 표시 중/ }),
        `${layer.id}: on/off 토글이 없다 — 죽은 면제가 되살아났는가?`,
      ).toBeTruthy();
    }
  });

  // ★부채를 초록 안에 남긴다(§C-13) — 커밋 메시지에만 적으면 드러나지 않는다.
  it.todo("표고·경사(elevation) 구현 시 자기 레이어로 되살린다 — 지금은 원천 미연동이라 레일에서 뺐다");
  it.todo("`aerial` 레거시 컨트롤 id 를 쓰는 저장분이 실재하는지 측정 — 없으면 배타 집합에서 뺀다");
});
