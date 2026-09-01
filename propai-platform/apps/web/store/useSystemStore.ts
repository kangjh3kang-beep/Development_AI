import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * LLM 프로바이더·모델 **선호값** 저장소.
 *
 * ★사용자 API 키는 **여기 없다**(2026-08-28 제거). 이유 — 실측:
 *   · `getActiveApiKey()` 소비처 **0건**. `git log -S` 로 보면 **도입 커밋(`ee7245bb`)부터**
 *     한 번도 불린 적이 없다.
 *   · `openaiApiKey`/`anthropicApiKey` 는 **설정 화면 자신**(입력칸 표시)에서만 읽혔다.
 *   · `lib/api-client.ts` 는 그 값을 **한 번도 싣지 않는다**(JWT `accessToken` 만).
 *   · 백엔드에 **사용자 키를 받는 경로가 없다** — `llm_provider.get_llm()` 은 `api_key` 인자
 *     자체가 없고 `get_clean_env_key()` 로 **서버 공통 키**를 쓴다.
 *   즉 사용자가 넣은 `sk-...` 는 **localStorage 에 평문으로 남기만 하고 아무 데도 쓰이지
 *   않았는데**, 화면은 길이 10자 이상이면 **초록 "Connected"** 라고 말했다.
 *   (BYOK 는 2026-06-03·06-11 두 단계로 서버 공통 키 아키텍처에 자리를 내주며 **의도적으로
 *    죽었고**, UI 만 남아 있었다. 볼트·계획서 189개에 BYOK 요구 **0건**.)
 *
 * ★`llmProvider`/`llmModel` 은 **살아 있다** — `lib/ai-analyze-client.ts` 의 `useAIReady()` 가
 *   소비한다. 그래서 이 저장소를 통째로 지우지 않는다.
 */
type SystemState = {
  llmProvider: 'openai' | 'anthropic';
  llmModel: string;
  setLLMProvider: (provider: 'openai' | 'anthropic') => void;
  setLLMModel: (model: string) => void;
};

/** 이미 브라우저에 저장된 키를 떨어내기 위한 스키마 버전(0 = 키가 있던 시절). */
export const SYSTEM_STORE_VERSION = 1;

/**
 * 옛 저장분에서 **키 필드만** 떨어낸다.
 *
 * ★제거만으로는 부족하다: `projectSync` 가 `propai-system-storage` 를 비우는 시점은
 *   **로그아웃·계정전환** 이라, 계속 로그인해 둔 사용자의 브라우저에는 쓰이지 않는 시크릿이
 *   그대로 남는다. 다음에 앱을 열 때 이 마이그레이션이 걷어낸다.
 * ★살아 있는 필드(`llmProvider`·`llmModel`)는 **보존**한다 — 두 모집단을 락으로 가른다.
 */
export function stripLegacyApiKeys(persisted: unknown): Partial<SystemState> {
  if (!persisted || typeof persisted !== 'object') return {};
  const { openaiApiKey, anthropicApiKey, ...rest } = persisted as Record<string, unknown>;
  void openaiApiKey;
  void anthropicApiKey;
  return rest as Partial<SystemState>;
}

export const useSystemStore = create<SystemState>()(
  persist(
    (set) => ({
      llmProvider: 'openai',
      llmModel: 'auto',

      setLLMProvider: (provider) => set({ llmProvider: provider, llmModel: 'auto' }),
      setLLMModel: (model) => set({ llmModel: model }),
    }),
    {
      name: 'propai-system-storage',
      version: SYSTEM_STORE_VERSION,
      migrate: (persisted) => stripLegacyApiKeys(persisted),
    },
  ),
);
