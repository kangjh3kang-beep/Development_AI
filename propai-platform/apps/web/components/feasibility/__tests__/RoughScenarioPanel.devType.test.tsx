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
    const dep = src.slice(src.indexOf("const buildBody"));
    const arr = dep.slice(dep.indexOf("["), dep.indexOf("]") + 1);
    expect(arr).toContain("devTypeOverride");
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

  it("자동 추천을 **끄지 않는다** — 기본 선택지가 빈 값이어야 한다", () => {
    // 기본값이 특정 유형이면 사용자가 고르지 않았는데 유형이 강제된다.
    expect(code()).toMatch(/useState<string>\(\s*""\s*\)/);
  });
});
