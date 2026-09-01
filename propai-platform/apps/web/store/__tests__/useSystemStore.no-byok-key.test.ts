/**
 * ★쓰이지 않는 사용자 LLM 키를 **받지도, 보관하지도 않는다**(2026-08-28).
 *
 * 【무엇이 잘못돼 있었나 — 실측】
 * · `hasValidKey()` = `key.trim().length >= 10` 만 보고 화면이 **초록 펄스 점 + "Connected"** 를 그렸다.
 * · 그런데 그 키는 **어디에도 쓰이지 않았다**: `getActiveApiKey()` 소비처 **0건**
 *   (`git log -S` — **도입 커밋부터** 한 번도 안 불림) · `api-client` 가 싣지 않음 ·
 *   백엔드에 **사용자 키 수신 경로 없음**(`get_llm()` 은 `api_key` 인자가 없다).
 * · `persist({name:'propai-system-storage'})` → 사용자의 `sk-...` 가 **localStorage 평문**으로 남았다.
 *
 * 【★제거만으로는 부족하다】
 * `projectSync` 가 그 저장소를 비우는 시점은 **로그아웃·계정전환** 이라, 계속 로그인해 둔
 * 브라우저에는 시크릿이 남는다. 그래서 `persist` 마이그레이션으로 **걷어낸다**.
 */
import { describe, expect, it } from "vitest";

import { stripLegacyApiKeys, SYSTEM_STORE_VERSION, useSystemStore } from "../useSystemStore";

describe("★키 필드가 스토어에 없다", () => {
  it("상태에 키·키관련 메서드가 **하나도** 없다(파생형 — 손 목록 아님)", () => {
    const keys = Object.keys(useSystemStore.getState());
    const banned = keys.filter((k) => /apikey|hasvalidkey|getactiveapikey/i.test(k));
    expect(banned, `쓰이지 않는 키 관련 필드가 남아 있다: ${banned.join(", ")}`).toEqual([]);
  });

  it("★대조군 — 살아 있는 필드는 그대로다(전부 지우지 않았다)", () => {
    const s = useSystemStore.getState();
    // `lib/ai-analyze-client.ts` 의 `useAIReady()` 가 이 둘을 소비한다.
    expect(s.llmProvider).toBeDefined();
    expect(s.llmModel).toBeDefined();
    expect(typeof s.setLLMProvider).toBe("function");
    expect(typeof s.setLLMModel).toBe("function");
  });
});

describe("★이미 저장된 키를 걷어낸다", () => {
  const LEGACY = {
    llmProvider: "anthropic",
    llmModel: "claude-x",
    openaiApiKey: "sk-proj-THIS-IS-A-SECRET",
    anthropicApiKey: "sk-ant-THIS-IS-A-SECRET",
  };

  it("옛 저장분에서 **키만** 떨어진다", () => {
    const out = stripLegacyApiKeys(LEGACY) as Record<string, unknown>;
    expect("openaiApiKey" in out, "openai 키가 남았다").toBe(false);
    expect("anthropicApiKey" in out, "anthropic 키가 남았다").toBe(false);
    // ★값이 어디에도 새지 않는지 — 직렬화 전체에서 확인(키 이름만 지우고 값이 남는 형태 차단).
    expect(JSON.stringify(out)).not.toContain("SECRET");
  });

  it("★두 번째 모집단 — **살아 있는 필드는 보존**된다(전부 버리지 않았다)", () => {
    const out = stripLegacyApiKeys(LEGACY) as Record<string, unknown>;
    expect(out.llmProvider, "선호 프로바이더가 사라졌다").toBe("anthropic");
    expect(out.llmModel, "선호 모델이 사라졌다").toBe("claude-x");
  });

  it("손상·부재 입력에서 죽지 않는다", () => {
    expect(stripLegacyApiKeys(null)).toEqual({});
    expect(stripLegacyApiKeys(undefined)).toEqual({});
    expect(stripLegacyApiKeys("not-an-object" as unknown)).toEqual({});
  });

  it("★마이그레이션이 **실제로 배선**돼 있다(함수만 있고 안 걸면 안 돈다)", () => {
    // persist 옵션은 스토어 생성 시 소비되므로, 버전이 0 보다 크다는 것이
    // `version`+`migrate` 를 건 유일한 관측 가능 신호다.
    expect(SYSTEM_STORE_VERSION).toBeGreaterThan(0);
    expect(useSystemStore.persist.getOptions().version).toBe(SYSTEM_STORE_VERSION);
    expect(typeof useSystemStore.persist.getOptions().migrate).toBe("function");
  });
});
