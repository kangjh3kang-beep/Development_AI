/**
 * 배선 불변식 — 현장앱 **셸**이 두 컴포넌트를 실제로 거치고, **무엇을 넘기는가**(DESIGN.md B3.3).
 *
 * ★행위 테스트만으로 부족한 이유: `FieldDesktopNav` 와 `FieldAppAffordance` 가 아무리 옳아도
 *   **셸이 그것을 안 부르면** 화면은 예전 그대로다. 이번 결함이 정확히 그 형태였다 —
 *   모바일 `FieldNav` 는 멀쩡히 있었는데 셸의 데스크톱 가지가 인라인으로 21탭을 나열했다.
 *
 * ## ★이 파일의 한계를 먼저 적는다 (2026-09-07 적대 리뷰)
 *
 * 이것은 **소스 문자열 검사**이지 렌더가 아니다. 계획서는 *"렌더 결과를 태운다(소스 grep 금지)"*
 * 라고 적었는데 **그 규칙을 이 파일이 어긴다.** 이유: 셸(`SiteWorkspaceClient`)은 패널 40여 개를
 * 임포트해 jsdom 렌더 비용이 크고, 저장소에 그 셸을 렌더하는 테스트가 **하나도 없다**.
 *
 * ⇒ **셸의 렌더 커버리지는 0 이다.** 이 파일은 그 공백을 *줄이는* 것이지 메우지 않는다.
 *   초판은 「태그가 소스에 있는가」만 봐서 `activeTab={tab}` → `activeTab="home"`,
 *   `onNavigate={setTab}` → `onNavigate={() => {}}` 같은 **배선 파괴를 전부 통과**시켰다
 *   (적대 리뷰가 단언 9개 전수 열거로 증명). 지금은 **각 요소의 속성**을 본다.
 *
 * ★공용 스트리퍼를 경유한다 — 손수 만든 정규식은 주석·문자열에 뚫린다(이 저장소 실증 4회).
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const SHELL = "components/sales-app/SiteWorkspaceClient.tsx";
const code = __stripCommentsForScan(readFileSync(resolve(process.cwd(), SHELL), "utf-8"), SHELL);

/**
 * 셸이 렌더하는 **자기닫힘 컴포넌트 요소** 전수(여는 태그부터 `/>` 까지).
 *
 * ★이름을 손으로 열거하지 않는다. 초판은 `<Field(BottomNav|DesktopNav|MenuSheet)` 라는
 *   **3-지 택일**을 써 놓고 주석에 *"표면을 새로 추가해도 자동으로 감시망에 들어온다"* 고
 *   적었다 — **거짓이었다.** 적대 리뷰가 SSOT 를 안 먹는 **네 번째 표면**을 셸에 넣어
 *   `::VERDICT=SURVIVED` 로 실증했다(이 PR 이 고치던 결함과 **같은 형태**가 그대로 통과).
 */
const selfClosing = code.match(/<[A-Z][A-Za-z0-9_]*\b[\s\S]*?\/>/g) ?? [];
/** 다른 컴포넌트를 품은 매치는 버린다(비-자기닫힘 요소를 가로질러 잡힌 것). */
const elements = selfClosing.filter((el) => !/<[A-Z][A-Za-z0-9_]*\b/.test(el.slice(1)));
/** ★`tabs=` 를 받는 **모든** 요소 — 새 표면이 생기면 **여기 자동으로 들어온다.** */
const tabsConsumers = elements.filter((el) => /\btabs=/.test(el));

describe("현장앱 셸 배선(W1) — `tabs` 를 받는 **모든** 요소가 같은 SSOT 를 먹는다", () => {
  it("★대조군 먼저: 파일을 실제로 읽었고 대상 요소가 실재한다", () => {
    expect(code.length).toBeGreaterThan(1000);
    expect(tabsConsumers.length).toBeGreaterThanOrEqual(3);
  });

  it("모든 소비자가 tabs={tabs} · activeTab={tab} 를 받고, 이동은 setTab 을 거친다", () => {
    // ★개수 대조가 아니라 **요소별 속성**을 본다(초판은 파일 전체의 `tabs={tabs}` 개수를
    //   태그 개수와 비교해 위양성·위음성을 함께 만들었다).
    for (const el of tabsConsumers) {
      expect(el).toMatch(/tabs=\{tabs\}/);
      expect(el).toMatch(/activeTab=\{tab\}/);
      // ★이 단언의 한계를 정직하게 적는다: `setTab` 이라는 **이름이 그 안에 있는지**만 본다.
      //   `onNavigate={() => setTab("home")}` 같은 **틀린 인자**는 통과한다(적대 리뷰 실증).
      //   그 축은 셸을 렌더해야 잡히고, 이 PR 은 **셸 렌더 커버리지가 0**임을 계획서 §3 에
      //   공시했다. 여기서 잠그는 것은 「핸들러가 통째로 no-op 이 되는 것」까지다.
      expect(el).toMatch(/onNavigate=\{[^}]*setTab/);
    }
  });
});

describe("현장앱 셸 배선(W2·W3) — 인라인 회귀 금지 · 두 모집단", () => {
  it("W2 데스크톱 내비를 셸이 다시 인라인으로 그리지 않는다 — 컴포넌트를 거친다", () => {
    expect(code).toContain("<FieldDesktopNav"); // 양성: 배선이 있다
    // 음성: 옛 인라인 탭바의 전용 CSS 클래스가 셸에 없다(이제 FieldNav 만 쓴다).
    expect(code).not.toContain("sa-tabbar");
  });

  it("W3 앱 어포던스를 셸이 다시 인라인으로 그리지 않는다 — 판정은 컴포넌트가 한다", () => {
    expect(code).toContain("<FieldAppAffordance"); // 양성
    // 음성: 셸이 직접 창을 열거나 라벨을 들고 있지 않다(가드가 형제마다 갈리던 원인).
    expect(code).not.toContain("window.open");
    expect(code).not.toContain("앱으로 열기");
    expect(code).not.toContain("별도 창으로 열기");
  });
});
