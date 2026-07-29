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
import type { ReactNode } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SATONG_MAP_SHELL_LAYERS, SatongMapShell } from "@/components/precheck/SatongMapShell";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "ko" }),
  usePathname: () => "/ko/precheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

// ★H2 봉합 이후 필수: 셸 오버레이(배지행·레일·팝오버 3종)는 SatongMultiMap의 topRightSlot으로
//   전달돼 지도 래퍼 '안'에서 렌더된다(풀스크린에서 살아남게 하는 봉합). 스텁이 슬롯을 삼키면
//   실제 화면엔 있는 UI가 테스트에서만 사라지므로, 실컴포넌트와 동일하게 슬롯을 렌더한다.
vi.mock("next/dynamic", () => ({
  default: () => {
    const DynamicStub = ({ topRightSlot }: { topRightSlot?: ReactNode }) => (
      <div data-testid="dynamic-map-stub">{topRightSlot}</div>
    );
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
    render(<SatongMapShell locale="ko" />);
    // 기본값은 펼침(railPinned=true)
    expect(rail().className).toContain("w-32");

    const panel = openLayerPopover();
    expect(panel.className).toContain("right-36");
    expect(panel.className).not.toContain("right-20");
  });

  it("접은 레일에서는 접힘 폭 기준 앵커로 돌아간다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByLabelText(/레이어 목록 접기/));
    expect(rail().className).toContain("w-16");

    const panel = openLayerPopover();
    expect(panel.className).toContain("right-20");
    expect(panel.className).not.toContain("right-36");
  });

  it("팝오버는 클립 컨테이너 안에서 잘리지 않도록 상한 높이·세로 스크롤을 갖는다", () => {
    render(<SatongMapShell locale="ko" />);
    const panel = openLayerPopover();
    expect(panel.className).toContain("overflow-y-auto");
    expect(panel.className).toMatch(/max-h-\[/);
  });
});

describe("팝오버 3종 전부 같은 앵커를 쓴다", () => {
  // ★적대적 리뷰 실증: 레이어 팝오버 하나만 검증하면 베이스맵·필지상세가 하드코딩으로
  //   되돌아가도 전부 초록이었다(변이 생존). 원 결함과 같은 '소비처 조용한 표류'이므로
  //   3종을 전부 고정한다.
  function assertAnchored(panel: HTMLElement, label: string) {
    expect(panel.className, `${label}: 파생 앵커 미사용`).toContain("sm:right-36");
    expect(panel.className, `${label}: 상한 높이 없음`).toMatch(/max-h-\[/);
    expect(panel.className, `${label}: 세로 스크롤 없음`).toContain("overflow-y-auto");
  }

  it("레이어 팝오버", () => {
    render(<SatongMapShell locale="ko" />);
    assertAnchored(openLayerPopover(), "레이어");
  });

  it("베이스맵 팝오버", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByLabelText("베이스맵 선택"));
    const panel = document.getElementById("satong-basemap-popover");
    if (!panel) throw new Error("베이스맵 팝오버를 찾지 못했습니다");
    assertAnchored(panel, "베이스맵");
  });

  it("★소비처 불변식 — 팝오버 앵커를 하드코딩한 곳이 하나도 없다", () => {
    // 필지상세 팝오버는 렌더에 선택 필지가 필요해 상호작용으로 닿기 어렵다.
    // 그래서 '모든 소비처가 SSOT를 쓴다'를 소스 수준에서 고정한다 —
    // 4번째 팝오버를 추가하는 사람도 이 불변식에 걸린다.
    // vitest 환경의 import.meta.url은 file 스킴이 아닐 수 있어 cwd 기준 경로를 쓴다.
    const src = readFileSync(
      resolve(process.cwd(), "components/precheck/SatongMapShell.tsx"),
      "utf-8",
    );
    const popoverLines = src
      .split("\n")
      .filter((line) => line.includes("top-20 z-[430]"));
    expect(popoverLines.length).toBeGreaterThanOrEqual(3); // 베이스맵·레이어·필지상세
    for (const line of popoverLines) {
      expect(line, `앵커 하드코딩 발견: ${line.trim().slice(0, 80)}`)
        .toContain("railPopoverAnchor(railPinned)");
    }
  });
});

describe("좁은 화면 확정 경로", () => {
  it("★<sm에서는 옆으로 밀지 않고 전폭으로 편다 — 확정 버튼 도달성 보존", () => {
    render(<SatongMapShell locale="ko" />);
    const panel = openLayerPopover();
    // 레일을 피해 옆에 세우면 모바일에서 100px 남짓이 되어 2열 컨트롤·확정 버튼이 못 들어간다.
    expect(panel.className).toContain("inset-x-4");
    // 옆 세우기는 sm 이상에서만 적용돼야 한다(무조건 적용이면 모바일이 다시 붕괴).
    expect(panel.className).toContain("sm:right-36");
    expect(panel.className).not.toMatch(/(^|\s)right-36/);
  });
});

describe("레이어 아이콘 유일성", () => {
  it("★아이콘-기능 1:1 — 같은 글리프를 두 레이어가 쓰면 안 된다", () => {
    const icons = SATONG_MAP_SHELL_LAYERS.map((l) => l.icon);
    // 개발계획·로드뷰가 같은 Route 글리프였던 실결함의 재발 방지(12개 전부 고정).
    expect(new Set(icons).size).toBe(icons.length);
  });
});

describe("레일 버튼 발견성", () => {
  it("★펼친 레일은 아이콘만이 아니라 짧은 라벨을 함께 보여준다(터치 발견성)", () => {
    render(<SatongMapShell locale="ko" />);
    const btn = screen.getByTitle(/지적도 — 미리보기 열기/);
    expect(btn.textContent).toContain("지적");
  });

  it("접힌 레일에서는 캡션을 숨겨 폭을 지킨다", () => {
    render(<SatongMapShell locale="ko" />);
    hoverClick(screen.getByLabelText(/레이어 목록 접기/));
    const btn = screen.getByTitle(/지적도 — 미리보기 열기/);
    expect(btn.textContent).not.toContain("지적");
  });
});
