import { classifyVWorldXmlException } from "@/lib/vworld-xml-exception";

const VWORLD_WMTS_BASE = "https://api.vworld.kr/req/wmts/1.0.0";
const SUPPORTED_LAYERS = new Set(["Base", "gray", "midnight", "Hybrid", "Satellite"]);

export type VWorldWmtsParams = {
  layer: string;
  z: string;
  y: string;
  x: string;
};

/**
 * ★PR#329 R1 리뷰(HIGH) 반영 — 서버 전용 키(`VWORLD_API_KEY`)만 사용, `NEXT_PUBLIC_VWORLD_API_KEY`
 *   (공개·도메인 제한 키, `lib/vworld-client.ts`·`AvmVisionPanel.tsx`가 브라우저에서 직접 사용하는
 *   별도 정책의 키)로 폴백하지 않는다. 폴백을 두면 서버 전용 키 미설정 시 조용히 같은 공개 키로
 *   동작해 "서버 전용 키 분리" 의도가 무력화된다(순 보안이득 ≈ 0). 미설정이면 503으로 정직 실패한다.
 */
function vworldKey(): string {
  return (process.env.VWORLD_API_KEY || "").trim();
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
//   (JSON 인증 실패·쿼터 초과는 upstreamError 503 경로가 처리. 200+XML은 본문을
//    classifyVWorldXmlException으로 분류 — coverage만 투명타일, auth/불명은 503 승격.)
//   ★Buffer는 Node 런타임 전제 — 이 프록시를 Edge 런타임으로 전환하면 깨진다(전환 시
//    base64→Uint8Array로 교체 필요, 지금은 금지).
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
      // 200 + 비이미지 본문은 두 현실이 섞여 있다 — content-type으로 1차 분기하고,
      // XML은 본문까지 읽어 2차 분류한다(MEDIUM2: VWorld는 인증/권한 오류도 200+XML로
      // 반환하므로 content-type만으로는 '정상 무제공영역'과 구분 불가):
      //  · XML(coverage — FileNotFound·제공영역 문구) → 투명타일(지도 유지) + warn 로그.
      //  · XML(auth/불명) 또는 그 외 비이미지(JSON 인증 실패·쿼터 초과 등) → 503 JSON.
      if (contentType.toLowerCase().includes("xml")) {
        const bodyText = await resp.text();
        const kind = classifyVWorldXmlException(bodyText);
        if (kind === "coverage") {
          console.warn(
            `[vworld-wmts-proxy] 200 + XML(coverage) → transparent tile`,
            { layer: cleanLayer, z: params.z, y: params.y, x: cleanX, contentType },
          );
          return transparentTile();
        }
        return upstreamError("VWorld WMTS returned an XML exception (auth/unknown)", resp.status, {
          layer: cleanLayer, z: params.z, y: params.y, x: cleanX, contentType,
          bodySnippet: bodyText.slice(0, 200),
        });
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
