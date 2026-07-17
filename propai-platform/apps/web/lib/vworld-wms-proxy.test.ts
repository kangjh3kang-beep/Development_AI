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
    // ★2026-07-17: 프론트가 version 1.3.0을 명시(VWorld WMS는 1.3.0만 허용 —
    //   1.1.1은 INVALID_RANGE로 거부됨). 1.3.0에서 Leaflet은 srs 대신 crs를 보낸다.
    version: "1.3.0",
    width: "256",
    height: "256",
    crs: "EPSG:3857",
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

  it("★PR#329 R1: NEXT_PUBLIC_VWORLD_API_KEY(공개키) 로는 폴백하지 않는다 — 서버 전용 키만 인정", async () => {
    vi.stubEnv("VWORLD_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_VWORLD_API_KEY", "PUBLIC-KEY-SHOULD-NOT-BE-USED");
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(503); // 공개키가 설정돼 있어도 서버 전용 키가 없으면 정직 실패
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

  it("★PR#329 R1 MEDIUM1(재현 완료): 중복 LAYERS 키 스머글링(?LAYERS=허용&LAYERS=차단)은 400 — 상류에 요청조차 안 보낸다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    let called = false;
    stubFetch(() => {
      called = true;
      return new Response(new Uint8Array(PNG_MAGIC).buffer, { status: 200, headers: { "content-type": "image/png" } });
    });
    // URLSearchParams는 문자열 생성자로만 진짜 중복 키를 만들 수 있다(객체 리터럴은 키가 유일).
    const incoming = new URLSearchParams(
      "service=WMS&request=GetMap&LAYERS=LP_PA_CBND_BUDB&LAYERS=LT_C_UQ111&format=image/png",
    );
    const res = await proxyVWorldWms(incoming);
    expect(res.status).toBe(400);
    expect(called).toBe(false); // 검증 실패 시 상류 fetch 자체를 하지 않는다
  });

  it("★PR#329 R1 MEDIUM1(재현 완료): 대소문자 변형 스머글링(?layers=차단&LAYERS=허용)도 400", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    let called = false;
    stubFetch(() => {
      called = true;
      return new Response(new Uint8Array(PNG_MAGIC).buffer, { status: 200, headers: { "content-type": "image/png" } });
    });
    const incoming = new URLSearchParams(
      "service=WMS&request=GetMap&layers=LT_C_UQ111&LAYERS=LP_PA_CBND_BUDB&format=image/png",
    );
    const res = await proxyVWorldWms(incoming);
    expect(res.status).toBe(400);
    expect(called).toBe(false);
  });

  it("정당한 대소문자 변형(Layers=…)은 통과하고, 상류엔 검증된 canonical 값만 단일 전달된다(원본 재전달 금지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    let requested = "";
    stubFetch((url) => {
      requested = url;
      return new Response(new Uint8Array(PNG_MAGIC).buffer, { status: 200, headers: { "content-type": "image/png" } });
    });
    const incoming = new URLSearchParams(
      "service=WMS&request=GetMap&Layers=LP_PA_CBND_BUDB,LP_PA_CBND_BONB&format=image/png",
    );
    const res = await proxyVWorldWms(incoming);
    expect(res.status).toBe(200);
    const url = new URL(requested);
    // 상류 URL엔 canonical LAYERS 파라미터가 정확히 1개만 존재 — 원본 "Layers" 키가 그대로
    // 새어나가 중복/미검증 값이 함께 전달되지 않는다.
    expect(url.searchParams.getAll("LAYERS")).toEqual(["LP_PA_CBND_BUDB,LP_PA_CBND_BONB"]);
    expect(url.searchParams.has("Layers")).toBe(false);
  });

  it("★200+XML(coverage — FileNotFound/제공영역 문구)은 투명 PNG로 대체(지도 깨짐 방지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() =>
      new Response(
        '<?xml version="1.0"?><ServiceExceptionReport>FileNotFound: 서비스 제공영역이 아닙니다</ServiceExceptionReport>',
        { status: 200, headers: { "content-type": "text/xml;charset=UTF-8" } },
      ),
    );
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(bytes.slice(0, 4))).toEqual(PNG_MAGIC);
  });

  it("★PR#329 R1 MEDIUM2: 200+XML(인증/권한 오류 — coverage 문구 없음)은 503으로 승격(무음 흡수 금지)", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() =>
      new Response(
        '<?xml version="1.0"?><ServiceExceptionReport><ServiceException code="INVALID_KEY">인증에 실패했습니다</ServiceException></ServiceExceptionReport>',
        { status: 200, headers: { "content-type": "text/xml;charset=UTF-8" } },
      ),
    );
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("XML exception");
    // ★2026-07-17: ServiceException code가 오류 메시지에 표면화된다 — "(auth/unknown)"
    //   뭉뚱그림 탓에 INVALID_RANGE(파라미터 오류)가 "키 미설정"으로 오독된 사고 재발 방지.
    expect(body.error).toContain("INVALID_KEY");
  });

  it("★근본원인 회귀(2026-07-17): INVALID_RANGE(WMS VERSION 오류)도 code가 그대로 표면화된다", async () => {
    vi.stubEnv("VWORLD_API_KEY", "SECRET-KEY");
    stubFetch(() =>
      new Response(
        '<?xml version="1.0" encoding="UTF-8" ?><ServiceExceptionReport version="1.3.0"><ServiceException code="INVALID_RANGE">VERSION 파라미터의 값이 유효한 범위를 넘었습니다. 유효한 파라미터 값의 범위 : [1.3.0], 입력한 파라미터 값 : 1.1.1</ServiceException></ServiceExceptionReport>',
        { status: 200, headers: { "content-type": "application/xml;charset=UTF-8" } },
      ),
    );
    const res = await proxyVWorldWms(leafletWmsQuery());
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("INVALID_RANGE");
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
