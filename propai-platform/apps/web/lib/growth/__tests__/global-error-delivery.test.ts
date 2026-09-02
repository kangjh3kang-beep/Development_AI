// @vitest-environment jsdom
/**
 * ★**전역 오류 경계가 자기 오류를 배달하는가** — 「불렸다」가 아니라 「그래서 나갔다」.
 *
 * 이 파일이 형제 `selection-contamination.transport.test.ts` 와 다른 점: 그 테스트는
 * `flush()` 를 **손으로 부른다.** 그래서 전송 **본문**은 잠그지만 *"무엇이 flush 를 구동하는가"*
 * 는 구조적으로 비껴간다. 여기서는 **flush 를 절대 손으로 부르지 않고** 앱이 실제로 갖고 있는
 * 구동자(임계 20건 · 5초 타이머 · pagehide)만으로 나가는지 본다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { earlyErrorBootstrap } from "@/lib/growth/early-error-bootstrap";

type Collector = typeof import("../event-collector");
type Reporter = typeof import("../report-boundary-error");

/** 네트워크 경계만 가로챈다(목 없이 진짜 collector 를 태운다). */
function captureSends(): string[] {
  const sent: string[] = [];
  // sendBeacon 을 없는 것으로 만들어 fetch 폴백을 강제한다(Blob 은 동기로 못 읽는다).
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  vi.stubGlobal("fetch", ((_u: string, init?: RequestInit) => {
    sent.push(String(init?.body ?? ""));
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
  return sent;
}

/**
 * 모듈 상태(ring·initialized·flushTimer)가 테스트 간에 새지 않도록 새 모듈을 받는다.
 * ★보고기도 **같은 리셋 뒤에** 받아야 같은 collector 인스턴스에 바인딩된다.
 */
async function freshModules(): Promise<{ c: Collector; r: Reporter }> {
  vi.resetModules();
  const c = (await import("../event-collector")) as Collector;
  const r = (await import("../report-boundary-error")) as Reporter;
  return { c, r };
}

/**
 * `app/global-error.tsx` 가 실제로 하는 호출 그대로.
 * ★여기서 `trackEvent` 를 직접 부르면 **제품이 안 쓰는 경로**를 재게 된다 — 배선 락은 별도
 *   파일(`error-boundary-report-wiring.test.ts`)이 파생형으로 잠근다.
 */
function reportAsGlobalError(r: Reporter): void {
  r.reportBoundaryError("global-error", Object.assign(new Error("boom"), { digest: "d1" }));
}

/** 앱이 가진 배달 구동자를 **전부** 발화시킨다(손 flush 금지). */
function driveEveryDeliveryTrigger(): void {
  vi.advanceTimersByTime(30_000); // 5초 타이머가 있었다면 6회 돌았을 시간
  window.dispatchEvent(new Event("pagehide"));
  Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
  window.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("★전역 오류 경계의 js_error 가 실제로 서버에 나가는가", () => {
  it("양성 대조군 — 수집기가 살아 있으면 1건도 타이머로 나간다(프로브 생존 증명)", async () => {
    const { c, r } = await freshModules();
    const sent = captureSends();
    c.initEventCollector();
    sent.length = 0; // init 자체가 보낸 것(조기 버퍼 등)을 배제

    reportAsGlobalError(r);
    driveEveryDeliveryTrigger();

    expect(sent.length, "구동자가 있는데도 안 나갔다 — 이 프로브는 배달을 볼 수 없다").toBeGreaterThan(0);
    const body = JSON.parse(sent[0]) as { events: Array<Record<string, unknown>> };
    expect(body.events.some((e) => e.event_type === "js_error")).toBe(true);
  });

  it("①초기 로드 크래시 — 프로바이더가 커밋 못 해 수집기가 안 돈 문서에서 배달된다", async () => {
    const { r } = await freshModules();
    const sent = captureSends();
    // 수집기를 **부르지 않는다** — 루트 트리가 커밋 전에 throw 해 프로바이더가 없는 문서.
    reportAsGlobalError(r);
    driveEveryDeliveryTrigger();

    expect(sent.length, "수집기 미초기화 문서에서 js_error 가 배달되지 않았다").toBeGreaterThan(0);
  });

  it("②마운트 후 크래시 — 언마운트 teardown 뒤에 난 오류도 배달된다", async () => {
    const { c, r } = await freshModules();
    const sent = captureSends();
    c.initEventCollector();
    c.teardownEventCollector(); // 루트 언마운트 cleanup: flush 로 링을 비우고 타이머·리스너 제거
    sent.length = 0;

    reportAsGlobalError(r); // GlobalError 의 useEffect 는 teardown **뒤에** 돈다
    driveEveryDeliveryTrigger();

    expect(sent.length, "teardown 뒤에 난 js_error 가 배달되지 않았다").toBeGreaterThan(0);
  });


  /**
   * ★**인계서가 남긴 「배달 경로 갭」이 실제로 닫히는가.**
   *
   * 조기 포착 버퍼는 *"초기 렌더 오류"* 를 위해 만들어졌는데, 그 오류가 트리를 죽이면
   * `initEventCollector()` 가 안 돌아 **버퍼가 담긴 채 버려졌다**. 경계가 뜨는 순간이 바로
   * 그 순간이므로, 경계가 수집기를 초기화하면 버퍼가 **자기 목적대로 도착한다.**
   */
  /**
   * ★**즉시** 나가야 한다 — 타이머(5초)나 `pagehide` 를 기다리면 안 된다.
   * 경계가 떴다는 것은 화면이 깨졌다는 뜻이고, 사용자는 대개 그 자리에서 새로고침하거나 닫는다.
   * 이 케이스가 없으면 보고기의 `flush()` 는 **타이머에 가려 무잠금**이 된다(이중 가드).
   */
  it("★구동자를 하나도 발화시키지 않아도 그 자리에서 나간다", async () => {
    const { r } = await freshModules();
    const sent = captureSends();

    reportAsGlobalError(r);
    // ★`driveEveryDeliveryTrigger()` 를 **부르지 않는다** — 타이머·pagehide 없이 판정한다.

    expect(
      sent.length,
      "경계 보고가 즉시 나가지 않았다 — 사용자가 5초를 기다려 줄 것이라고 가정할 수 없다",
    ).toBeGreaterThan(0);
  });

  it("★조기 포착 버퍼가 경계 보고와 함께 배달된다 — 배달 경로 갭이 닫힌다", async () => {
    const { r } = await freshModules();
    const sent = captureSends();

    // 문서 파싱 시점 인라인 부트스트랩을 **실제로 실행**한다(문자열 검사 아님).
    new Function(earlyErrorBootstrap)();
    // 하이드레이션 커밋 전에 난 오류 — 이 시점에 수집기는 존재하지 않는다.
    window.dispatchEvent(
      new ErrorEvent("error", {
        message: "early-boom-418",
        filename: "x.js",
        lineno: 1,
        colno: 2,
        error: new Error("early-boom-418"),
      }),
    );

    // 그 오류가 트리를 죽여 경계가 떴다.
    reportAsGlobalError(r);
    driveEveryDeliveryTrigger();

    expect(sent.length, "아무것도 배달되지 않았다").toBeGreaterThan(0);
    const events = sent.flatMap(
      (b) => (JSON.parse(b) as { events: Array<Record<string, unknown>> }).events,
    );
    const early = events.find(
      (e) => (e.payload as Record<string, unknown> | null)?.message === "early-boom-418",
    );
    expect(
      early,
      "조기 포착 버퍼의 오류가 배달되지 않았다 — 버퍼는 담겼는데 배달자가 없다(원래 결함)",
    ).toBeTruthy();
    // ★두 모집단이 같은 실행에서 갈린다: 조기분과 경계분이 **둘 다** 실린다.
    expect(
      events.some((e) => (e.payload as Record<string, unknown> | null)?.scope === "global-error"),
      "경계 자신의 보고가 없다",
    ).toBe(true);
    // 조기분은 `early: true` 로 자기를 구별한다(정식 경로와 뭉치지 않게).
    expect((early!.payload as Record<string, unknown>).early).toBe(true);
  });
});
