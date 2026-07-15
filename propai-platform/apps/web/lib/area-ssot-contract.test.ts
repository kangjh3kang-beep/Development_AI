import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * 면적 SSOT 계약 게이트 — "다필지 면적은 effectiveLandAreaSqm 으로만 읽는다".
 *
 * ■ 무엇을 막는가 (실제 발생한 버그)
 *   store 의 siteAnalysis 에는 면적이 두 개 있다:
 *     landAreaSqm       — 대표/단일 분석이 덮어쓰기도 하고, 이전 필지구성의 잔류값이 남기도 한다
 *     landAreaSqmTotal  — 다필지 통합면적(한 곳에서만 기록되어 안정적)
 *   raw 로 landAreaSqm 을 읽으면 다필지에서 통합면적과 갈린다. 실제로 /ko/permits 에서
 *   ContextHeader(=effectiveLandAreaSqm)는 3,059㎡ 를, 같은 화면의 요약 카드(=raw)는
 *   11,465㎡ 를 표시해 사용자가 어느 숫자도 믿을 수 없는 상태가 됐다.
 *   effectiveLandAreaSqm 은 "다필지면 통합 우선"이라는 규칙을 한 곳에 담은 SSOT 다.
 *
 * ■ 규칙
 *   컨텍스트 store 의 siteAnalysis 에서 면적을 꺼낼 때는 effectiveLandAreaSqm(sa) 를 쓴다.
 *   불가피하게 raw 가 필요하면(예: 대표필지 면적을 일부러 쓰는 경우) 해당 라인에
 *   `@area-ssot-ignore` 주석으로 사유를 남긴다.
 *
 * ■ 한계(정직 고지 — 이 게이트는 증명이 아니라 트립와이어다)
 *   정규식은 소스 식별자(siteAnalysis·sa·s.siteAnalysis·input.siteAnalysis 등)에서 .landAreaSqm 을
 *   직접 꺼내는 라인만 본다. 다음은 원리적으로 못 잡는다:
 *     - 별칭 우회: `const site = s.siteAnalysis` 후 `site.landAreaSqm` (site 는 임의 변수명)
 *     - 구조분해: `const { landAreaSqm } = sa`
 *     - prop 전달: `<Card landAreaSqm={sa.landAreaSqm} />` (JSX 속성)
 *     - ??-폴백 속성값: `key: sa?.landAreaSqm ?? null` — `??` 를 존재확인으로 보고 제외하므로
 *       놓친다. 이건 workspace-extended-panels.ts:90 원버그의 정확한 형태라, 재도입은 이 게이트가
 *       아니라 코드리뷰가 막아야 한다(존재확인 오탐과 트레이드오프 — 정확도 우선 결정).
 *   이 경로들은 코드리뷰가 커버한다. 게이트는 '직접 raw 읽기'라는 가장 흔한 재발 형태를 막는다.
 */

const WEB_ROOT = join(__dirname, "..");
// lib·hooks·store 도 스캔한다 — raw 유출은 매핑/훅 계층에서도 일어난다(실측: workspace-extended-panels).
const SCAN_DIRS = ["components", "app", "lib", "hooks", "store"];
// SSOT 정의 파일 자신·store 정의는 raw 를 다룰 수밖에 없어 제외(정의처는 계약의 예외).
const EXCLUDE_FILES = new Set(["lib/site-area.ts", "store/useProjectContextStore.ts"]);

// ■ 정조준: "raw 면적이 값으로 흘러나가는" 지점만 잡고, 존재 확인은 제외한다.
//   존재 확인(`(sa?.landAreaSqm ?? 0) > 0`·`!= null`·의존성 배열 `sa?.landAreaSqm]`)은 raw 로도
//   무해하다 — 전부 잡으면 과다발화해 아무도 게이트를 안 본다(정확도가 게이트의 생명).
//   ※ optional chaining(?.)·non-null 단언(!)을 모두 허용(`sa!.landAreaSqm!` 형태가 실제로 쓰임).
const SRC = String.raw`(?:siteAnalysis|sa|curSA|analysisCtx|s\.siteAnalysis|input\.siteAnalysis|ctx\.siteAnalysis)`;
const SA = String.raw`${SRC}\s*[!?]?\s*\.\s*landAreaSqm\s*!?`;

