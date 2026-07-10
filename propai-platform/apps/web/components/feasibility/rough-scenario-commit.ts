// 개략수지(rough-scenario) 결과 → 모세혈관(feasibilityData) 매핑 — 순수함수(테스트 용이).
//
// 왜 필요한가(쉬운 설명): RoughScenarioPanel이 계산한 결과를 화면에만 보여주고 SSOT에
// 저장하지 않으면, 뒤 단계(STEP2 투자수익성 요약·STEP3 리스크 시뮬 base 조립)가 이 값을
// 못 읽어 "먼저 개략수지를 만들어야 한다"는 안내만 반복한다. 이 파일은 그 결과를
// feasibilityData 패치(부분 갱신 객체)로 변환해, RoughScenarioPanel의 커밋 이펙트가
// updateFeasibilityData에 넘길 수 있게 한다.
//
// 무날조 원칙: 백엔드가 실제로 준 값만 옮긴다. 값이 없으면 해당 키를 patch에서 아예
// 생략해 기존 SSOT 값을 그대로 보존한다(0/가짜값으로 덮지 않음).
// 자기자본(equityWon 등)은 여기서 절대 건드리지 않는다 — updateFeasibilityData가
// 총사업비×비율로 자동 재파생하므로, 여기서 값을 세팅하면 그 자동재파생을 방해한다
// (equityIsManual=true로 오인돼 옛 값에 앵커링되는 함정 — FeasibilityEditorV2 정답 기준선 참고).

import type { FeasibilityData } from "@/store/useProjectContextStore";

/** RoughScenarioPanel의 RoughScenarioResult 중 매핑에 필요한 최소 구조(백엔드 응답 부분집합).
 *  RoughScenarioPanel.tsx의 private interface(RsSummary·RsRevenue·RsInputs 등)를 import하지
 *  않고, 이 파일이 실제로 읽는 필드만 구조적으로 다시 선언한다(테스트·재사용 용이). */
export interface RoughScenarioLike {
  project_id?: string | null;
  summary?: {
    total_cost_won?: number | null;
    total_revenue_won?: number | null;
    net_profit_won?: number | null;
    roi_pct?: number | null;
    npv_won?: number | null;
    grade?: string | null;
  } | null;
  revenue?: {
    sale_price_per_pyeong?: number | null;
  } | null;
  inputs?: {
    gfa_sqm?: number | null;
    // 세대수 가정(GFA÷유형 표준 전용면적, 백엔드 unit_standards 관례) — additive.
    total_households?: number | null;
  } | null;
  cashflow?: {
    summary?: {
      profit_rate_pct?: number | null;
    } | null;
  } | null;
}

/** 유한수일 때만 그대로, 아니면 null(무날조 — 0/NaN 강제 금지). */
function finiteOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 0보다 큰 유한수일 때만 그대로, 아니면 null. */
function positiveOrNull(v: unknown): number | null {
  const n = finiteOrNull(v);
  return n != null && n > 0 ? n : null;
}

/** 0보다 큰 정수일 때만 그대로(반올림), 아니면 null(세대수 등 정수 계약용). */
function positiveIntOrNull(v: unknown): number | null {
  const n = positiveOrNull(v);
  return n == null ? null : Math.round(n);
}

/** 개략수지 결과 → 모세혈관(feasibilityData) 패치 매핑.
 *  무날조: 백엔드가 준 값만 옮기고, 없으면 해당 키를 patch에서 생략해 기존 SSOT 값을 보존한다.
 *  자기자본(equityWon/equityIsManual/equityRatioPct)은 절대 건드리지 않는다 —
 *  updateFeasibilityData가 총사업비×비율로 자동 재파생한다(수동입력 앵커링 함정 회피).
 *  의미있는 값이 하나도 없으면 null을 반환해 호출측이 stamp(updatedAt.feasibility)를 아끼게 한다. */
export function roughResultToFeasibilityPatch(
  result: RoughScenarioLike | null | undefined,
): Partial<FeasibilityData> | null {
  if (!result) return null;
  const patch: Partial<FeasibilityData> = {};

  // ★L1: 총사업비·총수입은 양수일 때만 커밋한다(0·음수 degraded 값이 STEP2 게이트를
  //   "결과 있음"으로 잘못 열게 두지 않는다 — 순이익(profitRatePct)은 손실(음수)도 정상값이라
  //   별도로 취급한다).
  const totalCostWon = positiveOrNull(result.summary?.total_cost_won);
  if (totalCostWon != null) patch.totalCostWon = totalCostWon;

  const totalRevenueWon = positiveOrNull(result.summary?.total_revenue_won);
  if (totalRevenueWon != null) patch.totalRevenueWon = totalRevenueWon;

  const roiPct = finiteOrNull(result.summary?.roi_pct);
  if (roiPct != null) patch.roiPct = roiPct;

  const npvWon = finiteOrNull(result.summary?.npv_won);
  if (npvWon != null) patch.npvWon = npvWon;

  const grade = result.summary?.grade;
  if (typeof grade === "string" && grade.trim()) patch.grade = grade;

  // 수익률(%) — cashflow 요약(정밀 산출)이 우선, 없으면 총수입·순이익으로 산술파생
  //   (백엔드가 준 실데이터끼리의 산술이므로 무날조 위반 아님). 둘 다 없으면 생략.
  const cashflowProfitRate = finiteOrNull(result.cashflow?.summary?.profit_rate_pct);
  if (cashflowProfitRate != null) {
    patch.profitRatePct = cashflowProfitRate;
  } else {
    const netProfitWon = finiteOrNull(result.summary?.net_profit_won);
    if (totalRevenueWon != null && totalRevenueWon > 0 && netProfitWon != null) {
      patch.profitRatePct = (netProfitWon / totalRevenueWon) * 100;
    }
  }

  // 분양단가(원/평) — 백엔드 FeasibilityCalculateRequest.avg_sale_price_per_pyeong과
  //   동일 단위(무변환)로 옮긴다.
  const salePricePerPyeongWon = positiveOrNull(result.revenue?.sale_price_per_pyeong);
  if (salePricePerPyeongWon != null) patch.salePricePerPyeongWon = salePricePerPyeongWon;

  // 연면적(㎡) — 설계 확정 전 STEP3 base 조립 폴백(node-body-builders.ts가 설계 우선으로 소비).
  const totalGfaSqm = positiveOrNull(result.inputs?.gfa_sqm);
  if (totalGfaSqm != null) patch.totalGfaSqm = totalGfaSqm;

  // 세대수 가정(GFA÷유형 표준 전용면적) — 백엔드가 additive로 노출한 값을 그대로 소비한다
  //   (프론트가 산식을 복제하지 않음). 설계 확정 전 STEP3 base의 avg_area_pyeong 산식(세대수
  //   소거)이 이 값을 폴백으로 써 매출이 0으로 오탐하지 않게 한다.
  const totalHouseholds = positiveIntOrNull(result.inputs?.total_households);
  if (totalHouseholds != null) patch.totalHouseholds = totalHouseholds;

  return Object.keys(patch).length > 0 ? patch : null;
}
