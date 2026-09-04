/**
 * A② 타일 경로 168 일원화 — **릴레이 1순위 승격**의 배선 락.
 *
 * 【왜 이 파일이 필요한가】
 * 릴레이를 주 경로로 올리면서 가장 위험한 것은 **차단기가 죽는 것**이었다.
 * 종전 `relayViaApi` 는 `recordSuccess`/`recordFailure` 를 **한 번도 부르지 않았다** —
 * 직접 경로가 주 경로일 때는 드러나지 않지만, 릴레이가 주 경로가 되는 순간
 * `vworld-circuit-breaker.ts` 는 **아무것도 보호하지 않는 죽은 코드**가 된다.
 * 그러면 #495 가 고친 "실패 폭주" 구조가 158→168 링크에서 그대로 재생산된다
 * (자해 대상만 VWorld → 우리 백엔드로 바뀐다).
 *
 * 【두 모집단을 가른다】
 * 이 저장소의 규율: *"차가 0 인 픽스처는 잠금이 아니다."*
 * 성공 시 두 경로는 **바이트까지 같은 200 image/png** 를 낸다 — 그래서 응답만 봐서는
 * 어느 경로로 갔는지 구분할 수 없고, 배선을 끊어도 초록이 된다.
 * → **어느 호스트를 불렀는지**(상류 VWorld vs 릴레이 오리진)로 가른다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetBreakers } from "@/lib/vworld-circuit-breaker";

/**
 * ★차단기 상태는 **프록시와 같은 모듈 그래프**에서 읽어야 한다.
 *   `vi.resetModules()` 뒤 동적 import 는 새 그래프를 만든다 — 정적 import 한
 *   `breakerState` 는 프록시가 쓰는 registry 와 **다른 Map** 을 본다.
 *   그러면 배선이 멀쩡해도 항상 "closed" 로 읽히고, "closed" 를 기대하는 대조군은
 *   **관측이 깨진 채로 초록**이 된다(실제로 이 파일이 그 상태였다).
 */
async function loadBreakerState() {
  const m = await import("@/lib/vworld-circuit-breaker");
  return m.breakerState;
}

const RELAY_ORIGIN = "https://api.example.test";
const UPSTREAM = "https://api.vworld.kr";

beforeEach(() => {
  resetBreakers();
  vi.resetModules();
  process.env.VWORLD_API_KEY = "test-key-1234567890";
  process.env.NEXT_PUBLIC_API_BASE_URL = `${RELAY_ORIGIN}/api/v1`;
});
afterEach(() => {
  vi.restoreAllMocks();
  resetBreakers();
});

function wmsParams(): URLSearchParams {
  return new URLSearchParams({
    SERVICE: "WMS", REQUEST: "GetMap", VERSION: "1.3.0",
    LAYERS: "lp_pa_cbnd_bubun", CRS: "EPSG:3857",
    BBOX: "1,2,3,4", WIDTH: "256", HEIGHT: "256",
    FORMAT: "image/png", TRANSPARENT: "true",
  });
}

/** 호출된 호스트를 기록한다 — 이것이 두 모집단을 가르는 관측값이다. */
function installFetch(opts: { relayStatus?: number; relayThrows?: boolean } = {}) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: unknown) => {
    const url = String(input);
    calls.push(url);
    if (url.startsWith(RELAY_ORIGIN)) {
      if (opts.relayThrows) throw new TypeError("fetch failed");
      const status = opts.relayStatus ?? 200;
      if (status !== 200) return new Response("upstream sad", { status });
      return new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { "content-type": "image/png", "cache-control": "public, max-age=3600" },
      });
    }
    // 상류(VWorld) 직접 — 이 세션의 실측대로 막혀 있다고 본다.
    throw new TypeError("fetch failed");
  }));
  return calls;
}

describe("릴레이가 1순위 경로다", () => {
  it("★첫 요청은 회복 탐색이라 직접을 태우지만, 그 다음부터는 상류를 부르지 않는다", async () => {
    const calls = installFetch();
    const { proxyVWorldWms, __resetDirectProbeForTest } = await import("@/lib/vworld-wms-proxy");
    __resetDirectProbeForTest();

    await proxyVWorldWms(wmsParams()); // 1건: 회복 탐색(직접 시도 → 실패 → 릴레이)
    const afterProbe = calls.length;
    calls.length = 0;

    for (let i = 0; i < 5; i += 1) await proxyVWorldWms(wmsParams());

    expect(afterProbe, "첫 요청이 아무 호출도 안 했다 — 전제가 깨졌다").toBeGreaterThan(0);
    expect(
      calls.filter((u) => u.startsWith(UPSTREAM)),
      "탐색 간격 안인데 상류를 또 불렀다 — 릴레이 1순위가 배선되지 않았다",
    ).toEqual([]);
    expect(
      calls.filter((u) => u.startsWith(RELAY_ORIGIN)).length,
      "릴레이로 가지 않았다",
    ).toBe(5);
  });

  it("대조군: 릴레이 오리진이 없으면 **직접이 유일 경로**라 매번 상류를 태운다", async () => {
    // ★이 케이스가 위와 **다른 값**을 내야 위 테스트가 배선을 잠근다.
    //   둘 다 "상류 0회"면 배선을 끊어도 초록이다.
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    const calls = installFetch();
    const { proxyVWorldWms, __resetDirectProbeForTest } = await import("@/lib/vworld-wms-proxy");
    __resetDirectProbeForTest();

    await proxyVWorldWms(wmsParams());

    expect(
      calls.filter((u) => u.startsWith(UPSTREAM)).length,
      "릴레이가 없으면 직접이 유일 경로여야 한다",
    ).toBeGreaterThan(0);
  });
});

