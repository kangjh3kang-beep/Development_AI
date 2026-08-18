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

import { SATONG_BOTTOM_BAND_OWNERS, SATONG_UI_Z } from "@/lib/satong-map-z";

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

/**
 * ── P4 부채(2026-08-17 라이브 실측) ──────────────────────────────────────
 *
 * `it.todo` 로 **초록 안에 보이게** 남긴다(§회귀망 C.13 — 커밋 메시지에만 적으면 드러나지 않는다).
 *
 * 【실측】`/ko/precheck` 로그인 후:
 *     지도 클릭      → clickMenu(z470) 열림 · role=dialog 0
 *     레일 버튼 클릭 → clickMenu **여전히 열림** + role=dialog **1**  ← 동시 개방
 *     **ESC 1회**    → **둘 다 닫힘**
 *   (음성대조: ESC 를 더 눌러도 없는 것이 닫히지는 않는다)
 *
 * 【왜 결함인가 — 선언과 산출물이 갈린다】
 *   `SatongMultiMap` 의 ESC 효과는 주석에 *"ESC 단계적 해제 — ①팝오버 닫기 → ②측정 종료 →
 *   ③측정 결과 지우기"* 라고 **선언**한다. 그런데 그 단계는 **그 컴포넌트 안에서만** 성립한다.
 *   `SatongMapShell` 이 레이어·베이스맵 팝오버용 ESC 핸들러를 각각 `document` 에 따로 걸어,
 *   같은 keydown 에 **조율 없이 함께** 발화한다. 사용자는 한 번 눌렀는데 둘이 사라진다.
 *
 * 【고치려면 — 왜 이 PR 범위 밖인가】
 *   "가장 위 표면 하나만 닫는다"를 지키려면 컴포넌트 경계를 넘는 조율이 필요하다.
 *   `event.defaultPrevented` 로 서로 양보시키는 최소 처방은 **등록 순서가 승부를 정해**
 *   z 서열(clickMenu 470 > railPopover 430)과 어긋날 수 있다 — 이 PR 이 방금 없앤
 *   "우연에 기댄 순서"를 ESC 에서 되풀이하는 셈이다. 제대로 하려면 z 를 아는 해제 스택이
 *   필요하고, 그건 3개 컴포넌트를 건드리는 별건이다.
 *
 * 【함께 기각된 것 — 다시 제기되지 않도록 적는다】
 *   인계서 P4 의 나머지 주장은 실측에서 **성립하지 않았다**:
 *   · *"Leaflet 팝업 `popupopen`/`closePopup` 핸들러 0건"* → **낡음**. `#676` 이 배선했다(각 2건).
 *   · *"필지 상세 패널만 ESC 가 없다 = 비대칭 결함"* → **비대칭이 role 을 따른다.**
 *     ESC 가 있는 형제 둘은 `role="dialog"`(ARIA 상 ESC 가 계약)이고, 상세 패널은 role 없는
 *     **비모달 패널**(닫기 버튼 보유)이라 ESC 가 계약 위반이 아니다.
 *   · *"타일실패 오버레이 닫기 전무"* → 그 오버레이는 `tileStatus` 파생이라 **복구 시 자동 소멸**
 *     하고 재시도 버튼을 갖는다. 오류 고지를 사용자가 지울 수 있게 만드는 편이 오히려 위험하다.
 */
/**
 * ★2026-08-18 — 이 부채는 **해소됐다.** `lib/satong-dismiss.ts` 조정기가 z(SSOT rung)로
 *   가장 위 표면 하나만 닫는다. 셸의 레일·베이스맵 ESC 와 지도의 clickMenu ESC 가 모두
 *   그 조정기를 거친다. 잠금은 `lib/__tests__/satong-dismiss.test.ts` 7건이 한다
 *   (특히 **등록 순서를 뒤집어도 z 가 이긴다** — 그게 없으면 "우연히 먼저 등록된 것"과
 *   구분되지 않는다).
 * ★남는 것: 외부 포인터다운 닫힘은 각 표면이 그대로 갖는다(대상 판정이 표면마다 달라
 *   일반화가 이득보다 위험하다). 그건 결함이 아니라 **의도된 범위 한정**이다.
 */
