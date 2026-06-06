/**
 * v62 분양관리(sales) API 래퍼 — 기존 apiClient(인증/baseURL) 위에 /sales 프리픽스 +
 * X-Site-Code 헤더를 주입한다. (서브도메인 대신 헤더로 현장 컨텍스트 전달)
 *
 * Phase 1-A: 현장 2차인증 진입 토큰(site_token)을 site_id별 sessionStorage에 보관하고,
 * sales API 호출 시 X-Site-Token 헤더로 자동 첨부한다(api-client가 sales 경로 한정으로 주입).
 */
import { apiClient } from "@/lib/api-client";

type Body = Record<string, unknown> | undefined;

// ── 현장 진입 토큰(site_token) 저장소 ─────────────────────────────
// sessionStorage 키 접두사. 현장(site_id)별로 분리 저장하며 8h 만료를 자체 검증한다.
const SITE_TOKEN_PREFIX = "propai_site_token:";

interface StoredSiteToken {
  token: string;
  expiresAt: number; // epoch ms
  role?: string;
  features?: string[];
}

/** 현장 진입 토큰을 sessionStorage에 저장(현장별, 만료시각 포함). */
export function storeSiteToken(
  siteId: string,
  token: string,
  expiresInSec: number,
  meta?: { role?: string; features?: string[] },
) {
  if (typeof window === "undefined" || !siteId || !token) return;
  try {
    const payload: StoredSiteToken = {
      token,
      expiresAt: Date.now() + Math.max(0, expiresInSec) * 1000,
      role: meta?.role,
      features: meta?.features,
    };
    window.sessionStorage.setItem(SITE_TOKEN_PREFIX + siteId, JSON.stringify(payload));
  } catch {
    /* sessionStorage 비활성 환경 무시 */
  }
}

/** 저장된 현장 진입 토큰 조회. 만료 시 제거 후 null 반환. */
export function getStoredSiteToken(siteId: string): StoredSiteToken | null {
  if (typeof window === "undefined" || !siteId) return null;
  try {
    const raw = window.sessionStorage.getItem(SITE_TOKEN_PREFIX + siteId);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSiteToken;
    if (!parsed?.token || typeof parsed.expiresAt !== "number" || parsed.expiresAt <= Date.now()) {
      window.sessionStorage.removeItem(SITE_TOKEN_PREFIX + siteId);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** 현장 진입 토큰 제거(로그아웃·만료·진입실패 정리용). */
export function clearSiteToken(siteId: string) {
  if (typeof window === "undefined" || !siteId) return;
  try {
    window.sessionStorage.removeItem(SITE_TOKEN_PREFIX + siteId);
  } catch {
    /* noop */
  }
}

/** 현재 활성 현장 토큰의 raw 문자열(유효시)만 반환 — api-client 자동첨부용. */
export function activeSiteTokenValue(siteId: string): string {
  return getStoredSiteToken(siteId)?.token ?? "";
}

export function salesApi(siteCode: string) {
  const headers = { "X-Site-Code": siteCode };
  return {
    get: <T,>(p: string) => apiClient.get<T>(`/sales${p}`, { headers }),
    post: <T,>(p: string, body?: Body) => apiClient.post<T>(`/sales${p}`, { body, headers }),
    patch: <T,>(p: string, body?: Body) => apiClient.patch<T>(`/sales${p}`, { body, headers }),
    del: <T,>(p: string) => apiClient.delete<T>(`/sales${p}`, { headers }),
  };
}

/**
 * Phase 1-A 현장 진입 후 호출 래퍼 — site_id 경로 + 저장된 site_token(X-Site-Token)을 명시 첨부한다.
 * (api-client도 sales 경로면 활성 토큰을 자동첨부하지만, 명시 헤더로 site별 토큰을 확정 전달)
 */
export function salesSiteApi(siteId: string) {
  const siteHeaders = (): Record<string, string> => {
    const token = activeSiteTokenValue(siteId);
    return token ? { "X-Site-Token": token } : {};
  };
  return {
    get: <T,>(p: string) => apiClient.get<T>(`/sales/sites/${siteId}${p}`, { headers: siteHeaders() }),
    post: <T,>(p: string, body?: Body) =>
      apiClient.post<T>(`/sales/sites/${siteId}${p}`, { body, headers: siteHeaders() }),
    patch: <T,>(p: string, body?: Body) =>
      apiClient.patch<T>(`/sales/sites/${siteId}${p}`, { body, headers: siteHeaders() }),
    del: <T,>(p: string) => apiClient.delete<T>(`/sales/sites/${siteId}${p}`, { headers: siteHeaders() }),
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
