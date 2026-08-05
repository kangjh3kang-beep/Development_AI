/**
 * 비율 표기 전역 스윕 — 같은 결함이 다른 화면에서 재발하지 않게.
 *
 * ★왜(2026-08-05 R2 MEDIUM): #530이 종합분석 §1에서 "정수 반올림이 격차를 지운다"를 봉합했는데,
 *   **같은 결함이 다른 화면에 그대로 남아 있었다.**
 *     - 사통맵 필지 상세: `Math.round(effectiveFarPct)%` — 실효 79.6%가 "80%"가 되어
 *       바로 옆 법정 80%와 같아 보인다. 이 화면이 설명하려는 격차 자체가 사라진다.
 *     - 부지분석 페이지: 로컬 `pct()` 헬퍼가 같은 반올림 + `null → "—"`(0과 구분 불가).
 *
 *   CLAUDE.md의 버그수정 기본정책(전역 전파방지)이 요구하는 스윕이다 — 한 곳을 고쳤으면
 *   같은 패턴을 플랫폼 전역에서 찾아 함께 고치고, 공용 함수로 수렴시켜 재발을 막는다.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const TARGETS = [
  "components/precheck/SatongMapShell.tsx",
  "app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx",
  "components/cost/ChangeForecastCard.tsx",
  "components/sales/FairPriceSuggestCard.tsx",
];

function codeOf(file: string): string {
  return readFileSync(resolve(process.cwd(), file), "utf-8")
    .split("\n")
    .map((l) => l.replace(/(^|[^:])\/\/.*$/, "$1"))
    .filter((l) => !/^\s*\*/.test(l))
    .join("\n");
}

describe("비율 표기 — 정수 반올림이 격차를 지우지 않는다", () => {
  it("★값이 없을 때 '+%'·'+~%' 같은 깨진 표기를 만들지 않는다", () => {
    // #541이 종합분석에서 고친 것과 **완전히 동일한 형태**가 다른 화면 3곳에 남아 있었다.
    // CLAUDE.md 전역 전파방지: 파일 내가 아니라 플랫폼 전역 스윕이 요구된다.
    for (const f of TARGETS) {
      const code = codeOf(f);
      expect(code).not.toMatch(/`\+\$\{[^}]*\}%`/);
      expect(code).not.toMatch(/`\+\$\{[^}]*\}~\$\{[^}]*\}%`/);
    }
  });

  it("검사가 공허하지 않다 — 대상 파일이 실제로 공용 포매터를 부른다", () => {
    for (const f of TARGETS) {
      expect(codeOf(f)).toContain("formatPercent");
    }
  });

  it("★비율 필드에 Math.round가 다시 붙지 않는다", () => {
    for (const f of TARGETS) {
      const code = codeOf(f);
      // Math.round(...far/bcr/pct...) 형태 — 비율에 정수 반올림을 거는 패턴.
      const rounded = code.match(/Math\.round\([^)]*(?:[Ff]ar|[Bb]cr|[Pp]ct|[Pp]ercent)[^)]*\)/g) ?? [];
      expect(rounded).toEqual([]);
    }
  });

  it("★사통맵 필지 상세의 실효/현황 비율 3칸이 포매터를 거친다", () => {
    const code = codeOf(TARGETS[0]);
    for (const field of ["effectiveFarPct", "effectiveBcrPct", "currentFarPct"]) {
      expect(code).toContain(`formatPercent(detailFeature.${field})`);
    }
  });

  it("★부지분석 페이지의 로컬 헬퍼가 자체 규칙을 갖지 않는다", () => {
    const code = codeOf(TARGETS[1]);
    // 로컬 pct가 포매터에 위임하는지 — 자체 문자열 조립으로 되돌아가면 규칙이 두 벌이 된다.
    expect(code).toMatch(/const pct = \([^)]*\): string => formatPercent\(/);
    expect(code).not.toMatch(/const pct = [^;]*Math\.round/);
  });
});
