/**
 * ★전송 예산 — **64KiB 절벽에서의 조용한 전손**을 잠근다.
 *
 * 무엇이 결함이었나(2026-08-28 실측):
 *   `flush()` 가 `ring.splice(0, MAX_BATCH)` 로 **보내기 전에** 링을 비우는데, 본문이
 *   64KiB 를 넘으면 `sendBeacon` 이 `false` 를 주고 폴백 `fetch(keepalive:true)` 는
 *   **같은 64KiB 예산**을 쓰므로 같은 이유로 실패한다. 그 실패는 `.catch(() => {})` 가
 *   삼키고, 배치는 이미 링에서 빠진 뒤라 **되돌릴 대상조차 없다** → 조용한 전손.
 *
 * ★스텁 주의: 여기서는 `sendBeacon` 을 `undefined` 로 만들어 fetch 경로를 강제한다.
 *   그래도 **검증 대상 층을 우회하지 않는다** — 배치 조립(`takeBatchWithinBudget`)은
 *   전송 수단을 **고르기 전에** 끝나므로 두 전송로에서 동일하다. 우회했다면 이 파일이
 *   아니라 배치 조립을 직접 태우는 테스트가 따로 필요했을 것이다(규율 §3).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

/** ★계약 리터럴 — 구현 상수를 import 해서 자기 자신과 비교하면 아무것도 잠기지 않는다. */
const BUDGET_BYTES = 56_000;
const COUNT_CAP = 100;
const FIELD_CHARS = 2_000;

const utf8 = (text: string): number => new TextEncoder().encode(text).length;

/** 모듈 상태(`ring`)가 테스트 간에 새지 않도록 매번 새로 적재한다. */
async function freshCollector() {
  vi.resetModules();
  return import("../event-collector");
}

