// @vitest-environment node
/**
 * 수지 완성도 **순수 판정**의 계약.
 *
 * ★왜 순수 함수로 꺼냈나(2026-08-27 · 라이브 귀속): `FeasibilityEditorV2` 가 스토어 **메서드**
 *   `feasibilityCompleteness()` 를 렌더 중 호출했고, 그 메서드는 내부 `get()` 으로 **재수화된
 *   라이브 상태**를 읽어 zustand 의 서버 스냅샷을 우회했다. 서버 `0% · 부지 대기` /
 *   클라 `60% · 부지 반영` → 프로덕션 `Minified React error #418 (args[]=text)`.
 *   세 모집단으로 귀속했다 — 무개변 **1** / 그 블록 텍스트만 서버에서 일치시키면 **0** /
 *   무관 텍스트 개변 **1**(음성 대조군 생존).
 */
import { describe, expect, it } from "vitest";

import {
  computeFeasibilityCompleteness,
  selectFeasibilityCompletenessInputs,
  type FeasibilityCompletenessInputs,
} from "@/store/useProjectContextStore";

const 빈입력: FeasibilityCompletenessInputs = {
  landAreaSqm: 0, address: "", totalGfaSqm: 0, totalConstructionCostWon: 0, totalRevenueWon: 0,
};

describe("computeFeasibilityCompleteness — 판정은 한 곳뿐", () => {
  it("★두 모집단이 갈린다 — 서버(빈 상태) 0% ↔ 재수화 상태 60%", () => {
    // 이 대조가 없으면 "무엇을 넣어도 같은 값"인 구현이 초록으로 통과한다.
    expect(computeFeasibilityCompleteness(빈입력).pct).toBe(0);
    expect(
      computeFeasibilityCompleteness({ ...빈입력, landAreaSqm: 1000, totalGfaSqm: 3000 }).pct,
    ).toBe(60);
  });

  it("연속 완료만 누적한다 — 중간이 비면 직전까지", () => {
    // 부지·설계는 있고 공사비가 없는데 금융이 있어도 60 에서 멈춘다(건너뛰기 금지).
    expect(computeFeasibilityCompleteness({
      landAreaSqm: 1, address: "a", totalGfaSqm: 1, totalConstructionCostWon: 0, totalRevenueWon: 9e9,
    }).pct).toBe(60);
    expect(computeFeasibilityCompleteness({
      landAreaSqm: 1, address: "a", totalGfaSqm: 1, totalConstructionCostWon: 1, totalRevenueWon: 9e9,
    }).pct).toBe(100);
  });

  it("★주소만 있으면 done 이 아니라 partial — 거짓 30% 를 만들지 않는다", () => {
    const r = computeFeasibilityCompleteness({ ...빈입력, address: "서울시 …" });
    const site = r.stages.find((s) => s.key === "site")!;
    expect(site.done).toBe(false);
    expect(site.partial).toBe(true);
    expect(r.pct).toBe(0); // ★partial 은 반영도에 안 실린다
  });

  it("★단계 집합과 가중치는 계약이다 — 표시 계층이 이 키로 그린다", () => {
    const st = computeFeasibilityCompleteness(빈입력).stages;
    expect(st.map((s) => s.key)).toEqual(["site", "design", "cost", "finance"]);
    expect(st.map((s) => s.weightPct)).toEqual([30, 60, 85, 100]);
  });
});

describe("selectFeasibilityCompletenessInputs — 셀렉터가 판정 입력 전부를 덮는다", () => {
  it("★입력 5축이 각각 결과를 움직인다(어느 하나라도 안 실리면 그 축은 무잠금)", () => {
    const s = {
      siteAnalysis: { address: "서울", landAreaSqm: 1000 },
      designData: { totalGfaSqm: 3000 },
      costData: { totalConstructionCostWon: 500 },
      feasibilityData: { totalRevenueWon: 900 },
    } as never;
    const i = selectFeasibilityCompletenessInputs(s);
    expect(i).toEqual({
      landAreaSqm: 1000, address: "서울", totalGfaSqm: 3000,
      totalConstructionCostWon: 500, totalRevenueWon: 900,
    });
    // 셀렉터 → 판정이 실제로 이어지는가(배선). 값이 하나라도 누락되면 pct 가 100 이 안 된다.
    expect(computeFeasibilityCompleteness(i).pct).toBe(100);
  });

  it("★결측은 0/빈문자로 정규화된다 — undefined 가 판정에 새지 않는다", () => {
    expect(selectFeasibilityCompletenessInputs({} as never)).toEqual(빈입력);
  });

  it("★참조 안정성 — 같은 입력이면 shallow 로 같다(무한 리렌더 방지의 근거)", () => {
    const s = { siteAnalysis: { address: "a", landAreaSqm: 1 } } as never;
    const a = selectFeasibilityCompletenessInputs(s);
    const b = selectFeasibilityCompletenessInputs(s);
    expect(a).not.toBe(b);                      // 새 객체인 것은 맞고
    for (const k of Object.keys(a) as (keyof typeof a)[]) expect(a[k]).toBe(b[k]); // shallow 로는 동일
  });
});
