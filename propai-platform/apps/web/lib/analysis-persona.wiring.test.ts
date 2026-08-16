/**
 * 배선 불변식 — 종합분석 패널이 **정말로** 관점 순서를 따라 렌더하는가.
 *
 * ★순서 SSOT가 아무리 옳아도 패널이 섹션을 하드코딩 순서로 그리면 화면은 안 바뀐다.
 *   "로직은 고쳤는데 실제 경로가 그 코드를 안 탄다"는 이 저장소의 반복 결함이라 따로 잠근다.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { NEUTRAL_SECTION_ORDER } from "@/lib/analysis-persona";

const PANEL = "components/analysis/ComprehensiveAnalysisPanel.tsx";
const src = readFileSync(resolve(process.cwd(), PANEL), "utf-8");

/** ★2026-08-16 — 손수 만든 스트리퍼는 **단일행 `/* … *​/` 를 못 벗긴다**.
 *  스트립 규칙이 파일마다 갈리면 약한 쪽만 뚫린다 — 공용 도구로 일원화한다. */
const code = __stripCommentsForScan(src, PANEL);

describe("종합분석 패널 — 관점 순서 배선", () => {
  it("검사가 공허하지 않다 — 섹션 노드 맵이 실제로 존재한다", () => {
    expect(code).toContain("const sectionNodes");
    for (const id of NEUTRAL_SECTION_ORDER) {
      expect(code).toContain(`"${id}":`);
    }
  });

  it("★렌더가 순서 SSOT를 따라 돈다 — 하드코딩 나열이 아니다", () => {
    expect(code).toMatch(/sectionOrder\.map\(/);
    expect(code).toContain("sectionOrderFor(persona)");
  });

  it("관점을 바꾸면 섹션이 새 펼침 기본값으로 다시 뜬다", () => {
    // key에 관점이 안 들어가면 SectionCard의 useState(defaultOpen)가 옛 값을 붙들고 있는다.
    expect(code).toMatch(/key=\{`\$\{persona[^`]*\}:\$\{id\}`\}/);
  });

  it("펼침 판정이 관점 SSOT를 거친다 — 패널이 자체 규칙을 만들지 않는다", () => {
    expect(code).toContain("isExpandedFor(persona");
    // ★스코프는 **SectionCard 사용처**로 좁힌다. 넓게 잡으면 컴포넌트 정의부의 프로퍼티
    //   선언(`defaultOpen = false`·`defaultOpen?: boolean`)까지 위반으로 잡아 기준선이 깨진다
    //   (실제로 이 검사를 처음 쓸 때 그렇게 실패했다 — 과도스코프).
    //   ※§1-B(용적률 최적화)는 별도 컴포넌트(FarOptimizationPanel) 안의 하위 카드라 openFor에
    //     닿지 않는다. 그건 effective-far 묶음의 일부로 함께 움직이므로 대상에서 제외한다.
    const usages = (code.match(/<SectionCard[^>]*?>/g) ?? [])
      .filter((u) => /title="[1-7]\. /.test(u));
    expect(usages.length).toBe(7); // 공허진리 방지 — 최상위 섹션 7개 전부
    const notWired = usages.filter((u) => !u.includes("defaultOpen={openFor("));
    expect(notWired).toEqual([]);
  });

  it("기본값이 중립이다 — 관점 기능이 켜졌다고 화면이 멋대로 바뀌지 않는다", () => {
    expect(code).toMatch(/useState<PersonaKey \| null>\(null\)/);
  });
});
