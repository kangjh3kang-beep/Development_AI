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

  it("업스트림 200 + XML(ExceptionReport, 위성 미제공영역)은 투명타일 200으로 대체한다", async () => {
    // main(#197 계열)의 지도 유지 계약: 무제공 영역은 오류가 아니므로 tileerror 폭주 대신
    // 해당 타일만 투명 처리. (JSON 오류 위장은 위 테스트대로 503 관측 유지 — 분기 기준 content-type)
    fetchMock.mockResolvedValue(
      new Response("<ServiceExceptionReport>FileNotFound</ServiceExceptionReport>", {
        status: 200,
        headers: { "Content-Type": "text/xml" },
      }),
    );
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status).toBe(200);
    expect(resp.headers.get("Content-Type")).toBe("image/png");
    expect((await resp.arrayBuffer()).byteLength).toBeGreaterThan(0); // 투명 1x1 PNG
  });

  it("★PR#329 R1 MEDIUM2: 업스트림 200 + XML(인증/권한 오류 — coverage 문구 없음)은 503으로 승격한다", async () => {
    // 종전엔 content-type이 xml이기만 하면 본문을 읽지 않고 전부 투명타일 처리했다 —
    // VWorld는 인증 실패도 200+XML로 반환하므로 무음 실패가 됐다(MEDIUM2). 본문을 읽어
    // coverage 문구(FileNotFound·제공영역) 없는 XML은 auth로 분류해 503으로 승격한다.
    fetchMock.mockResolvedValue(
      new Response(
        '<ServiceException code="INVALID_KEY">인증에 실패했습니다</ServiceException>',
        { status: 200, headers: { "Content-Type": "text/xml" } },
      ),
    );
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status).toBe(503);
    expect(resp.headers.get("Content-Type")).toContain("application/json");
    const body = await resp.json();
    expect(body.error).toContain("XML exception");
  });

  it("★PR#329 R1: NEXT_PUBLIC_VWORLD_API_KEY(공개키)로는 폴백하지 않는다", async () => {
    const { proxyVWorldWmts } = await loadProxy({
      VWORLD_API_KEY: "",
      NEXT_PUBLIC_VWORLD_API_KEY: "PUBLIC-KEY-SHOULD-NOT-BE-USED",
    });
    const resp = await proxyVWorldWmts(PARAMS);
    expect(resp.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
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

  it("★네트워크 예외 + 릴레이 오리진 없음 → **정직 강등**(투명타일 + 강등 헤더)", async () => {
    // ★★2026-08-18 계약 변경 — 종전엔 `502 + JSON` 을 단언했다(MAP-006 평문 금지).
    //   MAP-006 의 목적은 "오류를 평문으로 삼키지 마라 = 관측 가능하게 하라" 였다.
    //   목적은 유지하되 **매체를 바꾼다**: JSON 본문 대신 **헤더**로 관측한다.
    //   이유는 502 가 목적의 절반만 달성하기 때문이다 — 관측은 되지만 Leaflet 이
    //   tileerror 로만 처리해 **지도 전체가 회색**이 된다(2026-08-16 실장애의 사용자 경험).
    //   ★`<img>` 는 본문도 헤더도 못 읽는다. 그러니 JSON 본문은 애초에 **사용자에게
    //     도달하지 않는 관측성**이었다 — 헤더는 진단 프로브가 실제로 읽어 배너를 띄운다.
    //     즉 이 변경은 관측성을 **줄인 게 아니라 도달하는 곳으로 옮긴 것**이다.
    //   ※`loadProxy()` 는 릴레이 오리진을 설정하지 않는다 → 이 케이스는 "대안 없음" 경로다.
    //     그 전제가 이 파일에 명시돼 있지 않았다는 지적(계약 렌즈 T2)을 받아 여기 적는다.
    fetchMock.mockRejectedValue(new Error("ECONNRESET"));
    const { proxyVWorldWmts } = await loadProxy();
    const resp = await proxyVWorldWmts(PARAMS);

    expect(resp.status, "502 면 지도가 회색이 된다").toBe(200);
    expect(resp.headers.get("Content-Type")).toContain("image/png");
    expect(
      resp.headers.get("X-VWorld-Degraded"),
      "강등 헤더가 없으면 무음 강등이다 — MAP-006 의 목적을 반대편으로 깬다",
    ).toContain("no-relay-origin");
    expect(resp.headers.get("Cache-Control") ?? "", "no-store 면 팬마다 폭주한다").not.toContain(
      "no-store",
    );
  });
});
