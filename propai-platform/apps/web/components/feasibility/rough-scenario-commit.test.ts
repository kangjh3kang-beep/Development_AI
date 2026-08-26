// roughResultToFeasibilityPatch 단위테스트 — 개략수지 결과 → 모세혈관(feasibilityData) 매핑.
// 순수 함수라 store/apiClient mock 불필요(백엔드 응답 형태를 직접 시드).

import { describe, it, expect } from "vitest";

import { roughResultToFeasibilityPatch, type RoughScenarioLike } from "./rough-scenario-commit";

/** 정상 응답(모든 축 확보) — 매핑 대상 8필드가 전부 채워지는 기준 시나리오. */
function fullResult(over: Partial<RoughScenarioLike> = {}): RoughScenarioLike {
  return {
    project_id: "p1",
    summary: {
      total_cost_won: 50_000_000_000,
      total_revenue_won: 60_000_000_000,
      net_profit_won: 10_000_000_000,
      roi_pct: 20,
      npv_won: 5_000_000_000,
      grade: "B",
    },
    revenue: {
      sale_price_per_pyeong: 30_000_000,
    },
    inputs: {
      gfa_sqm: 22_059,
    },
    cashflow: {
      summary: {
        profit_rate_pct: 16.7,
      },
    },
    ...over,
  };
}

