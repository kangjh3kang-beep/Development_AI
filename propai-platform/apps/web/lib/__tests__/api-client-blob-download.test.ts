/**
 * 다운로드가 **공용 클라이언트를 경유**하는지 잠근다 — 우회하면 401 갱신이 안 붙는다.
 *
 * ## 무엇이 결함이었나 (사용자 신고 + 화면 실측)
 *
 * 권리분석 보고서 PDF/DOCX 버튼 아래에 이 문장이 떴다:
 *
 *     유효하지 않은 토큰: Signature has expired.
 *
 * 액세스 토큰 TTL 은 **60분**이고, `api-client` 에는 **401 → refresh → 1회 재시도**가
 * 이미 있다. 그런데 다운로드는 `apiClient` 에 **blob 경로가 없어서** 손수 `fetch` 를
 * 조립했고 — 그래서 그 재시도를 **한 번도 받지 못했다.**
 *
 * ★그래서 증상이 «다운로드 기능만 깨짐» 으로 보인다: 화면의 다른 조회는 갱신을 받아
 *   살아 있기 때문이다. 원인을 다운로드 코드에서 찾게 만드는 **오도하는 증상**이었다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const resolveMockRequest = vi.fn();
vi.mock("@/mocks/handlers", () => ({ resolveMockRequest }));

async function load() {
  vi.resetModules();
  vi.unstubAllEnvs();
  window.localStorage.clear();
  vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  return import("@/lib/api-client");
}

function jsonRes(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
function blobRes(bytes = "PDFDATA") {
  // ★본문에 `Blob` 을 넣지 않는다 — jsdom/undici 에서 `new Response(new Blob(...))` 는
  //   본문을 `"[object Blob]"` 로 직렬화해 **픽스처가 조용히 거짓**이 된다(첫 실행 실측).
  return new Response(bytes, { status: 200, headers: { "content-type": "application/pdf" } });
}

describe("apiClient.download — blob 경로", () => {
  beforeEach(() => resolveMockRequest.mockReset());
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("★만료된 토큰이면 refresh 후 재시도해 **파일을 돌려준다**", async () => {
    const { apiClient } = await load();
    window.localStorage.setItem("propai_access_token", "expired");
    window.localStorage.setItem("propai_refresh_token", "r1");

    const calls: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("/auth/refresh")) return jsonRes(200, { access_token: "fresh" });
      // 첫 다운로드는 만료 401, 갱신 후 두 번째는 성공
      return calls.filter((c) => c.includes("/registry/rights-report")).length === 1
        ? jsonRes(401, { detail: "유효하지 않은 토큰: Signature has expired." })
        : blobRes();
    });
    vi.stubGlobal("fetch", fetchMock);

    const blob = await apiClient.download("/registry/rights-report", {
      method: "POST",
      body: { format: "pdf" },
    });

    // ★`toBeInstanceOf(Blob)` 을 쓰지 않는다 — jsdom 전역 `Blob` 과 undici 의 `Blob` 이
    //   **다른 클래스**라 진짜 Blob 이 와도 실패한다(첫 실행 실측). 대신 «JSON 으로 파싱된
    //   객체가 아니라 파일이다» 를 구조로 가른다.
    expect(typeof (blob as Blob).text).toBe("function");
    expect((blob as Blob).type).toBe("application/pdf");
    expect(await (blob as Blob).text()).toBe("PDFDATA");
    // ★배선 단언: 갱신이 **실제로 일어났고** 다운로드가 **두 번** 나갔다.
    //   «Blob 이 왔다» 만 보면 재시도 없이 처음부터 200 인 구현도 통과한다.
    expect(calls.filter((c) => c.includes("/auth/refresh"))).toHaveLength(1);
    expect(calls.filter((c) => c.includes("/registry/rights-report"))).toHaveLength(2);
  });

  it("★오류는 blob 으로 삼키지 않는다 — 서버 사유가 살아 있어야 한다", async () => {
    const { apiClient, apiErrorMessage } = await load();
    window.localStorage.setItem("propai_access_token", "t");
    vi.stubGlobal("fetch", vi.fn(async () => jsonRes(400, { detail: "필지 상한(50)을 넘었습니다" })));

    // ★두 모집단 중 «실패» 쪽. 성공만 보면 «항상 blob 으로 읽는» 구현이 통과하고,
    //   그러면 모든 오류가 «파일을 받았는데 열리지 않는다» 로 바뀐다(진단 불가).
    await expect(
      apiClient.download("/registry/rights-report", { method: "POST", body: {} }),
    ).rejects.toMatchObject({ name: "ApiClientError", status: 400 });

    try {
      await apiClient.download("/registry/rights-report", { method: "POST", body: {} });
      throw new Error("던지지 않았다");
    } catch (e) {
      expect(apiErrorMessage(e, "기본문구")).toBe("필지 상한(50)을 넘었습니다");
      // 음성 대조군: 사유가 없을 때만 기본문구가 나온다(항상 기본문구인 구현을 가른다)
      expect(apiErrorMessage(new Error(""), "기본문구")).toBe("기본문구");
      expect((e as Error).message).not.toBe("필지 상한(50)을 넘었습니다");
    }
  });

  it("정상 응답은 blob 으로 온다(모집단 대조 — 재시도 없이 1회)", async () => {
    const { apiClient } = await load();
    window.localStorage.setItem("propai_access_token", "t");
    const fetchMock = vi.fn(async () => blobRes("DOCX"));
    vi.stubGlobal("fetch", fetchMock);

    const blob = await apiClient.download("/registry/rights-report", { method: "POST", body: {} });
    expect(typeof (blob as Blob).text).toBe("function");
    expect(await (blob as Blob).text()).toBe("DOCX");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("apiErrorMessage 는 detail 의 세 형태를 모두 다룬다", async () => {
    const { apiErrorMessage } = await load();
    expect(apiErrorMessage({ payload: { detail: "문자열 사유" } }, "fb")).toBe("문자열 사유");
    expect(apiErrorMessage({ payload: { detail: { message: "객체 사유" } } }, "fb")).toBe("객체 사유");
    expect(apiErrorMessage({ payload: { detail: { code: "X" } } }, "fb")).toContain("X");
    expect(apiErrorMessage(new TypeError("네트워크 끊김"), "fb")).toBe("네트워크 끊김");
    expect(apiErrorMessage(null, "fb")).toBe("fb");
  });
});
