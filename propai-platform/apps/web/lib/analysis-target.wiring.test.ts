/**
 * 배선 불변식 — 종합분석 패널이 **정말로** 대상 전환 가드를 거치는가.
 *
 * ★왜 행위 테스트만으로 부족한가: 훅이 아무리 옳게 동작해도 소비처가 그 훅을 안 부르면
 *   화면은 그대로 깨진다. 2026-08-02 W4의 CRITICAL이 정확히 그 형태였다 — 로직은 고쳤는데
 *   실제 요청 흐름이 그 코드를 안 타서 숫자가 하나도 안 바뀌었다. 그래서 배선 층을 따로 잠근다.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { assertWiredThrough } from "@/lib/source-invariant";

const PANEL = "components/analysis/ComprehensiveAnalysisPanel.tsx";

describe("종합분석 패널 — 분석 대상 전환 가드 배선", () => {
  it("응답을 화면에 붙이기 전에 대상이 여전히 그 대상인지 확인한다", () => {
    assertWiredThrough({
      file: PANEL,
      // setResult로 서버 응답을 붙이는 줄들(초기화 setResult(null)은 제외).
      scope: /setResult\((core|\(prev\))/,
      mustContain: /.*/,
      minMatches: 2,
    });
    const src = readFileSync(resolve(process.cwd(), PANEL), "utf-8");
    // 두 번의 응답 반영(1단계 core·2단계 해석 병합) 각각 앞에 isCurrentTarget 관문이 있어야 한다.
    const guards = src.match(/isCurrentTarget\(runKey\)/g) ?? [];
    expect(guards.length).toBeGreaterThanOrEqual(2);
    // 착수 시점 대상 못박기가 있어야 runKey 자체가 성립한다.
    expect(src).toContain("beginAnalysisRun()");
  });

  it("무효화 판정이 주소 문자열 단독으로 되돌아가지 않는다", () => {
    const src = readFileSync(resolve(process.cwd(), PANEL), "utf-8");
    // 종전 결함 형태: 주소만 비교해 결과를 지우던 조건. 되살아나면 주소 없는 프로젝트에서 또 샌다.
    expect(src).not.toMatch(/mainAddr\s*!==\s*\(result/);
    // 판정 키는 공용 헬퍼로만 만든다(로컬 재구성 금지 — 두 곳이 갈리면 한쪽만 고쳐진다).
    expect(src).toContain("analysisTargetKey(projectId");
  });

  it("가드가 프로젝트 ID를 실제로 읽는다 — 주소만 보면 다필지 전환을 못 잡는다", () => {
    assertWiredThrough({
      file: PANEL,
      scope: /const targetKey = /,
      mustContain: "projectId",
      minMatches: 1,
    });
    const src = readFileSync(resolve(process.cwd(), PANEL), "utf-8");
    expect(src).toContain("useProjectContextStore((state) => state.projectId)");
  });
});
