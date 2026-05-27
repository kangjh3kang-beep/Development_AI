/**
 * AI 분석 클라이언트.
 *
 * useSystemStore의 API 키를 사용하여 /api/ai/analyze 호출.
 * React Query 기반 커스텀 훅 제공.
 */

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSystemStore } from "@/store/useSystemStore";
import type { AIDomain } from "@/lib/ai-prompts";

// ── Types ──

export type AIAnalysisRequest = {
  domain: AIDomain;
  context?: Record<string, unknown>;
  question?: string;
};

export type AIAnalysisResponse<T = unknown> = {
  domain: AIDomain;
  data: T | null;
  text?: string;
  model: string;
  usage: Record<string, number>;
};

export type AIAnalysisError = {
  error: string;
  code: string;
};

// ── Core fetch function ──

async function fetchAIAnalysis<T = unknown>(
  request: AIAnalysisRequest,
  apiKey: string,
  provider: string,
  model: string,
): Promise<AIAnalysisResponse<T>> {
  // API 키가 없으면 즉시 에러
  if (!apiKey || apiKey.trim().length < 10) {
    throw new Error("API 키가 등록되지 않았습니다. 설정 > API 키에서 등록해주세요.");
  }

  let response: Response;
  try {
    response = await fetch("/api/ai/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        ...request,
        provider,
        model,
      }),
    });
  } catch (networkError) {
    // 네트워크 연결 자체 실패
    throw new Error("네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요.");
  }

  if (!response.ok) {
    let errorMsg = `서버 에러 (${response.status})`;
    try {
      const errBody = await response.json();
      errorMsg = errBody.error || errBody.message || errorMsg;
      if (errBody.code) errorMsg += ` [${errBody.code}]`;
    } catch {
      // JSON 파싱 실패 → status 기반 메시지
      if (response.status === 401) errorMsg = "API 키가 유효하지 않습니다. 설정에서 확인해주세요.";
      else if (response.status === 429) errorMsg = "API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.";
      else if (response.status >= 500) errorMsg = "AI 서버 내부 에러입니다. 잠시 후 다시 시도해주세요.";
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

// ── React Query Hooks ──

/**
 * AI 분석 뮤테이션 훅 (사용자 액션 트리거용).
 *
 * @example
 * ```tsx
 * const { mutate, data, isLoading } = useAIAnalyze();
 * mutate({ domain: "site-analysis", context: { address: "서울시 강남구..." } });
 * ```
 */
export function useAIAnalyze<T = unknown>() {
  const { llmProvider, openaiApiKey, anthropicApiKey, llmModel, hasValidKey } =
    useSystemStore();

  const apiKey = llmProvider === "openai" ? openaiApiKey : anthropicApiKey;

  return useMutation<AIAnalysisResponse<T>, Error, AIAnalysisRequest>({
    mutationFn: (request) =>
      fetchAIAnalysis<T>(request, apiKey, llmProvider, llmModel),
    retry: 1,
    onError: (error) => {
      console.error("[AI Analysis Error]", error.message);
    },
  });
}

/**
 * AI 분석 쿼리 훅 (자동 실행용, 조건부).
 *
 * @example
 * ```tsx
 * const { data, isLoading } = useAIAnalysisQuery(
 *   "site-analysis",
 *   { address: "서울시 강남구..." },
 *   { enabled: !!address }
 * );
 * ```
 */
export function useAIAnalysisQuery<T = unknown>(
  domain: AIDomain,
  context: Record<string, unknown>,
  options?: { enabled?: boolean; staleTime?: number },
) {
  const { llmProvider, openaiApiKey, anthropicApiKey, llmModel, hasValidKey } =
    useSystemStore();

  const apiKey = llmProvider === "openai" ? openaiApiKey : anthropicApiKey;
  const contextKey = JSON.stringify(context);

  return useQuery<AIAnalysisResponse<T>, Error>({
    queryKey: ["ai-analysis", domain, contextKey],
    queryFn: () =>
      fetchAIAnalysis<T>({ domain, context }, apiKey, llmProvider, llmModel),
    enabled: (options?.enabled ?? true) && hasValidKey(),
    staleTime: options?.staleTime ?? 5 * 60 * 1000, // 5분 캐시
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * AI 분석이 가능한지 확인하는 훅.
 */
export function useAIReady() {
  const { hasValidKey, llmProvider, llmModel } = useSystemStore();
  return {
    isReady: hasValidKey(),
    provider: llmProvider,
    model: llmModel,
  };
}