describe("roughResultToFeasibilityPatch", () => {
  it("정상 결과 → 8필드 매핑(단위 무변환 확인 포함)", () => {
    const patch = roughResultToFeasibilityPatch(fullResult());
    expect(patch).not.toBeNull();
    expect(patch!.totalCostWon).toBe(50_000_000_000);
    expect(patch!.totalRevenueWon).toBe(60_000_000_000);
    expect(patch!.roiPct).toBe(20);
    expect(patch!.npvWon).toBe(5_000_000_000);
    expect(patch!.grade).toBe("B");
    expect(patch!.profitRatePct).toBe(16.7);
    // 원/평 단위 무변환(백엔드 값 그대로 전달).
    expect(patch!.salePricePerPyeongWon).toBe(30_000_000);
    expect(patch!.totalGfaSqm).toBe(22_059);
  });

  it("null/undefined 결과 → null 반환", () => {
    expect(roughResultToFeasibilityPatch(null)).toBeNull();
    expect(roughResultToFeasibilityPatch(undefined)).toBeNull();
  });

  it("summary 전부 null(다른 축도 없음) → null 반환", () => {
    const result: RoughScenarioLike = {
      project_id: "p1",
      summary: {
        total_cost_won: null,
        total_revenue_won: null,
        net_profit_won: null,
        roi_pct: null,
        npv_won: null,
        grade: null,
      },
    };
    expect(roughResultToFeasibilityPatch(result)).toBeNull();
  });

  it("equity 키(equityWon/equityIsManual/equityRatioPct)가 patch에 절대 없음", () => {
    const patch = roughResultToFeasibilityPatch(fullResult());
    expect(patch).not.toBeNull();
    expect("equityWon" in patch!).toBe(false);
    expect("equityIsManual" in patch!).toBe(false);
    expect("equityRatioPct" in patch!).toBe(false);
  });

  it("profitRatePct: cashflow.summary.profit_rate_pct 우선 채택", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: { summary: { profit_rate_pct: 16.7 } },
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: 999_999_999, // cashflow 값이 있으면 이 값은 무시돼야 함.
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch!.profitRatePct).toBe(16.7);
  });

  it("profitRatePct: cashflow 없으면 net_profit_won/total_revenue_won×100 산술파생", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: 10_000_000_000,
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch!.profitRatePct).toBeCloseTo((10_000_000_000 / 60_000_000_000) * 100, 6);
  });

  it("profitRatePct: cashflow도 없고 net_profit_won/total_revenue_won도 없으면 키 생략", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 60_000_000_000,
          net_profit_won: null,
          roi_pct: 20,
          npv_won: 5_000_000_000,
          grade: "B",
        },
      }),
    );
    expect(patch).not.toBeNull();
    expect("profitRatePct" in patch!).toBe(false);
  });

  it("grade 빈 문자열/공백 → 생략", () => {
    for (const bad of ["", "  "]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({
          summary: {
            total_cost_won: 50_000_000_000,
            total_revenue_won: 60_000_000_000,
            net_profit_won: 10_000_000_000,
            roi_pct: 20,
            npv_won: 5_000_000_000,
            grade: bad,
          },
        }),
      );
      expect(patch).not.toBeNull();
      expect("grade" in patch!).toBe(false);
    }
  });

  it("salePricePerPyeongWon: 0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({ revenue: { sale_price_per_pyeong: bad } }),
      );
      expect(patch).not.toBeNull();
      expect("salePricePerPyeongWon" in patch!).toBe(false);
    }
  });

  it("totalGfaSqm: 0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(fullResult({ inputs: { gfa_sqm: bad } }));
      expect(patch).not.toBeNull();
      expect("totalGfaSqm" in patch!).toBe(false);
    }
  });

  it("totalHouseholds(H1): 양수 정수(inputs.total_households)만 매핑", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({ inputs: { gfa_sqm: 22_059, total_households: 200 } }),
    );
    expect(patch).not.toBeNull();
    expect(patch!.totalHouseholds).toBe(200);
  });

  it("totalHouseholds(H1): 미확보/0/음수는 미주입(0 강제 금지)", () => {
    for (const bad of [undefined, null, 0, -5]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({ inputs: { gfa_sqm: 22_059, total_households: bad } }),
      );
      expect(patch).not.toBeNull();
      expect("totalHouseholds" in patch!).toBe(false);
    }
  });

  it("totalCostWon/totalRevenueWon(L1): 0/음수는 미주입(degraded 0이 STEP2 게이트를 열지 않음)", () => {
    for (const bad of [0, -1]) {
      const patch = roughResultToFeasibilityPatch(
        fullResult({
          summary: {
            total_cost_won: bad,
            total_revenue_won: bad,
            net_profit_won: 10_000_000_000,
            roi_pct: 20,
            npv_won: 5_000_000_000,
            grade: "B",
          },
        }),
      );
      expect(patch).not.toBeNull();
      expect("totalCostWon" in patch!).toBe(false);
      expect("totalRevenueWon" in patch!).toBe(false);
    }
  });

  it("profitRatePct(L1): 손실 프로젝트(음수 net_profit_won)는 음수 profitRatePct로 정상 커밋된다", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        cashflow: null,
        summary: {
          total_cost_won: 50_000_000_000,
          total_revenue_won: 40_000_000_000,
          net_profit_won: -10_000_000_000, // 손실.
          roi_pct: -20,
          npv_won: -3_000_000_000,
          grade: "D",
        },
      }),
    );
    expect(patch).not.toBeNull();
    expect(patch!.profitRatePct).toBeCloseTo((-10_000_000_000 / 40_000_000_000) * 100, 6);
    expect(patch!.profitRatePct as number).toBeLessThan(0);
  });
});

// ── ★정밀도 등급 — 생성 경로 배선 (2026-08-24) ─────────────────────────────
//
//  라이브 수용시험에서 잡았다: `#770`(백엔드 산출) + `#771`(프론트 배지)이 **둘 다
//  머지·배포**됐는데 화면에 배지가 뜨지 않았다. 사용자 계정으로 '개략수지 생성'을
//  실제로 눌러 확인한 결과 `등급 F` 는 생기는데 스토어에 `precision` 키가 **없었다**.
//
//  `feasibilityData` 의 쓰기 경로가 둘인데(하이드레이션 / 생성) 하나만 배선돼 있었다.

