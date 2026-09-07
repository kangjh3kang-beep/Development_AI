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

/** 셸이 렌더하는 내비 표면들의 **JSX 요소 원문**(여는 태그부터 닫힘까지). */
const navElements = code.match(/<Field(?:BottomNav|DesktopNav|MenuSheet)\b[\s\S]*?\/>/g) ?? [];

describe("현장앱 셸 배선(W1) — 각 내비 표면이 **무엇을 받는지** 본다", () => {
  it("★대조군 먼저: 파일을 실제로 읽었고 내비 요소가 실재한다", () => {
    expect(code.length).toBeGreaterThan(1000);
    // 파생으로 센다 — 표면을 새로 추가해도 자동으로 감시망에 들어온다.
    expect(navElements.length).toBeGreaterThanOrEqual(3);
  });

  it("모든 내비 표면이 같은 SSOT 와 같은 활성 탭·이동 핸들러를 받는다", () => {
    // ★개수 대조가 아니라 **요소별 속성**을 본다. 초판은 파일 전체의 `tabs={tabs}` 개수를
    //   태그 개수와 비교해서, 내비가 아닌 컴포넌트가 `tabs={tabs}` 를 쓰면 **정상 코드를
    //   빨갛게** 만들고(위양성), 한쪽 prop 을 빼고 다른 곳에 하나 더 쓰면 **통과**했다.
    for (const el of navElements) {
      expect(el).toMatch(/tabs=\{tabs\}/);
      expect(el).toMatch(/activeTab=\{tab\}/);
      // 이동은 반드시 셸의 상태 전이(`setTab`)로 간다 — no-op 로 갈아 끼우면 화면이 죽는다.
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
