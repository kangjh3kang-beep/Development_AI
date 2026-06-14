import { resolveMockRequest } from "@/mocks/handlers";
import { isMockMode } from "@/lib/runtime-mode";
import { trackEvent, isGrowthEndpoint } from "@/lib/growth/event-collector";

/**
 * API 호출 계측(자가성장 엔진 §3.1) — 논블로킹·격리.
 * 성공=api_call(샘플), 4xx/5xx=api_error(전수). 수집 실패가 본 호출을 막지 않는다.
 * growth 엔드포인트 자체는 제외(수집의 무한루프 방지).
 */
function trackApiCall(path: string, status: number, latencyMs: number): void {
  try {
    if (isGrowthEndpoint(path)) return;
    // 쿼리스트링 제거(정규화).
    const route = path.split("?")[0] ?? path;
    if (status >= 400) {
      trackEvent("api_error", {
        route,
        status_code: status,
        latency_ms: latencyMs,
        severity: status >= 500 ? "error" : "warn",
      });
    } else {
      trackEvent("api_call", {
        route,
        status_code: status,
        latency_ms: latencyMs,
        severity: "info",
      });
    }
  } catch {
    /* 수집 실패는 무시 */
  }
}

/* ── API base 해석 (단일 source of truth) ──
   v1·v2가 호스트 화이트리스트를 각각 중복 유지하던 결함을 단일 헬퍼로 통합한다.
   폴백 규칙:
     1) NEXT_PUBLIC_API_BASE_URL(빌드 환경변수)이 있으면 최우선.
     2) 로컬 개발(localhost/127.0.0.1)만 localhost:8000 직타격.
     3) 그 외 알 수 없는 브라우저 호스트는 프로덕션 API 베이스로 폴백
        (이전: localhost:8000 직타격 → 화이트리스트 밖 호스트에서 전 API 실패). */

// 프로덕션 백엔드 오리진 (api 버전 prefix 제외)
const PROD_API_ORIGIN = "https://api.4t8t.net";

// 환경변수 오버라이드: 명시되면 모든 도메인 감지보다 우선한다.
// 끝의 슬래시와 "/api/v1"·"/api/v2" 꼬리를 떼어 순수 오리진으로 정규화.
const ENV_API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/+$/, "").replace(/\/api\/v[12]$/, "");
})();

/** 로컬 개발 호스트(브라우저)인지 판정. */
function isLocalHost(host: string): boolean {
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
}

/**
 * 요청에 사용할 API 오리진(버전 prefix 제외)을 단일 규칙으로 해석.
 * @returns 예) "https://api.4t8t.net" | "http://localhost:8000" | "http://api:8000"
 */
export function resolveApiOrigin(): string {
  // 1) 환경변수 최우선
  if (ENV_API_ORIGIN) return ENV_API_ORIGIN;

  // 2) SSR(Node.js): Docker 내부 DNS
  if (typeof window === "undefined") return "http://api:8000";

  // 3) 브라우저: 로컬 개발만 localhost 직타격
  if (isLocalHost(window.location.hostname)) return "http://localhost:8000";

  // 4) 그 외 모든 호스트(프로덕션·프리뷰·커스텀·스테이징)는 프로덕션 API로 폴백.
  //    (이전엔 localhost:8000을 직타격해 화이트리스트 밖 호스트에서 전 API 실패)
  return PROD_API_ORIGIN;
}

/**
 * v1 API base URL — 컴포넌트별로 호스트 화이트리스트를 중복 하드코딩하던
 * designApiBase 류의 단일 대체(호출 시점 해석 — SSR/브라우저 분기 안전).
 * @returns 예) "https://api.4t8t.net/api/v1" | "http://localhost:8000/api/v1"
 */
export function apiV1BaseUrl(): string {
  return `${resolveApiOrigin()}/api/v1`;
}

// 런타임 진단/표시용 베이스(v1) — getRuntimeConfig에서 노출.
const apiBaseUrl = apiV1BaseUrl();

// mock 게이트 판정식은 runtime-mode SSOT 단일 출처를 사용한다("true"일 때만 mock).
const useMocksByDefault = isMockMode();
// 보안: NEXT_PUBLIC_* 환경변수는 빌드 시 클라이언트 번들에 포함되므로
// 토큰을 NEXT_PUBLIC_ 접두사 환경변수에 저장하면 안 됨.
// 토큰은 localStorage에서만 읽는다.
// TODO: 향후 HttpOnly 쿠키로 전환 권장 (XSS 방어 강화)

