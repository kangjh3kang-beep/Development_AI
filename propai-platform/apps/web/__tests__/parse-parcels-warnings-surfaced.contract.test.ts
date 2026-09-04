/**
 * 엑셀 업로드(`/zoning/parse-parcels`)의 **경고는 화면까지 닿아야 한다.**
 *
 * ★왜 계약인가(실측된 사고): 백엔드는 병합셀 복원 실패처럼 "지번이 조용히 빠지는" 사유를
 *   `verification_report.warnings` 에 담아 보낸다. 그런데 소비처가 **둘**인데 한쪽만 렌더했다:
 *     · `SatongMapShell`      — 경고 목록 렌더 ○
 *     · `GlobalAddressSearch` — 응답 **타입에조차 warnings 가 없어** 값이 와도 버려졌다 ✗
 *   `GlobalAddressSearch` 는 신고가 난 `/ko/precheck` 을 포함해 여러 화면에 붙어 있으므로,
 *   그쪽 업로드는 경고를 아무리 잘 만들어도 사용자에게 **한 글자도 보이지 않았다**.
 *   처방을 만들어 놓고 환자의 절반에게 전달하지 않은 셈이다.
 *
 * ★목록이 아니라 **파생**으로 검사한다: 이 엔드포인트를 부르는 파일을 코드에서 찾아 전수
 *   검사한다. 새 업로더가 생겨도 자동으로 감시망에 들어온다(사람이 센 목록 = 상한 금지).
 *
 * ★문자열이 아니라 **구문(AST)** 을 본다: 소스 문자열 검사는 주석·문자열에 뚫린다.
 *   (실제로 이 파일 초안이 "warnings" 라는 낱말이 든 **줄 주석**만으로 통과할 뻔했다.)
 *   주석은 AST 노드를 만들지 못하므로, "warnings 를 map 으로 펼치는 호출식이 있는가"를
 *   구문으로 물으면 주석·문자열 변이가 원리적으로 통하지 않는다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const ROOTS = ["components", "app", "lib"];
const ENDPOINT = "parse-parcels";

/**
 * ★테스트 파일은 **화면이 아니다** — 소비처에서 제외한다.
 *
 * 실측(2026-08-21): `#719` 가 `components/precheck/__tests__/SatongMapShell.excelJibun.test.tsx`
 * 를 추가하자 이 검사가 그것을 **세 번째 업로더로 집어** 빨강이 났다. 테스트 파일은
 * 엔드포인트 문자열을 스텁 분기에 쓰므로 `callsEndpoint` 에 걸리지만, 거기에 경고를 렌더할
 * 화면은 없다. 위양성도 결함이다 — 정상 코드를 막으면 다음 사람은 검사를 끈다.
 */
const TEST_FILE = /(^|[\\/])__tests__[\\/]|\.(test|spec)\.tsx?$/;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "__tests__") continue;
      walk(full, out);
    } else if (/\.tsx?$/.test(name) && !TEST_FILE.test(full)) out.push(full);
  }
  return out;
}

function parse(file: string, src: string) {
  return ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);
}

/** 이 파일이 **코드로** 해당 엔드포인트를 호출하는가(주석 언급은 제외). */
function callsEndpoint(sf: ts.SourceFile): boolean {
  let hit = false;
  const visit = (n: ts.Node) => {
    if (hit) return;
    // 문자열 리터럴은 실제 호출 인자로 쓰이므로 여기서는 리터럴을 본다.
    if (ts.isStringLiteralLike(n) && n.text.includes(ENDPOINT)) hit = true;
    else ts.forEachChild(n, visit);
  };
  ts.forEachChild(sf, visit);
  return hit;
}

/** `(...warnings...).map(...)` 형태의 호출식이 **구문으로** 존재하는가. */
function spreadsWarnings(sf: ts.SourceFile): boolean {
  let hit = false;
  const visit = (n: ts.Node) => {
    if (hit) return;
    if (
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === "map" &&
      /warnings/.test(n.expression.expression.getText(sf))
    ) {
      hit = true;
      return;
    }
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(sf, visit);
  return hit;
}

describe("parse-parcels 업로드 경고의 화면 도달성", () => {
  const root = resolve(process.cwd());
  const callers = ROOTS.flatMap((r) => walk(join(root, r)))
    .map((f) => ({ file: f.slice(root.length + 1), sf: parse(f, readFileSync(f, "utf8")) }))
    .filter(({ sf }) => callsEndpoint(sf));

  it("호출처가 실제로 존재한다(공허한 참 방지)", () => {
    // ★이 하한이 없으면 "위반 0"이 참인 이유가 "대상 0개"일 수 있다.
    //   실측(2026-08-21): SatongMapShell · GlobalAddressSearch 두 곳.
    //   lib/satong-map-layers.ts·lib/pnu.ts 는 주석에서만 언급하므로 구문 검사에서 정상 탈락한다.
    //
    // ★**정확한 개수로 잠그지 않는다.** 이 파일 머리글이 스스로 *"사람이 센 목록 = 상한 금지"*
    //   라고 적어 놓고 `toHaveLength(2)` 로 상한을 걸어, **새 업로더가 생기면 무조건 빨강**이
    //   됐다(실측: #719 의 테스트 파일 1개로 발화). 그래서 **알려진 화면 2곳이 반드시 들어 있다**
    //   (공허한 참 방지) + **새 업로더는 자동으로 아래 전수검사에 들어온다**로 바꾼다.
    //   개수 상한이 아니라 **하한과 포함**이 이 검사가 원하던 것이다.
    const files = callers.map((c) => c.file).sort();
    expect(files).toContain("components/precheck/SatongMapShell.tsx");
    expect(files).toContain("components/common/GlobalAddressSearch.tsx");
    // 테스트 파일이 소비처로 새어 들어오지 않는다(위양성 재발 방지).
    expect(files.filter((f) => /__tests__|\.(test|spec)\.tsx?$/.test(f))).toEqual([]);
  });

  it.each(callers.map((c) => c.file))("%s 는 경고를 화면에 펼친다", (file) => {
    const { sf } = callers.find((c) => c.file === file)!;
    expect(spreadsWarnings(sf)).toBe(true);
  });
});
