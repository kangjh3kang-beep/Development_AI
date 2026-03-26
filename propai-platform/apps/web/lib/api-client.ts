import { resolveMockRequest } from "@/mocks/handlers";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/latest";

const useMocksByDefault = process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
const publicAccessToken = process.env.NEXT_PUBLIC_API_ACCESS_TOKEN?.trim() ?? "";

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
};

function isAbsoluteUrl(path: string) {
  return /^https?:\/\//.test(path);
}

function getRequestUrl(path: string) {
  if (isAbsoluteUrl(path)) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${apiBaseUrl}${normalizedPath}`;
}

function getAccessToken() {
  if (typeof window !== "undefined") {
    const storedToken = window.localStorage.getItem("propai_access_token")?.trim();

    if (storedToken) {
      return storedToken;
    }
  }

  return publicAccessToken;
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

async function request<T>(path: string, options: ApiRequestOptions = {}) {
  const method = options.method ?? "GET";
  const useMock = options.useMock ?? useMocksByDefault;
  const accessToken = getAccessToken();

  if (useMock) {
    const mockResponse = await resolveMockRequest<T>(method, path);

    if (mockResponse !== undefined) {
      return mockResponse;
    }
  }

  const response = await fetch(getRequestUrl(path), {
    ...options,
    method,
    body: createRequestBody(options.body),
    headers: {
      Accept: "application/json",
      ...(shouldSetJsonContentType(options.body)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

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

export const apiClient = {
  request,
  get<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "GET" });
  },
  post<T>(path: string, options?: Omit<ApiRequestOptions, "method">) {
    return request<T>(path, { ...options, method: "POST" });
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