// (1) 소비 지점 — 표시·문자열화·산술·포맷/래핑 함수 인자.
const CONSUME = [
  `${SA}\\s*\\)?\\s*\\.(?:toLocaleString|toFixed|toString)\\(`, // sa.landAreaSqm.toLocaleString()
  // 함수 첫 인자로 raw 를 넘기는 모든 호출 — Number()·Math.round()·num()·formatArea() 등 래핑을
  //   통틀어 잡는다(래핑돼도 raw 값을 꺼내 쓰는 것은 동일한 유출이다).
  //   ★제어흐름 키워드(if/while/for/switch/return/catch)는 함수호출이 아니라 존재확인 가드라 제외 —
  //     `if (sa.landAreaSqm != null)` 를 함수호출로 오인해 거짓 실패하면 게이트 신뢰가 무너진다.
  `\\b(?!(?:if|while|for|switch|return|catch|typeof)\\b)[A-Za-z_]\\w*\\s*\\(\\s*${SA}`,
  `${SA}\\s*[*/]\\s*[A-Za-z0-9_.(]`, // 산술(곱·나눗셈): sa.landAreaSqm / PYEONG_SQM
  `\\$\\{[^}]*${SA}`, // 템플릿 리터럴: \`${sa.landAreaSqm}㎡\`
].join("|");

// (2) ★대입/바인딩 지점 — 리뷰어 지적의 핵심. 코드는 흔히 `const x = sa.landAreaSqm` 로 별칭에
//     담고 그 별칭을 소비한다. 소비만 검사하면 이 바인딩(진짜 방어선)을 못 본다.
//     - `= sa.landAreaSqm` 뒤에 존재확인 연산자(??·비교·]·)가 오면 제외(그건 guard).
//     - 객체 속성값 `key: sa.landAreaSqm` (raw 를 다른 객체/바디로 실어보냄).
const ASSIGN = [
  // const/let/var x = sa.landAreaSqm  (뒤가 존재확인이 아니어야 함)
  `[=]\\s*${SA}\\s*(?![!?=<>]|\\s*(?:\\?\\?|!=|==|>=|<=|[<>)\\]]))`,
  // 속성값: identifier: sa.landAreaSqm  (뒤가 존재확인이 아니어야 함)
  `[A-Za-z_]\\w*\\s*:\\s*${SA}\\s*(?![!?=<>]|\\s*(?:\\?\\?|!=|==|>=|<=|[<>)\\]]))`,
].join("|");

const RAW_READ = new RegExp(`${CONSUME}|${ASSIGN}`);
// 면제: 명시적 사유 주석
const IGNORE = /@area-ssot-ignore/;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === "node_modules" || name === "__tests__") continue;
      out.push(...walk(p));
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(p);
    }
  }
  return out;
}

describe("면적 SSOT 계약 — 다필지 면적은 effectiveLandAreaSqm 으로만 읽는다", () => {
  it("컨텍스트 siteAnalysis 의 landAreaSqm 을 raw 로 읽는 곳이 없다", () => {
    const violations: string[] = [];

    for (const dir of SCAN_DIRS) {
      for (const file of walk(join(WEB_ROOT, dir))) {
        const rel = file.replace(WEB_ROOT + "/", "");
        if (EXCLUDE_FILES.has(rel)) continue;
        const lines = readFileSync(file, "utf-8").split("\n");
        lines.forEach((line, i) => {
          if (!RAW_READ.test(line)) return;
          if (IGNORE.test(line)) return;
          // 바로 위 주석 블록(연속된 // 라인)에 면제가 있으면 허용 — 사유를 여러 줄로 적는 게 보통이다.
          for (let k = i - 1; k >= 0; k--) {
            const above = lines[k].trim();
            if (!above.startsWith("//")) break; // 주석 블록이 끊기면 중단
            if (IGNORE.test(above)) return;
          }
          violations.push(`${file.replace(WEB_ROOT + "/", "")}:${i + 1}\n    ${line.trim()}`);
        });
      }
    }

    expect(
      violations,
      `\n다필지 면적은 effectiveLandAreaSqm(sa) 로 읽어야 합니다(raw 금지).\n` +
        `대표필지 면적을 의도적으로 쓰는 경우에만 해당 라인에 @area-ssot-ignore 주석으로 사유를 남기세요.\n\n` +
        violations.join("\n") +
        "\n",
    ).toEqual([]);
  });
});
