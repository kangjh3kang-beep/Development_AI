// PropAI v30.0 - API 클라이언트 유틸리티
import type { ApiResponse, ErrorResponse } from '@propai/types';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly errorCode: string,
    message: string,
    public readonly details?: Record<string, unknown> | null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(base: string, path: string, params?: FetchOptions['params']): string {
  const url = new URL(path, base);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

export function createApiClient(baseUrl: string, getToken?: () => string | null) {
  async function request<T>(path: string, options: FetchOptions = {}): Promise<T> {
    const { body, params, headers: customHeaders, ...rest } = options;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...customHeaders as Record<string, string>,
    };

    const token = getToken?.();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(buildUrl(baseUrl, path, params), {
      ...rest,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      let errorBody: ErrorResponse | undefined;
      try {
        errorBody = await response.json() as ErrorResponse;
      } catch {
        // 응답 본문 파싱 실패
      }
      throw new ApiError(
        response.status,
        errorBody?.error_code ?? 'UNKNOWN',
        errorBody?.message ?? response.statusText,
        errorBody?.details,
      );
    }

    return response.json() as Promise<T>;
  }

  return {
    get: <T>(path: string, params?: FetchOptions['params']) =>
      request<T>(path, { method: 'GET', params }),

    post: <T>(path: string, body?: unknown) =>
      request<T>(path, { method: 'POST', body }),

    put: <T>(path: string, body?: unknown) =>
      request<T>(path, { method: 'PUT', body }),

    patch: <T>(path: string, body?: unknown) =>
      request<T>(path, { method: 'PATCH', body }),

    delete: <T>(path: string) =>
      request<T>(path, { method: 'DELETE' }),
  };
}
