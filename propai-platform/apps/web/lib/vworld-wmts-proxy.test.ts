import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyVWorldWmts } from "./vworld-wmts-proxy";

const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

function stubFetch(handler: (url: string) => Response) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => handler(String(url))));
}

describe("vworld-wmts-proxy", () => {
  it("위성(Satellite)은 상류 요청을 .jpeg로 보낸다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "TESTKEY");
    let requested = "";
    stubFetch((url) => {
      requested = url;
      return new Response(new Uint8Array([0xff, 0xd8, 0xff]).buffer, {
        status: 200,
        headers: { "content-type": "image/jpeg" },
      });
    });
    const res = await proxyVWorldWmts({ layer: "Satellite", z: "16", y: "25083", x: "55965.png" });
    expect(requested).toContain("/Satellite/16/25083/55965.jpeg");
    expect(res.headers.get("content-type")).toBe("image/jpeg");
  });

  it("Base는 .png로 보낸다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "TESTKEY");
    let requested = "";
    stubFetch((url) => {
      requested = url;
      return new Response(new Uint8Array(PNG_MAGIC).buffer, {
        status: 200,
        headers: { "content-type": "image/png" },
      });
    });
    await proxyVWorldWmts({ layer: "Base", z: "16", y: "25083", x: "55965.png" });
    expect(requested).toContain("/Base/16/25083/55965.png");
  });

  it("★200+XML(ExceptionReport)은 투명 PNG로 대체(지도 깨짐 방지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "TESTKEY");
    stubFetch(() =>
      new Response('<?xml version="1.0"?><ExceptionReport>서비스 제공영역이 아닙니다</ExceptionReport>', {
        status: 200,
        headers: { "content-type": "application/xml;charset=UTF-8" },
      }),
    );
    const res = await proxyVWorldWmts({ layer: "Satellite", z: "16", y: "1", x: "1.png" });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(bytes.slice(0, 4))).toEqual(PNG_MAGIC); // 유효 PNG(투명타일)
  });

  it("키 미설정 + API base 미설정 시 503", async () => {
    vi.stubEnv("VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const res = await proxyVWorldWmts({ layer: "Base", z: "16", y: "1", x: "1.png" });
    expect(res.status).toBe(503);
  });

  it("★WS-B2: 키 미설정 + API base 설정 시 api 타일 프록시로 중계(위성 jpeg 규칙 유지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.4t8t.net");
    let requested = "";
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      requested = String(url);
      return new Response(new Uint8Array([0x89, 0x50, 0x4e, 0x47]).buffer, { status: 200, headers: { "content-type": "image/jpeg" } });
    }));
    const res = await proxyVWorldWmts({ layer: "Satellite", z: "6", y: "24", x: "54.png" });
    expect(res.status).toBe(200);
    expect(requested).toBe("https://api.4t8t.net/api/v1/tiles/vworld/wmts/Satellite/6/24/54.jpeg");
    expect(requested).not.toContain("key");
  });

  it("★PR#329 R1: NEXT_PUBLIC_VWORLD_API_KEY(공개키)로는 폴백하지 않는다 — 서버 전용 키만 인정", async () => {
    vi.stubEnv("VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_VWORLD_API_KEY", "PUBLIC-KEY-SHOULD-NOT-BE-USED");
    const res = await proxyVWorldWmts({ layer: "Base", z: "16", y: "1", x: "1.png" });
    expect(res.status).toBe(503);
  });

  it("★PR#329 R1 MEDIUM2: 200+XML(인증/권한 오류 — coverage 문구 없음)은 503으로 승격(무음 흡수 금지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "TESTKEY");
    stubFetch(() =>
      new Response(
        '<?xml version="1.0"?><ServiceException code="INVALID_KEY">인증에 실패했습니다</ServiceException>',
        { status: 200, headers: { "content-type": "application/xml;charset=UTF-8" } },
      ),
    );
    const res = await proxyVWorldWmts({ layer: "Base", z: "16", y: "1", x: "1.png" });
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("XML exception");
  });
});
