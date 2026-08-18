/**
 * P2 매입전략 — 프론트 사업방식 목록이 **백엔드 정본과 어긋나지 않게** 잠근다.
 *
 * 【왜 필요한가】사용자가 고른 사업방식이 상류에서 미등록으로 떨어지면
 * `governing_act=null` 이 되어 **전건 판정보류**가 나온다. 화면은 정상처럼 동작하고
 * 결과만 전부 "판정보류" 라서 **조용한 실패**다. 오타 하나·개명 하나로 그렇게 된다.
 *
 * 【파생의 축】프론트 목록은 손으로 고른 **부분집합**이지만(매입전략 판정이 의미 있는 방식만),
 * 검사 대상인 백엔드 키는 `scenario_simulator.py` 의 `_SCHEME_LEGAL_KEYS` 에서 **파생**한다.
 * 즉 "내가 고른 9개"가 아니라 **"정본이 무엇이든 그 안에 있어야 한다"** 를 단언한다.
 *
 * 【상한도 함께】`MAX_STRATEGY_PARCELS` 는 백엔드 `MAX_BULK_ITEMS` 와 같은 값이어야 한다.
 * 어긋나면 프론트가 통과시킨 요청을 상류가 422 로 거부한다(사용자에겐 원인 불명의 실패).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { MAX_STRATEGY_PARCELS, STRATEGY_SCHEMES } from "@/components/operations/ParcelPurchaseStrategyPanel";

const API_ROOT = join(__dirname, "..", "..", "..", "api");

function readApi(rel: string): string {
  return readFileSync(join(API_ROOT, rel), "utf8");
}

/** 백엔드 정본에서 사업방식 키를 **파생**한다(손으로 옮겨 적지 않는다). */
function backendSchemes(): string[] {
  const src = readApi("app/services/development/scenario_simulator.py");
  const block = /_SCHEME_LEGAL_KEYS:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{([\s\S]*?)\n\}/.exec(src);
  if (!block) return [];
  return [...block[1].matchAll(/^\s*"([^"]+)"\s*:/gm)].map((m) => m[1]);
}

describe("P2 사업방식 — 프론트 목록이 백엔드 정본의 부분집합이다", () => {
  const backend = backendSchemes();

  it("전제: 백엔드 정본을 실제로 읽어냈다(공허한 초록 방지)", () => {
    // ★파싱이 깨지면 backend=[] 가 되고 아래 단언이 **전부 위반**으로 시끄럽게 죽는다.
    //   반대로 여기서 멈추지 않으면 "부분집합"이 공허하게 참이 될 수 있으므로 하한을 건다.
    expect(
      backend.length,
      "scenario_simulator._SCHEME_LEGAL_KEYS 파싱 실패 — 조회기가 죽었다",
    ).toBeGreaterThan(10);
    expect(STRATEGY_SCHEMES.length, "프론트 목록이 비었다").toBeGreaterThan(0);
  });

  it("★프론트가 제시하는 방식은 전부 백엔드에 등록돼 있다", () => {
    const missing = STRATEGY_SCHEMES.filter((s) => !backend.includes(s));
    expect(
      missing,
      `백엔드에 없는 사업방식을 제시한다 — 고르면 전건 판정보류가 된다:\n${missing.join("\n")}`,
    ).toEqual([]);
  });

  it("대조군: 존재하지 않는 방식은 실제로 걸린다(락이 무엇이든 통과시키지 않는다)", () => {
    // ★이 대조군이 없으면 위 단언은 "backend 가 전부를 포함한다"로도 통과할 수 있다.
    expect(backend.includes("존재하지않는사업방식XYZ")).toBe(false);
  });

  it("★필지 상한이 백엔드와 같다", () => {
    const src = readApi("routers/registry.py");
    const m = /^MAX_BULK_ITEMS\s*=\s*(\d+)/m.exec(src);
    expect(m, "MAX_BULK_ITEMS 를 못 찾았다 — 조회기가 죽었다").not.toBeNull();
    expect(
      MAX_STRATEGY_PARCELS,
      "프론트 상한이 백엔드와 다르다 — 통과시킨 요청을 상류가 422 로 거부한다",
    ).toBe(Number(m?.[1]));
  });
});
