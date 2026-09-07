import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import FieldAppLaunchLink from "@/components/sales-app/FieldAppLaunchLink";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★진입 링크의 계약 — **창을 열었을 때만 기본 이동을 막는다.**
 *
 * 두 실패가 정반대다:
 *   창이 떴는데 안 막으면 → 원래 창까지 현장앱으로 이동 = **사용자가 플랫폼을 잃는다**(신고 본체)
 *   못 떴는데 막으면      → **아무 데도 못 간다**(버튼 사망)
 * 그래서 두 모집단을 **같은 실행에서** 갈라 단언한다. 한쪽만 보면 «항상 막는다» 도 통과한다.
 */

const origOpen = window.open;

beforeEach(() => {
  window.name = "";
});

afterEach(() => {
  window.open = origOpen;
  vi.restoreAllMocks();
});

function renderLink() {
  const seen: string[] = [];
  render(
    <FieldAppLaunchLink href="/ko/sales/sites" onLaunched={(h) => seen.push(h)}>
      내 현장(앱)
    </FieldAppLaunchLink>,
  );
  return { seen, el: screen.getByRole("link", { name: /내 현장/ }) };
}

describe("FieldAppLaunchLink — 두 모집단이 반대 결과를 낸다", () => {
  it("① 창이 열리면 기본 이동을 **막는다**(플랫폼 창 보존)", () => {
    window.open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window) as typeof window.open;
    const { el, seen } = renderLink();

    // fireEvent.click 의 반환값 = "기본 동작이 살아 있는가". false 면 preventDefault 된 것.
    const notPrevented = fireEvent.click(el);

    expect(seen).toEqual(["window"]);
    expect(notPrevented).toBe(false); // ★막았다
  });

  it("② 팝업·새탭 둘 다 차단되면 기본 이동을 **막지 않는다**(오늘의 동작으로 폴백)", () => {
    window.open = vi.fn(() => null) as unknown as typeof window.open;
    const { el, seen } = renderLink();

    const notPrevented = fireEvent.click(el);

    expect(seen).toEqual(["same"]);
    expect(notPrevented).toBe(true); // ★막지 않았다 — 최악의 경우가 회귀가 아니다
  });

  it("★href 를 유지한다 — 가운데클릭·「새 탭에서 열기」·링크 복사가 살아 있어야 한다", () => {
    window.open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window) as typeof window.open;
    const { el } = renderLink();
    expect(el.getAttribute("href")).toBe("/ko/sales/sites");
  });

  it("★수식키 클릭은 가로채지 않는다 — 사용자가 스스로 새 컨텍스트를 요구한 것이다", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;
    const { el, seen } = renderLink();

    const notPrevented = fireEvent.click(el, { metaKey: true });

    expect(open).not.toHaveBeenCalled();
    expect(seen).toEqual([]);
    expect(notPrevented).toBe(true); // 브라우저에 맡긴다
  });

  it("★열 때 쓰는 창 이름이 현장앱 정본 상수다(정체성 판별자와 결속)", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;
    const { el } = renderLink();

    fireEvent.click(el);

    expect(open.mock.calls[0]![1]).toBe(FIELD_APP_WINDOW_NAME);
  });
});
