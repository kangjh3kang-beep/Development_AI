const VWORLD_WMTS_BASE = "https://api.vworld.kr/req/wmts/1.0.0";
const SUPPORTED_LAYERS = new Set(["Base", "gray", "midnight", "Hybrid", "Satellite"]);

export type VWorldWmtsParams = {
  layer: string;
  z: string;
  y: string;
  x: string;
};

function vworldKey(): string {
  return (process.env.VWORLD_API_KEY || process.env.NEXT_PUBLIC_VWORLD_API_KEY || "").trim();
}

// 투명 1x1 PNG — VWorld가 200+비이미지(XML ExceptionReport, 예: 위성 미제공영역)를 반환할 때
//   타일로 통과시키면 Leaflet tileerror로 지도 전체가 회색이 된다. 해당 타일만 빈 채로 두고 지도는 유지.
const TRANSPARENT_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

function transparentTile(): Response {
  return new Response(TRANSPARENT_PNG, {
    status: 200,
    headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=3600" },
  });
}

export async function proxyVWorldWmts(params: VWorldWmtsParams): Promise<Response> {
  const key = vworldKey();
  const cleanLayer = SUPPORTED_LAYERS.has(params.layer) ? params.layer : "Base";
  const cleanX = params.x.replace(/\.(png|jpe?g)$/i, "");
  // ★VWorld 위성영상(Satellite)은 jpeg로만 서빙된다 — png 요청 시 'FileNotFound: 서비스 제공영역이
  //   아닙니다' XML을 200으로 반환한다. 위성만 jpeg, 나머지(Base·Hybrid·gray·midnight)는 png.
  const ext = cleanLayer === "Satellite" ? "jpeg" : "png";

  if (!key) {
    return new Response("VWORLD_API_KEY is not configured", {
      status: 503,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }

  const targetUrl = `${VWORLD_WMTS_BASE}/${encodeURIComponent(key)}/${cleanLayer}/${params.z}/${params.y}/${cleanX}.${ext}`;

  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      return new Response(`VWorld WMTS failed: ${resp.status}`, {
        status: resp.status,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
        },
      });
    }
    // ★VWorld는 200 + XML ExceptionReport로 오류를 반환할 수 있다(위성 미제공영역 등). content-type이
    //   이미지가 아니면 타일로 통과시키지 말고 투명타일로 대체(지도 깨짐·tileerror 폭주 방지).
    const contentType = resp.headers.get("content-type") ?? "";
    if (!contentType.startsWith("image/")) {
      return transparentTile();
    }
    const buf = await resp.arrayBuffer();
    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": contentType || (ext === "jpeg" ? "image/jpeg" : "image/png"),
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    return new Response(`VWorld WMTS proxy failed: ${String(error)}`, {
      status: 502,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }
}
