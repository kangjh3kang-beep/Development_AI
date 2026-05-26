import { generateText, streamText } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { createAnthropic } from '@ai-sdk/anthropic';
import { NextResponse } from 'next/server';

export const runtime = 'edge';

export async function POST(req: Request) {
  try {
    const { messages, provider, model } = await req.json();
    const authHeader = req.headers.get('Authorization');
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json({ error: 'Missing or invalid Authorization header' }, { status: 401 });
    }

    const apiKey = authHeader.split(' ')[1];

    if (!apiKey) {
      return NextResponse.json({ error: 'API Key not provided' }, { status: 401 });
    }

    let languageModel;

    if (provider === 'anthropic') {
      const anthropic = createAnthropic({ apiKey });
      languageModel = anthropic(model || 'claude-3-haiku-20240307');
    } else {
      const openai = createOpenAI({ apiKey });
      languageModel = openai(model || 'gpt-3.5-turbo');
    }

    const result = streamText({
      model: languageModel,
      messages,
      system: `당신은 사통팔땅(PropAI) 플랫폼의 AI 비서입니다. 부동산 개발, 지적도 분석, 사업 타당성 검토, ESG, 디지털 트윈 등을 지원합니다. 전문적이고 간결하게 답변하세요.`,
    });

    return result.toTextStreamResponse();
  } catch (error: any) {
    console.error('AI API Error:', error);
    return NextResponse.json({ error: error.message || 'Internal Server Error' }, { status: 500 });
  }
}
