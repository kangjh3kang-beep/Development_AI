// @vitest-environment jsdom
/**
 * ★**`sendBeacon` 이 성공하는 하위경로와 Blob 본문**을 태운다.
 *
 * 【무엇이 무잠금이었나 — ★서사를 정정한다】
 * 초판은 *"프로덕션 분기를 **어떤 테스트도** 안 태운다 · 그 층 변이가 **모든 락을 통과**한다"* 고
 * 적었다. **거짓이었다.** 독립 리뷰가 반증했고 내가 직접 재서 확인했다:
 *
 *     `early-error-capture.test.ts` 는 `sendBeacon: () => false` 로 두어 **그 분기를 실제로 태운다**.
 *     변이 `sent = true; void blob;` 를 **기존 락만으로 CAUGHT** 한다.
 *
 * ★내가 그렇게 오판한 이유: 변이 러너를 **손으로 고른 3파일**로 짰고 거기에 그 파일이 없었다 —
 *   **러너 목록이 모집단의 상한이 됐다**(이 저장소가 반복해 데인 「목록은 곧 상한」).
 *   그래서 이 파일의 러너는 **디렉토리 파생형**이다(아래 주석 참조).
 *
 * 【그래도 이 락이 필요한 이유 — 좁혀서 말한다】
 * 기존 락은 `sendBeacon` 이 **`false` 를 주는 경로**만 태운다. 다음 두 변이는
 * **기존 락만으로 SURVIVED / 이 파일을 포함하면 CAUGHT** 다(독립 리뷰 실측):
 *
 *     Blob type "application/json" → "text/plain"
 *     sendBeacon(url, blob)        → sendBeacon(url, body)   ← Blob 이 아니라 문자열
 *
 * 즉 무잠금이었던 것은 **성공 하위경로 + Blob 의 형태·본문**이다. 그 좁은 범위로도 충분하다 —
 * **과장할 필요가 없었다.**
 *
 * 【★읽기 방법은 「고르기 전에」 쟀다 — 한 방법은 조용히 틀린 답을 준다】
 * 형제들이 폴백을 강제한 사유(*"Blob 을 **동기로** 못 읽는다"*)는 **참이다**. jsdom 실측:
 *
 *     blob.text / arrayBuffer / stream   → **undefined**
 *     new Response(blob).text()          → **"[object Blob]"**  ★던지지 않고 조용히 틀린 답
 *     FileReader.readAsText(blob)        → **{"a":1}**          ◎ 유일하게 옳다
 *
 * ★`Response` 로 짰으면 **통과하지만 아무것도 안 재는 테스트**가 됐다. 그래서 `readBlob` 은
 *   읽은 결과가 **실제 JSON 인지**까지 확인하고, 그 가드 자신도 두 모집단으로 잠근다.
 *
 * ★**런타임은 한 줄도 안 고친다.**
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveApiOrigin } from "@/lib/api-client";
import { flush, trackEvent } from "@/lib/growth/event-collector";

import { readBlobAsJsonText as readBlob } from "./_read-blob";

type BeaconCall = { url: string; blob: Blob };
let beacons: BeaconCall[] = [];
let fetches: Array<{ url: string; init?: RequestInit }> = [];

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
  // ★**본문만** 담으면 `keepalive`·`method`·헤더가 통째로 무잠금이 된다(독립 리뷰 실측:
  //   `keepalive:false`·`GET`·헤더 제거가 전부 SURVIVED). 요청 **형태**를 그대로 담는다.
  vi.stubGlobal("fetch", ((u: string, init?: RequestInit) => {
    fetches.push({ url: String(u), init });
    return Promise.resolve({ ok: true } as Response);
  }) as unknown as typeof fetch);
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

    // ★`toContain` 이면 **상대경로에서도 참**이다 — 그런데 그 상대경로는 `event-collector` 가
    //   스스로 경고하는 프로덕션 사고다(*"프론트 오리진으로 가서 404"*). 기대값도 **소스에서 파생**한다.
    expect(beacons[0].url, "오리진 해석이 빠지면 프론트 오리진으로 가서 404 가 된다").toBe(
      `${resolveApiOrigin()}/api/v1/growth/events`,
    );
    // ★`Blob` 은 **비동기로** 읽는다 — 이 한 줄이 그동안 이 층을 못 태우게 만든 제약이었다.
    const body = await readBlob(beacons[0].blob);
    const parsed = JSON.parse(body) as { events: Array<Record<string, unknown>> };
    const ev = parsed.events.find((e) => e.event_type === "js_error");
    expect(ev, "js_error 가 본문에 없다").toBeTruthy();
    expect((ev!.payload as Record<string, unknown>).scope).toBe("TX-PROBE");
    // 주석이 선언한 content-type 이 실제로 붙는지(선언 ≠ 구현 방지).
    // ★`toBe` 로 못 박으면 `application/json; charset=utf-8` 같은 **정당한 변형**을 막는다.
    expect(beacons[0].blob.type).toMatch(/^application\/json\b/);
  });

  it("★B `sendBeacon` 이 **false** 를 주면 `fetch keepalive` 로 폴백한다(예산 초과 경로)", async () => {
    installTransport(false);
    fire();
    expect(beacons.length, "beacon 을 시도조차 안 했다").toBe(1);
    expect(fetches.length, "beacon 이 false 인데 폴백이 안 돌았다 — 조용한 전손").toBe(1);
    const { init } = fetches[0];
    // ★**개수가 아니라 값**을 본다. 초판은 `events.length > 0` 만 봐서, **폴백 본문을 상수로
    //   동결하는** 변이를 **내 파일은 못 잡았다**(형제 테스트가 대신 잡아 CAUGHT 로 보였을 뿐 —
    //   내 파일 단독 러너로 재서 갈랐다). 동료 세션 `development-ai-ca` 가 같은 형태를
    //   `#920` 에서 실측해 넘겨 준 패턴이다:
    //     *"이 단언은 「이름이 있다」를 보는가, 「값이 실린다」를 보는가?"*
    const fbEvents = (JSON.parse(String(init?.body)) as {
      events: Array<Record<string, unknown>>;
    }).events;
    const mine = fbEvents.find(
      (e) => (e.payload as Record<string, unknown> | null)?.scope === "TX-PROBE",
    );
    expect(mine, `폴백 본문에 **내 이벤트의 값**이 없다: ${JSON.stringify(fbEvents).slice(0, 120)}`)
      .toBeTruthy();
    expect(mine!.event_type).toBe("js_error");
    // ★제목이 **선언**한 것을 단언한다 — `keepalive` 가 죽으면 **언로드 시 전손**이고,
    //   그것이 이 폴백이 존재하는 유일한 이유다(선언 ≠ 발화).
    expect(init?.keepalive, "keepalive 가 아니면 언로드 시 전손이다").toBe(true);
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)?.["Content-Type"]).toMatch(
      /^application\/json\b/,
    );
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
    // ★**설명되는 생존**: `if (ring.length === 0) return;` 단독 제거는 생존한다 —
    //   그 뒤 `batch.length === 0` 가 받아 주는 **이중 가드**다(점수용 단언을 붙이지 않는다).
    expect(beacons).toEqual([]);
    expect(fetches).toEqual([]);
  });
});