it("ESC 조정기가 배선돼 있다 — 두 컴포넌트가 각자 window 에 걸지 않는다", () => {
  const shell = executable(source());
  expect(shell).toContain("registerDismissible");
  // 종전 형태(자체 keydown 리스너)가 되살아나면 조정이 다시 깨진다.
  expect(
    shell,
    "셸이 ESC 를 다시 자체 리스너로 처리한다 — 조정기를 우회하면 '둘 다 닫힘'이 재발한다",
  ).not.toMatch(/addEventListener\("keydown"/);
});

/**
 * ── P3: 하단 밴드 슬롯 소유권 ─────────────────────────────────────────────
 *
 * SSOT 주석이 *"하단 신규 요소는 도크 flow 에 합류 · **독립 absolute 금지**"* 를 규정하면서
 * 같은 문단에 *"겹침이 **3회 재발**했다"* 고 적는다. **주석은 강제하지 않는다.**
 * → `SATONG_BOTTOM_BAND_OWNERS` 로 옮기고 여기서 **수를 세어** 강제한다.
 *
 * ★이 검사는 겹침을 **없애지 않는다.** 등록되지 않은 새 점유자가 **조용히** 들어오는 것을
 *   막을 뿐이다(알려진 겹침 2건은 사유와 함께 등록돼 있다).
 */
describe("사통맵 하단 밴드 — 점유자는 등록돼야 한다", () => {
  /** 두 컴포넌트에서 하단 밴드를 **독립 absolute** 로 점유하는 줄을 파생한다. */
  const bandOwners = () => {
    const files = [
      join(__dirname, "..", "..", "map", "SatongMultiMap.tsx"),
      SHELL,
    ];
    const hits: string[] = [];
    for (const f of files) {
      for (const line of executable(readFileSync(f, "utf8")).split("\n")) {
        if (!/\babsolute\b/.test(line)) continue;
        if (!/\bbottom-\d/.test(line)) continue;
        hits.push(line.trim().slice(0, 100));
      }
    }
    return hits;
  };

  it("전제: 파생 검사가 실제로 무언가를 찾는다(공허 진리 가드)", () => {
    expect(bandOwners().length, "밴드 점유자를 하나도 못 찾았다 — 검사기가 죽었다").toBeGreaterThan(0);
    expect(SATONG_BOTTOM_BAND_OWNERS.length).toBeGreaterThanOrEqual(2);
  });

  it("★등록되지 않은 밴드 점유자가 없다 — 수가 늘면 등록을 강제한다", () => {
    const found = bandOwners();
    expect(
      found.length,
      `하단 밴드 독립 absolute ${found.length}건 ≠ 등록 ${SATONG_BOTTOM_BAND_OWNERS.length}건.\n` +
        `새 요소를 밴드에 넣었다면 **도크 flow 에 합류**시키거나 ` +
        `SATONG_BOTTOM_BAND_OWNERS 에 사유와 함께 등록하라(주석 레지스트리는 3회 재발을 못 막았다).\n` +
        found.map((f) => `  ${f}`).join("\n"),
    ).toBe(SATONG_BOTTOM_BAND_OWNERS.length);
  });

  it("★등록 항목은 **사유**를 갖는다 — 빈 사유는 허용 목록을 쓰레기통으로 만든다", () => {
    for (const owner of SATONG_BOTTOM_BAND_OWNERS) {
      expect(owner.id.length, "id 가 비었다").toBeGreaterThan(0);
      expect(owner.anchor).toMatch(/bottom-/);
      expect(owner.why.length, `${owner.id}: why 가 너무 짧다 — 왜 flow 에 합류할 수 없는지 적어라`)
        .toBeGreaterThan(30);
    }
  });

  it("★검사기 판별력 — 밴드가 아닌 absolute 는 잡지 않는다(대조군)", () => {
    // "등록 수와 일치"가 참인 이유가 "아무거나 다 잡아서"이면 안 된다.
    const probe = (line: string) =>
      /\babsolute\b/.test(line) && /\bbottom-\d/.test(line);
    expect(probe('className="absolute bottom-16 left-1/2"')).toBe(true);
    expect(probe('className="absolute left-4 top-4"'), "상단 슬롯을 밴드로 오인한다").toBe(false);
    expect(probe('className="relative bottom-16"'), "absolute 가 아닌 것을 잡는다").toBe(false);
  });
});
