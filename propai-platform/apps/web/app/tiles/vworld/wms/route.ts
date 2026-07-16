import { NextRequest } from "next/server";
import { proxyVWorldWms } from "@/lib/vworld-wms-proxy";

/**
 * 연속지적도 WMS 프록시 라우트 — `L.tileLayer.wms("/tiles/vworld/wms", …)` 의 GetMap 요청을 받아
 * VWorld 로 중계한다. API 키·domain 은 프록시(vworld-wms-proxy)가 서버측에서 주입하므로
 * 브라우저 번들·네트워크에 키가 노출되지 않는다.
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  return proxyVWorldWms(url.searchParams);
}
