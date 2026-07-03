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

/**
 * 업스트림 오류를 명시적 JSON 오류(503)로 변환.
 *
 * Leaflet 타일 로더(<img>)는 상태 코드·본문을 구분하지 못해 실패가 회색 타일로만
 * 남는다. 오류를 상태 코드만 전파하거나(4xx 그대로) 비이미지 본문을 타일인 척
 * 포워딩하면 원인(인증 실패·레이어 미존재·쿼터 초과)이 완전히 무음이 된다.
 * 그래서 503 + JSON 본문 { error, status }로 고정 변환하고 서버 로그를 남긴다.
 */
function upstreamError(message: string, upstreamStatus: number, detail: Record<string, string>): Response {
  console.error(
    `[vworld-wmts-proxy] ${message} (upstream status=${upstreamStatus})`,
    detail,
  );
  return new Response(JSON.stringify({ error: message, status: upstreamStatus }), {
    status: 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

export async function proxyVWorldWmts(params: VWorldWmtsParams): Promise<Response> {
  const key = vworldKey();
  const cleanLayer = SUPPORTED_LAYERS.has(params.layer) ? params.layer : "Base";
  const cleanX = params.x.replace(/\.png$/i, "");

  if (!key) {
    // [MAP-006] 평문 본문 금지 — 오류는 항상 JSON({ error, status })으로 반환한다.
    // 평문은 타일 응답을 JSON으로 해석하는 소비자의 JSON.parse 예외를 유발한다.
    return new Response(
      JSON.stringify({ error: "VWORLD_API_KEY is not configured", status: 503 }),
      {
        status: 503,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      },
    );
  }

  const targetUrl = `${VWORLD_WMTS_BASE}/${encodeURIComponent(key)}/${cleanLayer}/${params.z}/${params.y}/${cleanX}.png`;

  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      // 상태 코드 무음 전파 금지 — 4xx/5xx는 명시적 프록시 오류로 변환.
      return upstreamError("VWorld WMTS upstream error", resp.status, {
        layer: cleanLayer, z: params.z, y: params.y, x: cleanX,
      });
    }
    const contentType = (resp.headers.get("content-type") ?? "").trim();
    if (contentType && !contentType.toLowerCase().startsWith("image/")) {
      // VWorld는 인증 실패·쿼터 초과를 200 + JSON/XML 본문으로 반환하기도 한다.
      // 비이미지 본문을 타일로 위장 포워딩하지 않는다(본문 검사).
      return upstreamError("VWorld WMTS returned a non-image body", resp.status, {
        layer: cleanLayer, z: params.z, y: params.y, x: cleanX, contentType,
      });
    }
    const buf = await resp.arrayBuffer();
    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": contentType || "image/png",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    // [MAP-006] 네트워크 예외도 JSON 오류 본문으로 반환(평문 금지).
    return new Response(
      JSON.stringify({ error: `VWorld WMTS proxy failed: ${String(error)}`, status: 502 }),
      {
        status: 502,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      },
    );
  }
}
