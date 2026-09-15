import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import PlatformReturnLink from "@/components/sales-app/PlatformReturnLink";
import { FIELD_APP_WINDOW_NAME } from "@/lib/field-app-shell";

/**
 * ★복귀로는 **한 모집단에만** 뜬다 — 세 모집단이 서로 다른 결과를 내야 한다.
 *
 * 사용자 지시: *"새창앱에서는 메인플랫폼으로 이동하지 않아도 되지만"*.
 * 그러므로 «항상 뜬다» 도 «항상 안 뜬다» 도 둘 다 오답이고, 하나만 단언하면
 * 그 둘을 구별하지 못한다(이 저장소가 반복해 데인 «한쪽만 거는 단언»).
 *
 * ★런타임(`usePwaRuntime`)만 갈아 끼우고 **판별 로직(`useFieldAppShell`)은 실물을 태운다** —
 *   `inSeparateWindow` 는 `window.name` 을 실제로 읽는다.
 */

const runtime = { installState: "unavailable" as const, standalone: false, requestInstall: vi.fn() };

vi.mock("@/components/pwa/PwaRuntimeProvider", () => ({
  usePwaRuntime: () => runtime,
}));

beforeEach(() => {
  runtime.standalone = false;
  window.name = "";
});

afterEach(() => {
  window.name = "";
  vi.restoreAllMocks();
});

const LABEL = /플랫폼으로/;

describe("PlatformReturnLink — 세 모집단이 갈린다", () => {
  it("① 일반 탭 → **보인다**(여기만 갇힌다)", () => {
    render(<PlatformReturnLink locale="ko" />);
    const link = screen.getByRole("link", { name: LABEL });
    // 목적지가 플랫폼 루트여야 한다 — 현장앱 안 어딘가로 보내면 탈출이 아니다.
    expect(link.getAttribute("href")).toBe("/ko");
  });

  it("② 별도 창 → **안 보인다**(사용자 지시 · 그 창에서 나가면 판별자가 틀린 답을 낸다)", () => {
    window.name = FIELD_APP_WINDOW_NAME;
    render(<PlatformReturnLink locale="ko" />);
    expect(screen.queryByRole("link", { name: LABEL })).toBeNull();
  });

  it("③ 설치본(standalone) → **안 보인다**(스코프 밖 동작이 미측정이다)", () => {
    runtime.standalone = true;
    render(<PlatformReturnLink locale="ko" />);
    expect(screen.queryByRole("link", { name: LABEL })).toBeNull();
  });

  it("★두 축을 **각각** 본다 — 설치본이면서 별도 창이어도 안 보인다", () => {
    // 형제 `FieldAppAffordance` 가 두 축을 하나로 뭉쳤다가 iOS 설치 경로를 막은 전례가 있다.
    runtime.standalone = true;
    window.name = FIELD_APP_WINDOW_NAME;
    render(<PlatformReturnLink locale="ko" />);
    expect(screen.queryByRole("link", { name: LABEL })).toBeNull();
  });

  it("★locale 이 목적지에 실제로 반영된다(하드코딩 /ko 회귀 방지)", () => {
    render(<PlatformReturnLink locale="en" />);
    expect(screen.getByRole("link", { name: LABEL }).getAttribute("href")).toBe("/en");
  });
});
