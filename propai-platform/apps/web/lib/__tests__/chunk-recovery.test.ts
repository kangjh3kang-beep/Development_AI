/**
 * 배포 직후 청크 404 자동복구 — **한 번만** 복구하고, **아무 오류나 새로고침하지 않는다.**
 *
 * 【실증 2026-08-18 · 사용자 스크린샷】
 *   "페이지 오류 — Failed to load chunk /_next/static/chunks/3b1cf6ac98c74f4b.js"
 *   실측: 그 청크 **404** · 현재 배포본 청크 **200** → 열린 탭이 이전 빌드 문서를 들고 있었다.
 *
 * 【이 테스트가 잠그는 두 가지 — 둘 다 없으면 위험하다】
 *   ① 복구하지 않으면 → 사용자가 **낫지 않는 "다시 시도" 버튼**을 누른다(reset 은 같은 문서 안이다)
 *   ② 무제한 복구하면 → 새로고침해도 안 낫는 경우 **무한 새로고침**으로 페이지를 못 벗어난다
 *      (원래 결함보다 나쁘다)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetChunkRecoveryForTest,
  isChunkLoadError,
  tryRecoverFromChunkError,
} from "@/lib/chunk-recovery";

const realLocation = window.location;

beforeEach(() => {
  __resetChunkRecoveryForTest();
  // jsdom 의 location 은 실제 이동을 하지 않으므로 replace 를 감시로 대체한다.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { href: "https://4t8t.net/ko/dashboard", replace: vi.fn() },
  });
});
afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: realLocation });
  __resetChunkRecoveryForTest();
});

describe("청크 오류 판별 — 넓게 잡지 않는다", () => {
  it("★청크 로드 실패의 여러 표현을 잡는다", () => {
    expect(isChunkLoadError({ name: "ChunkLoadError", message: "" })).toBe(true);
    expect(isChunkLoadError(new Error("Loading chunk 42 failed."))).toBe(true);
    // 사용자 화면에 실제로 찍힌 문구
    expect(
      isChunkLoadError(new Error("Failed to load chunk /_next/static/chunks/3b1cf6ac98c74f4b.js")),
    ).toBe(true);
    expect(isChunkLoadError(new Error("error loading dynamically imported module: /x.js"))).toBe(true);
  });

  it("★대조군: 평범한 버그는 청크 오류가 아니다 — 아니면 진짜 버그가 무한 새로고침으로 은폐된다", () => {
    expect(isChunkLoadError(new Error("Cannot read properties of undefined"))).toBe(false);
    expect(isChunkLoadError(new Error("network request failed"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError(undefined)).toBe(false);
  });
});

describe("복구는 세션당 한 번만 한다", () => {
  it("★첫 청크 오류는 복구한다(문서를 새로 받도록 표식을 붙인다)", () => {
    const ok = tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"));
    expect(ok).toBe(true);
    expect(window.location.replace).toHaveBeenCalledTimes(1);
    const url = (window.location.replace as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    // ★`reload()` 는 캐시된 문서를 다시 쓸 수 있어 같은 청크를 또 참조한다 — 쿼리로 미스시킨다.
    expect(url).toContain("_cr=");
  });

  it("★★두 번째부터는 복구하지 않는다 — 무한 새로고침이 원래 결함보다 나쁘다", () => {
    expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(true);
    const second = tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"));
    expect(second, "두 번째도 복구하면 루프가 된다").toBe(false);
    expect(window.location.replace).toHaveBeenCalledTimes(1);
  });

  it("대조군: 청크 오류가 아니면 표식도 남기지 않는다(다음 진짜 청크 오류의 기회를 뺏지 않는다)", () => {
    expect(tryRecoverFromChunkError(new Error("Cannot read properties of undefined"))).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
    // 이제 진짜 청크 오류가 오면 여전히 1회 기회가 남아 있어야 한다.
    expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(true);
  });

  it("★sessionStorage 가 막힌 환경에서는 **복구를 포기**한다", () => {
    // 표식을 남길 수 없으면 루프를 막을 방법이 없다 → 자동 새로고침을 하지 않는 쪽이 안전하다.
    const spy = vi.spyOn(window.sessionStorage.__proto__, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
