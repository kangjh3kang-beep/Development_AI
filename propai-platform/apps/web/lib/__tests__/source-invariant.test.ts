/**
 * 배선 불변식 헬퍼 자체의 계약.
 *
 * ★검증 도구도 적대 검증이 필요하다 — 이번 세션에서 "가드가 잡아야 할 회귀를
 *   false-healthy로 가리는" 사례를 이미 겪었다. 특히 **매치 0건 공허진리**는
 *   이 기법의 대표 실패모드라 반드시 실패해야 한다.
 */
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import ts from "typescript";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { assertWiredThrough, __blockCommentRangesForOracle } from "@/lib/source-invariant";

/**
 * ★독립 오라클 — 구현(스캐너 전수 열거)과 **다른 메커니즘**이어야 의미가 있다.
 * 여기서는 AST 를 **토큰 단위**로 훑는다(`getChildren` 은 `forEachChild` 와 달리
 * `}` `)` 같은 구두점 토큰까지 준다 — R2 가 구현의 미탐을 잡아낸 바로 그 순회).
 * 같은 코드를 두 번 쓰는 게 아니라 **다른 길로 같은 답에 도달하는지**를 본다.
 */
function oracleBlockComments(src: string, fileName: string): Array<[number, number]> {
  const kind = /\.tsx$/.test(fileName) ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(fileName, src, ts.ScriptTarget.Latest, true, kind);
  const jsx: Array<[number, number]> = [];
  const collectJsx = (n: ts.Node): void => {
    if (n.kind === ts.SyntaxKind.JsxText) jsx.push([n.pos, n.end]);
    n.forEachChild(collectJsx);
  };
  collectJsx(sf);
  const inJsx = (p: number): boolean => jsx.some(([s, e]) => p >= s && p < e);

  const seen = new Set<number>();
  const out: Array<[number, number]> = [];
  const take = (rs: readonly ts.CommentRange[] | undefined): void => {
    for (const r of rs ?? []) {
      // ★R3 — 줄 주석까지 등가 대조에 편입한다. 종전엔 블록만 봐서, 줄 주석 쪽
      //   관통(`://` 예외)을 이 테스트가 **구조적으로 못 봤다**.
      if (
        r.kind !== ts.SyntaxKind.MultiLineCommentTrivia &&
        r.kind !== ts.SyntaxKind.SingleLineCommentTrivia
      ) continue;
      if (seen.has(r.pos) || inJsx(r.pos)) continue;
      seen.add(r.pos);
      out.push([r.pos, r.end]);
    }
  };
  const walk = (n: ts.Node): void => {
    const kids = n.getChildren(sf);
    if (kids.length === 0) {
      take(ts.getLeadingCommentRanges(src, n.pos));
      take(ts.getTrailingCommentRanges(src, n.end));
      return;
    }
    for (const k of kids) walk(k);
  };
  walk(sf);
  return out;
}

/** apps/web 기준 절대경로 — 테스트가 `process.chdir` 로 tmp 에 들어가므로 미리 고정한다. */
const WEB_ROOT = process.cwd();
const resolveRepo = (p: string): string => join(WEB_ROOT, p);

function listSources(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name.startsWith(".")) continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) out.push(...listSources(full));
    else if (/\.tsx?$/.test(e.name)) out.push(full);
  }
  return out;
}

let dir: string;
let cwd: string;

function write(name: string, body: string): string {
  writeFileSync(join(dir, name), body, "utf-8");
  return name;
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "srcinv-"));
  cwd = process.cwd();
  process.chdir(dir);
});
afterEach(() => process.chdir(cwd));