export class ApiClientError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

export type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | null;
  useMock?: boolean;
  /** 요청 타임아웃(ms). 미지정 시 기본값. 0이면 무제한. */
  timeoutMs?: number;
};

// 백엔드 무응답 시 프론트가 영원히 대기("분석 중...")하는 것을 막는 기본 타임아웃.
// LLM·파이프라인 단계가 길 수 있어 넉넉히 두되, 무한대기는 차단한다.
const DEFAULT_TIMEOUT_MS = 120_000;

function isAbsoluteUrl(path: string) {
  return /^https?:\/\//.test(path);
}

function getRequestUrl(path: string) {
  if (isAbsoluteUrl(path)) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${resolveApiOrigin()}/api/v1${normalizedPath}`;
}

function getAccessToken(): string {
  // 토큰은 localStorage에서만 읽는다 (향후 HttpOnly 쿠키로 전환 권장)
  if (typeof window !== "undefined") {
    try {
      return window.localStorage.getItem("propai_access_token")?.trim() ?? "";
    } catch {
      // Ignored: localStorage is disabled or blocked in this environment
    }
  }
  return "";
}

// ── 현장 진입 토큰(site_token) 자동첨부 ─────────────────────────────
// Phase 1-A: sales 현장 경로(/sales/sites/{id}/...) 호출 시 sessionStorage에 저장된
// 현장 진입 토큰(site_token)을 X-Site-Token 헤더로 자동 주입한다.
// ★무파괴 원칙: sales 현장 경로 + 저장 토큰이 있을 때만 첨부하며, 호출자가 명시한
//   X-Site-Token 헤더가 있으면 그것을 우선한다(salesApi.ts와 동일 키 규약).
const SITE_TOKEN_PREFIX = "propai_site_token:";

/** /sales/sites/{site_id}/... 경로에서 site_id 추출(절대/상대 경로 모두). */
function extractSalesSiteId(path: string): string | null {
  const m = path.match(/\/sales\/sites\/([^/?#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/** 저장된 현장 진입 토큰(미만료) 조회. */
function getActiveSiteToken(siteId: string): string {
  if (typeof window === "undefined" || !siteId) return "";
  try {
    const raw = window.sessionStorage.getItem(SITE_TOKEN_PREFIX + siteId);
    if (!raw) return "";
    const parsed = JSON.parse(raw) as { token?: string; expiresAt?: number };
    if (!parsed?.token || typeof parsed.expiresAt !== "number" || parsed.expiresAt <= Date.now()) {
      window.sessionStorage.removeItem(SITE_TOKEN_PREFIX + siteId);
      return "";
    }
    return parsed.token;
  } catch {
    return "";
  }
}

function getRefreshToken(): string {
  if (typeof window !== "undefined") {
    try {
      return window.localStorage.getItem("propai_refresh_token")?.trim() ?? "";
    } catch {
      /* noop */
    }
  }
  return "";
}

function setStoredTokens(access?: string, refresh?: string) {
  if (typeof window === "undefined") return;
  try {
    if (access) window.localStorage.setItem("propai_access_token", access);
    if (refresh) window.localStorage.setItem("propai_refresh_token", refresh);
  } catch {
    /* noop */
  }
}

// 동시 401 다발 시 갱신 호출을 1개로 묶는다(중복 refresh 방지).
let _refreshInFlight: Promise<boolean> | null = null;

function isAuthPath(path: string): boolean {
  return /\/auth\/(login|refresh|register|logout)/.test(path);
}

/** 만료된 access token을 refresh token으로 갱신. 성공 시 새 토큰 저장. */
function refreshAccessToken(): Promise<boolean> {
  if (_refreshInFlight) return _refreshInFlight;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return Promise.resolve(false);

  _refreshInFlight = (async () => {
    try {
      const res = await fetch(getRequestUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access_token?: string; refresh_token?: string };
      if (data?.access_token) {
        setStoredTokens(data.access_token, data.refresh_token);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  })().finally(() => {
    _refreshInFlight = null;
  });

  return _refreshInFlight;
}

function createRequestBody(body: ApiRequestOptions["body"]) {
  if (
    body == null ||
    typeof body === "string" ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer
  ) {
    return body;
  }

  return JSON.stringify(body);
}

function shouldSetJsonContentType(body: ApiRequestOptions["body"]) {
  if (
    body == null ||
    typeof body === "string" ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer
  ) {
    return false;
  }

  return true;
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();

  return text ? { message: text } : null;
}

async function executeFetch(
  path: string,
  method: string,
  options: ApiRequestOptions,
): Promise<Response> {
  // 무한 대기 차단: AbortController로 타임아웃. timeoutMs=0이면 무제한.
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = timeoutMs > 0 && !options.signal ? new AbortController() : null;
  const timer =
    controller != null
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;

  const accessToken = getAccessToken();
  // sales 현장 경로면 저장된 현장 진입 토큰을 X-Site-Token으로 자동첨부(무파괴: 경로+토큰 존재시만).
  const salesSiteId = extractSalesSiteId(path);
  const siteToken = salesSiteId ? getActiveSiteToken(salesSiteId) : "";
  // 텔레메트리: 호출 지연·상태 계측(자가성장 엔진). 측정 시작.
  const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
  try {
    const response = await fetch(getRequestUrl(path), {
      ...options,
      method,
      body: createRequestBody(options.body),
      signal: options.signal ?? controller?.signal,
      headers: {
        Accept: "application/json",
        ...(shouldSetJsonContentType(options.body)
          ? { "Content-Type": "application/json" }
          : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(siteToken ? { "X-Site-Token": siteToken } : {}),
        // 호출자가 명시한 헤더(명시적 X-Site-Token 포함)는 자동첨부보다 우선.
        ...options.headers,
      },
    });
    // 정상 응답(2xx~5xx 모두) 계측 — 성공/오류는 trackApiCall 내부에서 분기.
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    trackApiCall(path, response.status, Math.round(now - startedAt));
    return response;
  } catch (err) {
    // 네트워크 실패/타임아웃: status 0(또는 408)으로 api_error 계측.
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const isTimeout = err instanceof DOMException && err.name === "AbortError";
    trackApiCall(path, isTimeout ? 408 : 0, Math.round(now - startedAt));
    if (isTimeout) {
      throw new ApiClientError(
        `요청 시간이 초과되었습니다(${Math.round(timeoutMs / 1000)}초). 서버 응답이 지연되고 있습니다.`,
        408,
        null,
      );
    }
    throw err;
  } finally {
    if (timer != null) clearTimeout(timer);
  }
}

async function request<T>(path: string, options: ApiRequestOptions = {}) {
  const method = options.method ?? "GET";
  const useMock = options.useMock ?? useMocksByDefault;

  if (useMock) {
    const mockResponse = await resolveMockRequest<T>(method, path);

    if (mockResponse !== undefined) {
      return mockResponse;
    }
  }

  let response = await executeFetch(path, method, options);

  // 토큰 만료(401) → refresh token으로 자동 갱신 후 1회 재시도(인증 엔드포인트 제외).
  // 액세스 토큰 60분 만료 후 모든 인증 호출이 실패하던 문제의 근본 해결.
  if (
    response.status === 401 &&
    typeof window !== "undefined" &&
    !isAuthPath(path) &&
    getRefreshToken()
  ) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await executeFetch(path, method, options);
    }
  }

  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new ApiClientError(
      "API 요청 처리에 실패했습니다.",
      response.status,
      payload,
    );
  }

  return payload as T;
}

function getV2RequestUrl(path: string) {
  if (isAbsoluteUrl(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  // v1과 동일한 단일 오리진 해석을 공유한다(화이트리스트 이중 유지 제거).
  return `${resolveApiOrigin()}/api/v2${normalizedPath}`;
}

export const apiClient = {
  request,
  get<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "GET" });
  },
  post<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "POST" });
  },
  put<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "PUT" });
  },
  patch<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "PATCH" });
  },
  delete<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "DELETE" });
  },
  getV2<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    const url = getV2RequestUrl(path);
    return request<T>(url, { ...options, method: "GET" });
  },
  postV2<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    const url = getV2RequestUrl(path);
    return request<T>(url, { ...options, method: "POST" });
  },
  putV2<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    const url = getV2RequestUrl(path);
    return request<T>(url, { ...options, method: "PUT" });
  },
  deleteV2<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    const url = getV2RequestUrl(path);
    return request<T>(url, { ...options, method: "DELETE" });
  },
  getRuntimeConfig() {
    const accessToken = getAccessToken();

    return {
      apiBaseUrl,
      useMocksByDefault,
      hasAccessToken: Boolean(accessToken),
      mode: useMocksByDefault ? ("mock" as const) : ("live" as const),
    };
  },
};
