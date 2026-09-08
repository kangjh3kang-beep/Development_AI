import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { launchFieldApp } from "@/lib/field-app-launch";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★공용 창 열기(`launchFieldApp`)의 계약 — **3분기가 서로 다른 값을 낸다.**
 *
 * 왜 불리언이 아닌가: 호출부는 «기본 이동을 막을지» 를 이 값으로 정한다.
 *   창이 떴는데 안 막으면 → **원래 창까지 현장앱으로 이동해 사용자가 플랫폼을 잃는다**(신고 본체)
 *   못 떴는데 막으면     → **버튼이 죽는다**
 * 두 실패가 정반대라 하나의 불리언으로 뭉갤 수 없다.
 *
 * ★세 모집단이 **서로 다른 반환값**을 내야 한다. 같은 값이면 배선을 끊어도 통과한다.
 */

const origOpen = window.open;

beforeEach(() => {
  window.name = "";
});

afterEach(() => {
  window.open = origOpen;
  window.name = "";
  vi.restoreAllMocks();
});

describe("launchFieldApp — 3분기가 서로 갈린다", () => {
  it("① 전용 창이 열리면 'window' 를 내고, **현장앱 이름**으로 연다", () => {
    const focus = vi.fn();
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    expect(launchFieldApp("/ko/sales/sites")).toBe("window");

    // 이름이 곧 현장앱 정체성 판별자다 — 하드코딩하지 않고 정본 상수와 결속시킨다.
    expect(open).toHaveBeenCalledTimes(1);
    expect(open.mock.calls[0]![1]).toBe(FIELD_APP_WINDOW_NAME);
    expect(open.mock.calls[0]![0]).toBe("/ko/sales/sites");
    expect(focus).toHaveBeenCalled();
  });

  it("② 팝업이 차단되면 새 탭으로 폴백하고 'tab' 을 낸다", () => {
    const open = vi
      .fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>()
      .mockReturnValueOnce(null) // 팝업 차단
      .mockReturnValueOnce({} as Window); // 새 탭은 허용
    window.open = open as unknown as typeof window.open;

    expect(launchFieldApp("/ko/sales/sites")).toBe("tab");
    expect(open).toHaveBeenCalledTimes(2);
    // ★폴백도 **같은 이름**으로 연다(2026-09-08 실측): `_blank`+`noopener` 는 sessionStorage 를
    //   새로 시작해 **현장 비밀번호를 다시 묻게 만들었다**(현장 토큰이 sessionStorage 에 산다).
    //   이름을 유지하면 세션 상속 + 앱 정체성 판별이 둘 다 산다.
    expect(open.mock.calls[1]![1]).toBe(FIELD_APP_WINDOW_NAME);
    // 팝업 features 는 주지 않는다 — 그래야 탭으로 열린다(차단을 우회하는 지점).
    expect(open.mock.calls[1]![2]).toBeUndefined();
  });

  it("③ 둘 다 차단되면 'same' 을 낸다 — 호출부가 기본 이동을 살려 두게", () => {
    const open = vi.fn().mockReturnValue(null);
    window.open = open as unknown as typeof window.open;

    expect(launchFieldApp("/ko/sales/sites")).toBe("same");
    expect(open).toHaveBeenCalledTimes(2);
  });

  it("★url 을 생략하면 현재 주소를 연다(어포던스의 「별도 창으로 열기」 경로)", () => {
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    launchFieldApp();

    expect(open.mock.calls[0]![0]).toBe(window.location.href);
  });

  it("★팝업 features 는 지키지 못할 약속(location=no)을 담지 않는다", () => {
    // 현대 브라우저가 무시해 주소창이 남는다 — 2026-09-07 라이브 실측으로 확정된 사실이다.
    // 이 단언이 없으면 «주소창을 숨긴다» 는 거짓 약속이 다시 기어든다.
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    launchFieldApp("/ko/sales/sites");

    const feat = String(open.mock.calls[0]![2]);
    expect(feat).not.toContain("location=no");
    expect(feat).toContain("popup=yes"); // 양성 대조 — features 자체는 살아 있다
  });
});

describe("★팝업 크기 — 주석이 선언한 불변식을 태운다(적대 리뷰 M-4)", () => {
  // `popupFeatures` 주석: "화면보다 크게 요청하지 않는다 — 일부 브라우저는 화면을 넘는 요청을
  // 통째로 무시해 크기 지정이 전부 날아간다". ★그 문장이 참인지 **재서** 확인한다.
  // 종전 판은 `Math.max(360, …)` 하한이 바깥에 있어 availWidth=320 에서 스스로 그 주석을 깼다.
  const setScreen = (w: number, h: number) =>
    Object.defineProperty(window, "screen", {
      value: { availWidth: w, availHeight: h },
      configurable: true,
    });
  const dims = (feat: string) => ({
    w: Number(/width=(\d+)/.exec(feat)?.[1]),
    h: Number(/height=(\d+)/.exec(feat)?.[1]),
  });

  it("초소형 화면(320×480)에서도 요청 치수가 화면을 넘지 않는다", () => {
    setScreen(320, 480);
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    launchFieldApp("/ko/sales/sites");
    const { w, h } = dims(String(open.mock.calls[0]![2]));

    expect(w).toBeLessThanOrEqual(320);
    expect(h).toBeLessThanOrEqual(480);
  });

  it("두 모집단 — 큰 화면(2560×1440)에서는 상한에서 멈춘다(무제한 확대 금지)", () => {
    setScreen(2560, 1440);
    const open = vi.fn<(_u?: string | URL, _t?: string, _f?: string) => Window | null>(() => ({ focus: vi.fn() }) as unknown as Window);
    window.open = open as unknown as typeof window.open;

    launchFieldApp("/ko/sales/sites");
    const { w, h } = dims(String(open.mock.calls[0]![2]));

    // 상한·하한을 **양방향으로** 건다 — 한쪽만 걸면 반대쪽이 무제한이 된다.
    expect(w).toBeLessThanOrEqual(1180);
    expect(w).toBeGreaterThan(320);
    expect(h).toBeLessThanOrEqual(900);
  });
});
