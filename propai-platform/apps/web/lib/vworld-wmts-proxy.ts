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

// 투명 1x1 PNG — VWorld가 200 + XML ExceptionReport(예: 위성 미제공영역 'FileNotFound')를
//   반환할 때 타일로 통과시키면 Leaflet tileerror로 지도 전체가 회색이 된다. 이는 오류가
//   아니라 정상적 무제공 영역이므로 해당 타일만 빈 채로 두고 지도는 유지한다.
//   (인증 실패·쿼터 초과는 JSON 본문으로 오므로 upstreamError 503 관측 경로가 따로 처리 —
//    두 계약의 분기 기준은 content-type: xml→투명타일, 그 외 비이미지→503 JSON.)
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

  const targetUrl = `${VWORLD_WMTS_BASE}/${encodeURIComponent(key)}/${cleanLayer}/${params.z}/${params.y}/${cleanX}.${ext}`;

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
      // 200 + 비이미지 본문은 두 현실이 섞여 있다 — content-type으로 분기해 양쪽 계약 보존:
      //  · XML(ExceptionReport, 위성 미제공영역 등 정상 무제공) → 투명타일(지도 유지) + warn 로그.
      //  · 그 외(JSON 인증 실패·쿼터 초과 등) → 503 JSON(관측 가능, 무음 위장 금지).
      if (contentType.toLowerCase().includes("xml")) {
        console.warn(
          `[vworld-wmts-proxy] 200 + XML body → transparent tile (coverage gap 추정)`,
          { layer: cleanLayer, z: params.z, y: params.y, x: cleanX, contentType },
        );
        return transparentTile();
      }
      return upstreamError("VWorld WMTS returned a non-image body", resp.status, {
        layer: cleanLayer, z: params.z, y: params.y, x: cleanX, contentType,
      });
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
