/**
 * 범용 AI 분석 Edge API.
 *
 * 사용자 브라우저의 API 키를 사용하여 도메인별 분석을 수행합니다.
 * - 스트리밍 없이 JSON 응답 반환
 * - 도메인별 시스템 프롬프트 자동 적용
 */

import { generateText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import { createAnthropic } from "@ai-sdk/anthropic";
import { NextResponse } from "next/server";
import {
  DOMAIN_PROMPTS,
  buildAnalysisPrompt,
  type AIDomain,
} from "@/lib/ai-prompts";

export const runtime = "nodejs";

export async function POST(req: Request) {
  try {
    const { domain, context, question, provider, model } = await req.json();
    const authHeader = req.headers.get("Authorization");

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return NextResponse.json(
        {
          error: "API 키가 필요합니다. 설정 페이지에서 API 키를 등록해주세요.",
          code: "AUTH_REQUIRED",
        },
        { status: 401 },
      );
    }

    const apiKey = authHeader.split(" ")[1];
    if (!apiKey || apiKey.length < 10) {
      return NextResponse.json(
        { error: "유효하지 않은 API 키입니다.", code: "INVALID_KEY" },
        { status: 401 },
      );
    }

    // 도메인 검증
    const validDomain: AIDomain =
      domain && domain in DOMAIN_PROMPTS ? domain : "general";
    const systemPrompt = DOMAIN_PROMPTS[validDomain];

    // 사용자 메시지 구성
    const userMessage =
      question || buildAnalysisPrompt(validDomain, context || {});

    // 모델 해석
    const resolvedModel =
      !model || model === "auto"
        ? provider === "anthropic"
          ? "claude-3-5-haiku-20241022"
          : "gpt-4o-mini"
        : model;

    // LLM Provider 생성
    let languageModel;
    if (provider === "anthropic") {
      const anthropic = createAnthropic({ apiKey });
      languageModel = anthropic(resolvedModel);
    } else {
      const openai = createOpenAI({ apiKey });
      languageModel = openai(resolvedModel);
    }

    // LLM 호출
    const result = await generateText({
      model: languageModel,
      system: systemPrompt,
      prompt: userMessage,
      temperature: 0.3,
    });

    // JSON 파싱 시도
    const text = result.text;
    let parsed: unknown = null;

    // ```json ... ``` 블록 추출
    const jsonMatch = text.match(/```json\s*([\s\S]*?)\s*```/);
    if (jsonMatch) {
      try {
        parsed = JSON.parse(jsonMatch[1]);
      } catch {
        // JSON 파싱 실패 → 원문 반환
      }
    }

    // 직접 JSON 파싱 시도
    if (!parsed) {
      try {
        parsed = JSON.parse(text);
      } catch {
        // 순수 텍스트 응답
      }
    }

    return NextResponse.json({
      domain: validDomain,
      data: parsed,
      text: parsed ? undefined : text,
      model: resolvedModel,
      usage: result.usage ?? {},
    });
  } catch (error: unknown) {
    const rawMessage =
      error instanceof Error ? error.message : String(error);
    console.error("AI Analyze Error:", rawMessage, error);

    // 세분화된 에러 분류
    const lowerMsg = rawMessage.toLowerCase();

    // 1) API 키 관련
    if (lowerMsg.includes("401") || lowerMsg.includes("unauthorized") || lowerMsg.includes("invalid_api_key") || lowerMsg.includes("incorrect api key")) {
      return NextResponse.json(
        { error: "API 키가 유효하지 않습니다. 설정에서 올바른 키를 등록해주세요.", code: "INVALID_KEY" },
        { status: 401 },
      );
    }

    // 2) 한도 초과
    if (lowerMsg.includes("429") || lowerMsg.includes("rate_limit") || lowerMsg.includes("rate limit") || lowerMsg.includes("quota")) {
      return NextResponse.json(
        { error: "API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.", code: "RATE_LIMITED" },
        { status: 429 },
      );
    }

    // 3) 모델 없음
    if (lowerMsg.includes("model") && (lowerMsg.includes("not found") || lowerMsg.includes("does not exist"))) {
      return NextResponse.json(
        { error: `선택한 모델을 사용할 수 없습니다. 설정에서 다른 모델을 선택하거나 'auto'로 설정해주세요. (${rawMessage})`, code: "MODEL_NOT_FOUND" },
        { status: 400 },
      );
    }

    // 4) 네트워크/타임아웃
    if (lowerMsg.includes("timeout") || lowerMsg.includes("econnrefused") || lowerMsg.includes("fetch failed") || lowerMsg.includes("network")) {
      return NextResponse.json(
        { error: "AI 서비스 연결에 실패했습니다. 네트워크 상태를 확인해주세요.", code: "NETWORK_ERROR" },
        { status: 502 },
      );
    }

    // 5) 잔액 부족
    if (lowerMsg.includes("insufficient") || lowerMsg.includes("billing") || lowerMsg.includes("payment")) {
      return NextResponse.json(
        { error: "API 사용 잔액이 부족합니다. API 제공사의 결제 설정을 확인해주세요.", code: "BILLING_ERROR" },
        { status: 402 },
      );
    }

    // 6) 기타 에러 — 원문 메시지 전달
    return NextResponse.json(
      { error: `AI 분석 중 오류: ${rawMessage}`, code: "ANALYSIS_ERROR" },
      { status: 500 },
    );
  }
}
