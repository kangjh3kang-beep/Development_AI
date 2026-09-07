/**
 * 개발유형 배선 락 — **payload 에 실리는가**(이름이 있는가가 아니라).
 *
 * ## 왜
 *
 * 백엔드 `build_rough_scenario(dev_type=…)` 는 **이미 이 인자를 받는다**
 * (*"미지정 시 Top1 자동 추천"*). 프론트 `buildBody` 가 **안 보냈을 뿐**이고,
 * `sale_price_resolver._exclusive_ratio_for` 독스트링이 *"진짜 처방은 호출부가
 * `dev_type` 을 갖는 것이고, **파이프라인은 아직 못 갖는다**"* 라고 부채로 적어 뒀다.
 *
 * ★이 락은 **소스에 이름이 있는지**를 보지 않는다 — 그건 주석 한 줄로 통과한다.
 *   `buildBody` 가 만드는 **객체를 실제로 만들어** 키의 유무를 본다.
 */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { DEV_TYPE_PRESETS } from "@/lib/dev-type-presets";

const SRC = path.resolve(__dirname, "..", "RoughScenarioPanel.tsx");

/** 실행 라인만 — 주석·JSX 주석에 뚫리지 않게. */
function code(): string {
  return fs
    .readFileSync(SRC, "utf8")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

/**
 * `useCallback` 의 **의존성 배열**만 뽑는다.
 *
 * ★★2026-09-07 자체 적발 — 첫 판은 `indexOf("[")` 로 첫 대괄호를 집었는데,
 *   본문에 구조분해(`([, v]) => …`)가 생기자 **그것을 의존성 배열로 읽었다**.
 *   조회기가 틀린 것을 코드 결함으로 신고할 뻔했다 → **닫는 형태로** 앵커한다.
 */
function buildBodyDeps(src: string): string {
  const from = src.indexOf("const buildBody");
  expect(from, "buildBody 를 찾지 못했다 — 조회기 사망").toBeGreaterThan(-1);
  const tail = src.slice(from);
  // useCallback(…, [deps]); 의 마지막 인자 — `],` 뒤에 닫는 `)` 가 오는 형태.
  const m = tail.match(/\n\s*\[([^\]]*)\],?\s*\n\s*\);/);
  expect(m, "의존성 배열을 찾지 못했다 — 조회기 사망").not.toBeNull();
  return m![1];
}

describe("개발유형 배선", () => {
  it("★스캔이 실제 파일을 읽는다(공허진리 차단)", () => {
    expect(code().length).toBeGreaterThan(5000);
    expect(code()).toContain("buildBody");
  });

  it("payload 에 dev_type 을 **조건부로** 싣는다 — 미선택이면 키 자체가 없다", () => {
    const src = code();
    // ★「없음」을 빈 문자열로 보내면 백엔드가 «지정됐다»로 읽어 Top1 자동추천이 죽는다.
    //   그래서 스프레드 조건부 형태여야 한다(`dev_type: devTypeOverride` 무조건 금지).
    expect(src).toMatch(/\.\.\.\(\s*devTypeOverride\s*\?\s*\{\s*dev_type:\s*devTypeOverride\s*\}/);
    expect(src, "무조건 대입이면 미선택이 빈 문자열로 나간다").not.toMatch(
      /\n\s*dev_type:\s*devTypeOverride\s*,/,
    );
  });

  it("★buildBody 의존성에 devTypeOverride 가 있다 — 없으면 낡은 값이 캡처된다", () => {
    const src = code();
    expect(buildBodyDeps(src)).toContain("devTypeOverride");
  });

  it("선택지는 **정본표에서 파생**된다 — 손 목록이 상한이 되지 않게", () => {
    const src = code();
    expect(src).toContain("DEV_TYPE_PRESETS.map");
    // 손으로 나열한 option 이 섞이면 그 목록이 곧 상한이다.
    const hardcoded = src.match(/<option value="M\d{2}"/g) ?? [];
    expect(hardcoded, `손으로 적은 유형 option 이 있다: ${hardcoded.join(", ")}`).toEqual([]);
    // 정본이 15유형 전수인지(부분집합 표를 쓰면 선택지가 조용히 줄어든다).
    expect(DEV_TYPE_PRESETS.length).toBe(15);
    expect(new Set(DEV_TYPE_PRESETS.map((p) => p.code)).size).toBe(15);
  });

  it("★건축개요 직접입력이 payload 에 **합쳐진다** — null 은 키에서 빠진다", () => {
    const src = code();
    // null 을 그대로 보내면 백엔드 `_num()` 이 0 으로 읽거나 «지정됨»으로 오해한다.
    expect(src).toMatch(/Object\.entries\(briefOv\)\s*\.filter\(\s*\(\[,\s*v\]\)\s*=>\s*v\s*!=\s*null\s*\)/);
    // 기존 overrides 와 **합쳐야** 한다 — 덮으면 2차 수정 패널 값이 사라진다.
    expect(src).toMatch(/\{\s*\.\.\.\(overrides\s*\?\?\s*\{\}\)\s*,\s*\.\.\.brief\s*\}/);
    // 의존성에 briefOv 가 없으면 낡은 값이 캡처된다.
    expect(buildBodyDeps(src)).toContain("briefOv");
  });

  it("★편집 가능/읽기전용의 **경계**가 유지된다", () => {
    const src = code();
    // 파생값(필지 선택의 산출물)은 여기서 덮으면 지도·법규 판정과 갈린다 → 읽기 전용.
    for (const readonlyLabel of ["통합면적", "용도지역", "실효 용적률", "필지 수"]) {
      expect(
        new RegExp(`<Tile\\s+label="${readonlyLabel}"`).test(src),
        `${readonlyLabel} 이 편집 가능해졌다 — 상류 파생값을 하류에서 덮으면 조용히 갈린다`,
      ).toBe(true);
    }
    // 건축개요 축은 편집 가능해야 한다(공허진리 차단 — 위 검사만 있으면 «전부 읽기전용»이 만점).
    for (const editable of ["연면적(GFA)", "분양가능면적", "전용률", "사업기간"]) {
      expect(
        new RegExp(`<EditableTile\\s+[\\s\\S]{0,80}label="${editable.replace(/[()]/g, "\\$&")}"`).test(src),
        `${editable} 이 편집 가능하지 않다`,
      ).toBe(true);
    }
  });

  it("자동 추천을 **끄지 않는다** — 기본 선택지가 빈 값이어야 한다", () => {
    // 기본값이 특정 유형이면 사용자가 고르지 않았는데 유형이 강제된다.
    expect(code()).toMatch(/useState<string>\(\s*""\s*\)/);
  });
});
