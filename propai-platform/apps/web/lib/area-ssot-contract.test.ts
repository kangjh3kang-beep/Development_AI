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
 */

const WEB_ROOT = join(__dirname, "..");
const SCAN_DIRS = ["components", "app"];

// ■ 정조준: "raw 면적을 값으로 소비"하는 곳만 잡는다.
//   존재 확인(`(sa?.landAreaSqm ?? 0) > 0`·`!= null`·의존성 배열)은 raw 로도 무해하므로 제외한다 —
//   전부 잡으면 게이트가 과다발화해 아무도 안 보게 된다(정확도가 게이트의 생명).
//   값 소비 = 화면 표시(toLocaleString)·문자열화(String())·산술. 이 클래스가 실제 버그였다.
//   ※ optional chaining(?.)과 non-null 단언(!)을 모두 허용해야 한다 —
//     `siteAnalysis!.landAreaSqm!.toLocaleString()` 같은 형태가 실제로 쓰인다(초기 게이트가 놓쳤던 구멍).
const SA = String.raw`(?:siteAnalysis|sa|curSA|analysisCtx)\s*[!?]?\s*\.\s*landAreaSqm\s*!?`;
const RAW_READ = new RegExp(
  [
    `${SA}\\s*\\)?\\s*\\.toLocaleString\\(`, // 표시: sa.landAreaSqm.toLocaleString()
    `String\\(\\s*${SA}`, // 문자열화: String(sa.landAreaSqm)
    `${SA}\\s*[/*+-]\\s*[A-Za-z0-9_.(]`, // 산술: sa.landAreaSqm / PYEONG_SQM 등
  ].join("|"),
);
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
