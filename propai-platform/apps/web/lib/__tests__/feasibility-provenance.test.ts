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

import { useProjectContextStore } from "@/store/useProjectContextStore";

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
