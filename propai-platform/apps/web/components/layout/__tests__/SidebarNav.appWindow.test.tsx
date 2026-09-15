import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { SidebarNav } from "@/components/layout/SidebarNav";
import { buildPrimaryNav, type NavNode, type NavSection } from "@/components/layout/nav-config";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★레지스트리 `launch:"app-window"` 가 **사이드바 클릭 동작까지 도달**하는지 잠근다.
 *
 * ## 왜 선언만 단언하면 안 되나
 *
 * 이 저장소가 반복해 데인 형태가 정확히 이것이다 — *"선언의 존재는 그 선언이 옳은지
 * 말해 주지 않는다"* · *"변이를 함수 안에만 넣으면 5/5 CAUGHT 인데 배선은 무잠금"*.
 * `launch` 를 레지스트리에 적어 두고 `toNavNode` 가 그것을 **안 흘리면** 사이드바는
 * 조용히 옛 동작(같은 창 이동)으로 돌아간다. 그래서 **행위를 태운다.**
 *
 * 축은 세 층이다: ①레지스트리 선언 ②`NavNode` 까지 도달 ③클릭 시 실제로 창을 연다.
 * 셋을 각각 단언한다 — 하나만 보면 나머지 두 층이 무잠금이다.
 */

const push = vi.fn();
let pathname = "/ko";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

const origOpen = window.open;

beforeEach(() => {
  pathname = "/ko";
  push.mockClear();
});

afterEach(() => {
  window.open = origOpen;
  vi.restoreAllMocks();
});

/** 레지스트리에서 파생 — 손으로 트리를 만들지 않는다(모집단이 곧 상한이 되지 않게). */
function findNode(sections: NavSection[], id: string): NavNode | undefined {
  const walk = (nodes: NavNode[]): NavNode | undefined => {
    for (const n of nodes) {
      if (n.id === id) return n;
      const hit = n.children ? walk(n.children) : undefined;
      if (hit) return hit;
    }
    return undefined;
  };
  return walk(sections.flatMap((s) => s.items));
}

describe("사이드바 — 앱형 라우트는 창을 빼앗지 않는다(3층 각각)", () => {
  const sections = buildPrimaryNav("ko");
  const node = findNode(sections, "sales-sites");

  it("① 레지스트리 선언이 `NavNode` 까지 **도달**한다", () => {
    expect(node, "sales-sites 노드를 못 찾았다 — 레지스트리 구조가 바뀌었다").toBeDefined();
    expect(node!.href).toBe("/ko/sales/sites");
    expect(node!.launch).toBe("app-window");
  });

  it("★② 대조군 — 앱형이 아닌 형제는 `launch` 가 없다(전부 참이면 판별력 0)", () => {
    const sibling = findNode(sections, "sales-projection");
    expect(sibling, "형제 노드를 못 찾았다").toBeDefined();
    expect(sibling!.launch).toBeUndefined();
  });

  it("③ 앱형 항목을 누르면 **현장앱 창을 열고 기본 이동을 막는다**", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    // ★그룹이 접혀 있으면 링크가 DOM 에 없다 — "검사는 있는데 대상이 없어" 통과하는
    //   공허한 그린을 피하려면 **그 상태를 만들어야** 한다.
    pathname = "/ko/sales/sites";
    render(<SidebarNav sections={sections} />);
    const link = screen.getByRole("link", { name: /내 분양 현장/ });
    const notPrevented = fireEvent.click(link);

    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0]![0]).toBe("/ko/sales/sites");
    expect(open.mock.calls[0]![1]).toBe(FIELD_APP_WINDOW_NAME);
    expect(notPrevented).toBe(false); // 기본 이동을 막았다 = 플랫폼 창 보존
  });

  it("★④ 두 모집단 — 앱형이 **아닌** 항목은 창을 열지 않는다", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    pathname = "/ko/sales/sites";
    render(<SidebarNav sections={sections} />);
    const sibling = screen.getByRole("link", { name: /분양관리요약/ });
    const notPrevented = fireEvent.click(sibling);

    expect(open).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true); // 평범한 이동 그대로
  });

  it("★★tab 폴백 — 새 탭으로 열려도 기본 이동을 막는다(적대 리뷰 M-2)", () => {
    window.open = vi
      .fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>()
      .mockReturnValueOnce(null)
      .mockReturnValueOnce({} as Window) as unknown as typeof window.open;

    pathname = "/ko/sales/sites";
    render(<SidebarNav sections={sections} />);
    const link = screen.getByRole("link", { name: /내 분양 현장/ });

    expect(fireEvent.click(link)).toBe(false); // 탭이어도 막는다
  });

  it("★⑤ 팝업이 차단되면 사이드바도 기본 이동을 막지 않는다(오늘의 동작 폴백)", () => {
    window.open = vi.fn(() => null) as unknown as typeof window.open;

    pathname = "/ko/sales/sites";
    render(<SidebarNav sections={sections} />);
    const link = screen.getByRole("link", { name: /내 분양 현장/ });

    expect(fireEvent.click(link)).toBe(true);
  });
});
