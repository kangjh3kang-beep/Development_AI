/**
 * 베이스맵 스위처 — terrain 컨트롤 상호배타 계약 + 우상단 레일 통합(2026-07-23).
 *   ① 레일 '베이스맵' 버튼으로 열기 전에는 스와치가 없다(도크 잔재 회귀 방지).
 *   ② 기본은 '일반' 활성. ③ '위성' 클릭 → 위성만 활성(상호배타). ④ '일반' 복귀 가능.
 *   ⑤ 레이어 팝오버와 상호배타(같은 좌표를 쓰므로 동시 표시 금지). ⑥ Esc 닫힘.
 */
import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

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
    const DynamicStub = (props: Record<string, unknown>) => {
      capturedMapProps.push(props);
      return <div data-testid="dynamic-map-stub" />;
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
    // 지적도는 초기 활성(cadastre 기본 ON)이라 좌상단 칩이 이미 존재한다.
    const railButton = screen.getByRole("button", { name: "지적도" });

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
    render(<SatongMapShell locale="ko" />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: "용도지역" }));
    expect(screen.getByRole("heading", { level: 3, name: "용도지역" })).toBeTruthy();

    fireEvent.mouseEnter(screen.getByRole("button", { name: "지적도" }));
    expect(screen.getByRole("heading", { level: 3, name: "지적도" })).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 3, name: "용도지역" })).toBeNull();
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

  it("★terrain(지형도·항공뷰)은 on/off를 노출하지 않는다 — 끄면 베이스맵이 조용히 롤백되고 라벨이 거짓이 된다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: /지형도·항공뷰/ }));
    expect(screen.getByRole("heading", { level: 3, name: "지형도·항공뷰" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /지도에 표시|지도 표시 중/ })).toBeNull();
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

  it("★cadastre(지적도)는 on/off 미노출 — 끌 수 없어 토글이 죽은 버튼이 된다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByRole("button", { name: "지적도" }));
    expect(screen.getByRole("heading", { level: 3, name: "지적도" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /지도에 표시|지도 표시 중/ })).toBeNull();
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
      fireEvent.mouseEnter(screen.getByRole("button", { name: "공시지가" })); // B 스침(전환)
      fireEvent.mouseEnter(aBtn); // A 복귀(전환)
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
      fireEvent.mouseEnter(screen.getByRole("button", { name: /용도지역/ })); // 레이어 스침(basemapOpen=false)
      fireEvent.mouseEnter(bmBtn); // 베이스맵 복귀
      fireEvent.mouseLeave(rail);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.getByRole("button", { name: "베이스맵: 일반" })).toBeTruthy();
    } finally { vi.useRealTimers(); }
  });
});
