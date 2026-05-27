/**
 * AI 챗봇 Edge API (스트리밍).
 *
 * 사용자 브라우저의 API 키로 대화형 AI 비서를 구동합니다.
 * 도메인별 시스템 프롬프트를 자동 적용합니다.
 */

import { streamText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import { createAnthropic } from "@ai-sdk/anthropic";
import { NextResponse } from "next/server";
import { DOMAIN_PROMPTS, type AIDomain } from "@/lib/ai-prompts";

export const runtime = "edge";

/**
 * pathname에서 도메인을 추론합니다.
 */
function inferDomain(pathname?: string): AIDomain {
  if (!pathname) return "general";
  if (pathname.includes("/site-analysis")) return "site-analysis";
  if (pathname.includes("/feasibility")) return "feasibility";
  if (pathname.includes("/design") || pathname.includes("/bim")) return "design";
  if (pathname.includes("/auction")) return "auction";
  if (pathname.includes("/esg") || pathname.includes("/carbon")) return "esg";
  if (pathname.includes("/tax")) return "tax";
  if (pathname.includes("/legal") || pathname.includes("/contracts")) return "legal";
  if (pathname.includes("/construction")) return "construction";
  if (pathname.includes("/finance")) return "finance";
  if (pathname.includes("/maintenance") || pathname.includes("/inspection")) return "maintenance";
  if (pathname.includes("/safety")) return "safety";
  if (pathname.includes("/market")) return "market";
  if (pathname.includes("/regulation") || pathname.includes("/permits")) return "regulation";
  if (pathname.includes("/investment") || pathname.includes("/cost")) return "feasibility";
  if (pathname.includes("/sre")) return "general";
  return "general";
}

export async function POST(req: Request) {
  try {
    const { messages, provider, model, pathname } = await req.json();
    const authHeader = req.headers.get("Authorization");

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return NextResponse.json(
        { error: "API 키가 필요합니다." },
        { status: 401 },
      );
    }

    const apiKey = authHeader.split(" ")[1];
    if (!apiKey) {
      return NextResponse.json(
        { error: "API Key not provided" },
        { status: 401 },
      );
    }

    // 도메인 추론 및 프롬프트 선택
    const domain = inferDomain(pathname);
    const systemPrompt = DOMAIN_PROMPTS[domain];

    // 모델 해석
    const resolvedModel =
      !model || model === "auto"
        ? provider === "anthropic"
          ? "claude-3-5-haiku-20241022"
          : "gpt-4o-mini"
        : model;

    let languageModel;
    if (provider === "anthropic") {
      const anthropic = createAnthropic({ apiKey });
      languageModel = anthropic(resolvedModel);
    } else {
      const openai = createOpenAI({ apiKey });
      languageModel = openai(resolvedModel);
    }

    const result = streamText({
      model: languageModel,
      messages,
      system: systemPrompt,
    });

    return result.toTextStreamResponse();
  } catch (error: unknown) {
    const message =
      error instanceof Error ? error.message : "Internal Server Error";
    console.error("AI Chat Error:", error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
