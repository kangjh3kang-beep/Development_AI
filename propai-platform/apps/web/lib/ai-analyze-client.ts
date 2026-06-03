/**
 * AI 분석 클라이언트.
 *
 * 도메인 프롬프트(ai-prompts)를 클라이언트에서 구성한 뒤, 서버 공통 LLM 키를 쓰는
 * 백엔드 프록시(POST /api/v1/ai/llm)를 JWT 인증으로 호출한다.
 * → 사용자별 API 키 등록 불필요(이미 등록된 서버 키를 공통 적용).
 */

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSystemStore } from "@/store/useSystemStore";
import { apiClient } from "@/lib/api-client";
import { DOMAIN_PROMPTS, buildAnalysisPrompt, type AIDomain } from "@/lib/ai-prompts";

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

// ── Core fetch function (백엔드 공통키 프록시) ──

function _stripFences(s: string): string {
  const m = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  return (m ? m[1] : s).trim();
}

async function fetchAIAnalysis<T = unknown>(
  request: AIAnalysisRequest,
): Promise<AIAnalysisResponse<T>> {
  const system = DOMAIN_PROMPTS[request.domain] ?? "";
  const prompt = request.question || buildAnalysisPrompt(request.domain, request.context || {});

  const res = await apiClient.post<{ text: string }>("/ai/llm", {
    body: { system, prompt },
    useMock: false,
    timeoutMs: 90000,
  });

  const text = res?.text ?? "";
  let data: T | null = null;
  try {
    data = JSON.parse(_stripFences(text)) as T;
  } catch {
    data = null; // 순수 텍스트 응답
  }
  return {
    domain: request.domain,
    data,
    text: data ? undefined : text,
    model: "server-common",
    usage: {},
  };
}

// ── React Query Hooks ──

/**
 * AI 분석 뮤테이션 훅 (사용자 액션 트리거용).
 */
export function useAIAnalyze<T = unknown>() {
  return useMutation<AIAnalysisResponse<T>, Error, AIAnalysisRequest>({
    mutationFn: (request) => fetchAIAnalysis<T>(request),
    retry: 1,
    onError: (error) => {
      console.error("[AI Analysis Error]", error.message);
    },
  });
}

/**
 * AI 분석 쿼리 훅 (자동 실행용, 조건부).
 */
export function useAIAnalysisQuery<T = unknown>(
  domain: AIDomain,
  context: Record<string, unknown>,
  options?: { enabled?: boolean; staleTime?: number },
) {
  const contextKey = JSON.stringify(context);

  return useQuery<AIAnalysisResponse<T>, Error>({
    queryKey: ["ai-analysis", domain, contextKey],
    queryFn: () => fetchAIAnalysis<T>({ domain, context }),
    enabled: options?.enabled ?? true,
    staleTime: options?.staleTime ?? 5 * 60 * 1000, // 5분 캐시
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * AI 분석이 가능한지 확인하는 훅.
 * 서버 공통 키를 사용하므로 항상 준비됨(로그인 전제).
 */
export function useAIReady() {
  const { llmProvider, llmModel } = useSystemStore();
  return {
    isReady: true,
    provider: llmProvider,
    model: llmModel,
  };
}
