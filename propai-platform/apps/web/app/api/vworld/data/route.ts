/**
 * VWORLD API 통합 프록시.
 *
 * VWORLD API가 CORS를 지원하지 않아 브라우저에서 직접 호출 불가.
 * Next.js API Route(Cloudflare Workers)를 통해 프록시한다.
 * Cloudflare Workers는 서울 엣지가 있어 한국 공공 API 접근이 원활하다.
 *
 * 사용법:
 *   /api/vworld/data?service=data&request=GetFeature&... (토지정보)
 *   /api/vworld/data?service=address&request=getcoord&... (지오코딩)
 */

import { NextRequest } from "next/server";

const VWORLD_BASE = "https://api.vworld.kr/req";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const params = new URLSearchParams(url.search);

  // service 파라미터로 address/data API 구분
  const service = params.get("service") ?? "data";
  const targetUrl = service === "address"
    ? `${VWORLD_BASE}/address?${params.toString()}`
    : `${VWORLD_BASE}/data?${params.toString()}`;

  try {
    const resp = await fetch(targetUrl);
    const text = await resp.text();

    return new Response(text, {
      status: resp.status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: "VWORLD API 프록시 실패", detail: String(error) }),
      {
        status: 502,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}
