/**
 * AI 비서 가용성 상태 — 서버(관리자 설정) LLM 키가 있는지 알려준다.
 * 클라이언트(브라우저) BYOK 키가 없어도, 서버 키가 있으면 비서를 "연결됨"으로 표시한다.
 */
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET() {
  const serverKeyAvailable = !!(
    process.env.ANTHROPIC_API_KEY || process.env.OPENAI_API_KEY
  );
  return NextResponse.json({ serverKeyAvailable });
}
