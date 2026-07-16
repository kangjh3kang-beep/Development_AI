import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyVWorldWms } from "./vworld-wms-proxy";

const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

function stubFetch(handler: (url: string) => Response) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => handler(String(url))));
}

// Leaflet WMS(`L.tileLayer.wms`)가 조립하는 GetMap 쿼리(키·domain 없음)를 모사한다.
function leafletWmsQuery(layers = "LP_PA_CBND_BUDB,LP_PA_CBND_BONB"): URLSearchParams {
  return new URLSearchParams({
    service: "WMS",
    request: "GetMap",
    layers,
    styles: layers,
    format: "image/png",
    transparent: "true",
    version: "1.1.1",
    width: "256",
    height: "256",
    srs: "EPSG:3857",
    bbox: "14135029,4518899,14137474,4521344",
  });
}

describe("vworld-wms-proxy", () => {
  it("★API 키는 서버측에서 주입되고 클라이언트 쿼리엔 없다 → 상류 URL에만 key/domain 이 붙는다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    let requested = "";
    stubFetch((url) => {
      requested = url;
      return new Response(new Uint8Array(PNG_MAGIC).buffer, {
        status: 200,
        headers: { "content-type": "image/png" },
      });
    });
    const incoming = leafletWmsQuery();
    expect(incoming.has("key")).toBe(false); // 클라이언트 요청엔 키 없음

    const res = await proxyVWorldWms(incoming);
    expect(res.status).toBe(200);
    expect(requested).toContain("https://api.vworld.kr/req/wms?");
    expect(requested).toContain("key=SECRET-KEY"); // 서버측 주입
    expect(requested).toContain("domain=www.4t8t.net");
    expect(requested).toContain("LP_PA_CBND");
  });

  it("허용되지 않은 WMS 레이어(용도지역 LT_C_UQ111 등)는 400으로 거부한다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() => new Response(new Uint8Array(PNG_MAGIC).buffer, { status: 200, headers: { "content-type": "image/png" } }));
    const res = await proxyVWorldWms(leafletWmsQuery("LT_C_UQ111"));
    expect(res.status).toBe(400);
  });

  it("빈 LAYERS 는 400", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    const res = await proxyVWorldWms(leafletWmsQuery(""));
    expect(res.status).toBe(400);
  });

  it("★200+XML(무제공영역 ExceptionReport)은 투명 PNG로 대체(지도 깨짐 방지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() =>
      new Response('<?xml version="1.0"?><ServiceExceptionReport>error</ServiceExceptionReport>', {
        status: 200,
        headers: { "content-type": "text/xml;charset=UTF-8" },
      }),
    );
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(bytes.slice(0, 4))).toEqual(PNG_MAGIC);
  });

  it("키 미설정 시 503(정직 강등 근거)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_VWORLD_API_KEY", "");
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(503);
  });

  it("상류 4xx/5xx 는 503 JSON 으로 승격(무음 회색타일 금지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() => new Response("nope", { status: 403 }));
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("upstream");
  });
});
