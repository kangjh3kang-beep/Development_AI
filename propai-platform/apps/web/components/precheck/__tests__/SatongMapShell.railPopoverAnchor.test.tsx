/**
 * 레일 ↔ 팝오버 좌표 계약 회귀망.
 *
 * ★실결함(라이브): 레일은 펼침(w-32=128px)이 기본인데 팝오버 앵커는 접힘 폭 기준
 *   right-20(80px)에 고정돼 있었다. 그 결과 팝오버가 레일 **왼쪽 열 버튼 7개를 통째로
 *   덮고**, z(430 > 420)까지 높아 클릭조차 막았다 — "롤오버로 탐색하고 팝오버에서 확정"
 *   이라는 설계 흐름 자체가 반쪽이 됐다.
 *   앵커를 레일 상태에서 파생시키는 것이 수정이고, 이 파일은 그 파생을 고정한다.
 *
 * ★추가 계약: 팝오버는 고정 클립 컨테이너(overflow-hidden) 안에 있으므로 상한 높이와
 *   세로 스크롤이 있어야 한다(레일은 이미 같은 이유로 고쳐졌는데 팝오버엔 미전파였다).
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

// jsdom의 click은 선행 mouseenter를 합성하지 않는다 — 레일은 hover 기반이라 반드시 함께.
function hoverClick(el: HTMLElement) {
  fireEvent.mouseEnter(el);
  fireEvent.click(el);
}

function openLayerPopover(): HTMLElement {
  const btn = screen.getByTitle(/지적도 — 미리보기 열기/);
  hoverClick(btn);
  const heading = screen.getByRole("heading", { name: "지적도" });
  // 팝오버 루트 = 앵커(absolute + right-*)를 가진 가장 가까운 조상.
  let el: HTMLElement | null = heading.parentElement;
  while (el && !(el.className.includes("absolute") && el.className.includes("right-"))) {
    el = el.parentElement;
  }
  if (!el) throw new Error("팝오버 루트를 찾지 못했습니다");
  return el;
}

function rail(): HTMLElement {
  const anchor = screen.getByLabelText(/레이어 목록/);
  const el = anchor.parentElement;
  if (!el) throw new Error("레일을 찾지 못했습니다");
  return el;
}

beforeEach(resetStores);
afterEach(() => { vi.clearAllMocks(); resetStores(); });

describe("레일 ↔ 팝오버 좌표 계약", () => {
  it("★펼친 레일에서 팝오버는 레일(144px)을 피해 더 왼쪽에 선다", () => {
    render(<SatongMapShell />);
    // 기본값은 펼침(railPinned=true)
    expect(rail().className).toContain("w-32");

    const panel = openLayerPopover();
    expect(panel.className).toContain("right-36");
    expect(panel.className).not.toContain("right-20");
  });

  it("접은 레일에서는 접힘 폭 기준 앵커로 돌아간다", () => {
    render(<SatongMapShell />);
    hoverClick(screen.getByLabelText(/레이어 목록 접기/));
    expect(rail().className).toContain("w-16");

    const panel = openLayerPopover();
    expect(panel.className).toContain("right-20");
    expect(panel.className).not.toContain("right-36");
  });

  it("팝오버는 클립 컨테이너 안에서 잘리지 않도록 상한 높이·세로 스크롤을 갖는다", () => {
    render(<SatongMapShell />);
    const panel = openLayerPopover();
    expect(panel.className).toContain("overflow-y-auto");
    expect(panel.className).toMatch(/max-h-\[/);
  });
});

describe("레일 버튼 발견성", () => {
  it("★펼친 레일은 아이콘만이 아니라 짧은 라벨을 함께 보여준다(터치 발견성)", () => {
    render(<SatongMapShell />);
    const btn = screen.getByTitle(/지적도 — 미리보기 열기/);
    expect(btn.textContent).toContain("지적");
  });

  it("접힌 레일에서는 캡션을 숨겨 폭을 지킨다", () => {
    render(<SatongMapShell />);
    hoverClick(screen.getByLabelText(/레이어 목록 접기/));
    const btn = screen.getByTitle(/지적도 — 미리보기 열기/);
    expect(btn.textContent).not.toContain("지적");
  });
});
