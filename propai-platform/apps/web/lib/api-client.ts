import { resolveMockRequest } from "@/mocks/handlers";

const apiBaseUrl = (() => {
  // 1) 빌드 타임 환경변수 (Vercel/로컬 등)
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  // 2) 브라우저 런타임: 도메인 기반 자동 감지
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    // 프로덕션 도메인들
    if (host === "4t8t.net" || host === "www.4t8t.net" || host.endsWith(".pages.dev") || host === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
})();

const useMocksByDefault = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
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

  // 환경변수에 API URL이 설정된 경우 (프로덕션: Railway 등)
  if (apiBaseUrl && apiBaseUrl !== "/api/proxy") {
    return `${apiBaseUrl}${normalizedPath}`;
  }

  // If executing in Node.js (Server Component), use Docker internal DNS.
  if (typeof window === "undefined") {
    return `http://api:8000/api/v1${normalizedPath}`;
  }

  // In Browser, Next.js Proxy throws internal 500 network errors due to IPv6 DNS bugs in Node 18+.
  // We completely bypass Next.js rewrites and hit the exposed host port directly!
  return `http://localhost:8000/api/v1${normalizedPath}`;
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
  try {
    return await fetch(getRequestUrl(path), {
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
        ...options.headers,
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
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

  // 프로덕션: Railway 백엔드
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "4t8t.net" || host === "www.4t8t.net" || host.endsWith(".pages.dev") || host === "propai.kr") {
      return `https://api.4t8t.net/api/v2${normalizedPath}`;
    }
  }

  // SSR (Docker)
  if (typeof window === "undefined") {
    return `http://api:8000/api/v2${normalizedPath}`;
  }
  // 로컬 개발
  return `http://localhost:8000/api/v2${normalizedPath}`;
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