/** fetch 를 가로채 전송 본문을 모은다. `sendBeacon` 은 없애 폴백 경로를 강제한다. */
function captureBodies(opts: { reject?: boolean } = {}) {
  const bodies: string[] = [];
  vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
  vi.stubGlobal("fetch", ((_url: string, init?: RequestInit) => {
    bodies.push(String(init?.body ?? ""));
    return opts.reject ? Promise.reject(new Error("network down")) : Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
  return bodies;
}

const eventsIn = (body: string): Array<Record<string, unknown>> =>
  (JSON.parse(body) as { events: Array<Record<string, unknown>> }).events;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("★전송 예산 — 예산을 넘는 배치를 만들지 않는다", () => {
  it("100건 대용량을 넣어도 **모든 본문이 예산 이하**이고 **한 건도 잃지 않는다**", async () => {
    const { trackEvent, flush, getDroppedEventCount } = await freshCollector();
    const bodies = captureBodies();

    // ★크기를 이렇게 잡는 이유(첫 판이 **공허하게 초록**이었다):
    //   `FLUSH_THRESHOLD=20` 이 20건마다 자동 flush 를 건다. 건당 1,500자로는 한 배치가
    //   ~32KB 라 **예산이 한 번도 안 걸리고**, 그런데도 "쪼개졌다"는 참이 된다(쪼갠 것은
    //   예산이 아니라 임계다). 그 상태에서는 예산 상수를 지워도 테스트가 통과한다 — 실측했다.
    //   건당 10,000자면 임계 배치(20건)만으로 ~200KB 라 **예산이 반드시 구속**한다.
    const TOTAL = 100;
    const PER_EVENT_CHARS = 10_000;
    for (let i = 0; i < TOTAL; i += 1) {
      trackEvent("js_error", { severity: "error", payload: { i, message: "x".repeat(PER_EVENT_CHARS) } });
    }

    // 링이 빌 때까지 flush(자동 flush 로 이미 일부 나갔을 수 있다).
    for (let i = 0; i < 50; i += 1) flush();

    // 공허 진리 가드 — 전송이 없었으면 아래 단언은 전부 무의미하다.
    expect(bodies.length, "전송이 한 번도 일어나지 않았다").toBeGreaterThan(0);

    // ★탐지: 어떤 본문도 예산을 넘지 않는다(이름이 아니라 **실측 바이트**).
    const oversized = bodies.map(utf8).filter((n) => n > BUDGET_BYTES);
    expect(oversized, `예산 초과 본문 ${oversized.length}건: ${oversized.join(",")}`).toEqual([]);

    // ★공허 방지 — **예산이 실제로 구속했는지**를 본다.
    //   단순히 "쪼개졌다"로는 부족하다: `FLUSH_THRESHOLD` 도 쪼개기 때문에 예산을 지워도 참이다.
    //   예산이 구속했다면 배치당 건수가 임계(20)보다 **작아야** 한다.
    const counts = bodies.map((b) => eventsIn(b).length);
    expect(
      Math.max(...counts),
      "배치당 건수가 임계(20) 이상이다 — 쪼갠 것이 예산이 아니라 임계라서 이 테스트가 공허하다",
    ).toBeLessThan(20);

    // ★무손실: 전손이 결함의 본체였다. 넣은 수와 나간 수가 같아야 한다.
    const delivered = bodies.reduce((n, b) => n + eventsIn(b).length, 0);
    expect(delivered, "전송된 이벤트 수가 넣은 수와 다르다 — 어딘가에서 잃었다").toBe(TOTAL);
    expect(getDroppedEventCount(), "버린 건이 있다").toBe(0);
  });

  it("★`TextEncoder` 가 없어도 예산을 지킨다 — 폴백은 **과대** 추정이어야 한다", async () => {
    // ★이 축은 jsdom 에 `TextEncoder` 가 **항상 있어서** 다른 테스트로는 절대 안 태워진다
    //   (변이 실측: 폴백을 `return 0` 으로 바꿔도 전 테스트 통과 = SURVIVED).
    //   폴백이 **과소** 추정하면 예산 계산이 무너져 그대로 절벽으로 돌아간다.
    const realEncoder = globalThis.TextEncoder;
    try {
      // @ts-expect-error — 폴백 경로를 강제로 태운다.
      delete (globalThis as Record<string, unknown>).TextEncoder;

      const { trackEvent, flush } = await freshCollector();
      const bodies: string[] = [];
      vi.stubGlobal("navigator", { ...globalThis.navigator, sendBeacon: undefined });
      vi.stubGlobal("fetch", ((_url: string, init?: RequestInit) => {
        bodies.push(String(init?.body ?? ""));
        return Promise.resolve({ ok: true } as Response);
      }) as unknown as typeof fetch);

      for (let i = 0; i < 40; i += 1) {
        trackEvent("js_error", { severity: "error", payload: { i, message: "x".repeat(10_000) } });
      }
      for (let i = 0; i < 30; i += 1) flush();

      expect(bodies.length, "전송이 없었다").toBeGreaterThan(0);
      // 실측 바이트는 **진짜** 인코더로 잰다(대상이 쓰는 폴백과 독립).
      const over = bodies.map((b) => new realEncoder().encode(b).length).filter((n) => n > BUDGET_BYTES);
      expect(over, `폴백이 과소 추정해 예산을 넘겼다: ${over.join(",")}`).toEqual([]);
    } finally {
      globalThis.TextEncoder = realEncoder;
    }
  });

  it("★특이도 — 예산 **이하** 입력은 쪼개지 않고 **한 번에** 보낸다", async () => {
    const { trackEvent, flush } = await freshCollector();
    const bodies = captureBodies();

    for (let i = 0; i < 5; i += 1) {
      trackEvent("js_error", { severity: "error", payload: { i, message: "짧은 오류" } });
    }
    flush();

    // ★이 축이 없으면 "항상 1건씩 보낸다"는 구현이 위 테스트에서 만점을 받는다.
    expect(bodies.length, "작은 입력을 불필요하게 쪼갰다").toBe(1);
    expect(eventsIn(bodies[0]).length).toBe(5);
    expect(utf8(bodies[0])).toBeLessThanOrEqual(BUDGET_BYTES);
  });

  it("★계약 — 건수 상한(백엔드 `_MAX_BATCH`)을 넘기지 않는다", async () => {
    const { trackEvent, flush } = await freshCollector();

    // ★상한 100 은 `trackEvent` 만으로는 **도달 불가**하다 — `FLUSH_THRESHOLD=20` 이
    //   20건마다 자동 flush 를 걸어 배치가 20을 못 넘긴다(첫 판에서 실측: 최대 20).
    //   상한이 실제로 걸리는 모집단은 **전송이 실패해 링에 쌓인 뒤 회복될 때**다.
    //   그 상태를 만들지 않으면 이 단언은 공허하다.
    const failing = captureBodies({ reject: true });
    for (let i = 0; i < 250; i += 1) {
      trackEvent("js_error", { severity: "error", payload: { i } });
    }
    for (let i = 0; i < 20; i += 1) flush();
    await Promise.resolve();
    await Promise.resolve();
    expect(failing.length, "실패 경로가 한 번도 안 탔다").toBeGreaterThan(0);
    vi.unstubAllGlobals();

    const bodies = captureBodies();
    for (let i = 0; i < 50; i += 1) flush();

    expect(bodies.length, "회복 후 전송이 없었다 — 링에 아무것도 안 남았다는 뜻").toBeGreaterThan(0);
    const counts = bodies.map((b) => eventsIn(b).length);
    expect(Math.max(...counts), `건수 상한 초과: ${Math.max(...counts)}`).toBeLessThanOrEqual(COUNT_CAP);
    // 상한이 **실제로 걸렸는지** — 전부 소량이면 위 단언은 공허하다.
    expect(Math.max(...counts), "상한이 한 번도 걸리지 않아 공허한 단언이 됐다").toBe(COUNT_CAP);
  });
});

describe("★실패 복원 — 전송이 실패해도 이벤트가 사라지지 않는다", () => {
  it("실패하면 링에 남아 **다음 flush 로 배달**된다(성공하면 재배달되지 않는다)", async () => {
    const { trackEvent, flush } = await freshCollector();

    // 모집단 A — 전송이 **실패**한다.
    const failed = captureBodies({ reject: true });
    trackEvent("js_error", { severity: "error", payload: { marker: "RESTORE_ME" } });
    flush();
    expect(failed.length, "1차 전송 시도가 없었다").toBe(1);
    await Promise.resolve();
    await Promise.resolve();
    vi.unstubAllGlobals();

    // 모집단 B — 이제 **성공**한다. 잃지 않았다면 여기서 나와야 한다.
    const ok = captureBodies();
    flush();
    const redelivered = ok.flatMap(eventsIn).filter(
      (e) => (e.payload as Record<string, unknown> | null)?.marker === "RESTORE_ME",
    );
    expect(redelivered.length, "실패한 이벤트가 사라졌다 — 조용한 전손이 그대로다").toBe(1);

    // ★대조 모집단 — 성공한 뒤에는 **재배달되지 않는다**(무한 재전송이 아니다).
    const again = captureBodies();
    flush();
    expect(again.flatMap(eventsIn).length, "성공한 이벤트가 다시 나갔다 — 중복 전송").toBe(0);
  });
});

describe("★형제 절단 — 두 경로가 **같은 길이**로 자른다", () => {
  it("정식 경로와 조기 경로의 `js_error` 메시지 절단이 동일하다", async () => {
    const mod = await freshCollector();
    const LONG = "가".repeat(5_000);

    // 조기 버퍼에 긴 오류를 심어 둔다(하이드레이션 전 포착분).
    (window as unknown as { __propaiEarly?: unknown }).__propaiEarly = {
      buf: [{ k: "error", m: LONG, f: null, l: null, c: null, s: null, t: 1 }],
      closed: false,
    };

    const bodies = captureBodies();
    mod.initEventCollector(); // 조기 버퍼를 비우며 js_error 를 만든다
    window.dispatchEvent(new ErrorEvent("error", { message: LONG })); // 정식 경로
    mod.flush();
    mod.teardownEventCollector();

    const all = bodies.flatMap(eventsIn);
    const lens = all
      .filter((e) => e.event_type === "js_error")
      .map((e) => String((e.payload as Record<string, unknown>).message ?? "").length);

    expect(lens.length, "js_error 가 두 경로에서 나오지 않았다").toBeGreaterThanOrEqual(2);
    // ★값을 못 박는다 — 상수를 import 해 자기 자신과 비교하면 아무것도 안 잠긴다.
    for (const n of lens) expect(n).toBe(FIELD_CHARS);
    // 두 경로가 **같은 길이**여야 analyzer 의 sha1 군집이 갈리지 않는다.
    expect(new Set(lens).size, "조기/정식 경로의 절단 길이가 다르다 — 시그니처가 분열된다").toBe(1);
  });
});
