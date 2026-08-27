// @vitest-environment jsdom
/**
 * ★**프로덕션이 실제로 타는 전송 경로**(`navigator.sendBeacon`)를 태운다.
 *
 * 【왜 이 파일이 필요한가 — 2026-08-28 실측】
 * 전송을 태우는 기존 테스트 **전부**가 `sendBeacon` 을 **없는 것으로 만들어** `fetch` 폴백을
 * 강제한다(`Blob` 을 **동기로** 못 읽어서다 — 그 사유가 형제 테스트 주석에 적혀 있다):
 *
 *     global-error-delivery · filename-masking · chunk-recovery ·
 *     selection-contamination.transport · boundary-render-delivery
 *       → 전부 `sendBeacon: undefined`
 *
 * 즉 **프로덕션이 실제로 타는 분기는 어떤 테스트도 안 태웠다.** 그 층에 변이를 넣으면
 * (`sent = true; void blob;` — 보내지 않고 성공으로 위장) **전부 초록**이었다.
 * 이 저장소가 문서화한 *"스텁이 검증 대상 층을 우회한다"*(§검증규율 3)의 정확한 사례다.
 *
 * ★해법은 **비동기로 읽는 것**이다. 동기로 못 읽는다는 제약은 *"그 층을 못 태운다"* 가 아니라
 *   *"동기 단언으로는 못 태운다"* 였다.
 *
 * ★**어떤 비동기 방법인가는 재서 골랐다**(jsdom Blob 능력 실측 2026-08-28):
 *
 *     blob.text / arrayBuffer / stream   → **undefined**(jsdom Blob 은 최소 구현이다)
 *     new Response(blob).text()          → **"[object Blob]"**  ← ★던지지 않고 **조용히 틀린 답**
 *     FileReader.readAsText(blob)        → **{"a":1}**          ← ◎ 유일하게 옳다
 *
 *   ★`Response` 경로는 **위험하다** — 실패하지 않고 문자열을 주므로, 그것으로 단언을 짜면
 *   **통과하지만 아무것도 안 재는 테스트**가 된다. 그래서 아래 `readBlob` 은 읽은 결과가
 *   **실제 JSON 인지**까지 확인한다(조용히 틀린 답을 초록으로 넘기지 않는다).
 *
 * ★**런타임은 한 줄도 안 고친다.** 오늘 낸 `#903`·`#919` 가 전부 이 경로에 의존하는데
 *   그 경로가 무잠금이었다 — 그 사실만 닫는다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { flush, trackEvent } from "@/lib/growth/event-collector";

type BeaconCall = { url: string; blob: Blob };
let beacons: BeaconCall[] = [];
let fetches: string[] = [];

/** `sendBeacon` 을 **있는 것으로** 두고 본문을 붙잡는다(프로덕션과 같은 분기). */
function installTransport(beaconResult: boolean | "throw"): void {
  beacons = [];
  fetches = [];
  vi.stubGlobal("navigator", {
    ...globalThis.navigator,
    sendBeacon: vi.fn((url: string, data: Blob) => {
      if (beaconResult === "throw") throw new Error("beacon boom");
      beacons.push({ url: String(url), blob: data });
      return beaconResult;
    }),
  });
  vi.stubGlobal("fetch", ((u: string, init?: RequestInit) => {
    fetches.push(String(init?.body ?? u));
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
}

/**
 * `Blob` 을 텍스트로 읽는다. ★`FileReader` 만 jsdom 에서 옳다(위 실측 표).
 * 읽은 것이 **JSON 이 아니면 시끄럽게 실패**한다 — `"[object Blob]"` 류의 조용히 틀린 답 차단.
 */
async function readBlob(blob: Blob): Promise<string> {
  const text = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error ?? new Error("FileReader 실패"));
    r.readAsText(blob);
  });
  try {
    JSON.parse(text);
  } catch {
    throw new Error(
      `Blob 을 읽었는데 JSON 이 아니다 — 읽기 방법이 조용히 틀린 답을 줬다: ${text.slice(0, 80)}`,
    );
  }
  return text;
}

