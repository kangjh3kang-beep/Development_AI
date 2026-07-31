/**
 * DesignStudio → SeedDesignMassComparison **prop 배선**(W4 / R2 MR8 생존 변이 봉합).
 *
 * ★왜 이 파일이 필요한가: R2가 `pnu={siteAnalysis?.pnu ?? null}` 한 줄을 지우는 변이를 넣었는데
 *   프론트 30건이 **전부 통과**했다. 그 한 줄이 R1 MEDIUM-1("PNU 가드가 소비처에서 사문화")의
 *   유일한 실질 봉합인데 되돌려도 초록이다 — 이 저장소가 반복 지적한 **'배선 미변이로 뚫림'**
 *   그 자체다(MEMORY `feedback_mutation_wiring_and_scope`: "배선 미변이로 4회 뚫림").
 *
 * ★한계를 밝힌다: 이건 **소스 수준 존재 검사**이지 런타임 증명이 아니다(도구 자신이 docstring에
 *   그렇게 명시한다). DesignStudio를 렌더하려면 부지분석 컨텍스트 전체가 필요해 취약해지므로
 *   "닿지 않는 곳의 최후 수단"으로 공용 도구를 쓴다. 실제 판정 로직(`massSeedAppliesTo`)과
 *   수신측 소비는 `satong-mass-seed.test.ts`·`SeedDesignMassComparison.massSeed.test.tsx`가
 *   행위로 잠근다.
 */
import { describe, expect, it } from "vitest";

import { assertWiredThrough } from "@/lib/source-invariant";

describe("DesignStudio — 매스 시드 대조용 식별자 배선(W4)", () => {
  it("★SeedDesignMassComparison 호출부가 pnu를 넘긴다(가드 사문화 방지)", () => {
    // ★하중을 받는 것은 `minMatches`다: 이 파일에는 pnu를 넘기는 호출부가 **2곳**(설계 시드
    //   비교·등기/토지조서)이고, 시드 비교 쪽 한 줄이 사라지면 1건 < 2건으로 **하드 실패**한다.
    //   (R3 LOW 지적대로 mustContain을 scope 밖으로 빼려다 scope를 넓혔더니 pnu 줄을 지워도
    //    컴포넌트 줄이 매치해 **잠금이 깨졌다** — 개수 잠금이 이 도구의 옳은 사용법이다.)
    expect(() =>
      assertWiredThrough({
        file: "components/design/DesignStudio.tsx",
        scope: /pnu=\{siteAnalysis\?\.pnu/,
        mustContain: "siteAnalysis?.pnu",
        minMatches: 2,
      }),
    ).not.toThrow();
  });

  it("★인계 대조 면적이 실제 설계 부지 면적 배선을 따른다", () => {
    // 면적 대조(R1 HIGH-3)는 이 prop이 **설계 부지** 면적일 때만 의미가 있다.
    expect(() =>
      assertWiredThrough({
        file: "components/design/DesignStudio.tsx",
        scope: /landAreaSqm=\{Number\(form\.landArea\)/,
        mustContain: "effectiveLandAreaSqm(siteAnalysis)",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});
