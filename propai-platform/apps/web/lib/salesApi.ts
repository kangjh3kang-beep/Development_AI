/**
 * v62 분양관리(sales) API 래퍼 — 기존 apiClient(인증/baseURL) 위에 /sales 프리픽스 +
 * X-Site-Code 헤더를 주입한다. (서브도메인 대신 헤더로 현장 컨텍스트 전달)
 */
import { apiClient } from "@/lib/api-client";

type Body = Record<string, unknown> | undefined;

export function salesApi(siteCode: string) {
  const headers = { "X-Site-Code": siteCode };
  return {
    get: <T,>(p: string) => apiClient.get<T>(`/sales${p}`, { headers }),
    post: <T,>(p: string, body?: Body) => apiClient.post<T>(`/sales${p}`, { body, headers }),
    patch: <T,>(p: string, body?: Body) => apiClient.patch<T>(`/sales${p}`, { body, headers }),
    del: <T,>(p: string) => apiClient.delete<T>(`/sales${p}`, { headers }),
  };
}

// 현장 컨텍스트가 없는 호출(현장목록/시행사 투영)
export const salesGlobal = {
  get: <T,>(p: string) => apiClient.get<T>(`/sales${p}`),
  post: <T,>(p: string, body?: Body) => apiClient.post<T>(`/sales${p}`, { body }),
};

export const won = (n: number) =>
  new Intl.NumberFormat("ko-KR").format(Math.round(n || 0)) + "원";

export type UnitStatus = "AVAILABLE" | "HOLD" | "APPLIED" | "CONTRACTED" | "CANCELLED";
