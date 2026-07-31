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
    // ★스코프는 **이 호출부의 형태에만** 좁힌다(`?? null`). 같은 파일의 다른 pnu 배선
    //   (등기/토지조서, `|| undefined`)은 이 PR 소관이 아니므로 스코프에 넣지 않는다 —
    //   넣었더니 그쪽을 **의미 보존 리팩터만 해도 깨지는 위양성**이 났다(R4가 프로브로 실증.
    //   MEMORY `feedback_mutation_wiring_and_scope`의 "과도스코프가 정상코드 깨뜨림").
    // ★하중을 받는 것은 `minMatches`다: 이 줄이 사라지면 0건 < 1건으로 **하드 실패**한다.
    //   `mustContain`은 스코프 정규식의 부분문자열이라 사실상 장식이다(도구가 요구하는
    //   필수 인자라 채운다) — 정직하게 밝혀 둔다. 진짜 검사는 아래 두 번째 케이스다.
    expect(() =>
      assertWiredThrough({
        file: "components/design/DesignStudio.tsx",
        scope: /pnu=\{siteAnalysis\?\.pnu \?\? null\}/,
        mustContain: "siteAnalysis?.pnu",
        minMatches: 1,
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