describe("assertWiredThrough", () => {
  it("모든 대상 줄이 공용 경로를 거치면 통과한다", () => {
    const f = write("a.ts", [
      'base.on("tileload", () => track(true));',
      'base.on("tileerror", () => track(false));',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 2,
    })).not.toThrow();
  });

  it("★한 줄이라도 우회하면 그 줄을 지목해 실패한다", () => {
    const f = write("b.ts", [
      'base.on("tileload", () => track(true));',
      'base.on("tileerror", () => onTileState("error"));',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 2,
    })).toThrow(/우회한 줄 1건[\s\S]*b\.ts:2/);
  });

  it("★매치 0건이면 반드시 실패한다(공허진리 = 가짜 안전 차단)", () => {
    const f = write("c.ts", "const unrelated = 1;\n");
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 2,
    })).toThrow(/매치 0건 < 최소 2건/);
  });

  it("매치가 최소치에 못 미쳐도 실패한다(스코프 표류 감지)", () => {
    const f = write("d.ts", 'base.on("tileload", () => track(true));\n');
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 4,
    })).toThrow(/매치 1건 < 최소 4건/);
  });

  it("mustNotContain으로 우회 경로를 직접 금지할 수 있다", () => {
    const f = write("e.ts", 'x.on("tileload", () => { track(true); onTileState("ready"); });\n');
    expect(() => assertWiredThrough({
      file: f, scope: /on\("tile/, mustContain: "track(",
      mustNotContain: /onTileState\(/, minMatches: 1,
    })).toThrow(/우회한 줄 1건/);
  });

  // ── 주석 제거 계약 (★R4 리뷰 M-3) ──────────────────────────────────────────
  //
  // 이 도구는 22개 불변식이 의존하는 공용 인프라인데 **주석 제거를 태우는 테스트가 0건**
  // 이었다. 그래서 "여러 줄 JSX 주석으로 렌더를 감싸면 락이 초록"(R4 H-1)이 안 잡혔다.
  // 주석 처리는 이 도구의 **핵심 계약**이므로 직접 잠근다.

  it("줄 끝 `//` 주석은 조건을 충족시키지 못한다", () => {
    const f = write("g.ts", 'const aggregatable = true;  // locatedKeys.has 로 대체 예정\n');
    expect(() => assertWiredThrough({
      file: f, scope: /const aggregatable/, mustContain: "locatedKeys.has", minMatches: 1,
    })).toThrow(/우회한 줄|공용 경로/);
  });

  it("`://`(URL)는 주석으로 오인하지 않는다 — 정상 코드를 위반으로 만들지 않는다", () => {
    const f = write("h.ts", 'const u = "https://x.test/track(";  // 설명\n');
    expect(() => assertWiredThrough({
      file: f, scope: /const u =/, mustContain: "track(", minMatches: 1,
    })).not.toThrow();
  });

  it("★한 줄 JSX 주석은 조건을 충족시키지 못한다", () => {
    const f = write("i.tsx", '{/* TODO: {res.reason} 렌더 복구 예정 */}\n');
    expect(() => assertWiredThrough({
      file: f, scope: /TODO/, mustContain: "res.reason", minMatches: 1,
    })).toThrow(/매치 0건|우회한 줄|공용 경로/);
  });

  it("★★여러 줄 JSX 주석도 조건을 충족시키지 못한다(H-1 회귀락)", () => {
    // 렌더를 통째로 여러 줄 주석에 넣으면 화면은 침묵인데 게이트는 초록이었다.
    // 줄 단위 검사의 한계라 **줄 분할 전에** 파일 수준에서 지워야 잡힌다.
    const f = write("j.tsx", [
      "{/* TODO(정직성): 디자인 검토중이라 잠시 뺀다 — 복구 예정.",
      "      {res.reason ? (",
      "        <p>{res.reason}</p>",
      "      ) : null}",
      "*/}",
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /\{res\.reason\}/, mustContain: "res.reason", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  it("★JSX 주석 제거가 정상 코드를 삼키지 않는다(과도 제거 방지)", () => {
    // `{` + JSDoc `/** */` 조합을 JSX 주석으로 오인해 **44,444자를 삼킨** 실측 사고가 있었다.
    // 여는 쪽 공백을 불허하는 것이 그 방어다.
    const f = write("k.tsx", [
      "interface P {",
      "  /** 단일 필지 선택 콜백 */",
      "  onPick?: () => void;",
      "}",
      "const x = () => { track(true); /* noop */ };",
      'base.on("tileload", () => track(true));',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).not.toThrow();
  });

  it("★★JSX 주석 제거가 사이 코드를 삼키지 않는다(R6 F-B — 이 수정 자체가 무잠금이었다)", () => {
    // ★이 PR 의 **공허한 참 6번째** 형태: 빈 단언이 아니라 **잠기지 않은 수정**.
    //   R5 가 정규식을 `(?:(?!\*\/)[\s\S])*` 로 구조화했는데, 되돌려도 전건 통과했다
    //   (리뷰어 변이 실증). 실효 있는 하드닝이 무보호로 남아 누구든 조용히 되돌릴 수 있었다.
    //
    //   구정규식(`[\s\S]*?`)은 `{/* c */ a: 1 }` 같은 **객체 리터럴**에서 시작해
    //   한참 뒤 `*/}` 까지를 통째로 삼켰다 — R4 에서 44,444자를 날린 그 구조다.
    const f = write("l.tsx", [
      "const o = {/* c */ a: 1 };",
      "base.on(\"tileload\", () => track(true));",
      "const tail = 1; {/* tail */}",
    ].join("\n"));
    // 사이 코드가 살아 있어야 스코프에 걸리고, 걸려야 위반 여부를 판정할 수 있다.
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).not.toThrow();
  });

  // ★R3 — "JSX 주석 40줄 폭주 백스톱"과 그 테스트를 **삭제했다.** 근거를 남긴다:
  //   그 가드는 "정규식이 폭주해 코드를 삼켰다"의 신호를 잡는 것이었는데, 이제 **정규식으로
  //   지우는 코드가 없다**(간극 열거로 대체). raw 소스에서 `{/* */}` 매치의 개행 수만 세므로
  //   스트립이 무엇을 삼켰는지와 **원리적으로 무관**하고, 남은 실효는 한 방향뿐이다 —
  //   락 대상 파일이 41줄 넘는 정당한 JSX 주석을 가지면 그 파일의 모든 락이 **거짓 빨강**.
  //   변이 실측(R3): 가드 호출을 지워도 **자기 자신의 테스트만** 실패했다(자기참조 락).
  //   ★R2 때 "중복이라 걷어냈다"가 거짓이었던 전례가 있어, 이번엔 지우는 이유를 실측으로
  //   댄다 — 지킬 대상이 사라진 가드는 유지가 아니라 **거짓 근거**다.

  it("★닫는 쪽 공백(`*/ }`)도 제거한다 — 안 지우면 주석이 조건을 충족시킨다", () => {
    // R5 가 `\s*` 를 지웠는데 방향이 반대였다(R6 F-D). 주석이 남으면 **주석 처리된 JSX**
    // 위에서 락이 초록이 된다 = R4 H-1 과 같은 계열.
    const f = write("n.tsx", '{/* {res.reason} */ }\n');
    expect(() => assertWiredThrough({
      file: f, scope: /res\.reason/, mustContain: "res.reason", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  // ── 블록 주석 `/* … */` (2026-08-06 실증한 여섯 번째 형태) ────────────────────
  //
  // R3~R6 네 라운드가 이 헬퍼를 다듬었지만 전부 `{/* … */}` 만 봤다. TS/TSX 에서 가장
  // 흔한 평범한 블록 주석은 검토된 적이 없어, **배선을 끊고도 락이 초록**이었다.
  // origin/main 실측: `avmCaveat: payload.avm_caveat` 를 `/* … */` 로 감싸면 통과.

  it("★평범한 한 줄 블록 주석으로 배선을 끊으면 실패한다(= 종전엔 통과했다)", () => {
    const f = write("o.ts", "/* avmCaveat: payload.avm_caveat, */\n");
    expect(() => assertWiredThrough({
      file: f, scope: /avmCaveat:/, mustContain: "avm_caveat", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  it("★여러 줄 블록 주석으로 감싸도 실패한다", () => {
    const f = write("p.ts", ["/*", "avmCaveat: payload.avm_caveat,", "*/"].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /avmCaveat:/, mustContain: "avm_caveat", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  // ★줄끝 주석은 `//` 만 떼어냈다 — 같은 줄에 `/* … */` 로 needle 을 적으면 **우회한 줄이
  //   needle 을 충족시켜** 락이 초록이었다. 종전 구현에서 실제로 통과한다(확인함).
  it("★같은 줄의 블록 주석이 needle 을 대신 충족시키지 못한다", () => {
    const f = write("q.ts", 'base.on("tileload", () => sendDirect(true)); /* track( */\n');
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/우회한 줄 1건/);
  });

  // ★스트립이 과도하면 정상 코드를 삼켜 기준선이 깨진다 — 이 파일이 두 번 데인 실패다.
  //   문자열 리터럴 안의 `/*` 는 주석이 아니므로 **살아 있어야** 한다.
  it("★문자열 안의 `/*` 를 주석으로 오인하지 않는다(과도스코프 방지)", () => {
    const f = write("r.ts", [
      'const glob = "src/*";',
      'base.on("tileload", () => track(true));',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).not.toThrow();
  });

  // ── R1 적대검증이 뚫은 두 형태 (2026-08-07) ───────────────────────────────────
  //
  // 첫 봉합은 따옴표 상태를 **손으로** 추적하는 스캐너였다. 정규식 리터럴 안의 따옴표를
  // 문자열 시작으로 오인해, 그 지점부터 파일 끝까지 스트립이 죽었다 — 872파일 중
  // 따옴표 상태를 오인해 그 지점부터 파일 끝까지 스트립이 죽었다. 리뷰어가 실제 락에서
  // 재현했다. "정규식도 예외 처리"는 또 하나의 목록형이라, 판정을 TS 파서에 넘겼다.

  // ★판별하려면 **주석만이 유일한 매치**여야 한다. 다른 줄이 대신 실패시키면 양쪽 판이
  //   똑같이 빨강이 되어 아무것도 잠그지 못한다(첫 시도에서 실제로 그랬다).
  it("★정규식 리터럴 안의 따옴표가 뒤따르는 블록 주석을 살려두지 않는다", () => {
    const f = write("t.ts", [
      // 손수 스캐너를 오염시킨 실제 형태 — 여는 `'` 뒤로 짝이 없어 EOF 까지 문자열로 오인됐다
      "const clean = (s: string) => s.replace(/'/g, \"\");",
      '/* base.on("tileload", () => track(true)); */',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  it("★템플릿 리터럴 `${}` 안의 블록 주석이 매치 수를 위조하지 못한다", () => {
    const f = write("u.ts", [
      'const t = `x ${ /* base.on("tileload", () => track(true)); */ 1 } y`;',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  // ★과도 스트립의 실패 방향은 **거짓 초록**이다(첫 봉합은 "거짓 빨강이라 안전"이라고
  //   반대로 적었고 R1 이 반증했다). 정상 코드가 지워지면 **위반 줄이 삼켜지고** 남은
  //   정상 줄이 minMatches 를 채워 통과한다. 그 방향을 여기서 직접 태운다.
  it("★정규식 리터럴을 주석으로 오인해 위반 줄을 삼키지 않는다(거짓 초록 방지)", () => {
    const f = write("v.ts", [
      "const re = /[/*]/;",                          // 오인하면 여기서 주석이 열린다
      'base.on("tileload", () => bypass(true));',    // ★위반 줄 — 삼켜지면 안 된다
      "const marker = 0; /* 닫는 지점 */",
      'base.on("tileerror", () => track(false));',   // 정상 줄
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/우회한 줄 1건/);
  });

  // ── R2 적대검증이 뚫은 형태 (2026-08-07) ──────────────────────────────────────
  //
  // 2차 봉합은 AST `forEachChild` 순회였는데, 그건 `}` `)` `]` 같은 **구두점 토큰을
  // 방문하지 않는다**. 그래서 블록·객체·배열·인자목록의 **닫는 괄호 앞 자기 줄 주석**이
  // 전부 살아남았다. R3 재실측(873파일): 오라클 대비 미탐 2,301건/311파일, 그중 "자기 줄
  // 평범 주석"만 109건/50파일 — 어느 쪽이든 옛 손수 스캐너(9파일)보다 훨씬 넓었다.

  it("★객체 리터럴 닫는 괄호 앞 주석이 매치 수를 위조하지 못한다", () => {
    const f = write("w.ts", [
      "const entry = {",
      "  cappedCount: 0,",
      '  /* groups: base.on("tileload", () => track(true)) */',
      "};",
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  it("★블록 끝·빈 블록의 주석도 지워진다", () => {
    const f = write("x.ts", [
      "function f() {",
      '  /* base.on("tileload", () => track(true)); */',
      "}",
      "const empty = () => {",
      '  /* base.on("tileerror", () => track(false)); */',
      "};",
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  // ★★형태를 세는 것으로는 끝나지 않는다 — 네 라운드 모두 "다음 형태"로 뚫렸다.
  //   그래서 **구현과 다른 메커니즘**(AST 토큰 순회)으로 같은 답이 나오는지를 잠근다.
  //   구현이 어떤 형태를 놓치기 시작하면 형태를 몰라도 여기서 터진다.
  it("★★구현이 찾는 블록 주석 = 독립 오라클(AST 토큰 순회)이 찾는 것 — 저장소 전수(app·components·hooks·lib)", () => {
    const roots = ["app", "components", "hooks", "lib"].map(resolveRepo);
    const files = roots.flatMap((r) => listSources(r));
    // 공허 진리 방지 — 하한을 실측(873)에 붙인다. 헐거우면 한 디렉토리가 통째로
    // 빠져도 통과한다(종전 하한 300 은 lib+hooks 197 이 빠져도 못 잡았다).
    expect(files.length).toBeGreaterThan(800);

    const mismatched: string[] = [];
    for (const abs of files) {
      const src = readFileSync(abs, "utf-8");
      const mine = new Set(
        __blockCommentRangesForOracle(src, abs).map(([a, b]) => `${a}:${b}`),
      );
      const oracle = new Set(oracleBlockComments(src, abs).map(([a, b]) => `${a}:${b}`));
      const missed = [...oracle].filter((k) => !mine.has(k));   // 미탐 = 거짓 초록
      const extra = [...mine].filter((k) => !oracle.has(k));    // 오탐 = 위반 줄 삼킴
      if (missed.length || extra.length) {
        mismatched.push(`${abs}: 미탐 ${missed.length} · 오탐 ${extra.length}`);
      }
    }
    expect(mismatched).toEqual([]);
    // ★기본 10s 로는 **단독 실행에선 통과하고 전수에선 실패**한다(병렬 부하에서 6s→14s).
    //   그런 테스트는 없느니만 못하므로 넉넉히 준다. 실제 비용은 1회 6초대다.
  }, 60_000);

  // ── R3 적대검증이 뚫은 형태 + 무잠금 수정 3건 (2026-08-07) ────────────────────
  //
  // 블록 주석은 막혔는데 **같은 함수의 다른 절반**(줄 주석)이 열려 있었다. 종전
  // `stripLineComment` 은 `(^|[^:])//` 라 **`:` 바로 앞의 `//` 를 주석으로 안 봤다**.
  // TS 에서 `:` 직후 줄바꿈은 타입 주석·삼항 else·객체 속성 어디서나 합법이므로,
  // `X://needle` 로 쓰면 주석 속 needle 이 `mustContain` 을 충족시킨다.
  // R3 가 이 형태로 실제 락 2개를 **tsc·eslint 클린 상태로** 초록으로 만들었다.

  it("★`://` 앞이라도 줄 주석은 조건을 충족시키지 못한다(다섯 번째 관통구)", () => {
    // R3 익스플로잇의 실제 형태 — 삼항 else 의 `:` 뒤에 붙인다(문법상 완전히 합법).
    const f = write("y.ts", [
      "const groups = flag ? localRebuild(cat) ://selectMappableGroups",
      "  [];",
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /const groups/, mustContain: "selectMappableGroups", minMatches: 1,
    })).toThrow(/우회한 줄|매치 0건/);
  });

  it("★`.ts` 를 TSX 로 읽지 않는다 — 제네릭 화살표가 JSX 로 오독되면 뒤가 다 어긋난다", () => {
    const f = write("z.ts", [
      // ★`<T,>` 는 TSX 에서도 합법이라 판별하지 못한다(첫 픽스처가 그래서 생존했다).
      //   TSX 가 **JSX 로 오독하는** 레거시 타입 단언을 써야 갈린다.
      "const n = <number>raw;",
      '/* base.on("tileload", () => track(true)); */',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/매치 0건/);
  });

  it("★파스가 깨진 파일은 조용히 통과시키지 않고 시끄럽게 실패한다", () => {
    const f = write("bad.ts", "const a = ;\nbase.on(\n");
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on/, mustContain: "track(", minMatches: 1,
    })).toThrow(/파싱에 실패했다/);
  });

  it("스코프 밖 줄은 검사하지 않는다(과도한 불변식이 정상 코드를 깨뜨리지 않게)", () => {
    const f = write("f.ts", [
      'base.on("tileload", () => track(true));',
      // WMS 오버레이는 각자 노트 콜백을 쓰는 게 정상 — 스코프 밖이어야 한다
      'wmsTile.on("tileerror", () => setRegulationNote("실패"));',
    ].join("\n"));
    expect(() => assertWiredThrough({
      file: f, scope: /^\s*base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).not.toThrow();
  });
});
