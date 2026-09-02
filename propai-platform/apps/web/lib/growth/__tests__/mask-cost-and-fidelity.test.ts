/**
 * ★마스킹의 **비용**과 **충실도**를 함께 잠근다.
 *
 * 왜 비용이 계약인가(2026-08-28 실측, node):
 *   `EMAIL_RE` 의 local-part 수량자에 상한이 없으면 `@` 가 없는 긴 문자열에서
 *   **2차 백트래킹**이 난다. 같은 입력 `"x".repeat(n)` 기준 —
 *
 *       n=4,000    무상한 15.1ms   → 상한 1.1ms
 *       n=10,000   무상한 90.9ms   → 상한 3.1ms
 *       n=50,000   무상한 2,450.9ms → 상한 14.6ms   (**168배**)
 *
 *   대조군: 같은 길이라도 `@` 가 있으면 무상한도 0.0ms — 길이가 아니라 백트래킹이 원인이다.
 *   이 마스킹은 `window.onerror` 경로에서 **사용자 메인 스레드**에 돈다. 즉 긴 오류 메시지
 *   하나가 탭을 초 단위로 멈출 수 있었다.
 *
 * ★비용만 잠그면 "마스킹을 안 하면 빠르다"가 만점을 받는다 — **충실도를 같은 파일에서**
 *   함께 단언한다.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

/** 절대 예산 — 실측 상한값 14.6ms 대비 55배 여유, 무상한값 2,450ms 대비 3배 미만. */
const MASK_BUDGET_MS = 800;
const LONG_N = 50_000;

async function freshCollector() {
  vi.resetModules();
  return import("../event-collector");
}

function captureBodies() {
  const bodies: string[] = [];
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  vi.stubGlobal("fetch", ((_url: string, init?: RequestInit) => {
    bodies.push(String(init?.body ?? ""));
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
  return bodies;
}

/** 전송 본문에서 이 이벤트의 payload 를 되읽는다(마스킹 **결과**를 본다 — 소스가 아니라). */
function maskedPayload(bodies: string[], marker: number): Record<string, unknown> {
  const events = bodies.flatMap(
    (b) => (JSON.parse(b) as { events: Array<Record<string, unknown>> }).events,
  );
  const hit = events.find((e) => (e.payload as Record<string, unknown> | null)?.marker === marker);
  expect(hit, "대상 이벤트가 본문에 없다 — 이 테스트가 공허해진다").toBeTruthy();
  return hit!.payload as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("★마스킹 비용 — 긴 문자열이 메인 스레드를 멈추지 않는다", () => {
  it(`\`@\` 없는 ${LONG_N.toLocaleString()}자를 예산(${MASK_BUDGET_MS}ms) 안에 처리한다`, async () => {
    const { trackEvent, flush } = await freshCollector();
    captureBodies();

    const started = performance.now();
    trackEvent("js_error", { severity: "error", payload: { marker: 1, blob: "x".repeat(LONG_N) } });
    flush();
    const elapsed = performance.now() - started;

    // ★무상한 수량자면 여기서 2,450ms 규모가 나온다(실측). 예산은 그 3분의 1 미만.
    expect(
      elapsed,
      `마스킹이 ${elapsed.toFixed(0)}ms 걸렸다 — 수량자 상한이 사라져 백트래킹이 돌아온 것으로 보인다`,
    ).toBeLessThan(MASK_BUDGET_MS);
  });

  it("★대조군 — 비용을 줄이려고 **마스킹을 그만두지는 않았다**", async () => {
    const { trackEvent, flush } = await freshCollector();
    const bodies = captureBodies();

    trackEvent("js_error", {
      severity: "error",
      payload: {
        marker: 2,
        // RFC 유효 이메일 · 휴대폰 · 지번 — 셋 다 마스킹 대상이다.
        email: "user.name+tag@sub.example.com",
        phone: "010-1234-5678",
        addr: "테헤란로 123",
      },
    });
    flush();

    const p = maskedPayload(bodies, 2);
    expect(String(p.email), "이메일이 그대로 새어 나갔다").not.toContain("user.name+tag");
    expect(String(p.email), "이메일이 그대로 새어 나갔다").not.toContain("sub.example.com");
    expect(String(p.phone), "휴대폰이 그대로 새어 나갔다").not.toContain("1234-5678");
    expect(String(p.addr), "주소가 그대로 새어 나갔다").not.toContain("123");
  });

  it("★긴 문자열 **안에 있는** 이메일도 마스킹된다(자르기가 탐지를 죽이지 않았다)", async () => {
    const { trackEvent, flush } = await freshCollector();
    const bodies = captureBodies();

    // 앞쪽(보존 구간)에 이메일을 심는다 — 자르기 순서를 바꿔도 여기는 남아야 한다.
    trackEvent("js_error", {
      severity: "error",
      payload: { marker: 3, blob: `앞부분 secret.user@example.com ${"x".repeat(LONG_N)}` },
    });
    flush();

    const p = maskedPayload(bodies, 3);
    expect(String(p.blob), "긴 문자열 안의 이메일이 마스킹되지 않았다").not.toContain(
      "secret.user@example.com",
    );
  });
});

describe("★절단 순서 — 자른 뒤 마스킹해도 경계에서 새지 않는다", () => {
  it("`js_error.message` 는 상한까지만 남고, 경계 부근 이메일이 노출되지 않는다", async () => {
    const mod = await freshCollector();
    const bodies = captureBodies();

    // 상한(2,000자) 경계에 걸치도록 이메일을 배치한다.
    const head = "y".repeat(1_990);
    const long = `${head}boundary.leak@example.com${"z".repeat(5_000)}`;

    mod.initEventCollector();
    window.dispatchEvent(new ErrorEvent("error", { message: long }));
    mod.flush();
    mod.teardownEventCollector();

    const events = bodies.flatMap(
      (b) => (JSON.parse(b) as { events: Array<Record<string, unknown>> }).events,
    );
    const hit = events.find((e) => e.event_type === "js_error");
    expect(hit, "js_error 가 전송되지 않았다").toBeTruthy();
    const msg = String((hit!.payload as Record<string, unknown>).message ?? "");

    // ★양방향으로 건다(§D-19). 상한만 걸면 "전부 버린다"가 만점을 받는다.
    //   마스킹이 `[email]`(7자)로 치환하므로 보존분이 **상한보다 짧아지는 것은 정상**이다
    //   — 그래서 정확히 2,000 이 아니라 범위로 잡는다.
    expect(msg.length, "상한이 지켜지지 않았다").toBeLessThanOrEqual(2_000);
    expect(msg.length, "내용이 통째로 사라졌다 — 상한을 지킨다고 다 버리면 안 된다").toBeGreaterThan(1_500);
    expect(msg, "경계에 걸친 이메일이 부분 노출됐다").not.toContain("boundary.leak@example.com");
    expect(msg, "경계에 걸친 이메일의 앞부분이 남았다").not.toContain("boundary.leak");
  });
});
