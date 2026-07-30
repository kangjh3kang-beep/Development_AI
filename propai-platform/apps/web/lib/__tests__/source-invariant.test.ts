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