const fire = (): void => {
  trackEvent("js_error", { severity: "error", payload: { scope: "TX-PROBE", message: "m" } });
  flush();
};

beforeEach(() => {
  flush(); // 선행 잔재 제거
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("★전송 — 프로덕션 분기(sendBeacon)를 실제로 태운다", () => {
  it("A `sendBeacon` 이 있으면 **그 경로로** 나가고 `fetch` 는 안 쓴다", async () => {
    installTransport(true);
    fire();

    // 공허 진리 가드 — 전송이 아예 없었으면 아래 단언은 무의미하다.
    expect(beacons.length, "sendBeacon 이 한 번도 안 불렸다").toBe(1);
    // ★두 모집단: beacon 이 성공하면 **fetch 는 안 탄다**(한쪽만 보면 "둘 다 보내는" 구현도 통과).
    expect(fetches, "beacon 이 성공했는데 fetch 도 탔다 — 이중 전송").toEqual([]);

    expect(beacons[0].url).toContain("/api/v1/growth/events");
    // ★`Blob` 은 **비동기로** 읽는다 — 이 한 줄이 그동안 이 층을 못 태우게 만든 제약이었다.
    const body = await readBlob(beacons[0].blob);
    const parsed = JSON.parse(body) as { events: Array<Record<string, unknown>> };
    const ev = parsed.events.find((e) => e.event_type === "js_error");
    expect(ev, "js_error 가 본문에 없다").toBeTruthy();
    expect((ev!.payload as Record<string, unknown>).scope).toBe("TX-PROBE");
    // 주석이 선언한 content-type 이 실제로 붙는지(선언 ≠ 구현 방지).
    expect(beacons[0].blob.type).toBe("application/json");
  });

  it("★B `sendBeacon` 이 **false** 를 주면 `fetch keepalive` 로 폴백한다(예산 초과 경로)", async () => {
    installTransport(false);
    fire();
    expect(beacons.length, "beacon 을 시도조차 안 했다").toBe(1);
    expect(fetches.length, "beacon 이 false 인데 폴백이 안 돌았다 — 조용한 전손").toBe(1);
    expect(JSON.parse(fetches[0]).events.length).toBeGreaterThan(0);
  });

  it("C `sendBeacon` 이 **던지면** 폴백한다(수집 실패가 앱을 막지 않는다)", () => {
    installTransport("throw");
    expect(() => fire()).not.toThrow();
    expect(fetches.length, "예외 뒤 폴백이 없다").toBe(1);
  });

  it("★readBlob 의 **조용한 오답 가드**가 실제로 발화한다", async () => {
    // ★변이 실측: 이 케이스가 없으면 `JSON.parse(text)` 가드를 지워도 **생존**했다.
    //   그 가드는 `new Response(blob).text()` 처럼 **던지지 않고 `"[object Blob]"` 를 주는**
    //   읽기 방법을 채택하는 것을 막는다 — 그런 방법을 쓰면 **통과하지만 아무것도 안 재는**
    //   테스트가 된다. 가드 자신을 잠그지 않으면 그 방어가 장식이다.
    await expect(readBlob(new Blob(["[object Blob]"]))).rejects.toThrow(/JSON 이 아니다/);
    // 두 모집단 — 정상 JSON 은 **통과해야** 한다(과잉 억제 방지).
    await expect(readBlob(new Blob(['{"a":1}']))).resolves.toBe('{"a":1}');
  });

  it("★D 음성 대조군 — 보낼 것이 없으면 **아무 경로도** 타지 않는다", () => {
    installTransport(true);
    flush(); // 링이 비어 있다
    expect(beacons).toEqual([]);
    expect(fetches).toEqual([]);
  });
});
