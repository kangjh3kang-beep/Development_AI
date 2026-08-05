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
