import { NextRequest, NextResponse } from "next/server";


/* ── 프록시 대상 백엔드 해석 ────────────────────────────────────────────────
   ★기존 결함: `http://api:8000` 하드코드. 이 주소는 프론트 서버(158)에 함께 떠 있는
   compose api 컨테이너인데, 그 컨테이너는 프론트 배포 때만 갱신되어 백엔드 서버(168)의
   배포 주기를 따라가지 못하고 몇 주씩 뒤처졌다(실측: 이미지 생성 2026-07-02 ≈ 4주 전).
   결과적으로 이 프록시를 타는 요청만 조용히 구버전 API 응답을 받았다.

   해석 규칙은 lib/api-client.ts 의 resolveApiOrigin() SSOT 1순위와 동일하게 맞춘다
   (NEXT_PUBLIC_API_BASE_URL 우선 + 끝 슬래시·/api/v{1,2} 꼬리 제거).
   api-client 를 직접 import 하지 않는 이유: 그 모듈은 growth 이벤트 수집기 등 브라우저
   지향 의존을 함께 끌어와 서버 라우트 번들에 불필요하게 편입된다 — 규칙만 좁게 맞춘다.

   폴백을 api:8000 으로 유지하는 이유: 로컬 docker-compose 개발에서는 이 주소가 정답이고
   NEXT_PUBLIC_API_BASE_URL 이 비어 있다. 프로덕션은 이 값이 설정돼 있어(158 web 컨테이너
   실측: https://api.4t8t.net/api/v1) 항상 최신 백엔드로 간다. */
const API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (raw) return raw.replace(/\/+$/, "").replace(/\/api\/v[12]$/, "");
  return "http://api:8000";
})();

const API_BASE_URL = `${API_ORIGIN}/api/v1`;

async function handleProxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const path = resolvedParams.path.join("/");
    const url = new URL(request.url);
    const targetUrl = `${API_BASE_URL}/${path}${url.search}`;

    const headers = new Headers(request.headers);
    headers.delete("host"); // Let the fetch API handle the host header

    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    // Only add body for methods that allow it
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
      if (request.body) {
        fetchOptions.body = request.body;
      }
    }

    const response = await fetch(targetUrl, fetchOptions);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding"); // Let Next.js handle compression

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Proxy error:", error);
    return new NextResponse("Internal Server Error", { status: 500 });
  }
}

export const GET = handleProxy;
export const POST = handleProxy;
export const PUT = handleProxy;
export const PATCH = handleProxy;
export const DELETE = handleProxy;
export const OPTIONS = handleProxy;
