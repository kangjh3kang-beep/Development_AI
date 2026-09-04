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
import { __stripCommentsForScan, assertWiredThrough } from "@/lib/source-invariant";

const PANEL = "components/analysis/ComprehensiveAnalysisPanel.tsx";

/** 주석·독스트링을 걷어낸 소스.
 *
 *  ★종전에는 이 파일이 **원시 `readFileSync` 결과**에 `toContain`/`match` 를 걸었다.
 *    `/* beginAnalysisRun() *​/` 한 줄이면 단언이 충족된다 — 이 저장소가 실제로 겪은 우회 경로다.
 *  ★형제 파일들이 쓰는 손수 만든 스트리퍼(`//` 제거 + `^\s*\*` 필터)는 **단일행 `/* … *​/` 를
 *    못 벗긴다**. 공용 도구를 쓴다 — 스트립 규칙이 갈리면 한쪽만 뚫린다.
 */
function code(): string {
  return __stripCommentsForScan(readFileSync(resolve(process.cwd(), PANEL), "utf-8"), PANEL);
}

/** `setResult(core…)` / `setResult((prev)…)` 로 **서버 응답을 화면에 붙이는** 줄 번호들. */
const SET_RESULT = /setResult\((core|\(prev\))/;
/** 응답을 붙이기 전에 통과해야 하는 관문. */
const GUARD = /isCurrentTarget\(runKey\)/;
/** 관문이 응답 반영 **앞** 몇 줄 안에 있어야 하는가(같은 핸들러 블록 범위). */
const GUARD_WINDOW = 12;

describe("종합분석 패널 — 분석 대상 전환 가드 배선", () => {
  it("★응답을 화면에 붙이기 전에 대상이 여전히 그 대상인지 확인한다", () => {
    // ★2026-08-16 — 종전 이 자리에는 `mustContain: /.*/` 가 있었다. 그 정규식은 **빈 줄을
    //   포함해 모든 줄에 참**이라 위반이 구조적으로 0이었다(`assertWiredThrough` 가 잠근
    //   것은 `minMatches` 뿐). CLAUDE.md 검증 규율 표가 **이름으로 지목한 결함**
    //   ("mustContain 이 scope 에 함의됨 — 공허한 참")이 이 트리에 그대로 살아 있었다.
    //   → 대역이 아니라 **관문과 응답반영의 근접성**이라는 실제 계약을 잠근다.
    const lines = code().split("\n");
    const sites = lines
      .map((text, i) => ({ text, i }))
      .filter(({ text }) => SET_RESULT.test(text));

    // 공허진리 가드 — 대상이 0개라 "위반 0"이 참이 되는 것을 막는다.
    expect(sites.length, "응답 반영 지점이 없다 — 아래 검사가 공허해진다").toBeGreaterThanOrEqual(2);

    for (const { i } of sites) {
      const before = lines.slice(Math.max(0, i - GUARD_WINDOW), i).join("\n");
      expect(
        GUARD.test(before),
        `setResult @${i + 1} 앞 ${GUARD_WINDOW}줄에 대상 확인 관문(isCurrentTarget)이 없다 — ` +
          "전환된 대상에 옛 응답이 붙는다",
      ).toBe(true);
    }

    // 착수 시점 대상 못박기가 있어야 runKey 자체가 성립한다.
    expect(code()).toContain("beginAnalysisRun()");
  });

  it("무효화 판정이 주소 문자열 단독으로 되돌아가지 않는다", () => {
    const src = code();  // ★주석 경유 우회 차단 — 원시 소스 금지
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
    const src = code();  // ★주석 경유 우회 차단 — 원시 소스 금지
    expect(src).toContain("useProjectContextStore((state) => state.projectId)");
  });
});
