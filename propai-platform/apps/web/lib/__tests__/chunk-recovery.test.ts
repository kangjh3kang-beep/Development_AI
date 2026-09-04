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

/**
 * ★전송을 **실제로 가로챈다**. 이 스텁이 없으면 `flush()` 가 `sendBeacon` 부재 → `fetch` 폴백 →
 * `try/catch` 로 삼켜져 **조용히 초록**이 된다 — 락이 아니라 장식이 된다(적대 리뷰 지적).
 */
let sent: string[] = [];
/** ★전송과 리로드를 **하나의 타임라인**에 기록한다 — 「리로드 전에 보낸다」는 성질을 직접 잠근다. */
let timeline: string[] = [];
function captureSends(): void {
  sent = [];
  timeline = [];
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  vi.stubGlobal("fetch", ((_u: string, init?: RequestInit) => {
    sent.push(String(init?.body ?? ""));
    timeline.push("send");
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
}
const sentScopes = (): string[] =>
  sent.flatMap((b) => {
    try {
      return (JSON.parse(b) as { events: Array<Record<string, unknown>> }).events.map(
        (e) => String((e.payload as Record<string, unknown> | null)?.scope ?? ""),
      );
    } catch {
      return [];
    }
  });

beforeEach(() => {
  __resetChunkRecoveryForTest();
  captureSends();
  // jsdom 의 location 은 실제 이동을 하지 않으므로 replace 를 감시로 대체한다.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      href: "https://4t8t.net/ko/dashboard",
      replace: vi.fn(() => {
        timeline.push("replace");
      }),
    },
  });
});
afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: realLocation });
  vi.unstubAllGlobals();
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

/**
 * ★**자동복구가 도는 그 사건이 텔레메트리에 남는가.**
 *
 * 【라이브 실측 2026-08-27 · 네트워크 층에서 `POST /growth/events` 를 가로채 문서 리로드를 넘겨 관측】
 *     `_cr` 자동복구 리로드      25,682ms
 *     첫 청크 오류(리로드 前)  `js_error` **0건**   ← 유실
 *     두 번째  (리로드 後)  `js_error` **1건**   ← `scope="dashboard-error"`
 *   두 번째가 배달됐으므로 **프로브 사망이 아니다**(같은 실행 안 양성 대조군).
 *   즉 **배포 직후 열린 탭이 깨지는, 가장 정보가 많은 경우**가 통째로 안 남았다.
 *
 * ★**두 단언을 둘 다 건다.** `replace` 단언이 없으면 「자동복구를 통째로 제거」한 변이가 초록이고,
 *   전송 단언이 없으면 원래 결함이 그대로다.
 */
describe("★자동복구는 **보고한 뒤에** 리로드한다", () => {
  it("A(결함이 살던 자리) 첫 청크 오류 — 전송 ≥1 **그리고** replace 1회", () => {
    const ok = tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"));
    expect(ok).toBe(true);
    expect(
      sentScopes(),
      "리로드 전에 보고하지 않았다 — 이 사건은 어디에도 남지 않는다",
    ).toContain("chunk-auto-recovery");
    expect(
      window.location.replace,
      "보고는 했는데 복구를 안 했다 — 사용자는 낫지 않는 화면에 남는다",
    ).toHaveBeenCalledTimes(1);

    // ★**순서**까지 잠근다. 초판은 이것을 안 걸어 「보고를 `replace` 뒤로 옮기는」 변이가
    //   **생존**했다 — jsdom 의 `replace` 는 스텁이라 실제 이동이 없어 뒤에서도 보고가 돈다.
    //   프로덕션에서 그 순서가 안전한지는 **재지 않았다**(내비게이션이 이미 시작된 뒤다).
    //   재지 않은 것에 기대지 않는다 — 계약을 「리로드 **전에** 보낸다」로 못 박는다.
    // ★`toEqual(["send","replace"])` 로 못 박지 **않는다** — 조기 포착 버퍼가 임계(20)를 넘으면
    //   drain 루프 안에서 먼저 flush 되어 `["send","send","replace"]` 가 **정상**인데 빨개진다
    //   (독립 리뷰 지적 — 가드의 위양성도 결함이다). 잠그는 것은 **순서**이지 횟수가 아니다.
    expect(timeline.indexOf("send"), "전송이 아예 없다").toBeGreaterThanOrEqual(0);
    expect(
      timeline.indexOf("send"),
      `전송이 리로드보다 뒤다 — 이 순서의 안전성은 미측정이다: ${JSON.stringify(timeline)}`,
    ).toBeLessThan(timeline.indexOf("replace"));
    expect(timeline.filter((x) => x === "replace"), "리로드가 1회가 아니다").toHaveLength(1);
  });

  it("B(음성 대조군) 평범한 오류 — 여기서는 아무것도 하지 않는다(경계가 보고한다)", () => {
    const ok = tryRecoverFromChunkError(new Error("undefined is not a function"));
    expect(ok).toBe(false);
    expect(window.location.replace).not.toHaveBeenCalled();
    // ★과잉 억제 방지의 반대편: 여기서 보고하면 경계 보고와 **이중**이 된다.
    expect(sentScopes(), "청크 오류가 아닌데 자동복구 보고가 나갔다").not.toContain(
      "chunk-auto-recovery",
    );
  });

  it("C 두 번째 청크 오류 — 복구를 포기하므로 **여기서는** 보고하지 않는다(경계가 한다)", () => {
    expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(true);
    sent = [];
    expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(false);
    expect(sentScopes(), "복구도 안 하면서 보고까지 하면 경계 보고와 이중이다").toEqual([]);
  });

  it("★sessionStorage 가 막혀 복구를 포기할 때도 **여기서는** 보고하지 않는다", () => {
    const realSS = window.sessionStorage;
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      get() {
        throw new Error("blocked");
      },
    });
    try {
      expect(tryRecoverFromChunkError(new Error("Failed to load chunk /a.js"))).toBe(false);
      expect(sentScopes()).toEqual([]);
    } finally {
      Object.defineProperty(window, "sessionStorage", { configurable: true, value: realSS });
    }
  });
});