describe("roughResultToFeasibilityPatch — 정밀도 등급(#770)", () => {
  it("★생성 경로에서 precision 3필드를 옮긴다 — 배지가 뜨는 조건", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({
        precision: "E",
        precision_label: "개략(추정)",
        precision_basis: "설계 산출물 없이 부지 정보만으로 추정",
      }),
    );
    expect(patch).not.toBeNull();
    // 배지 조건은 `grade && precision === "E"` 다 — **두 값이 같이** 있어야 한다.
    expect(patch?.grade, "grade 가 빠지면 배지 조건 앞부분이 무너진다").toBe("B");
    expect(patch?.precision).toBe("E");
    expect(patch?.precisionLabel).toBe("개략(추정)");
    expect(patch?.precisionBasis).toContain("설계 산출물 없이");
  });

  it("★대조군 — 백엔드가 안 주면 키를 만들지 않는다(구 응답 하위호환)", () => {
    // ★위 케이스는 *무엇이든 채워 넣는* 구현에서도 초록이다. 반대 방향을 함께 본다.
    const patch = roughResultToFeasibilityPatch(fullResult());
    expect(patch).not.toBeNull();
    expect(patch?.grade, "전제: 다른 필드는 정상 매핑된다").toBe("B");
    // ★계약 변경(2026-08-24) — 종전 기대는 "키를 만들지 않는다"였다. 그 근거는 *기존 SSOT 보존*
    //   이었는데, 보존되는 그 값은 **다른 등급을 설명하던 정밀도**다. 새 `grade` 와 함께 남으면
    //   배지가 그 새 등급을 잘못 라벨한다(merge 패치). `grade` 를 쓰는 순간 정밀도는
    //   **모른다고 명시**하는 것이 정직하다 — 화면은 "정밀도 미표기"로 남는다.
    //   ★`grade` 를 **안 쓰는** 패치는 종전대로 키를 만들지 않는다(아래 대조군에서 고정).
    expect("precision" in (patch ?? {}), "grade 를 쓰면 정밀도를 명시해야 한다").toBe(true);
    expect(patch?.precision, "모르면 null — 옛 등급의 정밀도를 물려주지 않는다").toBeNull();
    expect("precisionLabel" in (patch ?? {})).toBe(false);
    expect("precisionBasis" in (patch ?? {})).toBe(false);
  });

  it("★모르는 등급은 넣지 않는다 — 소비처가 판정할 수 없는 값을 만들지 않는다", () => {
    for (const bad of ["X", "e", "", "  ", "EE"]) {
      const patch = roughResultToFeasibilityPatch(fullResult({ precision: bad }));
      // 잘못된 값은 **그대로 통과하지 않는다**(핵심 락 유지). 다만 grade 가 실려 있으므로
      //   키 자체는 `null` 로 명시된다(위 계약 변경) — 소비처 조건 `precision === "E"` 는 거짓.
      expect(patch?.precision, `precision="${bad}" 가 통과했다`).toBeNull();
    }
    // 정상 3등급은 전부 통과한다(과잉 차단 방지).
    for (const ok of ["E", "D", "V"] as const) {
      const patch = roughResultToFeasibilityPatch(fullResult({ precision: ok }));
      expect(patch?.precision, `precision="${ok}" 가 막혔다 — 위양성`).toBe(ok);
    }
  });

  it("★라벨·근거는 빈 문자열이면 생략한다(빈 값으로 덮지 않는다)", () => {
    const patch = roughResultToFeasibilityPatch(
      fullResult({ precision: "E", precision_label: "   ", precision_basis: "" }),
    );
    expect(patch?.precision).toBe("E");
    expect("precisionLabel" in (patch ?? {})).toBe(false);
    expect("precisionBasis" in (patch ?? {})).toBe(false);
  });

  it("★★precision 은 최상위다 — summary 안에 넣어도 주워 오지 않는다(형태 결속)", () => {
    // 백엔드 orchestrator 는 `summary` 와 **형제**로 싣는다. 그 위치가 바뀌면 여기서 갈린다.
    const patch = roughResultToFeasibilityPatch(
      fullResult({ summary: { grade: "B", precision: "E" } as never }),
    );
    // 형태 결속 유지 — summary 안의 "E" 를 최상위로 착각해 **주워 오면** 여기서 갈린다.
    //   (키는 grade 동반으로 존재하되 값은 null 이어야 한다.)
    expect(patch?.precision, "summary 안의 값을 최상위로 착각해 읽었다").toBeNull();
  });
});
