/**
 * 수지 수동값 보호 — **행위**를 태운다.
 *
 * ## 무엇이 있었나 (2026-08-26 실측)
 *
 * `ProvenanceModule` 에 `feasibility` 가 **없었다**(`siteAnalysis|cost|design|tax|esg`).
 * 그래서 백엔드 파이프라인 재실행(`ProjectPipelinePanel` → `updateFeasibilityData`)이
 * **사용자가 손으로 넣은 수지값을 조용히 덮었다.** 보호되던 것은 `equityWon` 하나뿐이고
 * 그것도 provenance 가 아니라 `equityIsManual` 이라는 **전용 플래그**였다.
 * 노드 레지스트리는 이 사실을 `provenanceGuarded: false` 로 정직하게 적어 두고 있었다 —
 * **알고 있었는데 잠그지 않았다.**
 *
 * ## ★두 모집단을 가른다
 *
 * *"사용자 값이 남는다"* 만 단언하면 **아무것도 갱신하지 않는 구현**도 통과한다.
 * 같은 실행에서 *"자동값은 실제로 갱신된다"* 를 함께 잠근다.
 *
 * ## ★소스가 아니라 행위
 *
 * `ProvenanceModule` 에 문자열이 있는지 보는 것은 *"부른다"* 를 잠그는 것이다.
 * 여기서는 스토어를 **실제로 돌려** 값이 남는지 본다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/** 워크스페이스 상대 소스를 주석 걷어 읽는다(형제 락과 같은 공용 헬퍼 경유). */
const readSrc = (rel: string) =>
  __stripCommentsForScan(readFileSync(resolve(__dirname, "../..", rel), "utf8"), rel);

const reset = () =>
  useProjectContextStore.setState({ feasibilityData: null, manualFields: {} } as never);

const feas = () =>
  (useProjectContextStore.getState().feasibilityData ?? {}) as Record<string, unknown>;

beforeEach(reset);

describe("수지 수동값 보호 — 행위", () => {
  it("★전제: 자동 경로가 실제로 값을 쓴다(공허한 초록 방지)", () => {
    useProjectContextStore.getState().updateFeasibilityData(
      { totalCostWon: 1_000 } as never,
      { source: "auto" },
    );
    expect(feas().totalCostWon).toBe(1_000);
  });

  it("★★사용자가 넣은 값은 **자동 재실행에 안 덮인다**", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData({ totalCostWon: 111 } as never, { source: "user" });
    // 파이프라인 재실행이 같은 키를 자동으로 덮으려 한다
    s().updateFeasibilityData({ totalCostWon: 999 } as never, { source: "auto" });
    expect(feas().totalCostWon, "★사용자 수지값이 자동 경로에 덮였다 — 데이터 손실").toBe(111);
  });

  it("★음성 대조군 — **자동값은 갱신된다**(아무것도 안 바꾸는 구현과 구별)", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData({ totalCostWon: 111 } as never, { source: "auto" });
    s().updateFeasibilityData({ totalCostWon: 999 } as never, { source: "auto" });
    expect(feas().totalCostWon, "자동값이 갱신되지 않는다 — 가드가 과하다").toBe(999);
  });

  it("사용자가 **직접** 다시 고치는 것은 막지 않는다", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData({ totalCostWon: 111 } as never, { source: "user" });
    s().updateFeasibilityData({ totalCostWon: 222 } as never, { source: "user" });
    expect(feas().totalCostWon).toBe(222);
  });

  it("★플래그 안 걸린 키는 자동 갱신이 그대로 통과한다(과잉 보호 방지)", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData({ totalCostWon: 111 } as never, { source: "user" });
    s().updateFeasibilityData(
      { totalCostWon: 999, totalRevenueWon: 777 } as never,
      { source: "auto" },
    );
    expect(feas().totalCostWon, "보호 대상이 덮였다").toBe(111);
    expect(feas().totalRevenueWon, "★비보호 키까지 막혔다 — 위양성").toBe(777);
  });

  it("기본값은 auto — meta 없이 부르면 종전 동작(무회귀)", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData({ totalCostWon: 111 } as never);
    s().updateFeasibilityData({ totalCostWon: 999 } as never);
    expect(feas().totalCostWon, "meta 없는 호출이 종전과 달라졌다").toBe(999);
  });

  it("★`equityWon` 전용 플래그는 그대로 살아 있다(기존 계약 무회귀)", () => {
    const s = () => useProjectContextStore.getState();
    s().updateFeasibilityData(
      { totalCostWon: 1_000_000, equityWon: 500_000, equityIsManual: true } as never,
      { source: "auto" },
    );
    expect(feas().equityWon, "equityIsManual 보존 계약이 깨졌다").toBe(500_000);
  });
});

// ─────────────────────────────────────────────────────────────────────────
// ★생산자 배선 — **테스트가 스스로 생산자 역할을 하지 않게**
//
// 적대 리뷰가 짚은 것: 위 케이스들은 `{source:"user"}` 를 **테스트가 직접** 부른다.
// 그런데 프로덕션 호출부 **7곳 중 `meta` 를 주는 곳이 0곳**이었다 →
// `manualFields.feasibility` 를 **아무도 쓰지 않아** 가드가 장식이었다.
// *"정의만 하고 소비처 0"* — 이 저장소가 반복해 데인 형태다.
//
// 그래서 **실제 사용자 편집 경로**(`PipelineResultDetail` 의 STORE_FIELD_MAP → persistFieldToStore)가
// 존재하고 feasibility 를 다루는지 **소스에서 파생형으로** 잠근다.
// ★이것은 소스 락이다 — 그 컴포넌트를 렌더까지 태우는 것은 별건(범위 밖·미측정으로 적는다).
// ─────────────────────────────────────────────────────────────────────────
describe("생산자 배선 — 가드가 장식이 되지 않게", () => {
  const SRC = "components/pipeline/PipelineResultDetail.tsx";
  const read = () => readSrc(SRC);

  it("★전제: 대상 파일을 읽었고 편집 표면이 있다(공허한 초록 방지)", () => {
    const src = read();
    expect(src.length, `${SRC} 를 못 읽었다`).toBeGreaterThan(2000);
    expect(src, "편집 가능 필드가 없다 — 검사 전제가 깨졌다").toContain("editable: true");
  });

  it("★수지 필드가 **영속 맵**에 있다 — 없으면 편집이 세션 한정으로 사라진다", () => {
    const src = read();
    expect(src).toContain('"feasibility.total_cost_won"');
    expect(src).toContain('"feasibility.total_revenue_won"');
  });

  it("★★그 편집이 **`{source:\"user\"}` 로 store 에 간다** — stamp 생산자", () => {
    const src = read();
    expect(
      src,
      "updateFeasibilityData 를 user 로 부르는 곳이 없다 — manualFields.feasibility 를 아무도 안 써서 가드가 장식이 된다",
    ).toMatch(/updateFeasibilityData\([\s\S]{0,200}?source:\s*"user"/);
  });

  it("★음성 대조군 — 자동 환류 경로는 `auto` 로 부른다(무차별 user 승격 배제)", () => {
    const src = readSrc("hooks/useNodeRunner.ts");
    expect(src, "자동 환류가 user 로 stamp 하면 이후 자동 갱신이 통째로 막힌다").toMatch(
      /updateFeasibilityData\([\s\S]{0,120}?source:\s*"auto"/,
    );
  });
});
