import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

/**
 * ★**현장앱 창을 여는 코드는 한 곳뿐이다** — 축은 파일 목록이 아니라
 * **「`window.open` 과 현장앱 창 이름이 같은 파일의 실행 코드에 함께 있는가」**(파생형).
 *
 * ## 축을 이렇게 좁힌 이유 (위양성 실측 2026-09-08)
 *
 * 처음엔 «`window.open` 을 담은 파일은 정의처뿐» 으로 썼다가 **재보니 정상 코드 3개를
 * 막고 있었다** — `DesignGenPanel`·`G2BBidAnalysisModal`·`TerminationCertPanel` 은
 * 문서·PDF 를 여는 **정당한** 사용이다. ★**가드가 정상 코드를 막으면 그것도 결함이다.**
 *
 * 결함 클래스는 «`window.open` 을 쓴다» 가 아니라 **«현장앱 창을 제각각 연다»** 다.
 * 현장앱 창 열기는 팝업 features·차단 폴백·창 이름 **세 조각**이라, 새 소비처가 한 조각만
 * 베껴 가면 그 자리만 조용히 다르게 동작한다(이 저장소가 반복해 데인 형태).
 *
 * ## 주석에 뚫리지 않게
 *
 * 저장소 스트리퍼(`__stripCommentsForScan`)는 **블록 주석만** 걷는다(원문 확인).
 * 줄 주석은 여기서 따로 떨어낸다 — 실제로 `FieldAppAffordance.tsx` 와 `field-app-shell.ts` 는
 * 두 낱말을 **주석에** 담고 있어서, 안 걷으면 **정상 파일 2개를 위반으로 신고**한다.
 * ★그래서 스트리퍼 자신에 **대조군**을 건다(아래 첫 케이스).
 */

const WEB_ROOT = join(__dirname, "..");
const DEFINITION = join("lib", "field-app-launch.ts");
const OPEN = "window.open";
const NAME = "FIELD_APP_WINDOW_NAME";

const SKIP_DIRS = new Set(["node_modules", ".next", "dist", "build", "coverage", "e2e", "public"]);

/** 블록 주석(저장소 도구) + 줄 주석(여기) 을 모두 걷어 **실행되는 줄만** 남긴다. */
function codeOnly(src: string, file: string): string {
  return __stripCommentsForScan(src, file)
    .split("\n")
    .filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*");
    })
    .join("\n");
}

function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      sourceFiles(full, acc);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(name)) continue;
    // 테스트는 window.open 을 **모킹**하므로 당연히 담는다 — 검사 대상이 아니다.
    if (/\.(test|spec)\.tsx?$/.test(name)) continue;
    acc.push(full);
  }
  return acc;
}

const files = sourceFiles(WEB_ROOT);

describe("현장앱 창 열기 — 소비처는 공용 함수를 거친다(파생형 전수)", () => {
  it("★공허 진리 가드 + 스트리퍼 대조군 — 조회기가 살아 있다", () => {
    // ①모집단이 비어 있지 않다. 0이면 아래 "위반 0" 이 무의미하다.
    expect(files.length).toBeGreaterThan(200);

    // ②★스트리퍼가 실제로 주석을 걷는지 **원문으로** 확인한다.
    //   `FieldAppAffordance.tsx` 는 두 낱말 중 window.open 을 **주석에만** 담고 있다.
    const aff = files.find((f) => f.endsWith(join("sales-app", "FieldAppAffordance.tsx")))!;
    const raw = readFileSync(aff, "utf8");
    expect(raw, "전제가 바뀌었다 — 이 파일이 window.open 을 안 담는다").toContain(OPEN);
    expect(
      codeOnly(raw, aff),
      "스트리퍼가 주석을 못 걷는다 — 이 락의 모든 판정이 위양성이 된다",
    ).not.toContain(OPEN);
  });

  it("★대조군 — 정의처는 실행 코드에 둘 다 담고 있다", () => {
    const def = files.find((f) => f.endsWith(DEFINITION));
    expect(def, `정의처를 못 찾았다: ${DEFINITION}`).toBeDefined();
    const code = codeOnly(readFileSync(def!, "utf8"), def!);
    expect(code).toContain(OPEN);
    expect(code).toContain(NAME);
  });

  it("현장앱 창을 여는 실행 코드는 **정의처 하나뿐**이다", () => {
    const offenders = files
      .filter((f) => !f.endsWith(DEFINITION))
      .filter((f) => {
        const code = codeOnly(readFileSync(f, "utf8"), f);
        return code.includes(OPEN) && code.includes(NAME);
      })
      .map((f) => f.slice(WEB_ROOT.length + 1));

    expect(
      offenders,
      `현장앱 창을 직접 여는 파일이 있다 — lib/field-app-launch.ts 의 launchFieldApp 을 쓰라:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });

  it("★정본 상수의 소비처는 정의처와 판별처 둘뿐이다(새 소비처는 이 락을 통과해야 한다)", () => {
    // 여는 쪽과 판별하는 쪽이 **같은 상수**를 써야 문자열 두 벌이 생기지 않는다.
    // 새 파일이 이 상수를 집어 쓰기 시작하면 여기서 드러난다.
    const consumers = files
      .filter((f) => codeOnly(readFileSync(f, "utf8"), f).includes(NAME))
      .map((f) => f.slice(WEB_ROOT.length + 1))
      .sort();

    expect(consumers).toEqual([join("lib", "field-app-launch.ts"), join("lib", "field-app-shell.ts")]);
  });
});
