/**
 * VWORLD 데이터 API 프록시.
 *
 * VWORLD /req/data API는 CORS를 지원하지 않아 브라우저에서 직접 호출 불가.
 * Next.js API Route(Cloudflare Workers)를 통해 프록시한다.
 * Cloudflare Workers는 서울 엣지가 있어 한국 공공 API 접근이 원활하다.
 */

import { NextRequest, NextResponse } from "next/server";

const VWORLD_DATA_URL = "https://api.vworld.kr/req/data";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  // 모든 쿼리 파라미터를 VWORLD로 전달
  const params = new URLSearchParams();
  searchParams.forEach((value, key) => {
    params.set(key, value);
  });

  try {
    const resp = await fetch(`${VWORLD_DATA_URL}?${params.toString()}`, {
      headers: {
        Referer: "https://developmentai-production.up.railway.app",
      },
    });

    const data = await resp.text();

    return new NextResponse(data, {
      status: resp.status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "VWORLD 데이터 API 프록시 실패", detail: String(error) },
      { status: 502 },
    );
  }
}
