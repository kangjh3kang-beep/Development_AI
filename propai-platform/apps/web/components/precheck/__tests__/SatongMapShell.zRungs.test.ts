/**
 * 사통맵 셸 **z rung 결속** 락 — "옳은 순서가 우연히 나오는" 상태를 끝낸다.
 *
 * ## 무엇이 문제였나 (2026-08-17 라이브 실측)
 *
 * 레이어 레일이 `z-[420]` 하드코딩이었고 그건 `SATONG_UI_Z.tileFailure` 와 **동률**이었다.
 * 화면 결과는 옳았다 — 타일실패 스크림이 레일 **위**로 그려졌고, 그건 `SATONG_POPUP_YIELD`
 * 가 선언한 분류(스크림 = **불양보**(오류 고지) · 레일 = **양보**(상시 크롬))와 일치한다.
 *
 * **문제는 그 옳은 순서가 값이 아니라 DOM 순서에서 나왔다는 것이다.** 셸에서 레일이
 * `<SatongMultiMap>` 보다 앞에 있고 z 가 같아서 나중 것이 이겼을 뿐이다 —
 * JSX 순서를 바꾸는 무해해 보이는 리팩토링 하나로 **조용히 뒤집힌다.**
 *
 * 라이브 실측(대조군 포함): 레일 rect 128×402 가 스크림 `inset-0` 과 겹치고, 동률에서
 * 스크림이 이겼다(양성대조 z=421 → 스크림 승 · 음성대조 z=419 → 레일 승).
 * 지도 래퍼는 `relative`(z 없음)라 스택 컨텍스트를 만들지 않아 둘은 같은 층에서 경쟁한다.
 *
 * ## ★이 결함은 `elementFromPoint` 로 잡을 수 없다 (방법론의 사각)
 *
 * 스크림은 `pointer-events:none` 이라 히트테스트에서 **투명하다**. `§회귀망 D.18`("z 결함은
 * 좌표가 아니라 페인트 순서로 판정하라")의 표준 도구가 이 부류에는 눈이 먼다.
 * 위 라이브 판정도 같은 부모·같은 z 에 pointer-events 를 켠 **대리 스크림**을 심어
 * 쌓임만 갈라 낸 것이다. → 그래서 여기서는 **값의 순서를 직접 잠근다.**
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { SATONG_UI_Z } from "@/lib/satong-map-z";

const SHELL = join(__dirname, "..", "SatongMapShell.tsx");
const source = () => readFileSync(SHELL, "utf8");

/** 주석·JSX 주석을 걷어낸 **실행되는 줄**만 본다 — 소스 검사가 주석에 뚫린 사고가 반복됐다(§A.3). */
const executable = (src: string) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !/^\s*\/\//.test(l))
    .join("\n");

describe("사통맵 셸 — z rung 이 값으로 선언된다", () => {
  it("전제: 셸 소스를 실제로 읽었다(공허 진리 가드)", () => {
    const code = executable(source());
    expect(code.length).toBeGreaterThan(50_000);
    expect(code).toContain("SatongMapShell"); // 양성대조 — 조회기 생존
    expect(code).not.toContain("zzz-absent-sentinel"); // 음성대조
  });

  it("★레일은 타일실패 스크림보다 **아래임이 값으로** 선언된다 — DOM 순서에 기대지 않는다", () => {
    expect(SATONG_UI_Z.layerRail).toBeLessThan(SATONG_UI_Z.tileFailure);
    // 동률이면 승부가 DOM 순서로 떨어진다 — 그게 종전 상태였다.
    expect(
      SATONG_UI_Z.layerRail,
      "레일과 타일실패가 같은 값이면 순서가 선언되지 않은 것이다(DOM 순서가 결정한다).",
    ).not.toBe(SATONG_UI_Z.tileFailure);
    // 코너 도크보다는 위여야 종전 화면이 보존된다(동작 보존 확인).
    expect(SATONG_UI_Z.layerRail).toBeGreaterThan(SATONG_UI_Z.cornerDock);
  });

  it("★rung 값이 서로 중복되지 않는다 — 중복은 곧 '우연에 맡긴 순서'다", () => {
    const entries = Object.entries(SATONG_UI_Z);
    const seen = new Map<number, string>();
    const dups: string[] = [];
    for (const [name, value] of entries) {
      const prev = seen.get(value);
      if (prev) dups.push(`${prev} = ${name} = ${value}`);
      else seen.set(value, name);
    }
    expect(entries.length, "SATONG_UI_Z 가 비었다 — 검사기가 죽었다").toBeGreaterThanOrEqual(8);
    expect(dups, `동률 rung: ${dups.join(" · ")} — 동률이면 DOM 순서가 승부를 정한다`).toEqual([]);
  });

  it("★셸이 레일·배지행 z 를 하드코딩하지 않고 SSOT 상수를 쓴다", () => {
    const code = executable(source());
    expect(code, "셸이 SSOT 를 import 하지 않는다").toContain("SATONG_UI_Z");
    expect(code).toContain("zIndex: SATONG_UI_Z.layerRail");
    expect(code).toContain("zIndex: SATONG_UI_Z.badgeRow");
    // 종전 하드코딩이 남아 있으면 상수는 장식이 된다(§A.5 — 계약 상수는 결속시킨다).
    expect(code, "레일의 z-[420] 하드코딩이 남아 있다").not.toMatch(/z-\[420\]/);
    expect(code, "배지행의 z-[380] 하드코딩이 남아 있다").not.toMatch(/z-\[380\]/);
  });

  it("[부채 결속] 아직 클래스로 남은 z-[430] 은 상수와 **같은 값**이어야 한다", () => {
    // ★정직: 레일 팝오버 3종은 여전히 `z-[430]` 클래스다. 기존 테스트
    //   (SatongMapShell.railPopoverAnchor.test.tsx)가 그 리터럴을 앵커로 쓰고 있어
    //   이번 범위에서 바꾸지 않았다. 대신 **값이 갈라지는 것**만 막는다 —
    //   상수만 바꾸고 클래스를 안 바꾸면(또는 반대) 조용히 어긋난다.
    const code = executable(source());
    const hits = code.match(/z-\[430\]/g) ?? [];
    expect(hits.length, "z-[430] 팝오버가 사라졌다면 이 부채 결속을 갱신할 것").toBe(3);
    expect(SATONG_UI_Z.railPopover).toBe(430);
    expect(SATONG_UI_Z.railPopover).toBeGreaterThan(SATONG_UI_Z.tileFailure);
  });

  it("★검사기 판별력 — executable() 이 주석을 실제로 걷어내는가(대조군)", () => {
    // "하드코딩 0건"이 참인 이유가 "전처리가 다 지워서"일 수 있다.
    expect(executable("// z-[420] 주석\nconst a = 1;")).not.toContain("z-[420]");
    expect(executable("/* z-[420] 블록 */\nconst a = 1;")).not.toContain("z-[420]");
    expect(executable('const c = "z-[420]";'), "실행 줄까지 지우면 검사가 공허해진다").toContain(
      "z-[420]",
    );
  });
});
