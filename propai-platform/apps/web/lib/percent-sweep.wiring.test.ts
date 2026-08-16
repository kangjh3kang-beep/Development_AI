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
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";

/**
 * ★2026-08-16 — 종전에는 **손수 나열한 4개**를 `TARGETS` 로 두고 파일 헤더는 "전역 스윕"이라
 *   적었다. 실제 모집단은 `components/` + `app/` 하위 **`.tsx` 472개**였고(커버리지 4/472),
 *   **스캔 밖에 같은 형태의 진짜 위반 8건**이 살아 있었다:
 *     `GenerativeDesignPanel.tsx` 1333·1334·1524·1525·1661·1672
 *     `ReferenceAssemblyCard.tsx` 291·292
 *   실효 79.6% 가 "80%" 로 반올림되어 **바로 옆 법정 80% 와 같아 보이던** 원래 결함과
 *   정확히 같은 클래스다(이 파일이 막겠다고 선언한 바로 그것).
 *
 * ★CLAUDE.md 회귀망 규율 A-4: **목록형이 아니라 전수/파생형으로 쓴다.**
 *   사람이 센 목록이 곧 상한이 된다 — 그래서 대상을 **코드에서 파생**시킨다.
 *   새 화면이 같은 형태를 쓰면 **자동으로** 이 그물에 걸린다.
 *
 * ★주석 스트립은 공용 도구를 쓴다. 손수 만든 스트리퍼(`//` 제거 + `^\s*\*` 필터)는
 *   **단일행 `/* … *\/` 를 못 벗겨** 약한 쪽만 뚫린다.
 */
const ROOTS = ["components", "app"];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "__tests__" || name === "node_modules") continue;
      walk(full, out);
    } else if (name.endsWith(".tsx") && !name.includes(".test.")) {
      out.push(relative(process.cwd(), full));
    }
  }
  return out;
}

/** 감시 모집단 — 코드에서 파생한다(사람이 센 목록 금지). */
const ALL_TSX = ROOTS.flatMap((r) => walk(resolve(process.cwd(), r)));

/** 종전 목록 — 이 4개는 **여전히** 포매터를 거쳐야 한다(회귀 방지용 하한). */
const SEEDS = [
  "components/precheck/SatongMapShell.tsx",
  "app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx",
  "components/cost/ChangeForecastCard.tsx",
  "components/sales/FairPriceSuggestCard.tsx",
];

function codeOf(file: string): string {
  return __stripCommentsForScan(readFileSync(resolve(process.cwd(), file), "utf-8"), file);
}

describe("비율 표기 — 정수 반올림이 격차를 지우지 않는다", () => {
  it("★값이 없을 때 '+%'·'+~%' 같은 깨진 표기를 만들지 않는다", () => {
    // #541이 종합분석에서 고친 것과 **완전히 동일한 형태**가 다른 화면 3곳에 남아 있었다.
    // CLAUDE.md 전역 전파방지: 파일 내가 아니라 플랫폼 전역 스윕이 요구된다.
    // ★파생 전수 — 새 화면이 같은 형태를 쓰면 자동으로 걸린다.
    expect(ALL_TSX.length, "모집단이 비었다 — 아래 '위반 0'이 공허해진다").toBeGreaterThan(100);
    const bad: string[] = [];
    for (const f of ALL_TSX) {
      const code = codeOf(f);
      if (/`\+\$\{[^}]*\}%`/.test(code) || /`\+\$\{[^}]*\}~\$\{[^}]*\}%`/.test(code)) bad.push(f);
    }
    expect(bad, `깨진 부호 표기(+%·+~%)가 남아 있다`).toEqual([]);
  });

  it("검사가 공허하지 않다 — 대상 파일이 실제로 공용 포매터를 부른다", () => {
    // 종전 4개는 회귀 하한으로 유지한다(파생 전수가 이들을 덮더라도 명시적으로 잠근다).
    for (const f of SEEDS) {
      expect(codeOf(f), `${f} 가 공용 포매터를 안 쓴다`).toContain("formatPercent");
    }
  });

  it("★비율 필드에 Math.round가 다시 붙지 않는다", () => {
    // ★파생 전수 — 종전에는 손수 나열한 4개만 봐서 CAD 패널 6건을 놓쳤다.
    //
    // ★술어를 **건폐율·용적률**로 좁힌다(위양성 방지). 이 둘만 **법정 한도와 나란히**
    //   읽히므로 반올림이 격차를 지운다 — 실효 79.6% 가 "80%" 가 되어 법정 80% 와 같아 보인다.
    //   넓은 술어(`pct`·`percent` 전부)를 쓰면 **정상 코드를 막는다**. 실측으로 배제한 것들:
    //     · `Math.round((land * far) / 100)`  → **면적(㎡)** 계산
    //     · `Math.round(far / 20)`            → **층수** 추정
    //     · `progress_pct.toFixed(0)`         → 진행률(비교 대상 없음)
    //     · `old30Pct.toFixed(0)% (3/12동)`   → 노후도(**건수 병기**로 격차 보존)
    //     · 바 차트 `w-10` 고정폭 비율        → 소수 1자리가 레이아웃을 깬다
    //   ★"하한을 넘는 등가 표기를 위반으로 신고하면 정상 코드를 막는다"(회귀망 규율 A-6).
    expect(ALL_TSX.length, "모집단이 비었다 — 아래 '위반 0'이 공허해진다").toBeGreaterThan(100);
    const PATTERNS = [
      /Math\.round\([^)]*(?:[Ff]ar|[Bb]cr)[^)]*\)\s*\}?\s*%/g,
      /(?:far|bcr|Far|Bcr)\w*\.toFixed\(0\)\s*\}?\s*%/g,
    ];
    const bad: string[] = [];
    for (const f of ALL_TSX) {
      const code = codeOf(f);
      const hits = PATTERNS.flatMap((re) => code.match(re) ?? []);
      if (hits.length) bad.push(`${f}: ${hits.join(", ")}`);
    }
    expect(bad, "건폐율·용적률에 정수 반올림이 붙어 법정 한도와의 격차가 지워진다").toEqual([]);
  });

  it("★사통맵 필지 상세의 실효/현황 비율 3칸이 포매터를 거친다", () => {
    const code = codeOf(SEEDS[0]);
    for (const field of ["effectiveFarPct", "effectiveBcrPct", "currentFarPct"]) {
      expect(code).toContain(`formatPercent(detailFeature.${field})`);
    }
  });

  it("★부지분석 페이지의 로컬 헬퍼가 자체 규칙을 갖지 않는다", () => {
    const code = codeOf(SEEDS[1]);
    // 로컬 pct가 포매터에 위임하는지 — 자체 문자열 조립으로 되돌아가면 규칙이 두 벌이 된다.
    expect(code).toMatch(/const pct = \([^)]*\): string => formatPercent\(/);
    expect(code).not.toMatch(/const pct = [^;]*Math\.round/);
  });
});
