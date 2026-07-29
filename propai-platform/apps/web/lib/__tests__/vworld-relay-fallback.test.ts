/**
 * 상류 도달 불가 시 api(168) 릴레이 폴백 — 지도 생존 계약.
 *
 * ★실장애: web 서버(158)에서만 VWorld 경로가 막혀(도메인 전체 502/연결실패) 지도가 통째로
 *   회색이 됐다. 같은 클라우드의 api 서버(168)는 같은 키로 정상 200이었고, 168에는 동일
 *   계약의 타일 프록시가 이미 있는데도 폴백이 **'키 부재/키 오류'에만** 발동하도록 좁혀져
 *   있어 쓰이지 못했다.
 *   → 발동 조건을 '상류 도달 불가'까지 넓히면 벤더 조치를 기다리지 않고 지도가 살아난다.
 *
 * 한계(정직 고지): 이 테스트는 '릴레이를 시도한다'는 배선을 고정할 뿐,
 *   168이 실제로 타일을 주는지는 라이브에서만 확인된다(별도 확인: wms/wmts 둘 다 200 실측).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetBreakers } from "@/lib/vworld-circuit-breaker";

const RELAY_ORIGIN = "https://api.example.test";

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

/** fetch를 가로채 (상류=실패, 릴레이=성공)로 갈라 응답한다. */
function installSplitFetch(upstream: "throw" | "500") {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: unknown) => {
    const url = String(input);
    calls.push(url);
    if (url.startsWith(RELAY_ORIGIN)) {
      return new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { "content-type": "image/png", "cache-control": "public, max-age=3600" },
      });
    }
    if (upstream === "throw") throw new TypeError("fetch failed");
    return new Response("bad gateway", { status: 502 });
  }));
  return calls;
}

describe("상류 도달 불가 → api 릴레이", () => {
  it("★네트워크 예외(이번 실장애 경로)에서 릴레이로 타일을 받아온다", async () => {
    const calls = installSplitFetch("throw");
    const { proxyVWorldWms } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());

    expect(resp.status, "릴레이가 안 되면 502로 끝난다").toBe(200);
    expect(resp.headers.get("content-type")).toContain("image/png");
    expect(calls.some((u) => u.startsWith(RELAY_ORIGIN)), "api 릴레이를 시도하지 않았다").toBe(true);
  });

  it("상류가 5xx를 줘도 릴레이한다", async () => {
    const calls = installSplitFetch("500");
    const { proxyVWorldWms } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());

    expect(resp.status).toBe(200);
    expect(calls.some((u) => u.startsWith(RELAY_ORIGIN))).toBe(true);
  });

  it("★차단기가 열린 뒤에도 릴레이는 계속된다 — 투명 타일로 끝내지 않는다", async () => {
    installSplitFetch("throw");
    const { proxyVWorldWms } = await import("@/lib/vworld-wms-proxy");

    // 연속 실패로 차단기를 연다.
    for (let i = 0; i < 6; i += 1) await proxyVWorldWms(wmsParams());

    const resp = await proxyVWorldWms(wmsParams());
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type")).toContain("image/png");
    // 차단기 열림 응답(투명 타일)이 아니라 릴레이 결과여야 한다.
    expect(resp.headers.get("X-VWorld-Breaker")).toBeNull();
  });

  it("릴레이 오리진이 없으면 기존 정직 실패를 유지한다(무음 성공 금지)", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    installSplitFetch("throw");
    const { proxyVWorldWms } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());
    expect(resp.status).toBe(502);
  });
});
