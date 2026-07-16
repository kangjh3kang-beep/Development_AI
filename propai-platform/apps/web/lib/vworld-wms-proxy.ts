/**
 * VWorld WMS 프록시 — 연속지적도(LP_PA_CBND_*) WMS 타일을 프론트 서버 경유로 부설한다.
 *
 * ★보안(WP-M5): 종전엔 SatongMultiMap 이 `L.tileLayer.wms("https://api.vworld.kr/req/wms", {key})`
 *   로 브라우저에서 직결하며 API 키를 프론트 번들에 하드코딩(폴백 문자열)했다 — 같은 파일의
 *   "키 노출 금지·프록시 경유" 자기 원칙(WMTS 경로) 위반. 여기서 키·domain 을 서버측에서만
 *   주입하고, 클라이언트는 이미지 바이트만 받는다(키가 번들·네트워크 어디에도 남지 않는다).
 *
 * WMTS 프록시(vworld-wmts-proxy.ts)와 동일한 오류 계약을 따른다:
 *   · 4xx/5xx  → 503 JSON({error,status}) (무음 회색타일 금지)
 *   · 200+XML(무제공영역 ExceptionReport) → 투명 PNG(지도 유지)
 *   · 그 외 200+비이미지 → 503 JSON
 */

const VWORLD_WMS_BASE = "https://api.vworld.kr/req/wms";

// 프록시가 허용하는 WMS 레이어(오픈 프록시 남용 방지) — 연속지적도만.
//   ★용도지역(LT_C_UQ111)은 의도적으로 제외한다: '용도지역' 레이어 소관(의미 1:1)이며,
//     지적 토글에 함께 부설하면 위성 가림·표현 중복을 유발한다(WP-M5).
const ALLOWED_WMS_LAYERS = new Set(["LP_PA_CBND_BUDB", "LP_PA_CBND_BONB"]);

function vworldKey(): string {
  return (process.env.VWORLD_API_KEY || process.env.NEXT_PUBLIC_VWORLD_API_KEY || "").trim();
}

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message, status }), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function upstreamError(message: string, upstreamStatus: number, detail: Record<string, string>): Response {
  console.error(`[vworld-wms-proxy] ${message} (upstream status=${upstreamStatus})`, detail);
  return jsonError(message, 503);
}

// 투명 1x1 PNG — 200+XML(정상 무제공영역)을 타일 자리에 흡수해 지도 전체가 회색이 되지 않게.
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

/**
 * Leaflet WMS(`L.tileLayer.wms`)가 조립한 GetMap 쿼리를 받아 VWorld 로 중계한다.
 * @param incoming Leaflet 이 보낸 원본 쿼리(BBOX·WIDTH·HEIGHT·SRS·LAYERS·FORMAT 등). key/domain 없음.
 */
export async function proxyVWorldWms(incoming: URLSearchParams): Promise<Response> {
  const key = vworldKey();
  if (!key) {
    // [MAP-006] 평문 금지 — 오류는 항상 JSON. (키 미설정 노출은 지적 토글 시 정직 강등의 근거)
    return jsonError("VWORLD_API_KEY is not configured", 503);
  }

  // LAYERS 화이트리스트 검증(대소문자 파라미터명 모두 수용, 콤마 구분).
  const layersParam = incoming.get("LAYERS") ?? incoming.get("layers") ?? "";
  const requested = layersParam.split(",").map((s) => s.trim()).filter(Boolean);
  if (requested.length === 0 || !requested.every((layer) => ALLOWED_WMS_LAYERS.has(layer))) {
    return jsonError("Unsupported WMS layer", 400);
  }

  // 키·domain 을 서버측에서 주입(클라이언트 미노출). SERVICE 누락 시 보정.
  const params = new URLSearchParams(incoming);
  params.set("key", key);
  params.set("domain", "www.4t8t.net");
  if (!params.get("SERVICE") && !params.get("service")) params.set("SERVICE", "WMS");

  const targetUrl = `${VWORLD_WMS_BASE}?${params.toString()}`;
  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      return upstreamError("VWorld WMS upstream error", resp.status, { layers: requested.join(",") });
    }
    const contentType = (resp.headers.get("content-type") ?? "").trim();
    if (contentType && !contentType.toLowerCase().startsWith("image/")) {
      if (contentType.toLowerCase().includes("xml")) {
        console.warn(`[vworld-wms-proxy] 200 + XML body → transparent tile (coverage gap 추정)`, {
          layers: requested.join(","),
          contentType,
        });
        return transparentTile();
      }
      return upstreamError("VWorld WMS returned a non-image body", resp.status, {
        layers: requested.join(","),
        contentType,
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
    return jsonError(`VWorld WMS proxy failed: ${String(error)}`, 502);
  }
}
