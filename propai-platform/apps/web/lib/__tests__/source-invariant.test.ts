/**
 * 배선 불변식 헬퍼 자체의 계약.
 *
 * ★검증 도구도 적대 검증이 필요하다 — 이번 세션에서 "가드가 잡아야 할 회귀를
 *   false-healthy로 가리는" 사례를 이미 겪었다. 특히 **매치 0건 공허진리**는
 *   이 기법의 대표 실패모드라 반드시 실패해야 한다.
 */
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { assertWiredThrough } from "@/lib/source-invariant";

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

  it("★JSX 주석이 40줄을 넘으면 큰 실패로 알린다(정규식 회귀 백스톱)", () => {
    const body = Array.from({ length: 45 }, (_, i) => `   설명 ${i}`).join("\n");
    const f = write("m.tsx", `{/* ${body} */}\nbase.on("tileload", () => track(true));\n`);
    expect(() => assertWiredThrough({
      file: f, scope: /base\.on\("tile/, mustContain: "track(", minMatches: 1,
    })).toThrow(/상한 40/);
  });

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
  // 146파일(16.7%)에 오염 구간이 생겼고, 리뷰어가 실제 락에서 배선을 죽이고도 전수 초록을
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
