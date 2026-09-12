/**
 * v62 분양관리(sales) API 래퍼 — 기존 apiClient(인증/baseURL) 위에 /sales 프리픽스 +
 * X-Site-Code 헤더를 주입한다. (서브도메인 대신 헤더로 현장 컨텍스트 전달)
 *
 * Phase 1-A: 현장 2차인증 진입 토큰(site_token)을 site_id별 sessionStorage에 보관하고,
 * sales API 호출 시 X-Site-Token 헤더로 자동 첨부한다(api-client가 sales 경로 한정으로 주입).
 */
import { apiClient } from "@/lib/api-client";
import { useSalesStore } from "@/store/useSalesStore";

type Body = Record<string, unknown> | undefined;

// ── 현장 진입 토큰(site_token) 저장소 ─────────────────────────────
// sessionStorage 키 접두사. 현장(site_id)별로 분리 저장하며 8h 만료를 자체 검증한다.
const SITE_TOKEN_PREFIX = "propai_site_token:";

interface StoredSiteToken {
  token: string;
  expiresAt: number; // epoch ms
  role?: string;
  features?: string[];
  /** 어떤 인증으로 들어왔나 — `membership`(승인) vs `password`(2차 비번).
   *  ★서버 응답의 `auth` 를 그대로 보관한다. 종전엔 응답에만 있고 **소비처 0건**이라
   *    «이 세션이 무엇으로 인증됐는지» 를 화면 어디서도 알 수 없었다(2026-09-09 리뷰 M4). */
  auth?: "membership" | "password";
}

/** 현장 진입 토큰을 sessionStorage에 저장(현장별, 만료시각 포함). */
export function storeSiteToken(
  siteId: string,
  token: string,
  expiresInSec: number,
  meta?: { role?: string; features?: string[]; auth?: "membership" | "password" },
) {
  if (typeof window === "undefined" || !siteId || !token) return;
  try {
    const payload: StoredSiteToken = {
      token,
      expiresAt: Date.now() + Math.max(0, expiresInSec) * 1000,
      role: meta?.role,
      features: meta?.features,
      auth: meta?.auth,
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

/** 현장 진입 토큰 제거(로그아웃·만료·진입실패 정리용).
 *
 * ★★**그 현장의 캐시된 세대도 함께 버린다**(2026-09-09 · Stage 3).
 *   토큰을 버리는 사건은 «이 현장을 볼 근거가 사라졌다» 는 뜻이다(멤버십 상실 4403 · 만료 ·
 *   로그아웃). 그런데 스토어는 **모듈 싱글톤**이라 토큰만 지우면 세대 목록은 메모리에 남고,
 *   같은 탭에서 다른 현장으로 갔다가 돌아오면 **권한이 사라진 현장의 데이터가 다시 그려진다.**
 *
 *   ★배선을 **호출부가 아니라 여기**에 둔다 — 호출부는 둘이고(`SiteWorkspaceClient` ·
 *     `UnitLiveBoard`) 앞으로 늘어난다. 한 곳을 고치면 형제가 따라오게 하는 저장소 규율이다.
 *   ★순환 임포트 없음: `store/useSalesStore.ts` 가 이 파일에서 가져가는 것은 `type UnitStatus`
 *     **하나뿐**이라 컴파일 시 지워진다(런타임 참조 0).
 */
export function clearSiteToken(siteId: string) {
  if (typeof window === "undefined" || !siteId) return;
  try {
    window.sessionStorage.removeItem(SITE_TOKEN_PREFIX + siteId);
  } catch {
    /* noop */
  }
  useSalesStore.getState().clearSite(siteId);
}

/** 현재 활성 현장 토큰의 raw 문자열(유효시)만 반환 — api-client 자동첨부용. */
export function activeSiteTokenValue(siteId: string): string {
  return getStoredSiteToken(siteId)?.token ?? "";
}

export function salesApi(siteCode: string) {
  // X-Site-Code(현장 식별)는 기존 그대로 유지. 추가로, Phase 1-B 현장앱 진입(site_token) 흐름에서는
  // siteCode 자리에 현장 UUID(site_id)를 넘기므로, 저장된 site_token이 있으면 X-Site-Token도 함께
  // 첨부한다(백엔드 sales_ctx 토큰 우선 컨텍스트). 토큰 없으면 기존 X-Site-Code 멤버십 경로로 동작(무파괴).
  const headers = (): Record<string, string> => {
    const token = activeSiteTokenValue(siteCode);
    return token ? { "X-Site-Code": siteCode, "X-Site-Token": token } : { "X-Site-Code": siteCode };
  };
  return {
    get: <T,>(p: string) => apiClient.get<T>(`/sales${p}`, { headers: headers() }),
    post: <T,>(p: string, body?: Body) => apiClient.post<T>(`/sales${p}`, { body, headers: headers() }),
    patch: <T,>(p: string, body?: Body) => apiClient.patch<T>(`/sales${p}`, { body, headers: headers() }),
    del: <T,>(p: string) => apiClient.delete<T>(`/sales${p}`, { headers: headers() }),
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
  // ★`headers` 를 받는다 — 과금 경로(예: /provision)는 재전송 안전 키를 붙여야 한다.
  //   래퍼가 헤더를 안 받으면 호출부가 apiClient 를 직접 쓰게 되고 규칙이 갈라진다.
  post: <T,>(p: string, body?: Body, headers?: Record<string, string>) =>
    apiClient.post<T>(`/sales${p}`, headers ? { body, headers } : { body }),
};

export const won = (n: number) =>
  new Intl.NumberFormat("ko-KR").format(Math.round(n || 0)) + "원";

export type UnitStatus = "AVAILABLE" | "HOLD" | "APPLIED" | "CONTRACTED" | "CANCELLED";
