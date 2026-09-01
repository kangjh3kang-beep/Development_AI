/**
 * 설정 화면 — **쓰지 않을 시크릿을 받지 않고, "Connected" 라 말하지 않는다**(2026-08-28).
 *
 * 이 앱은 **서버 공통 키**로 LLM 을 호출한다(`llm_provider.get_llm()` 에 `api_key` 인자가 없다).
 * 그런데 화면은 사용자에게 `sk-...` 를 받아 localStorage 에 저장하고, 길이 10자 이상이면
 * **초록 펄스 점 + "Connected — OpenAI …"** 를 그렸다.
 *
 * ★소스 grep 이 아니라 **파일 내용을 파싱**한다 — 다만 이 화면은 서버 컴포넌트·다중 탭이라
 *   렌더 비용이 크므로, **주석·문자열을 걷어낸 실행 소스**를 본다(`__stripCommentsForScan`).
 *   ★그래서 내 설명 주석이 검사에 걸리지 않는다(이 저장소가 반복해 데인 형태).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const PAGE = join(__dirname, "..", "settings", "page.tsx");
const SRC = __stripCommentsForScan(readFileSync(PAGE, "utf8"), PAGE);

describe("★설정 화면 — 사용자 LLM 키를 받지 않는다", () => {
  it("키 입력칸이 없다(placeholder `sk-...` 로 파생)", () => {
    expect(SRC, "OpenAI 키 입력칸이 남아 있다").not.toContain('"sk-..."');
    expect(SRC, "Anthropic 키 입력칸이 남아 있다").not.toContain('"sk-ant-..."');
  });

  it("스토어의 키 필드·판정기를 읽지 않는다", () => {
    for (const dead of ["openaiApiKey", "anthropicApiKey", "hasValidKey", "getActiveApiKey"]) {
      expect(SRC, `${dead} 를 아직 읽는다`).not.toContain(dead);
    }
  });

  it('★"Connected" 라고 주장하지 않는다', () => {
    expect(SRC, '사용자 키가 연결됐다는 뜻으로 읽히는 "Connected" 가 남아 있다').not.toContain(
      "Connected",
    );
  });

  it("★대신 **사실**을 말한다 — 서버 공통 키", () => {
    expect(SRC, "무엇을 쓰는지 화면이 말하지 않는다").toContain("서버 공통 키 사용");
  });

  it("★대조군 — 살아 있는 선호 설정은 그대로 렌더한다(전부 지우지 않았다)", () => {
    expect(SRC, "프로바이더 선택이 사라졌다").toContain("setLLMProvider");
    expect(SRC, "모델 선택이 사라졌다").toContain("llmModel");
  });

  it("★검사기 생존 — 걷어낸 주석이 아니라 **실행 소스**를 본다", () => {
    // 이 파일의 변경 주석에는 "Connected"·"sk-..." 가 설명으로 등장한다.
    // 걷어내기가 죽으면 위 단언들이 **원문 주석 때문에** 실패해야 정상이다.
    const raw = readFileSync(PAGE, "utf8");
    expect(raw, "설명 주석이 사라졌다 — 이 대조군이 무의미해진다").toContain("Connected");
    expect(SRC, "주석 걷어내기가 동작하지 않는다").not.toContain("Connected");
  });
});
