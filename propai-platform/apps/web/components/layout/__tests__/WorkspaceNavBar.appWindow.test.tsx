import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { WorkspaceNavBar } from "@/components/layout/WorkspaceNavBar";
import { buildPrimaryNav } from "@/components/layout/nav-config";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★**데스크톱 내비**가 앱형 라우트에서 창을 빼앗지 않는지 — **행위를 태운다.**
 *
 * ## 왜 이 파일이 따로 있나 (2026-09-08 적대 리뷰 BLOCKER-1)
 *
 * 나는 사이드바(`SidebarNav`)만 고쳐 놓고 *"진입점 2곳 전수"* 라고 적었다. **거짓이었다**:
 *
 *     SidebarNav      ← MobileSidebarToggle 안에서만 렌더 · 그 파일은 전부 `lg:hidden`  = **모바일 전용**
 *     WorkspaceNavBar ← `lg:block`                                                      = **데스크톱 전용**
 *
 * 두 렌더러는 **정확히 배타적인 모집단**이고, 신고자(«메인플랫폼 이용자»)는 데스크톱에 있다.
 * ⇒ 내 수정은 신고자에게 **아무 효과가 없었다.**
 * ★저장소가 그 형제를 이름으로 이미 적어 두고 있었다 — `route-registry.ts:86`
 *   *"렌더러(SidebarNav·WorkspaceNavBar)는 …"*. **내가 편집한 바로 그 파일이다.**
 *
 * ## 왜 소스 검사로는 부족한가
 *
 * 형제 락(`field-app-entry.wiring.test.ts` ③)은 «파일이 `shouldInterceptFieldAppClick` 을
 * 담는가» 를 본다. 그런데 이 파일은 링크를 **두 자리**(드롭다운·singleLeaf)에서 그리므로
 * **한 자리만 되돌려도 이름은 남아 통과한다** — 실제로 변이가 `SURVIVED` 했다.
 * ⇒ **존재를 잠그면 행위는 안 잠긴다.** 그래서 렌더해서 누른다.
 */

let pathname = "/ko";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));

const origOpen = window.open;
const TY = "(_u?: string | URL, _t?: string, _f?: string) => Window | null";

beforeEach(() => {
  pathname = "/ko";
});

afterEach(() => {
  window.open = origOpen;
  vi.restoreAllMocks();
});

const sections = buildPrimaryNav("ko");

/** 「분양 관리」 섹션의 플라이아웃을 열고 「내 분양 현장」 링크를 집는다. */
function openFieldAppLink() {
  const trigger = screen.getByRole("button", { name: /분양/ });
  fireEvent.focus(trigger); // onFocus 로도 열린다(원문 :189)
  return screen.getByRole("link", { name: /내 분양 현장/ });
}

describe("데스크톱 내비 — 앱형 라우트는 창을 빼앗지 않는다(행위)", () => {
  it("★① 앱형 항목을 누르면 현장앱 창을 열고 **기본 이동을 막는다**", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(
      () => ({ focus: vi.fn() }) as unknown as Window,
    );
    window.open = open as unknown as typeof window.open;

    render(<WorkspaceNavBar sections={sections} />);
    const notPrevented = fireEvent.click(openFieldAppLink());

    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0]![0]).toBe("/ko/sales/sites");
    expect(open.mock.calls[0]![1]).toBe(FIELD_APP_WINDOW_NAME);
    expect(notPrevented).toBe(false); // 플랫폼 창 보존
  });

  it("★② 두 모집단 — 앱형이 **아닌** 형제는 창을 열지 않는다", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(
      () => ({ focus: vi.fn() }) as unknown as Window,
    );
    window.open = open as unknown as typeof window.open;

    render(<WorkspaceNavBar sections={sections} />);
    const trigger = screen.getByRole("button", { name: /분양/ });
    fireEvent.focus(trigger);
    const notPrevented = fireEvent.click(screen.getByRole("link", { name: /분양관리요약/ }));

    expect(open).not.toHaveBeenCalled();
    expect(notPrevented).toBe(true);
  });

  it("★③ `tab` 폴백 — 팝업이 막혀 새 탭으로 열려도 **기본 이동을 막는다**", () => {
    // 리뷰 M-2: 이 갈래가 무잠금이라 `!== \"same\"` → `=== \"window\"` 변이가 생존했다.
    // 그 변이의 실제 동작은 «새 탭이 열리고 + 원래 창도 현장앱으로 이동» = 신고 증상 재현이다.
    const open = vi
      .fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>()
      .mockReturnValueOnce(null) // 팝업 차단
      .mockReturnValueOnce({} as Window); // 새 탭 허용
    window.open = open as unknown as typeof window.open;

    render(<WorkspaceNavBar sections={sections} />);
    const notPrevented = fireEvent.click(openFieldAppLink());

    expect(open).toHaveBeenCalledTimes(2);
    expect(notPrevented).toBe(false); // ★탭이어도 막는다
  });

  it("★④ 둘 다 막히면 기본 이동을 **살려 둔다**(오늘의 동작 폴백)", () => {
    window.open = vi.fn(() => null) as unknown as typeof window.open;

    render(<WorkspaceNavBar sections={sections} />);
    expect(fireEvent.click(openFieldAppLink())).toBe(true);
  });
});

describe("★singleLeaf 자리 — 오늘은 도달 불가지만 무잠금으로 두지 않는다", () => {
  // 현재 레지스트리에서 `sales-sites` 는 부모(`sales-mgmt`)가 있어 **드롭다운**으로 그려지므로
  // 이 분기는 도달하지 않는다(변이가 SURVIVED 했다 — 구멍이 아니라 도달 불가다).
  // ★그러나 «설명할 수 없는 생존» 으로 남기지 않는다: 섹션에 리프가 하나뿐이 되는 순간
  //   여기로 그려지고, 그때 정책이 빠져 있으면 **데스크톱이 조용히 옛 동작으로 돌아간다.**
  //   그래서 그 상태를 **만들어서** 태운다(조건부 렌더는 그 상태를 만들어 검사하라).
  // ★이 자리의 링크 텍스트는 `section.title` 이다(원문 확인) — `link.label` 이 아니다.
  it("리프가 하나뿐인 섹션의 앱형 링크도 창을 열고 기본 이동을 막는다", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(
      () => ({ focus: vi.fn() }) as unknown as Window,
    );
    window.open = open as unknown as typeof window.open;

    const solo = [
      {
        id: "solo-section",
        title: "단독섹션",
        items: [
          { id: "solo-app", label: "단독 현장앱", href: "/ko/sales/sites", launch: "app-window" as const },
        ],
      },
    ];
    render(<WorkspaceNavBar sections={solo} />);

    const notPrevented = fireEvent.click(screen.getByRole("link", { name: /단독섹션/ }));

    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0]![1]).toBe(FIELD_APP_WINDOW_NAME);
    expect(notPrevented).toBe(false);
  });

  it("★두 모집단 — 같은 자리에 `launch` 가 없으면 창을 열지 않는다", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(
      () => ({ focus: vi.fn() }) as unknown as Window,
    );
    window.open = open as unknown as typeof window.open;

    const solo = [
      { id: "solo-plain", title: "평범섹션", items: [{ id: "solo-x", label: "평범 링크", href: "/ko/projects" }] },
    ];
    render(<WorkspaceNavBar sections={solo} />);

    expect(fireEvent.click(screen.getByRole("link", { name: /평범섹션/ }))).toBe(true);
    expect(open).not.toHaveBeenCalled();
  });
});
