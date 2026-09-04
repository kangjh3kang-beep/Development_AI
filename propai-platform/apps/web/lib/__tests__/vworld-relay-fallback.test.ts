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

  it("릴레이 오리진이 없어도 **무음 성공은 금지** — 강등 사유를 다르게 말한다", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    installSplitFetch("throw");
    const { proxyVWorldWms, VWORLD_DEGRADED_HEADER } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());

    // ★★2026-08-18: 종전 502 → 강등(투명타일). 이 케이스가 지키는 것은 **"무음 성공 금지"** 이고
    //   그것은 그대로다 — 다만 "실패했다"를 status 가 아니라 **헤더**로 말한다.
    //   ★그리고 사유가 **다른 값**이어야 한다: 오리진 없음은 **설정 결함**이라 처방이 다르다
    //     (릴레이가 있는데 못 닿은 것과 혼동되면 다음 사람이 엉뚱한 곳을 본다).
    //     두 모집단이 같은 문자열을 내면 이 락은 아무것도 구분하지 못한다.
    expect(resp.status).toBe(200);
    expect(resp.headers.get(VWORLD_DEGRADED_HEADER)).toContain("no-relay-origin");
  });
});

/**
 * ★2026-08-17 실장애: VWorld 가 web 서버(158) IP 를 차단해 상류가 죽었는데, 릴레이까지
 *   끊긴 순간의 오류 문구가 `VWORLD_API_KEY is not configured` 였다. 키는 **정상**이었다.
 *   그 거짓 원인이 화면 배너로 올라가 "관리자 화면에 키를 등록하라"는 없는 복구 경로를
 *   안내했고, 여러 세션이 키를 의심하며 시간을 썼다.
 *   이 블록은 "원인을 지어내지 않는다"를 잠근다 — 두 모집단이 **다른 문구**를 내야 한다.
 */
describe("릴레이도 끊겼을 때 — 원인을 지어내지 않는다", () => {
  /** 상류·릴레이 둘 다 죽은 상태(실장애 최악 경로). */
  function installAllDeadFetch() {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("fetch failed");
    }));
  }

  it("★키가 멀쩡한데 '키 미설정'이라고 단정하지 않는다 (근거를 강등 헤더로 이관)", async () => {
    installAllDeadFetch();
    const { proxyVWorldWms, VWORLD_DEGRADED_HEADER } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());

    // ★★2026-08-18 **매체 변경** — 이 케이스가 지키는 것은 "원인을 지어내지 않는다"(#677)이고
    //   그 원칙은 그대로다. 바뀐 것은 **어디에 적히는가**다: JSON 본문 → 강등 헤더.
    //   응답이 투명 PNG 가 되었으므로 `res.json()` 은 PNG 바이트를 파싱하려다 죽는다.
    //   ※이 케이스를 **지우면 안 된다** — 지우는 순간 "강등 시 무엇을 말하는가"가 무잠금이 되고,
    //     옛 문구("키 미설정")가 되살아나도 아무도 모른다.
    const reason = resp.headers.get(VWORLD_DEGRADED_HEADER) ?? "";

    expect(resp.status, "회색 지도를 만들지 않는다").toBe(200);
    expect(resp.headers.get("content-type")).toContain("image/png");
    // 키는 이 테스트에서 설정돼 있다(beforeEach) — 키를 원인으로 지목하면 거짓이다.
    expect(process.env.VWORLD_API_KEY, "전제: 키는 설정돼 있다").toBeTruthy();
    expect(reason, "키가 정상인데 키를 원인으로 단정했다").not.toContain("VWORLD_API_KEY");
    // 어느 경로가 끊겼는지 식별 가능해야 한다(무엇이 실패했는지 말한다).
    expect(reason, "강등 사유가 비었다 — 무음 강등이다").toContain("relay");
  });

  it("대조군: 키가 **정말** 없고 릴레이 오리진도 없으면 키를 원인으로 말해도 참이다", async () => {
    delete process.env.VWORLD_API_KEY;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    installAllDeadFetch();
    const { proxyVWorldWms } = await import("@/lib/vworld-wms-proxy");

    const resp = await proxyVWorldWms(wmsParams());
    const body = (await resp.json()) as { error: string };

    expect(resp.status).toBe(503);
    // ★이 단언이 위 케이스와 **다른 값**을 내야 잠금이 성립한다(둘 다 같은 문구면 무잠금).
    expect(body.error).toContain("VWORLD_API_KEY");
  });
});