describe("★릴레이 링크도 차단기가 보호한다 (죽은 코드 방지)", () => {
  it("릴레이가 연속 실패하면 릴레이 차단기가 열린다", async () => {
    installFetch({ relayThrows: true });
    const { proxyVWorldWms, RELAY_BREAKER_KEY, __resetDirectProbeForTest } = await import(
      "@/lib/vworld-wms-proxy"
    );
    __resetDirectProbeForTest();

    const breakerState = await loadBreakerState();
    expect(breakerState(RELAY_BREAKER_KEY), "시작은 closed 여야 한다").toBe("closed");
    for (let i = 0; i < 6; i += 1) await proxyVWorldWms(wmsParams());

    expect(
      breakerState(RELAY_BREAKER_KEY),
      "릴레이가 6번 죽었는데 차단기가 닫혀 있다 — relayViaApi 가 차단기에 기록하지 않는다",
    ).toBe("open");
  });

  it("대조군: 릴레이가 성공하면 차단기는 닫힌 채로 남는다", async () => {
    // ★두 모집단이 **다른 상태**를 내야 위 단언이 잠금이 된다.
    installFetch({ relayStatus: 200 });
    const { proxyVWorldWms, RELAY_BREAKER_KEY, __resetDirectProbeForTest } = await import(
      "@/lib/vworld-wms-proxy"
    );
    __resetDirectProbeForTest();

    for (let i = 0; i < 6; i += 1) await proxyVWorldWms(wmsParams());

    const breakerState = await loadBreakerState();
    expect(breakerState(RELAY_BREAKER_KEY)).toBe("closed");
  });

  it("★4xx 는 링크 장애로 세지 않는다 — 잘못된 요청이 정상 링크를 차단시키면 위양성이다", async () => {
    installFetch({ relayStatus: 400 });
    const { proxyVWorldWms, RELAY_BREAKER_KEY, __resetDirectProbeForTest } = await import(
      "@/lib/vworld-wms-proxy"
    );
    __resetDirectProbeForTest();

    for (let i = 0; i < 6; i += 1) await proxyVWorldWms(wmsParams());

    const breakerState = await loadBreakerState();
    expect(breakerState(RELAY_BREAKER_KEY), "4xx 로 링크를 차단하면 정상 코드를 막는다").toBe(
      "closed",
    );
  });
});

describe("릴레이가 끊기면 **정직하게 강등**한다 (회색 지도 금지 · 무음 금지)", () => {
  it("★투명타일 200 + 강등 헤더 + 음성 캐시", async () => {
    installFetch({ relayThrows: true });
    const { proxyVWorldWms, VWORLD_DEGRADED_HEADER, __resetDirectProbeForTest } = await import(
      "@/lib/vworld-wms-proxy"
    );
    __resetDirectProbeForTest();
    await proxyVWorldWms(wmsParams()); // 회복 탐색 소진

    const resp = await proxyVWorldWms(wmsParams());
    const cc = resp.headers.get("cache-control") ?? "";

    // (1) 회색 지도 금지 — 503 이면 Leaflet 이 지도 전체를 회색으로 만든다.
    expect(resp.status, "503 이면 지도가 회색이 된다(2026-08-16 실장애의 사용자 경험)").toBe(200);
    expect(resp.headers.get("content-type")).toContain("image/png");
    // (2) 무음 금지 — 강등 사실이 헤더로 관측 가능해야 한다.
    expect(
      resp.headers.get(VWORLD_DEGRADED_HEADER),
      "강등 헤더가 없다 — 투명타일만 주면 배너가 뜰 수 없어 **무음 강등**이 된다",
    ).toContain("relay-unreachable");
    // (3) 폭주 금지 — no-store 면 팬/줌마다 전 타일이 재요청된다.
    expect(cc, `강등 응답이 no-store 다 — 폭주 구조가 그대로다 (cc=${cc})`).not.toContain("no-store");
    expect(cc).toMatch(/max-age=\d+/);
  });

  it("대조군: 릴레이가 살아 있으면 강등 헤더가 **없다**", async () => {
    // ★두 모집단이 갈려야 잠금이 성립한다 — 정상 타일도 200 image/png 라
    //   상태·타입만 보면 강등과 구분되지 않는다. 헤더 유무가 유일한 판별자다.
    installFetch({ relayStatus: 200 });
    const { proxyVWorldWms, VWORLD_DEGRADED_HEADER, __resetDirectProbeForTest } = await import(
      "@/lib/vworld-wms-proxy"
    );
    __resetDirectProbeForTest();
    await proxyVWorldWms(wmsParams());

    const resp = await proxyVWorldWms(wmsParams());
    expect(resp.status).toBe(200);
    expect(
      resp.headers.get(VWORLD_DEGRADED_HEADER),
      "정상인데 강등 헤더가 붙었다 — 위양성이면 배너가 항상 뜬다",
    ).toBeNull();
  });
});
