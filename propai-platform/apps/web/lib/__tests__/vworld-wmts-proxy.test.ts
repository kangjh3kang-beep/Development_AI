import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * [MAP-009 P1] VWorld WMTS 프록시 — 업스트림 오류를 무음 포워딩하지 않는지 검증.
 *
 * Leaflet 타일 로더는 <img> 기반이라 상태 코드/본문을 구분 못 하고 회색 타일로만
 * 실패한다. 프록시는 업스트림 4xx·비이미지 본문(인증 실패·쿼터 초과가 200+JSON으로
 * 오는 VWorld 특성)을 명시적 503 + JSON 오류 본문으로 변환해야 관측 가능하다.
 */

const fetchMock = vi.fn();

async function loadProxy(env: Record<string, string | undefined> = { VWORLD_API_KEY: "test-key" }) {
  vi.resetModules();
  vi.unstubAllEnvs();
  for (const [key, value] of Object.entries(env)) {
    if (value !== undefined) vi.stubEnv(key, value);
  }
  vi.stubGlobal("fetch", fetchMock);
  return import("@/lib/vworld-wmts-proxy");
}

const PARAMS = { layer: "Base", z: "12", y: "1234", x: "5678" };

describe("proxyVWorldWmts — 업스트림 오류의 명시화", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("키 미설정이면 503과 no-store + JSON 오류 본문을 반환한다(기존 계약 회귀 가드, MAP-006 흡수)", async () => {
    const { proxyVWorldWmts } = await loadProxy({ VWORLD_API_KEY: "", NEXT_PUBLIC_VWORLD_API_KEY: "" });
    const resp = await proxyVWorldWmts(PARAMS);
    expect(resp.status).toBe(503);
    expect(resp.headers.get("Cache-Control")).toBe("no-store");
    expect(fetchMock).not.toHaveBeenCalled();
    // [MAP-006] 평문 금지 — JSON.parse가 예외 없이 성공해야 한다.
    expect(resp.headers.get("Content-Type")).toContain("application/json");
    const body = await resp.json();
    expect(body.error).toContain("VWORLD_API_KEY");
    expect(body.status).toBe(503);
  });

  it("업스트림 4xx(인증 실패·레이어 미존재·쿼터)는 503 + JSON 오류 본문으로 변환한다", async () => {
    fetchMock.mockResolvedValue(
      new Response("<ServiceExceptionReport>...</ServiceExceptionReport>", {
        status: 404,
        headers: { "Content-Type": "text/xml" },
      }),
    );
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    // 상태 코드 무음 전파(404 그대로) 금지 — 명시적 프록시 오류로 변환.
    expect(resp.status).toBe(503);
    expect(resp.headers.get("Content-Type")).toContain("application/json");
    expect(resp.headers.get("Cache-Control")).toBe("no-store");
    const body = await resp.json();
    expect(body.error).toBeTruthy();
    expect(body.status).toBe(404);
  });

  it("업스트림 200 + 비이미지 본문(JSON 오류 위장)은 타일로 위장 포워딩하지 않는다", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "INVALID_KEY" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status).toBe(503);
    expect(resp.headers.get("Content-Type")).toContain("application/json");
    expect(resp.headers.get("Cache-Control")).toBe("no-store");
    const body = await resp.json();
    expect(body.error).toBeTruthy();
    expect(body.status).toBe(200);
  });

  it("정상 이미지 타일은 200으로 포워딩하고 캐시 헤더를 유지한다", async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    fetchMock.mockResolvedValue(
      new Response(png, { status: 200, headers: { "Content-Type": "image/png" } }),
    );
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status).toBe(200);
    expect(resp.headers.get("Content-Type")).toBe("image/png");
    expect(resp.headers.get("Cache-Control")).toContain("max-age=86400");
    expect(new Uint8Array(await resp.arrayBuffer())).toEqual(png);
  });

  it("content-type 헤더가 없는 200 응답은 기존대로 image/png로 포워딩한다(과차단 금지)", async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    const upstream = new Response(png, { status: 200 });
    upstream.headers.delete("Content-Type");
    fetchMock.mockResolvedValue(upstream);
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status).toBe(200);
    expect(resp.headers.get("Content-Type")).toBe("image/png");
  });

  it("네트워크 예외는 502 + JSON 오류 본문을 유지한다(기존 계약 회귀 가드, MAP-006 흡수)", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNRESET"));
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);
    expect(resp.status).toBe(502);
    expect(resp.headers.get("Cache-Control")).toBe("no-store");
    // [MAP-006] 평문 금지 — 오류 원인·상태가 JSON 본문으로 관측 가능해야 한다.
    expect(resp.headers.get("Content-Type")).toContain("application/json");
    const body = await resp.json();
    expect(body.error).toContain("ECONNRESET");
    expect(body.status).toBe(502);
  });
});
